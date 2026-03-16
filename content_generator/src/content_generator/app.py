"""
GEO Content Generator — Reflex Web UI v2.0

Веб-інтерфейс для запуску CrewAI пайплайну генерації контенту.
Запуск: reflex run (з кореневої папки content_generator/)

Зміни v2.0:
- Ukrainian-First Review Pipeline
- Нова архітектура LocalizationCrew (market_key замість localizer_name)
- Реальні виклики CrewAI (замість імітацій)
- Збереження файлів у output/
"""

import reflex as rx
import os
import re
import shutil
import datetime
import asyncio
from functools import partial

from parsers import extract_text_from_pdf, extract_text_from_urls
from crew import ECommerceContentCrew, LocalizationCrew, SITES_CONFIG


# =====================================================================
# 🛠️ ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================================

_INVALID_CHARS = r'[\\/:*?"<>|()]'


def _sanitize_name(name: str) -> str:
    return re.sub(_INVALID_CHARS, '', name).replace(' ', '_')


def _save_html(output_dir: str, filename: str, html_content: str) -> str:
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


# =====================================================================
# 🧠 СТАН ДОДАТКУ
# =====================================================================

class AppState(rx.State):
    """Глобальний стан Reflex-додатку."""

    # --- Вхідні дані ---
    product_name: str = ""
    target_site: str = "EXPERT3D"
    data_source: str = "Auto Search (AI)"
    raw_text_input: str = ""
    url_input: str = ""
    pdf_path_input: str = ""

    # --- UI States ---
    is_processing: bool = False
    progress_log: list[str] = []
    generated_results: dict[str, str] = {}  # {"Language": "HTML Code"}
    output_folder: str = ""

    # --- Допоміжні UI ---
    site_options: list[str] = list(SITES_CONFIG.keys())

    def add_log(self, message: str):
        self.progress_log = [*self.progress_log, message]

    @rx.background
    async def run_generation(self):
        """Запускає повний CrewAI пайплайн у фоновому потоці."""

        # Валідація
        async with self:
            if not self.product_name.strip():
                self.add_log("❌ Помилка: введіть назву продукту!")
                return

            self.is_processing = True
            self.progress_log = []
            self.generated_results = {}
            self.output_folder = ""
            self.add_log(f"🚀 Запуск: {self.product_name} | Сайт: {self.target_site}")

        # =============================================================
        # ЗБІР ВХІДНИХ ДАНИХ
        # =============================================================
        raw_text = ""
        use_auto_search = False

        async with self:
            if self.data_source == "Manual Text":
                raw_text = self.raw_text_input
                self.add_log(f"📥 Введений текст: {len(raw_text)} символів.")
            elif self.data_source == "URL Input":
                self.add_log(f"🔗 Парсимо URL: {self.url_input}...")

        # URL парсинг (блокуючий, але у @rx.background це ок)
        if self.data_source == "URL Input":
            async with self:
                url_list = [u.strip() for u in self.url_input.split(",") if u.strip()]
            raw_text = await asyncio.to_thread(extract_text_from_urls, url_list)
            async with self:
                self.add_log(f"✅ Спарсено {len(raw_text)} символів.")

        elif self.data_source == "PDF File":
            async with self:
                pdf_path = self.pdf_path_input
                self.add_log(f"📄 Читаємо PDF: {pdf_path}...")
            raw_text = await asyncio.to_thread(extract_text_from_pdf, pdf_path)
            async with self:
                self.add_log(f"✅ PDF: {len(raw_text)} символів.")

        elif self.data_source == "Auto Search (AI)":
            use_auto_search = True
            async with self:
                self.add_log("🤖 Агент Web Researcher шукатиме в Google...")

        # =============================================================
        # СТВОРЕННЯ ПАПКИ РЕЗУЛЬТАТІВ
        # =============================================================
        async with self:
            site_info = SITES_CONFIG[self.target_site]
            product = self.product_name
            site = self.target_site

        timestamp = datetime.datetime.now().strftime("%d-%m-%Y-%H-%M")
        folder_name = f"{_sanitize_name(site)}-{_sanitize_name(product)}-{timestamp}"
        output_dir = os.path.join("output", folder_name)
        os.makedirs(output_dir, exist_ok=True)

        async with self:
            self.output_folder = output_dir
            self.add_log(f"📂 Папка: {output_dir}")

        # =============================================================
        # ФАЗА 1: АНГЛІЙСЬКА БАЗА
        # =============================================================
        async with self:
            self.add_log("⚙️ Фаза 1: SEO → JSON → Копірайтинг → QA → HTML...")

        core_inputs = {
            'product_name': product,
            'site_name': site,
            'target_country': "Global Market (USA/UK)",
            'raw_source_text': raw_text,
            'language_instruction': (
                "CRITICAL SYSTEM DIRECTIVE: Regardless of the language of the source text, "
                "YOU MUST OUTPUT 100% OF YOUR RESPONSE IN ENGLISH."
            )
        }

        core_crew_module = ECommerceContentCrew()

        if use_auto_search:
            tasks_to_run = [
                core_crew_module.url_discovery_task(product),
                core_crew_module.content_extraction_task(product),
                core_crew_module.tech_specs_extraction_task(product),
                core_crew_module.seo_strategy_task(),
                core_crew_module.copywriting_task(),
                core_crew_module.quality_assurance_task(),
                core_crew_module.html_integration_task()
            ]
        else:
            tasks_to_run = [
                core_crew_module.tech_specs_extraction_task(product),
                core_crew_module.seo_strategy_task(),
                core_crew_module.copywriting_task(),
                core_crew_module.quality_assurance_task(),
                core_crew_module.html_integration_task()
            ]

        active_core_crew = core_crew_module.create_crew(tasks_to_run)

        # Блокуючий виклик CrewAI в окремому потоці
        core_result = await asyncio.to_thread(
            active_core_crew.kickoff, inputs=core_inputs
        )
        base_english_html = core_result.raw

        # Зберігаємо англійську базу
        _save_html(output_dir, f"{folder_name}_BASE_English.html", base_english_html)

        async with self:
            self.generated_results["BASE English"] = base_english_html
            self.add_log("✅ Базовий HTML (English + GEO Microdata) згенеровано!")

        # =============================================================
        # ФАЗА 2, КРОК 1: ОБОВ'ЯЗКОВИЙ УКРАЇНСЬКИЙ РЕВ'Ю
        # =============================================================
        ua_is_production = site_info.get('ua_is_production', False)

        if ua_is_production:
            ua_market_key = 'localizer_ua'
            ua_label = "Ukrainian (review + production)"
            ua_filename = f"{folder_name}_Ukrainian.html"
        else:
            ua_market_key = 'review_ua'
            ua_label = "REVIEW Ukrainian"
            ua_filename = f"{folder_name}_REVIEW_Ukrainian.html"

        async with self:
            self.add_log(f"📋 Крок 1: {ua_label}...")

        ua_crew_module = LocalizationCrew(market_key=ua_market_key)
        ua_crew = ua_crew_module.crew()
        ua_inputs = ua_crew_module.get_inputs(
            product_name=product,
            site_name=site,
            target_language='Ukrainian',
            base_html=base_english_html
        )

        ua_result = await asyncio.to_thread(ua_crew.kickoff, inputs=ua_inputs)

        _save_html(output_dir, ua_filename, ua_result.raw)

        async with self:
            self.generated_results[ua_label] = ua_result.raw
            self.add_log(f"💾 {ua_label} — збережено.")

        # =============================================================
        # ФАЗА 2, КРОК 2: РЕШТА МОВ
        # =============================================================
        localizer_key = site_info['localizer']

        async with self:
            self.add_log(f"🌍 Крок 2: Локалізація (агент: {localizer_key})...")

        for language in site_info['languages']:
            if language == 'Ukrainian':
                async with self:
                    self.add_log(f"  ⏩ {language} — вже є (Крок 1), пропуск.")
                continue

            async with self:
                self.add_log(f"  🔄 Транскреація: {language}...")

            loc_crew_module = LocalizationCrew(market_key=localizer_key)
            loc_crew = loc_crew_module.crew()
            loc_inputs = loc_crew_module.get_inputs(
                product_name=product,
                site_name=site,
                target_language=language,
                base_html=base_english_html
            )

            loc_result = await asyncio.to_thread(loc_crew.kickoff, inputs=loc_inputs)

            safe_lang = language.split(" ")[0]
            filename = f"{folder_name}_{safe_lang}.html"
            _save_html(output_dir, filename, loc_result.raw)

            async with self:
                self.generated_results[language] = loc_result.raw
                self.add_log(f"  💾 {language} — збережено.")

        # =============================================================
        # АРХІВАЦІЯ
        # =============================================================
        zip_base = os.path.join("output", folder_name)
        await asyncio.to_thread(shutil.make_archive, zip_base, 'zip', output_dir)
        shutil.move(f"{zip_base}.zip", os.path.join(output_dir, f"{folder_name}.zip"))

        async with self:
            self.add_log(f"📦 ZIP-архів створено.")
            self.add_log(f"🎉 ГОТОВО! Файли: {output_dir}")
            self.is_processing = False


# =====================================================================
# 🎨 ІНТЕРФЕЙС (UI)
# =====================================================================

def site_badge(site_name: str) -> str:
    """Генерує мітку для магазину."""
    cfg = SITES_CONFIG.get(site_name, {})
    flag = "🟢 prod" if cfg.get("ua_is_production") else "🔵 review"
    return f"{site_name} ({cfg.get('country', '?')}) [{flag}]"


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            # --- Шапка ---
            rx.heading("🤖 GEO-Content Generator", size="8", color="indigo"),
            rx.text(
                "Генерація карток товарів з Schema.org Microdata для OpenCart. "
                "Ukrainian-First Review Pipeline.",
                color="gray",
                size="3"
            ),

            # --- Форма вводу ---
            rx.card(
                rx.vstack(
                    rx.input(
                        placeholder="Назва продукту (напр. Creality K1 Max)",
                        on_blur=AppState.set_product_name,
                        width="100%",
                        size="3",
                    ),
                    rx.select(
                        list(SITES_CONFIG.keys()),
                        value=AppState.target_site,
                        on_change=AppState.set_target_site,
                        label="Цільовий сайт",
                    ),
                    rx.radio(
                        ["Auto Search (AI)", "Manual Text", "URL Input", "PDF File"],
                        value=AppState.data_source,
                        on_change=AppState.set_data_source,
                        direction="row",
                    ),

                    # Динамічні поля
                    rx.cond(
                        AppState.data_source == "Manual Text",
                        rx.text_area(
                            placeholder="Вставте сирий текст або характеристики...",
                            on_blur=AppState.set_raw_text_input,
                            width="100%",
                            height="150px",
                        ),
                    ),
                    rx.cond(
                        AppState.data_source == "URL Input",
                        rx.input(
                            placeholder="https://official-site.com/product (через кому для кількох)",
                            on_blur=AppState.set_url_input,
                            width="100%",
                        ),
                    ),
                    rx.cond(
                        AppState.data_source == "PDF File",
                        rx.input(
                            placeholder="Повний шлях до PDF файлу",
                            on_blur=AppState.set_pdf_path_input,
                            width="100%",
                        ),
                    ),

                    rx.button(
                        "🚀 Згенерувати контент",
                        on_click=AppState.run_generation,
                        loading=AppState.is_processing,
                        size="4",
                        width="100%",
                        color_scheme="indigo",
                    ),
                    width="100%",
                    spacing="4",
                ),
                width="100%",
            ),

            # --- Лог прогресу ---
            rx.cond(
                AppState.progress_log.length() > 0,
                rx.card(
                    rx.heading("Статус виконання:", size="4"),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                AppState.progress_log,
                                lambda log: rx.text(log, font_family="monospace", size="2"),
                            ),
                            align_items="start",
                        ),
                        height="250px",
                        type="always",
                    ),
                    width="100%",
                    background_color="var(--gray-3)",
                ),
            ),

            # --- Результати (таби з мовами) ---
            rx.cond(
                AppState.generated_results.length() > 0,
                rx.card(
                    rx.heading("Результати:", size="4"),
                    rx.tabs.root(
                        rx.tabs.list(
                            rx.foreach(
                                AppState.generated_results.keys(),
                                lambda lang: rx.tabs.trigger(lang, value=lang),
                            ),
                        ),
                        rx.foreach(
                            AppState.generated_results.keys(),
                            lambda lang: rx.tabs.content(
                                rx.code_block(
                                    AppState.generated_results[lang],
                                    language="html",
                                    show_line_numbers=True,
                                ),
                                value=lang,
                            ),
                        ),
                        width="100%",
                    ),
                    # Посилання на папку
                    rx.cond(
                        AppState.output_folder != "",
                        rx.text(
                            rx.text.strong("📂 Файли: "),
                            AppState.output_folder,
                            size="2",
                            color="gray",
                            margin_top="10px",
                        ),
                    ),
                    width="100%",
                ),
            ),
            width="100%",
            max_width="900px",
            spacing="6",
            padding_top="40px",
            padding_bottom="40px",
        ),
    )


app = rx.App()
app.add_page(index)