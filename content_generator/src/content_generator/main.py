import os
import shutil
import datetime
import sys
import io
import re
from dotenv import load_dotenv

# Force UTF-8 encoding for stdout/stderr (Windows support)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

# Гарантуємо абсолютні імпорти при запуску через python main.py або uv run
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_current_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from content_generator.tools.parsers import (
    extract_text_from_pdf, extract_text_from_urls,
    extract_text_from_md, extract_text_from_md_dir,
)
from content_generator.crew import ECommerceContentCrew, LocalizationCrew, SITES_CONFIG, CTA_TEMPLATES


# =====================================================================
# 🛠️ ДОПОМІЖНІ ФУНКЦІЇ
# =====================================================================

_INVALID_CHARS = r'[\\/:*?"<>|()]'


def _sanitize_name(name: str) -> str:
    """Очищує назву від пробілів та заборонених символів Windows."""
    return re.sub(_INVALID_CHARS, '', name).replace(' ', '_')


def _save_html(output_dir: str, filename: str, html_content: str) -> str:
    """Зберігає HTML-файл і повертає повний шлях."""
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def get_user_input():
    """Pre-flight меню для оператора: вибір продукту, сайту, джерела даних."""
    print("\n" + "=" * 60)
    print("🛠️  СИСТЕМА ГЕНЕРАЦІЇ GEO-КОНТЕНТУ OPENCART  🛠️")
    print("=" * 60)

    product_name = input("Введіть назву продукту (напр. Creality K1 Max): ")

    print("\nДоступні сайти:")
    sites_list = list(SITES_CONFIG.keys())
    for i, site in enumerate(sites_list, 1):
        cfg = SITES_CONFIG[site]
        ua_flag = "🟢 UA=prod" if cfg["ua_is_production"] else "🔵 UA=review"
        print(f"  {i}. {site} ({cfg['country']}) [{ua_flag}]")

    site_choice = input(f"Оберіть сайт (введіть точну назву зі списку): ")
    if site_choice not in SITES_CONFIG:
        print(f"❌ Помилка: Сайт '{site_choice}' не знайдено! Зупинка.")
        sys.exit(1)

    print("\nЯке джерело даних використаємо?")
    print("  1. Вставити готовий текст")
    print("  2. Вказати URL-адреси (через кому)")
    print("  3. Завантажити PDF (вказати шлях)")
    print("  4. Автоматичний пошук (агент шукатиме в Google)")
    print("  5. Markdown файл (вказати шлях)")
    print("  6. Директорія Markdown файлів (рекурсивний скан)")

    data_choice = input("Оберіть варіант (1-6): ")
    raw_text = ""
    use_auto_search = False

    if data_choice == '1':
        print("Вставте текст (натисніть Enter двічі для завершення):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        raw_text = "\n".join(lines)

    elif data_choice == '2':
        urls_input = input("Введіть URL(и) через кому: ")
        urls = [url.strip() for url in urls_input.split(",") if url.strip()]
        print("⏳ Парсимо URL...")
        raw_text = extract_text_from_urls(urls)

    elif data_choice == '3':
        pdf_path = input("Введіть повний шлях до PDF файлу: ")
        print("⏳ Читаємо PDF...")
        raw_text = extract_text_from_pdf(pdf_path)

    elif data_choice == '4':
        use_auto_search = True
        print("🤖 Агент Web Researcher сам шукатиме інформацію в мережі.")

    elif data_choice == '5':
        md_path = input("Введіть повний шлях до Markdown файлу: ")
        print("⏳ Читаємо Markdown...")
        raw_text = extract_text_from_md(md_path)

    elif data_choice == '6':
        md_dir = input("Введіть шлях до директорії з Markdown файлами: ")
        exclude_input = input(
            "Виключити файли (через кому, або Enter для стандартних): "
        ).strip()
        exclude_patterns = None
        if exclude_input:
            exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]
        print("⏳ Скануємо директорію Markdown файлів...")
        raw_text = extract_text_from_md_dir(md_dir, exclude_patterns=exclude_patterns)

    else:
        print("⚠️ Невірний вибір. Використовуємо автоматичний пошук.")
        use_auto_search = True

    return product_name, site_choice, raw_text, use_auto_search


# =====================================================================
# 🚀 ОСНОВНИЙ ПАЙПЛАЙН
# =====================================================================

def run_pipeline():
    # 1. Збираємо вхідні дані від оператора
    product_name, target_site, raw_text, use_auto_search = get_user_input()
    site_info = SITES_CONFIG[target_site]

    # 2. Створюємо папку для результатів
    timestamp = datetime.datetime.now().strftime("%d-%m-%Y-%H-%M")
    safe_site = _sanitize_name(target_site)
    safe_product = _sanitize_name(product_name)
    folder_name = f"{safe_site}-{safe_product}-{timestamp}"
    output_dir = os.path.join("output", folder_name)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n📂 Папка результатів: {output_dir}")

    # 3. Формуємо CTA контекст для копірайтера
    cta_data = CTA_TEMPLATES.get(target_site, {})
    if cta_data:
        advantages_text = "\n".join(f"- {adv}" for adv in cta_data.get("store_advantages", []))
        urgency = cta_data.get("urgency_hook", "")
        cta_context = f"STORE ADVANTAGES for {target_site}:\n{advantages_text}\n\nURGENCY HOOK: {urgency}"
    else:
        cta_context = f"No specific CTA data for {target_site}. Write a generic professional CTA."

    # 4. Базові inputs для Фази 1 (завжди англійська)
    core_inputs = {
        'product_name': product_name,
        'site_name': target_site,
        'target_country': "Global Market (USA/UK)",
        'raw_source_text': raw_text,
        'cta_context': cta_context,
        'language_instruction': (
            "CRITICAL SYSTEM DIRECTIVE: Regardless of the language of the source text, "
            "YOU MUST OUTPUT 100% OF YOUR RESPONSE IN ENGLISH. "
            "Do not translate SEO keywords to other languages. Everything MUST be in English."
        )
    }

    # =================================================================
    # ФАЗА 1: АНГЛІЙСЬКА БАЗА (збір даних → HTML)
    # =================================================================
    print("\n" + "=" * 60)
    print(f"🚀 ФАЗА 1: ЗБІР ДАНИХ ТА АНГЛІЙСЬКА ВЕРСТКА ({target_site})")
    print("=" * 60)

    core_crew_module = ECommerceContentCrew()

    if use_auto_search:
        print("\n" + "!" * 60)
        print("🛑 HUMAN-IN-THE-LOOP: AUTO-SEARCH ENABLED")
        print(f"   Product: {product_name}")
        print(f"   Target Site: {target_site}")
        input("   Press ENTER to authorize search and extraction... ")
        print("!" * 60 + "\n")

        tasks_to_run = [
            core_crew_module.url_discovery_task(product_name),
            core_crew_module.content_extraction_task(product_name),
            core_crew_module.tech_specs_extraction_task(product_name),
            core_crew_module.seo_strategy_task(),
            core_crew_module.copywriting_task(),
            core_crew_module.quality_assurance_task(),
            core_crew_module.html_integration_task()
        ]
    else:
        print(f"✅ Знайдено {len(raw_text)} символів сирого тексту. Пропускаємо пошук.")
        tasks_to_run = [
            core_crew_module.tech_specs_extraction_task(product_name),
            core_crew_module.seo_strategy_task(),
            core_crew_module.copywriting_task(),
            core_crew_module.quality_assurance_task(),
            core_crew_module.html_integration_task()
        ]

    active_core_crew = core_crew_module.create_crew(tasks_to_run)
    core_result = active_core_crew.kickoff(inputs=core_inputs)
    base_english_html = core_result.raw

    # Зберігаємо англійську базу (завжди корисно мати оригінал)
    _save_html(output_dir, f"{folder_name}_BASE_English.html", base_english_html)
    print("✅ Базовий HTML (English + GEO Microdata) згенеровано та збережено.\n")

    # =================================================================
    # ФАЗА 2: ЛОКАЛІЗАЦІЯ
    # =================================================================
    localizer_key = site_info['localizer']
    ua_is_production = site_info.get('ua_is_production', False)

    # -----------------------------------------------------------------
    # КРОК 1: ОБОВ'ЯЗКОВИЙ УКРАЇНСЬКИЙ РЕВ'Ю
    # -----------------------------------------------------------------
    # Завжди генерується ПЕРШИМ, незалежно від магазину.
    # Для UA магазинів: один файл = review + production.
    # Для інших: окремий REVIEW файл (не публікується).
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("📋 КРОК 1: УКРАЇНСЬКА ВЕРСІЯ (REVIEW)")
    print("=" * 60)

    if ua_is_production:
        # UA магазин: використовуємо повний localizer_ua (з ринковими адаптаціями)
        ua_market_key = 'localizer_ua'
        ua_label = "REVIEW + PRODUCTION"
        ua_filename = f"{folder_name}_Ukrainian.html"
    else:
        # Інші ринки: використовуємо нейтральний review_ua (без ринкових адаптацій)
        ua_market_key = 'review_ua'
        ua_label = "REVIEW ONLY (не публікується)"
        ua_filename = f"{folder_name}_REVIEW_Ukrainian.html"

    ua_crew_module = LocalizationCrew(market_key=ua_market_key)
    ua_crew = ua_crew_module.crew()
    ua_inputs = ua_crew_module.get_inputs(
        product_name=product_name,
        site_name=target_site,
        target_language='Ukrainian',
        base_html=base_english_html
    )
    ua_result = ua_crew.kickoff(inputs=ua_inputs)

    _save_html(output_dir, ua_filename, ua_result.raw)
    print(f"💾 [{ua_label}] Збережено: {ua_filename}")

    # -----------------------------------------------------------------
    # КРОК 2: РЕШТА МОВ
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"🌍 КРОК 2: ЛОКАЛІЗАЦІЯ РЕШТИ МОВ (агент: {localizer_key})")
    print("=" * 60)

    for language in site_info['languages']:
        # Пропускаємо Ukrainian — вже згенеровано на Кроці 1
        if language == 'Ukrainian':
            print(f"  ⏩ {language} — вже згенеровано (Крок 1), пропуск.")
            continue

        print(f"\n  🔄 Транскреація: {language}...")

        loc_crew_module = LocalizationCrew(market_key=localizer_key)
        loc_crew = loc_crew_module.crew()
        loc_inputs = loc_crew_module.get_inputs(
            product_name=product_name,
            site_name=target_site,
            target_language=language,
            base_html=base_english_html
        )
        loc_result = loc_crew.kickoff(inputs=loc_inputs)

        safe_lang = language.split(" ")[0]
        filename = f"{folder_name}_{safe_lang}.html"
        _save_html(output_dir, filename, loc_result.raw)
        print(f"  💾 Збережено: {filename}")

    # -----------------------------------------------------------------
    # АРХІВАЦІЯ (ZIP)
    # -----------------------------------------------------------------
    print("\n📦 Створення ZIP-архіву...")
    zip_base = os.path.join("output", folder_name)
    shutil.make_archive(zip_base, 'zip', output_dir)
    shutil.move(f"{zip_base}.zip", os.path.join(output_dir, f"{folder_name}.zip"))

    print(f"\n🎉 Готово! Усі файли та архів:\n   👉 {output_dir}")

    # Показуємо фінальний зміст папки
    print("\n📂 Зміст:")
    for f in sorted(os.listdir(output_dir)):
        size_kb = os.path.getsize(os.path.join(output_dir, f)) / 1024
        print(f"   {'📄' if f.endswith('.html') else '📦'} {f} ({size_kb:.1f} KB)")


# =====================================================================
# 🏋️ РЕЖИМ ТРЕНУВАННЯ
# =====================================================================

def train_pipeline():
    """Ізольований режим тренування для Core Crew (Фаза 1)."""
    print("\n" + "=" * 60)
    print("🏋️  РЕЖИМ ТРЕНУВАННЯ (TRAINING MODE)  🏋️")
    print("=" * 60)
    print("УВАГА: Тренування вимагає зворотного зв'язку на кожній ітерації.")
    print("Система згенерує результат, запитає критику, і оптимізує поведінку.\n")

    try:
        n_iterations = int(input("Кількість ітерацій (рекомендовано 2-3): ") or 2)
    except ValueError:
        n_iterations = 2

    filename = input("Назва файлу моделі (напр. core_crew_model.pkl): ") or "core_crew_model.pkl"

    product_name, target_site, raw_text, use_auto_search = get_user_input()

    if not raw_text and use_auto_search:
        print(
            "\n❌ [ФАТАЛЬНА ПОМИЛКА]: Режим тренування вимагає статичного тексту.\n"
            "   Ви не можете використовувати 'Автоматичний пошук' (Опція 4),\n"
            "   оскільки вхідні дані змінюватимуться між ітераціями.\n"
            "   Перезапустіть і оберіть Опцію 1, 2, 3, 5 або 6."
        )
        sys.exit(1)

    # Формуємо CTA контекст
    cta_data = CTA_TEMPLATES.get(target_site, {})
    if cta_data:
        advantages_text = "\n".join(f"- {adv}" for adv in cta_data.get("store_advantages", []))
        urgency = cta_data.get("urgency_hook", "")
        cta_context = f"STORE ADVANTAGES for {target_site}:\n{advantages_text}\n\nURGENCY HOOK: {urgency}"
    else:
        cta_context = f"No specific CTA data for {target_site}. Write a generic professional CTA."

    core_inputs = {
        'product_name': product_name,
        'site_name': target_site,
        'target_country': "Global Market (USA/UK)",
        'raw_source_text': raw_text,
        'cta_context': cta_context,
        'language_instruction': (
            "CRITICAL SYSTEM DIRECTIVE: YOU MUST OUTPUT 100% OF YOUR RESPONSE IN ENGLISH."
        )
    }

    core_crew_module = ECommerceContentCrew()

    print("\n[АУДИТ]: Переводимо систему в режим тренування...")
    tasks_to_run = [
        core_crew_module.tech_specs_extraction_task(product_name),
        core_crew_module.seo_strategy_task(),
        core_crew_module.copywriting_task(),
        core_crew_module.quality_assurance_task(),
        core_crew_module.html_integration_task()
    ]

    active_core_crew = core_crew_module.create_crew(tasks_to_run)

    print(f"\n⏳ Запуск тренування ({n_iterations} ітерацій)...")
    active_core_crew.train(
        n_iterations=n_iterations,
        filename=filename,
        inputs=core_inputs
    )

    print(f"\n🎉 Тренування завершено! Дані збережено: {filename}")


# =====================================================================
# 🚪 ENTRY POINT
# =====================================================================

def run():
    """Стандартний режим генерації."""
    run_pipeline()


if __name__ == "__main__":
    print("\n" + "!" * 60)
    print("ОБЕРІТЬ РЕЖИМ ЗАПУСКУ")
    print("!" * 60)
    print("  1. 🚀 PRODUCTION (генерація + локалізація)")
    print("  2. 🏋️ TRAINING (тренування з Human Feedback)")

    mode = input("\nВаш вибір (1 або 2): ")

    if mode == '2':
        train_pipeline()
    else:
        run()