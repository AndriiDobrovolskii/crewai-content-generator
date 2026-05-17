"""Headless pipeline runner для GUI.

Вся логіка run_pipeline() з main.py, але без input() — параметри
передаються аргументами, прогрес — через log_callback.

Зміни v2:
- Multi-PDF / Multi-Markdown: comma-separated шляхи
- Early-exit guard: [ПОМИЛКА] зупиняє pipeline до CrewAI
- run_discovery_headless(): Phase 0 — окремий URL discovery для GUI HITL
- auto_search source_type: повний авто-пошук (discovery → scrape → pipeline)
"""

import contextlib
import datetime
import logging
import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from content_generator.tools.cost_tracker import PipelineCostTracker

logger = logging.getLogger(__name__)

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_INVALID_CHARS = r'[\\/:*?"<>|()]'
_URL_PATTERN = re.compile(r'https?://[^\s,\)\"\'>]+')  # Витяг URL з виводу агента

# Per-thread storage for the active GUI callback.
# Each thread that enters a _ThreadLocalStdout context manager gets its own
# callback slot; threads without an active slot see None and are not routed.
_thread_local = threading.local()


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _sanitize_name(name: str) -> str:
    return re.sub(_INVALID_CHARS, "", name).replace(" ", "_")


def _save_html(output_dir: str, filename: str, html_content: str) -> str:
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def _strip_markdown_fence(html: str) -> str:
    """Видаляє markdown code fence якщо LLM загорнув вивід у ```html ... ```."""
    import re
    # Варіант 1: ```html на початку
    html = re.sub(r'^```(?:html)?\s*\n', '', html.strip())
    # Варіант 2: ``` в кінці
    html = re.sub(r'\n```\s*$', '', html)
    return html.strip()


# Мапінг user-friendly міток мов → BCP-47 ISO коди для SEO metadata bundle.
_LANGUAGE_LABEL_TO_ISO: dict[str, str | None] = {
    "English (Base)": "en-GB",
    "English":        "en-GB",
    "Ukrainian":      "uk-UA",
    "Ukrainian (Review)": "uk-UA",
    "Russian":        "ru-UA",
    "Polish":         "pl-PL",
    "German":         "de-DE",
    "Spanish (Castilian es-ES)": "es-ES",
    "Spanish":        "es-ES",
    "American English": "en-US",
    "US Spanish":     "es-US",
}


def _label_to_iso(lang_label: str, site_info: dict) -> str | None:
    """Конвертує user-friendly мітку мови у BCP-47 ISO код.

    Для US-магазину (localizer_us) "English (Base)" / "English" → "en-US".
    Повертає None для невідомих міток — вони виключаються з SEO bundle.
    """
    if site_info.get("localizer") == "localizer_us":
        us_overrides: dict[str, str] = {
            "English (Base)": "en-US",
            "English": "en-US",
        }
        if lang_label in us_overrides:
            return us_overrides[lang_label]
    return _LANGUAGE_LABEL_TO_ISO.get(lang_label)


class _ThreadLocalStdout:
    """Перехоплює stdout для всіх потоків; callback маршрутизується через threading.local().

    sys.stdout swap залишається (необхідний щоб перехоплювати print()), але
    вибір callback-а є per-thread через _thread_local.callback — тому
    два паралельних pipeline-и не перезаписують один одному callback.
    """

    def __init__(self, callback: Callable[[str], None], target_thread_id: int | None):
        # target_thread_id зберігається для сумісності з існуючими call-site-ами,
        # але більше не використовується для маршрутизації — це робить _thread_local.
        self._orig = sys.stdout
        self._callback = callback
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        # BUG-17: callback lookup через thread-local замість self._target порівняння.
        cb = getattr(_thread_local, 'callback', None)
        # BUG-16: _orig.write всередині lock — серіалізує термінальний вивід
        #         від усіх потоків, що пишуть через цей екземпляр.
        with self._lock:
            self._orig.write(text)
            # BUG-18: перевіряємо text (до ANSI-strip) — так ANSI-only рядки
            #         не відфільтровують контент, який реально є у вхідному тексті.
            if cb is not None and text.strip():
                clean = _strip_ansi(text)
                cb(clean if clean.endswith("\n") else clean + "\n")
        return len(text)

    def flush(self) -> None:
        self._orig.flush()

    def fileno(self) -> int:
        return self._orig.fileno()

    def __enter__(self) -> "_ThreadLocalStdout":
        # BUG-17: реєструємо callback у thread-local ДО підміни sys.stdout,
        #         щоб перший же write() від цього потоку вже бачив свій callback.
        _thread_local.callback = self._callback
        sys.stdout = self
        return self

    def __exit__(self, *_: Any) -> None:
        sys.stdout = self._orig
        # BUG-17: знімаємо реєстрацію — після виходу з блоку цей потік
        #         більше не є "активним" і його print()-и не йдуть у callback.
        _thread_local.callback = None


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


# =====================================================================
# 🔎 URL DISCOVERY (Phase 0)
# =====================================================================

def _parse_urls_from_output(raw_output: str) -> list[str]:
    """Витягує унікальні URL з тексту агента, зберігаючи порядок."""
    urls = _URL_PATTERN.findall(raw_output)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        url = re.sub(r'[.,;:)>\]]+$', '', url)  # Прибираємо trailing пунктуацію
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def run_discovery_headless(
    product_name: str,
    site: str,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Запускає ТІЛЬКИ URL discovery (Phase 0) і повертає знайдені URL.

    Використовується GUI для Шляху Б (пошук URL → перевірка → генерація).

    Returns:
        {
            "urls":       list[str],  # Знайдені URL
            "raw_output": str,        # Повний вивід агента
            "error":      str | None,
        }
    """
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _src_dir = os.path.dirname(_current_dir)
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)

    from dotenv import load_dotenv
    load_dotenv()

    result: dict[str, Any] = {"urls": [], "raw_output": "", "error": None}

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    try:
        from content_generator.crew import ECommerceContentCrew

        task_cb = _make_task_callback(log_callback) if log_callback else None
        stdout_ctx: Any = (
            _ThreadLocalStdout(log_callback, threading.current_thread().ident)
            if log_callback
            else contextlib.nullcontext()
        )

        _log("🔎 Phase 0: URL Discovery...\n")
        _log(f"   Продукт: {product_name}\n")
        _log(f"   Магазин: {site}\n\n")

        core_crew_module = ECommerceContentCrew()
        discovery_crew = core_crew_module.create_discovery_crew(
            product_name, task_callback=task_cb
        )

        discovery_inputs = {
            "product_name": product_name,
            "site_name": site,
        }

        with stdout_ctx:
            crew_result = discovery_crew.kickoff(inputs=discovery_inputs)

        raw_output = crew_result.raw
        result["raw_output"] = raw_output

        urls = _parse_urls_from_output(raw_output)
        result["urls"] = urls

        if urls:
            _log(f"\n✅ Знайдено {len(urls)} URL:\n")
            for i, u in enumerate(urls, 1):
                _log(f"   {i}. {u}\n")
        else:
            _log("\n⚠️ Агент не знайшов жодного URL.\n")

    except Exception as exc:
        logger.exception("Discovery error")
        result["error"] = str(exc)
        _log(f"\n❌ ПОМИЛКА discovery: {exc}\n")

    return result


# =====================================================================
# 🚀 ОСНОВНИЙ PIPELINE
# =====================================================================

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
        source_type:  "text" | "urls" | "pdf" | "markdown" | "markdown_dir" | "auto_search"
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
        "cost_report": None,
        "error": None,
    }

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    # ── Cost tracker (failure-isolated; tracker errors NEVER crash pipeline) ──
    try:
        cost_tracker: PipelineCostTracker | None = PipelineCostTracker()
        cost_tracker.set_context(product_name=product_name, site=site)
    except Exception as exc:
        logger.warning(f"Cost tracker init failed — continuing without telemetry: {exc}")
        cost_tracker = None

    # Завантажуємо env після налаштування шляхів
    from dotenv import load_dotenv
    load_dotenv()

    from content_generator.tools.parsers import (
        extract_text_from_md,
        extract_text_from_mds,
        extract_text_from_md_dir,
        extract_text_from_pdf,
        extract_text_from_pdfs,
        extract_text_from_urls,
    )
    from content_generator.crew import (
        CTA_TEMPLATES,
        ECommerceContentCrew,
        LocalizationCrew,
        SITES_CONFIG,
        run_seo_metadata_post_hook,
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
            pdf_paths = [p.strip() for p in raw_input.split(",") if p.strip()]
            if len(pdf_paths) == 1:
                _log(f"📄 Читаємо PDF: {pdf_paths[0]}\n")
                raw_text = extract_text_from_pdf(pdf_paths[0])
            else:
                _log(f"📄 Читаємо {len(pdf_paths)} PDF файлів...\n")
                raw_text = extract_text_from_pdfs(pdf_paths)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "markdown":
            md_paths = [p.strip() for p in raw_input.split(",") if p.strip()]
            if len(md_paths) == 1:
                _log(f"📑 Читаємо Markdown: {md_paths[0]}\n")
                raw_text = extract_text_from_md(md_paths[0])
            else:
                _log(f"📑 Читаємо {len(md_paths)} Markdown файлів...\n")
                raw_text = extract_text_from_mds(md_paths)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "markdown_dir":
            _log(f"📁 Сканую директорію Markdown: {raw_input}\n")
            raw_text = extract_text_from_md_dir(raw_input, exclude_patterns=exclude_patterns)
            _log(f"✅ Отримано {len(raw_text):,} символів\n")

        elif source_type == "auto_search":
            # ── Повний авто-пошук: discovery → scrape → pipeline ─────
            _log("🔍 AUTO-SEARCH: запуск URL Discovery агента...\n")
            discovery = run_discovery_headless(
                product_name=product_name,
                site=site,
                log_callback=log_callback,
            )
            if discovery.get("error"):
                result["error"] = f"Discovery failed: {discovery['error']}"
                return result

            found_urls = discovery.get("urls", [])
            if not found_urls:
                result["error"] = (
                    "Auto-search не знайшов жодного URL. "
                    "Спробуйте вказати URL вручну або вставити текст."
                )
                return result

            _log(f"\n⏳ Витягуємо контент із {len(found_urls)} URL...\n")
            raw_text = extract_text_from_urls(found_urls)
            _log(f"✅ Отримано {len(raw_text):,} символів з auto-search\n")

        else:
            result["error"] = f"Невідомий тип джерела: '{source_type}'"
            return result

        if not raw_text.strip():
            result["error"] = "Порожній текст після обробки джерела даних. Перевірте вхідні дані."
            return result

        # Guard: якщо парсер повернув помилку замість контенту — зупинити pipeline
        # до виклику CrewAI, щоб не витрачати API-токени на порожній прохід.
        if raw_text.lstrip().startswith("[ПОМИЛКА]"):
            result["error"] = raw_text.strip()
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
            core_crew_module.image_intelligence_task(),
            core_crew_module.html_integration_task(),
        ]

        active_core_crew = core_crew_module.create_crew(tasks_to_run, task_callback=task_cb)
        with stdout_ctx:
            core_result = active_core_crew.kickoff(inputs=core_inputs)

        # ── Cost telemetry: Phase 1 ─────────────────────────────────
        if cost_tracker is not None:
            cost_tracker.register_kickoff(
                crew_label="Phase 1: Core",
                usage_metrics=getattr(core_result, "token_usage", None),
                primary_model="gpt-4o",
                task_outputs=getattr(core_result, "tasks_output", None),
            )

        base_english_html = _strip_markdown_fence(core_result.raw)
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
        ua_crew = ua_crew_module.crew(task_callback=task_cb)
        with stdout_ctx:
            ua_result = ua_crew.kickoff(inputs=ua_inputs)

        # ── Cost telemetry: Phase 2 Step 1 (Ukrainian) ──────────────
        if cost_tracker is not None:
            cost_tracker.register_kickoff(
                crew_label=f"Phase 2: {ua_label}",
                usage_metrics=getattr(ua_result, "token_usage", None),
                primary_model="gpt-4o",
                task_outputs=getattr(ua_result, "tasks_output", None),
            )

        ua_html = _strip_markdown_fence(ua_result.raw)
        _save_html(output_dir, ua_filename, ua_html)
        result["files"][ua_label] = ua_html
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
            loc_crew = loc_crew_module.crew(task_callback=task_cb)
            with stdout_ctx:
                loc_result = loc_crew.kickoff(inputs=loc_inputs)

            # ── Cost telemetry: Phase 2 Step 2 (per-language) ──────
            if cost_tracker is not None:
                cost_tracker.register_kickoff(
                    crew_label=f"Phase 2: {language}",
                    usage_metrics=getattr(loc_result, "token_usage", None),
                    primary_model="gpt-4o",
                    task_outputs=getattr(loc_result, "tasks_output", None),
                )

            loc_html = _strip_markdown_fence(loc_result.raw)
            safe_lang = language.split(" ")[0]
            filename = f"{folder_name}_{safe_lang}.html"
            _save_html(output_dir, filename, loc_html)
            result["files"][language] = loc_html
            _log(f"  💾 Збережено: {filename}\n")

        # ── Post-pipeline: SEO metadata bundle ───────────────────────────
        _log("\n📊 Генерація seo_metadata.json...\n")

        finalized_html_by_language: dict[str, str] = {}
        for lang_label, html_content in result["files"].items():
            iso = _label_to_iso(lang_label, site_info)
            if iso and isinstance(html_content, str):
                finalized_html_by_language[iso] = html_content

        if finalized_html_by_language:
            seo_hook_result = run_seo_metadata_post_hook(
                product_name=product_name,
                site_name=site,
                currency_symbol=site_info.get("currency_symbol", "€"),
                finalized_html_by_language=finalized_html_by_language,
                output_dir=output_dir,
                task_callback=task_cb,
                cost_tracker=cost_tracker,
            )
            if seo_hook_result.get("path"):
                _log(f"💾 SEO metadata збережено: {seo_hook_result['path']}\n")
                result["files"]["SEO Metadata"] = seo_hook_result["path"]
            elif seo_hook_result.get("error"):
                _log(f"⚠️ SEO metadata generation failed: {seo_hook_result['error']}\n")
        else:
            _log("⚠️ No finalized HTML to extract SEO metadata from.\n")

        # ── Cost report ───────────────────────────────────────────────────
        if cost_tracker is not None:
            try:
                cost_tracker.to_console(_log)
                cost_report_path = os.path.join(output_dir, "cost_report.json")
                if cost_tracker.to_json(Path(cost_report_path)) is not None:
                    _log(f"💾 Cost report збережено: {cost_report_path}\n")
                    result["cost_report"] = cost_report_path
            except Exception as cost_exc:
                logger.warning(f"Cost report dump failed: {cost_exc}")

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

        # Partial cost report навіть при падінні — forensic data
        if cost_tracker is not None and result.get("output_dir"):
            try:
                partial_path = os.path.join(
                    result["output_dir"], "cost_report_PARTIAL.json"
                )
                cost_tracker.to_json(Path(partial_path))
                _log(f"💾 Partial cost report (до помилки): {partial_path}\n")
            except Exception:
                pass  # Failed forensic dump — silently skip

    return result