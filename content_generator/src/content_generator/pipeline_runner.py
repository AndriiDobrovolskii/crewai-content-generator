"""Headless pipeline runner для GUI.

Вся логіка run_pipeline() з main.py, але без input() — параметри
передаються аргументами, прогрес — через log_callback.
"""

import contextlib
import datetime
import logging
import os
import re
import shutil
import sys
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_INVALID_CHARS = r'[\\/:*?"<>|()]'


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _sanitize_name(name: str) -> str:
    return re.sub(_INVALID_CHARS, "", name).replace(" ", "_")


def _save_html(output_dir: str, filename: str, html_content: str) -> str:
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


class _ThreadLocalStdout:
    """Перехоплює stdout тільки для цільового потоку; інші потоки пишуть у оригінал."""

    def __init__(self, callback: Callable[[str], None], target_thread_id: int):
        self._orig = sys.stdout
        self._callback = callback
        self._target = target_thread_id
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        self._orig.write(text)
        if threading.current_thread().ident == self._target:
            clean = _strip_ansi(text)
            if clean.strip():
                with self._lock:
                    self._callback(clean + "\n" if not clean.endswith("\n") else clean)
        return len(text)

    def flush(self) -> None:
        self._orig.flush()

    def fileno(self) -> int:
        return self._orig.fileno()

    def __enter__(self) -> "_ThreadLocalStdout":
        sys.stdout = self
        return self

    def __exit__(self, *_: Any) -> None:
        sys.stdout = self._orig


def _make_task_callback(log_cb: Callable[[str], None]) -> Callable:
    """Форматований колбек для task_callback CrewAI."""
    def cb(task_output: Any) -> None:
        try:
            agent = getattr(task_output, "agent", "Agent")
            summary = getattr(task_output, "summary", None) or ""
            if summary:
                summary = summary[:120] + ("..." if len(summary) > 120 else "")
            log_cb(f"\n✅ [{agent}] завершив задачу\n")
            if summary:
                log_cb(f"   {summary}\n")
        except Exception:
            pass
    return cb


def run_pipeline_headless(
    product_name: str,
    site: str,
    source_type: str,
    raw_input: str,
    log_callback: Callable[[str], None] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Запускає повний пайплайн без будь-яких input().

    Args:
        product_name: Назва продукту.
        site:         Ключ з SITES_CONFIG.
        source_type:  "text" | "urls" | "pdf" | "markdown" | "markdown_dir"
        raw_input:    Сирий текст, URL(и) через кому, або шлях до файлу/директорії.
        log_callback: Функція, яка отримує рядки прогресу в реальному часі.
        exclude_patterns: Тільки для "markdown_dir" — паттерни виключення.

    Returns:
        {
            "output_dir": str | None,
            "zip_path":   str | None,
            "files":      dict[str, str],   # {label: html_content}
            "error":      str | None,
        }
    """
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _src_dir = os.path.dirname(_current_dir)
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)

    result: dict[str, Any] = {
        "output_dir": None,
        "zip_path": None,
        "files": {},
        "error": None,
    }

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    # Завантажуємо env після налаштування шляхів
    from dotenv import load_dotenv
    load_dotenv()

    from content_generator.tools.parsers import (
        extract_text_from_md,
        extract_text_from_md_dir,
        extract_text_from_pdf,
        extract_text_from_urls,
    )
    from content_generator.crew import (
        CTA_TEMPLATES,
        ECommerceContentCrew,
        LocalizationCrew,
        SITES_CONFIG,
    )

    task_cb = _make_task_callback(log_callback) if log_callback else None
    stdout_ctx: Any = (
        _ThreadLocalStdout(log_callback, threading.current_thread().ident)
        if log_callback
        else contextlib.nullcontext()
    )

    try:
        site_info = SITES_CONFIG[site]

        # ── Підготовка сирого тексту ─────────────────────────────────────
        raw_text = ""

        if source_type == "text":
            raw_text = raw_input
            _log(f"📄 Використовуємо вставлений текст ({len(raw_text):,} символів)\n")

        elif source_type == "urls":
            urls = [u.strip() for u in raw_input.split(",") if u.strip()]
            _log(f"🌐 Парсимо {len(urls)} URL(s)...\n")
            raw_text = extract_text_from_urls(urls)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "pdf":
            _log(f"📄 Читаємо PDF: {raw_input}\n")
            raw_text = extract_text_from_pdf(raw_input)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "markdown":
            _log(f"📑 Читаємо Markdown: {raw_input}\n")
            raw_text = extract_text_from_md(raw_input)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "markdown_dir":
            _log(f"📁 Сканую директорію Markdown: {raw_input}\n")
            raw_text = extract_text_from_md_dir(raw_input, exclude_patterns=exclude_patterns)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        else:
            result["error"] = f"Невідомий тип джерела: '{source_type}'"
            return result

        if not raw_text.strip():
            result["error"] = "Порожній текст після обробки джерела даних. Перевірте вхідні дані."
            return result

        # ── Створення директорії виводу ──────────────────────────────────
        timestamp = datetime.datetime.now().strftime("%d-%m-%Y-%H-%M")
        safe_site = _sanitize_name(site)
        safe_product = _sanitize_name(product_name)
        folder_name = f"{safe_site}-{safe_product}-{timestamp}"
        output_dir = os.path.join("output", folder_name)
        os.makedirs(output_dir, exist_ok=True)
        result["output_dir"] = output_dir
        _log(f"📂 Папка результатів: {output_dir}\n")

        # ── CTA контекст ─────────────────────────────────────────────────
        cta_data = CTA_TEMPLATES.get(site, {})
        if cta_data:
            advantages_text = "\n".join(
                f"- {adv}" for adv in cta_data.get("store_advantages", [])
            )
            urgency = cta_data.get("urgency_hook", "")
            cta_context = (
                f"STORE ADVANTAGES for {site}:\n{advantages_text}\n\nURGENCY HOOK: {urgency}"
            )
        else:
            cta_context = f"No specific CTA data for {site}. Write a generic professional CTA."

        # ── Core inputs для Фази 1 ───────────────────────────────────────
        core_inputs = {
            "product_name": product_name,
            "site_name": site,
            "target_country": "Global Market (USA/UK)",
            "raw_source_text": raw_text,
            "cta_context": cta_context,
            "language_instruction": (
                "CRITICAL SYSTEM DIRECTIVE: Regardless of the language of the source text, "
                "YOU MUST OUTPUT 100% OF YOUR RESPONSE IN ENGLISH. "
                "Do not translate SEO keywords to other languages. Everything MUST be in English."
            ),
        }

        # ================================================================
        # ФАЗА 1: Core Content Crew
        # ================================================================
        _log(f"\n{'=' * 60}\n")
        _log(f"🚀 ФАЗА 1: ЗБІР ДАНИХ ТА АНГЛІЙСЬКА ВЕРСТКА ({site})\n")
        _log(f"{'=' * 60}\n")

        core_crew_module = ECommerceContentCrew()
        tasks_to_run = [
            core_crew_module.tech_specs_extraction_task(product_name),
            core_crew_module.seo_strategy_task(),
            core_crew_module.copywriting_task(),
            core_crew_module.quality_assurance_task(),
            core_crew_module.html_integration_task(),
        ]

        with stdout_ctx:
            active_core_crew = core_crew_module.create_crew(tasks_to_run, task_callback=task_cb)
            core_result = active_core_crew.kickoff(inputs=core_inputs)

        base_english_html = core_result.raw
        english_filename = f"{folder_name}_BASE_English.html"
        _save_html(output_dir, english_filename, base_english_html)
        result["files"]["English (Base)"] = base_english_html
        _log("\n✅ Базовий HTML (English + GEO Microdata) збережено.\n")

        # ================================================================
        # ФАЗА 2: Локалізація
        # ================================================================
        localizer_key = site_info["localizer"]
        ua_is_production = site_info.get("ua_is_production", False)

        # ── Крок 1: Обов'язкова українська версія ───────────────────────
        _log(f"\n{'=' * 60}\n")
        _log("📋 КРОК 1: УКРАЇНСЬКА ВЕРСІЯ\n")
        _log(f"{'=' * 60}\n")

        if ua_is_production:
            ua_market_key = "localizer_ua"
            ua_label = "Ukrainian"
            ua_filename = f"{folder_name}_Ukrainian.html"
        else:
            ua_market_key = "review_ua"
            ua_label = "Ukrainian (Review)"
            ua_filename = f"{folder_name}_REVIEW_Ukrainian.html"

        ua_crew_module = LocalizationCrew(market_key=ua_market_key)
        ua_inputs = ua_crew_module.get_inputs(
            product_name=product_name,
            site_name=site,
            target_language="Ukrainian",
            base_html=base_english_html,
        )
        with stdout_ctx:
            ua_crew = ua_crew_module.crew(task_callback=task_cb)
            ua_result = ua_crew.kickoff(inputs=ua_inputs)

        _save_html(output_dir, ua_filename, ua_result.raw)
        result["files"][ua_label] = ua_result.raw
        _log(f"💾 Збережено: {ua_filename}\n")

        # ── Крок 2: Решта мов ────────────────────────────────────────────
        _log(f"\n{'=' * 60}\n")
        _log(f"🌍 КРОК 2: ЛОКАЛІЗАЦІЯ РЕШТИ МОВ (агент: {localizer_key})\n")
        _log(f"{'=' * 60}\n")

        for language in site_info["languages"]:
            if language == "Ukrainian":
                _log(f"  ⏩ {language} — вже згенеровано, пропуск.\n")
                continue

            _log(f"\n  🔄 Транскреація: {language}...\n")
            loc_crew_module = LocalizationCrew(market_key=localizer_key)
            loc_inputs = loc_crew_module.get_inputs(
                product_name=product_name,
                site_name=site,
                target_language=language,
                base_html=base_english_html,
            )
            with stdout_ctx:
                loc_crew = loc_crew_module.crew(task_callback=task_cb)
                loc_result = loc_crew.kickoff(inputs=loc_inputs)

            safe_lang = language.split(" ")[0]
            filename = f"{folder_name}_{safe_lang}.html"
            _save_html(output_dir, filename, loc_result.raw)
            result["files"][language] = loc_result.raw
            _log(f"  💾 Збережено: {filename}\n")

        # ── ZIP-архів ────────────────────────────────────────────────────
        _log("\n📦 Створення ZIP-архіву...\n")
        zip_base = os.path.join("output", folder_name)
        shutil.make_archive(zip_base, "zip", output_dir)
        zip_path = os.path.join(output_dir, f"{folder_name}.zip")
        shutil.move(f"{zip_base}.zip", zip_path)
        result["zip_path"] = zip_path

        _log(f"\n🎉 Готово! Усі файли: {output_dir}\n")
        _log(f"📦 Архів: {zip_path}\n")
        _log(f"\n{'=' * 60}\n")
        _log(f"Згенеровано {len(result['files'])} файл(ів):\n")
        for label in result["files"]:
            _log(f"  ✓ {label}\n")

    except Exception as exc:
        logger.exception("Pipeline error")
        result["error"] = str(exc)
        _log(f"\n❌ ПОМИЛКА: {exc}\n")

    return result
