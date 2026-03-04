import reflex as rx
import os
import asyncio
from parsers import extract_text_from_pdf, extract_text_from_urls
# Імпортуємо ваші налаштовані Crew
from crew import ECommerceContentCrew, LocalizationCrew, SITES_CONFIG

class AppState(rx.State):
    """Глобальний стан нашого додатку"""
    product_name: str = ""
    target_site: str = "EXPERT3D"
    data_source: str = "Auto Search (AI)"
    raw_text_input: str = ""
    url_input: str = ""
    
    # UI States
    is_processing: bool = False
    progress_log: list[str] = []
    generated_results: dict[str, str] = {}  # { "Language": "HTML Code" }

    def add_log(self, message: str):
        """Додає повідомлення в лог на екрані"""
        self.progress_log.append(message)

    @rx.background
    async def run_generation(self):
        """Фонова задача, яка запускає CrewAI, щоб не блокувати UI"""
        async with self:
            self.is_processing = True
            self.progress_log =[]
            self.generated_results = {}
            self.add_log(f"🚀 Запуск конвеєра для: {self.product_name} | Сайт: {self.target_site}")

        # Імітація збору даних (Тут виклик ваших parsers.py)
        raw_text = ""
        use_auto_search = False
        
        async with self:
            if self.data_source == "Manual Text":
                self.add_log("📥 Використовуємо введений текст...")
                raw_text = self.raw_text_input
            elif self.data_source == "URL Input":
                self.add_log(f"🔗 Парсимо URL: {self.url_input}...")
                # В реальності тут: raw_text = extract_text_from_urls([self.url_input])
                raw_text = "Імітація спарсеного тексту..." 
            else:
                self.add_log("🤖 Агент Web Researcher починає пошук в Google...")
                use_auto_search = True

            self.add_log("⚙️ Запуск CrewAI (Фаза 1: SEO, JSON, Копірайтинг, HTML)...")
            
        # ТУТ ЗАПУСКАЄТЬСЯ CREW AI (це блокуючий виклик, але оскільки 
        # ми в @rx.background, він не "вішає" інтерфейс користувача)
        
        # ІМІТАЦІЯ ЗАТРИМКИ CREW AI ДЛЯ ТЕСТУ (Замініть на реальний виклик active_core_crew.kickoff)
        await asyncio.sleep(3) 
        base_english_html = "<h1>Test HTML</h1><p>Done by Frontend Developer</p>"
        
        async with self:
            self.add_log("✅ Базовий HTML (з GEO Microdata) успішно згенеровано!")
            self.add_log("🌍 Перехід до Фази 2: Локалізація...")

        site_info = SITES_CONFIG.get(self.target_site)
        localizer_agent = site_info['localizer']

        for language in site_info['languages']:
            async with self:
                self.add_log(f"🔄 Транскреація для мови: {language} (Агент: {localizer_agent})...")
            
            # ІМІТАЦІЯ ЛОКАЛІЗАЦІЇ (Замініть на loc_crew.kickoff)
            await asyncio.sleep(2)
            localized_html = f"<!-- Мова: {language} -->\n" + base_english_html
            
            async with self:
                self.generated_results[language] = localized_html
                self.add_log(f"💾 Готово: {language}")

        async with self:
            self.add_log("🎉 УСІ ЗАВДАННЯ ВИКОНАНО УСПІШНО!")
            self.is_processing = False


def index() -> rx.Component:
    """Головна сторінка інтерфейсу (UI)"""
    return rx.container(
        rx.vstack(
            rx.heading("🤖 GEO-Content Generator (CrewAI)", size="8", color="indigo"),
            rx.text("Створення карток товарів з Microdata для OpenCart.", color="gray"),
            
            # Форма вводу
            rx.card(
                rx.vstack(
                    rx.input(placeholder="Назва продукту (напр. Creality K1 Max)", on_blur=AppState.set_product_name, width="100%"),
                    rx.select(
                        list(SITES_CONFIG.keys()), 
                        value=AppState.target_site, 
                        on_change=AppState.set_target_site,
                        label="Цільовий сайт"
                    ),
                    rx.radio(
                        ["Auto Search (AI)", "Manual Text", "URL Input"], 
                        value=AppState.data_source, 
                        on_change=AppState.set_data_source,
                        direction="row"
                    ),
                    
                    # Динамічні поля залежно від вибору
                    rx.cond(
                        AppState.data_source == "Manual Text",
                        rx.text_area(placeholder="Вставте сирий текст або характеристики...", on_blur=AppState.set_raw_text_input, width="100%", height="150px"),
                    ),
                    rx.cond(
                        AppState.data_source == "URL Input",
                        rx.input(placeholder="https://official-site.com/product", on_blur=AppState.set_url_input, width="100%"),
                    ),
                    
                    rx.button(
                        "🚀 Згенерувати контент", 
                        on_click=AppState.run_generation, 
                        loading=AppState.is_processing,
                        size="4",
                        width="100%",
                        color_scheme="indigo"
                    ),
                    width="100%",
                    spacing="4"
                ),
                width="100%",
            ),

            # Секція логів прогресу
            rx.cond(
                AppState.progress_log.length() > 0,
                rx.card(
                    rx.heading("Статус виконання:", size="4"),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(AppState.progress_log, lambda log: rx.text(log, font_family="monospace", size="2")),
                            align_items="start"
                        ),
                        height="200px",
                        type="always"
                    ),
                    width="100%",
                    background_color="var(--gray-3)"
                )
            ),

            # Результати (Таби з мовами)
            rx.cond(
                AppState.generated_results.length() > 0,
                rx.tabs.root(
                    rx.tabs.list(
                        rx.foreach(
                            AppState.generated_results.keys(),
                            lambda lang: rx.tabs.trigger(lang, value=lang)
                        )
                    ),
                    rx.foreach(
                        AppState.generated_results.keys(),
                        lambda lang: rx.tabs.content(
                            rx.code_block(AppState.generated_results[lang], language="html", show_line_numbers=True),
                            value=lang
                        )
                    ),
                    width="100%",
                    margin_top="20px"
                )
            ),
            
            width="100%",
            max_width="800px",
            spacing="6",
            padding_top="50px",
            padding_bottom="50px"
        )
    )

app = rx.App()
app.add_page(index)