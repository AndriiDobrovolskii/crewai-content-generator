"""GUI для демонстрації CrewAI Content Generation Pipeline.

Запуск:
    uv run src/content_generator/gui.py
    python src/content_generator/gui.py

Потребує: gradio>=4.0  (uv add gradio)

Зміни v3:
- 7 джерел даних (text, urls, pdf, markdown, markdown_dir, auto_search, auto_search_review)
- Native File Explorer: tkinter.filedialog для PDF та Markdown
- HITL: "🔎 Шукати URL" → агент знаходить URL → вставляє в textbox →
  оператор перевіряє/редагує → натискає "Генерувати"
"""

import os
import queue
import sys
import threading

import gradio as gr

# ── Налаштування шляхів (аналогічно main.py) ─────────────────────────────────
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_current_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from dotenv import load_dotenv
load_dotenv()

from content_generator.crew import SITES_CONFIG
from content_generator.pipeline_runner import run_pipeline_headless, run_discovery_headless


# ── Константи UI ──────────────────────────────────────────────────────────────

def _site_label(site: str) -> str:
    cfg = SITES_CONFIG[site]
    ua_flag = "🟢 UA=prod" if cfg["ua_is_production"] else "🔵 UA=review"
    langs = " · ".join(cfg["languages"])
    return f"{site}  ({cfg['country']})  [{ua_flag}]  —  {langs}"


SITE_LABELS: dict[str, str] = {_site_label(s): s for s in SITES_CONFIG}
SITE_CHOICES: list[str] = list(SITE_LABELS.keys())

SOURCE_MAP: dict[str, str] = {
    "📝 Вставити текст": "text",
    "🌐 URL-адреси (через кому)": "urls",
    "📄 PDF файл(и)": "pdf",
    "📑 Markdown файл(и)": "markdown",
    "📁 Директорія Markdown (шлях)": "markdown_dir",
    "🔍 Auto-search (повний авто)": "auto_search",
    "🔎 Auto-search (знайти URL)": "auto_search_review",
}
SOURCE_CHOICES: list[str] = list(SOURCE_MAP.keys())

# Джерела, для яких показуємо кнопку Browse (файли)
_BROWSE_FILE_SOURCES = {"pdf", "markdown"}
# Джерела, для яких показуємо кнопку Browse (директорія)
_BROWSE_DIR_SOURCES = {"markdown_dir"}
# Джерело, для якого показуємо кнопку "Шукати URL"
_DISCOVER_SOURCES = {"auto_search_review"}

INPUT_PLACEHOLDERS: dict[str, str] = {
    "📝 Вставити текст": "Вставте сирий текст про продукт (технічні характеристики, опис, FAQ)...",
    "🌐 URL-адреси (через кому)": "https://example.com/product, https://store.com/item",
    "📄 PDF файл(и)": r"Шлях(и) до PDF: C:\docs\spec.pdf, C:\docs\manual.pdf",
    "📑 Markdown файл(и)": r"Шлях(и) до MD: C:\docs\spec.md, C:\docs\manual.md",
    "📁 Директорія Markdown (шлях)": r"C:\docs\product_folder",
    "🔍 Auto-search (повний авто)": "Поле не потрібне — агент шукатиме автоматично",
    "🔎 Auto-search (знайти URL)": "Натисніть '🔎 Шукати URL' — знайдені URL з'являться тут для перевірки",
}

# tkinter file dialog фільтри
_FILE_DIALOG_FILTERS: dict[str, list[tuple[str, str]]] = {
    "pdf": [("PDF файли", "*.pdf"), ("Усі файли", "*.*")],
    "markdown": [("Markdown файли", "*.md;*.markdown"), ("Усі файли", "*.*")],
}

CSS = """
/* Загальний layout */
.main-header { text-align: center; padding: 1rem 0 0.25rem; }
.main-subtitle { text-align: center; color: #6b7280; font-size: 0.88rem; margin-bottom: 1.5rem; }

/* Ліва панель */
.left-panel { background: #f9fafb; border-radius: 12px; padding: 1rem; }

/* Кнопка генерації */
.generate-btn { min-height: 54px !important; font-size: 1.05rem !important; font-weight: 700 !important; }

/* Кнопки browse / discover */
.browse-btn { min-height: 40px !important; }
.discover-btn { min-height: 42px !important; font-weight: 600 !important; }

/* Лог агентів */
.log-area textarea {
    font-family: 'Courier New', 'Consolas', monospace !important;
    font-size: 0.78rem !important;
    line-height: 1.45 !important;
    background: #0f172a !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}

/* HTML preview */
.preview-frame {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fff;
    min-height: 400px;
    padding: 1rem 1.5rem;
    overflow-y: auto;
}

/* Статус-бейдж */
.status-ready { color: #16a34a; font-weight: 600; }
.status-working { color: #d97706; font-weight: 600; }
"""


# ── Native File Explorer (tkinter) ───────────────────────────────────────────

def _open_file_dialog(source_label: str) -> str:
    """Відкриває нативний Windows File Explorer для вибору файлів або директорії."""
    source_type = SOURCE_MAP.get(source_label, "text")

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return "[ПОМИЛКА] tkinter не встановлено. Вставте шляхи вручну."

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()

    result = ""

    try:
        if source_type in _BROWSE_FILE_SOURCES:
            filetypes = _FILE_DIALOG_FILTERS.get(source_type, [("Усі файли", "*.*")])
            files = filedialog.askopenfilenames(
                title="Оберіть файл(и) для екстракції даних",
                filetypes=filetypes,
            )
            if files:
                result = ",".join(files)

        elif source_type in _BROWSE_DIR_SOURCES:
            directory = filedialog.askdirectory(
                title="Оберіть директорію з Markdown файлами",
            )
            if directory:
                result = directory

    finally:
        root.destroy()

    return result


# ── Обробники подій ───────────────────────────────────────────────────────────

def on_source_change(source_label: str):
    """Перемикає видимість кнопок та стан textbox залежно від джерела."""
    source_type = SOURCE_MAP.get(source_label, "text")

    show_browse = source_type in _BROWSE_FILE_SOURCES or source_type in _BROWSE_DIR_SOURCES
    show_discover = source_type in _DISCOVER_SOURCES
    interactive = source_type != "auto_search"

    textbox_update = gr.update(
        placeholder=INPUT_PLACEHOLDERS.get(source_label, ""),
        lines=3 if (show_browse or show_discover) else 10,
        interactive=interactive,
    )

    browse_update = gr.update(visible=show_browse)
    discover_update = gr.update(visible=show_discover)

    return textbox_update, browse_update, discover_update


def on_browse_click(source_label: str, current_input: str) -> str:
    """Кнопка Browse → нативний File Explorer → шляхи в textbox (append)."""
    new_paths = _open_file_dialog(source_label)
    if not new_paths:
        return current_input
    if current_input.strip():
        return f"{current_input.strip()},{new_paths}"
    return new_paths


def discover_urls(product_name: str, site_label: str):
    """Streaming: '🔎 Шукати URL' → URL Discovery агент → URL в textbox.

    HITL flow:
    1. Агент шукає URL → лог показує прогрес
    2. Знайдені URL вставляються в textbox (editable)
    3. Джерело перемикається на "🌐 URL-адреси"
    4. Оператор перевіряє/редагує/додає URL
    5. Натискає "Генерувати" — pipeline працює з відредагованими URL

    Yields:
        (log_text, raw_input_value, source_radio_value)
    """
    if not product_name.strip():
        yield (
            "❌ Вкажіть назву продукту перед пошуком.",
            gr.update(),
            gr.update(),
        )
        return

    site = SITE_LABELS[site_label]
    log_q: queue.Queue[tuple[str, str | None]] = queue.Queue()
    discovery_result: dict = {}

    def _run() -> None:
        data = run_discovery_headless(
            product_name=product_name.strip(),
            site=site,
            log_callback=lambda msg: log_q.put(("log", msg)),
        )
        discovery_result.update(data)
        log_q.put(("done", None))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    log_text = ""
    while True:
        kind, payload = log_q.get()
        if kind == "log":
            log_text += payload
            yield (log_text, gr.update(), gr.update())
        elif kind == "done":
            break

    if discovery_result.get("error"):
        log_text += f"\n❌ Помилка discovery: {discovery_result['error']}\n"
        yield (log_text, gr.update(), gr.update())
        return

    urls = discovery_result.get("urls", [])
    if not urls:
        log_text += "\n⚠️ URL не знайдено. Спробуйте ввести вручну.\n"
        yield (log_text, gr.update(), gr.update())
        return

    urls_text = ", ".join(urls)
    log_text += (
        f"\n✅ Знайдено {len(urls)} URL → вставлено у поле вводу.\n"
        "📋 Перевірте/відредагуйте URL і натисніть '🚀 Генерувати контент'.\n"
    )

    # Перемикаємо джерело на URL-адреси та вставляємо знайдені URL
    url_source_label = [k for k, v in SOURCE_MAP.items() if v == "urls"][0]
    yield (
        log_text,
        gr.update(value=urls_text, interactive=True),
        gr.update(value=url_source_label),
    )


def generate_content(
    product_name: str,
    site_label: str,
    source_label: str,
    raw_input: str,
):
    """Streaming-генератор для кнопки 'Генерувати'.

    Yields:
        (log_text, lang_choices, selected_lang, preview_html,
         download_file, results_visible, files_state)
    """
    if not product_name.strip():
        yield (
            "❌ Вкажіть назву продукту.",
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(visible=False), {},
        )
        return

    site = SITE_LABELS[site_label]
    source_type = SOURCE_MAP[source_label]

    if not raw_input.strip() and source_type not in ("text", "auto_search"):
        yield (
            "❌ Оберіть файли або вставте дані.",
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(visible=False), {},
        )
        return

    log_q: queue.Queue[tuple[str, str | None]] = queue.Queue()
    pipeline_result: dict = {}

    def _run() -> None:
        data = run_pipeline_headless(
            product_name=product_name.strip(),
            site=site,
            source_type=source_type,
            raw_input=raw_input.strip(),
            log_callback=lambda msg: log_q.put(("log", msg)),
        )
        pipeline_result.update(data)
        log_q.put(("done", None))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    log_text = ""
    _empty = (
        gr.update(choices=[], value=None),
        gr.update(value=""),
        gr.update(value=None, visible=False),
        gr.update(visible=False),
        {},
    )
    while True:
        kind, payload = log_q.get()
        if kind == "log":
            log_text += payload
            yield (log_text, *_empty)
        elif kind == "done":
            break

    if pipeline_result.get("error"):
        log_text += f"\n\n❌ ПОМИЛКА: {pipeline_result['error']}\n"
        yield (log_text, *_empty)
        return

    files: dict[str, str] = pipeline_result.get("files", {})
    zip_path: str | None = pipeline_result.get("zip_path")
    lang_list = list(files.keys())
    first_lang = lang_list[0] if lang_list else None
    first_html = _wrap_preview(files.get(first_lang, "")) if first_lang else ""

    log_text += "\n\n✅ ГЕНЕРАЦІЮ ЗАВЕРШЕНО!\n"
    yield (
        log_text,
        gr.update(choices=lang_list, value=first_lang),
        gr.update(value=first_html),
        gr.update(value=zip_path, visible=bool(zip_path)),
        gr.update(visible=bool(files)),
        files,
    )


def on_lang_select(lang: str, files: dict) -> str:
    if not lang or not files:
        return ""
    return _wrap_preview(files.get(lang, ""))


def _wrap_preview(html_fragment: str) -> str:
    if not html_fragment:
        return ""
    return f"""
<div style="
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px; line-height: 1.6; color: #1e293b;
    max-width: 900px; margin: 0 auto;
">
{html_fragment}
</div>
"""


# ── Побудова інтерфейсу ───────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    theme = gr.themes.Soft(
        primary_hue="violet",
        secondary_hue="indigo",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    ).set(
        button_primary_background_fill="*primary_600",
        button_primary_background_fill_hover="*primary_700",
        block_label_text_size="sm",
        block_title_text_size="md",
    )

    with gr.Blocks(title="GEO Content Generator") as demo:

        gr.Markdown("# 🤖 GEO Content Generator", elem_classes=["main-header"])
        gr.Markdown(
            "CrewAI Multi-Agent Pipeline · E-Commerce Product Descriptions",
            elem_classes=["main-subtitle"],
        )

        files_state: gr.State = gr.State({})

        with gr.Row(equal_height=False):

            # ══════════════════════════════════════════════════════════════
            # ЛІВА ПАНЕЛЬ
            # ══════════════════════════════════════════════════════════════
            with gr.Column(scale=1, min_width=340, elem_classes=["left-panel"]):
                gr.Markdown("### ⚙️ Параметри генерації")

                product_input = gr.Textbox(
                    label="Назва продукту",
                    placeholder="напр. Bambu Lab X1 Carbon, Creality K1 Max",
                    lines=1,
                )

                site_dropdown = gr.Dropdown(
                    choices=SITE_CHOICES,
                    value=SITE_CHOICES[0],
                    label="Цільовий магазин",
                )

                source_radio = gr.Radio(
                    choices=SOURCE_CHOICES,
                    value=SOURCE_CHOICES[0],
                    label="Джерело даних",
                )

                # ── Кнопка Browse (PDF / MD / dir) ─────────────────────────
                browse_btn = gr.Button(
                    "📂  Відкрити File Explorer",
                    variant="secondary",
                    visible=False,
                    elem_classes=["browse-btn"],
                )

                # ── Кнопка Discover URL (HITL) ────────────────────────────
                discover_btn = gr.Button(
                    "🔎  Шукати URL",
                    variant="secondary",
                    visible=False,
                    elem_classes=["discover-btn"],
                )

                # ── Textbox ───────────────────────────────────────────────
                raw_input = gr.Textbox(
                    label="Вхідні дані",
                    placeholder=INPUT_PLACEHOLDERS[SOURCE_CHOICES[0]],
                    lines=10,
                    max_lines=25,
                )

                generate_btn = gr.Button(
                    "🚀  Генерувати контент",
                    variant="primary",
                    elem_classes=["generate-btn"],
                )

            # ══════════════════════════════════════════════════════════════
            # ПРАВА ПАНЕЛЬ
            # ══════════════════════════════════════════════════════════════
            with gr.Column(scale=2, min_width=520):

                gr.Markdown("### 📊 Лог виконання агентів")
                log_output = gr.Textbox(
                    label="",
                    lines=20,
                    max_lines=35,
                    interactive=False,
                    placeholder=(
                        "Тут з'являться логи роботи агентів...\n\n"
                        "▶  tech_specs_analyst  →  seo_strategist  →  copywriter\n"
                        "   editor_qa  →  frontend_developer  →  localizer"
                    ),
                    elem_classes=["log-area"],
                )

                with gr.Column(visible=False) as results_col:

                    gr.Markdown("### 👁️ Preview результату")

                    with gr.Row():
                        lang_dropdown = gr.Dropdown(
                            choices=[], value=None,
                            label="Мова / версія",
                            scale=2, interactive=True,
                        )
                        download_file = gr.File(
                            label="📦 Завантажити ZIP",
                            visible=False, scale=1, interactive=False,
                        )

                    preview_html = gr.HTML(
                        value="",
                        label="HTML Preview",
                        elem_classes=["preview-frame"],
                    )

        # ── Events ────────────────────────────────────────────────────────

        # Перемикання джерела → показати/сховати кнопки
        source_radio.change(
            fn=on_source_change,
            inputs=[source_radio],
            outputs=[raw_input, browse_btn, discover_btn],
        )

        # Browse → нативний File Explorer → шляхи в textbox
        browse_btn.click(
            fn=on_browse_click,
            inputs=[source_radio, raw_input],
            outputs=[raw_input],
        )

        # Discover → URL Discovery агент → URL в textbox + перемикання на "urls"
        discover_btn.click(
            fn=discover_urls,
            inputs=[product_input, site_dropdown],
            outputs=[log_output, raw_input, source_radio],
        )

        # Генерація
        generate_btn.click(
            fn=generate_content,
            inputs=[product_input, site_dropdown, source_radio, raw_input],
            outputs=[
                log_output,
                lang_dropdown,
                preview_html,
                download_file,
                results_col,
                files_state,
            ],
        )

        lang_dropdown.change(
            fn=on_lang_select,
            inputs=[lang_dropdown, files_state],
            outputs=[preview_html],
        )

    return demo


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        inbrowser=True,
        theme=gr.themes.Soft(
            primary_hue="violet",
            secondary_hue="indigo",
            neutral_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
        ).set(
            button_primary_background_fill="*primary_600",
            button_primary_background_fill_hover="*primary_700",
            block_label_text_size="sm",
            block_title_text_size="md",
        ),
        css=CSS,
    )