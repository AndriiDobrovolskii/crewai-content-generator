"""GUI для демонстрації CrewAI Content Generation Pipeline.

Запуск:
    uv run src/content_generator/gui.py
    python src/content_generator/gui.py

Потребує: gradio>=4.0  (uv add gradio)

Зміни v2:
- File Explorer: gr.File для PDF та Markdown (вибір файлів через діалог ОС)
- Автоматичне перемикання між текстовим вводом і файловим вибором
- Multi-file підтримка: кілька PDF або MD файлів за раз
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
from content_generator.pipeline_runner import run_pipeline_headless


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
}
SOURCE_CHOICES: list[str] = list(SOURCE_MAP.keys())

# Джерела, для яких показуємо file picker замість textbox
_FILE_PICKER_SOURCES = {"pdf", "markdown"}

INPUT_PLACEHOLDERS: dict[str, str] = {
    "📝 Вставити текст": "Вставте сирий текст про продукт (технічні характеристики, опис, FAQ)...",
    "🌐 URL-адреси (через кому)": "https://example.com/product, https://store.com/item",
    "📄 PDF файл(и)": r"Або вставте шлях(и) через кому: C:\docs\file1.pdf, C:\docs\file2.pdf",
    "📑 Markdown файл(и)": r"Або вставте шлях(и) через кому: C:\docs\spec.md, C:\docs\manual.md",
    "📁 Директорія Markdown (шлях)": r"C:\docs\product_folder",
}

FILE_PICKER_LABELS: dict[str, str] = {
    "pdf": "📄 Оберіть PDF файл(и)",
    "markdown": "📑 Оберіть Markdown файл(и)",
}

FILE_PICKER_TYPES: dict[str, list[str]] = {
    "pdf": [".pdf"],
    "markdown": [".md", ".markdown"],
}

CSS = """
/* Загальний layout */
.main-header { text-align: center; padding: 1rem 0 0.25rem; }
.main-subtitle { text-align: center; color: #6b7280; font-size: 0.88rem; margin-bottom: 1.5rem; }

/* Ліва панель */
.left-panel { background: #f9fafb; border-radius: 12px; padding: 1rem; }

/* Кнопка генерації */
.generate-btn { min-height: 54px !important; font-size: 1.05rem !important; font-weight: 700 !important; }

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

/* Роздільник OR */
.or-divider { text-align: center; color: #9ca3af; font-size: 0.82rem; margin: 0.3rem 0; }
"""


# ── Обробники подій ───────────────────────────────────────────────────────────

def on_source_change(source_label: str):
    """Перемикає видимість: textbox ↔ file picker залежно від джерела."""
    source_type = SOURCE_MAP.get(source_label, "text")
    use_picker = source_type in _FILE_PICKER_SOURCES

    # Textbox: завжди видимий, але менший коли є picker
    textbox_update = gr.update(
        placeholder=INPUT_PLACEHOLDERS.get(source_label, ""),
        visible=True,
        lines=2 if use_picker else 10,
        label="Або вставте шлях(и) вручну" if use_picker else "Вхідні дані",
    )

    # File picker: видимий тільки для pdf / markdown
    picker_update = gr.update(
        visible=use_picker,
        label=FILE_PICKER_LABELS.get(source_type, "Оберіть файли"),
        file_types=FILE_PICKER_TYPES.get(source_type, None),
        value=None,
    )

    # OR-розділювач між picker і textbox
    or_update = gr.update(visible=use_picker)

    return textbox_update, picker_update, or_update


def _resolve_raw_input(
    source_label: str,
    raw_input: str,
    uploaded_files: list | None,
) -> str:
    """Формує фінальний raw_input: пріоритет — file picker, fallback — textbox."""
    source_type = SOURCE_MAP.get(source_label, "text")

    # Якщо file picker активний і файли обрано — використовуємо їх шляхи
    if source_type in _FILE_PICKER_SOURCES and uploaded_files:
        paths = []
        for f in uploaded_files:
            # gr.File повертає str (шлях) або NamedString-подібний об'єкт
            path = f if isinstance(f, str) else getattr(f, "name", str(f))
            if path:
                paths.append(path)
        if paths:
            return ",".join(paths)

    # Fallback: textbox (ручний ввід шляхів або тексту)
    return raw_input


def generate_content(
    product_name: str,
    site_label: str,
    source_label: str,
    raw_input: str,
    uploaded_files: list | None,
):
    """Streaming-генератор для кнопки 'Генерувати'.

    Yields:
        (log_text, lang_choices, selected_lang, preview_html,
         download_file, results_visible, files_state)
    """
    # ── Валідація ─────────────────────────────────────────────────────────────
    if not product_name.strip():
        yield (
            "❌ Вкажіть назву продукту.",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(visible=False),
            {},
        )
        return

    site = SITE_LABELS[site_label]
    source_type = SOURCE_MAP[source_label]
    final_input = _resolve_raw_input(source_label, raw_input, uploaded_files)

    if not final_input.strip() and source_type != "text":
        yield (
            "❌ Оберіть файли або вставте шлях / текст.",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(visible=False),
            {},
        )
        return

    # ── Черга для streaming-логу ──────────────────────────────────────────────
    log_q: queue.Queue[tuple[str, str | None]] = queue.Queue()
    pipeline_result: dict = {}

    def _run() -> None:
        data = run_pipeline_headless(
            product_name=product_name.strip(),
            site=site,
            source_type=source_type,
            raw_input=final_input.strip(),
            log_callback=lambda msg: log_q.put(("log", msg)),
        )
        pipeline_result.update(data)
        log_q.put(("done", None))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # ── Streaming log до завершення ───────────────────────────────────────────
    log_text = ""
    _empty = (
        gr.update(choices=[], value=None),   # lang_dropdown
        gr.update(value=""),                 # preview_html
        gr.update(value=None, visible=False),# download_file
        gr.update(visible=False),            # results_col
        {},                                  # files_state
    )
    while True:
        kind, payload = log_q.get()
        if kind == "log":
            log_text += payload
            yield (log_text, *_empty)
        elif kind == "done":
            break

    # ── Результат ─────────────────────────────────────────────────────────────
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
    """Оновлює HTML-preview при виборі мови."""
    if not lang or not files:
        return ""
    return _wrap_preview(files.get(lang, ""))


def _wrap_preview(html_fragment: str) -> str:
    """Обгортає HTML-фрагмент у мінімальну сторінку для preview."""
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

        # ── Заголовок ─────────────────────────────────────────────────────────
        gr.Markdown("# 🤖 GEO Content Generator", elem_classes=["main-header"])
        gr.Markdown(
            "CrewAI Multi-Agent Pipeline · E-Commerce Product Descriptions",
            elem_classes=["main-subtitle"],
        )

        # ── Стан (зберігає dict файлів між подіями) ───────────────────────────
        files_state: gr.State = gr.State({})

        with gr.Row(equal_height=False):

            # ══════════════════════════════════════════════════════════════════
            # ЛІВА ПАНЕЛЬ — параметри
            # ══════════════════════════════════════════════════════════════════
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

                # ── File picker (прихований за замовчуванням) ─────────────────
                file_picker = gr.File(
                    label="📄 Оберіть файл(и)",
                    file_count="multiple",
                    file_types=[".pdf", ".md", ".markdown"],
                    visible=False,
                    interactive=True,
                )

                or_divider = gr.Markdown(
                    "_— або —_",
                    visible=False,
                    elem_classes=["or-divider"],
                )

                # ── Textbox (основний ввід) ───────────────────────────────────
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

                gr.Markdown(
                    "_Auto-search (URL Discovery) недоступний у GUI — "
                    "використовуйте URL або текст._",
                    visible=True,
                )

            # ══════════════════════════════════════════════════════════════════
            # ПРАВА ПАНЕЛЬ — моніторинг + preview
            # ══════════════════════════════════════════════════════════════════
            with gr.Column(scale=2, min_width=520):

                # ── Лог агентів ───────────────────────────────────────────────
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

                # ── Результати (приховані до завершення генерації) ────────────
                with gr.Column(visible=False) as results_col:

                    gr.Markdown("### 👁️ Preview результату")

                    with gr.Row():
                        lang_dropdown = gr.Dropdown(
                            choices=[],
                            value=None,
                            label="Мова / версія",
                            scale=2,
                            interactive=True,
                        )
                        download_file = gr.File(
                            label="📦 Завантажити ZIP",
                            visible=False,
                            scale=1,
                            interactive=False,
                        )

                    preview_html = gr.HTML(
                        value="",
                        label="HTML Preview",
                        elem_classes=["preview-frame"],
                    )

        # ── Events ────────────────────────────────────────────────────────────

        # Перемикання джерела → показати/сховати file picker
        source_radio.change(
            fn=on_source_change,
            inputs=[source_radio],
            outputs=[raw_input, file_picker, or_divider],
        )

        # Генерація: передаємо і textbox, і file picker
        generate_btn.click(
            fn=generate_content,
            inputs=[
                product_input,
                site_dropdown,
                source_radio,
                raw_input,
                file_picker,
            ],
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