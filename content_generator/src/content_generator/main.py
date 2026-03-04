import os
import shutil
import datetime
import sys
import io
from dotenv import load_dotenv

# Force UTF-8 encoding for stdout/stderr to support Ukrainian characters on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Завантажуємо ключі з .env файлу, який лежить у корені
load_dotenv()

from .tools.parsers import extract_text_from_pdf, extract_text_from_urls
from .crew import ECommerceContentCrew, LocalizationCrew
from crewai import Crew, Process

SITES_CONFIG = {
    "3DDevice": {
        "country": "Ukraine", 
        "languages": ["English", "Ukrainian", "Russian"],
        "localizer": "localizer_ua"
    },
    "3DPrinter": {
        "country": "Ukraine", 
        "languages": ["English", "Ukrainian", "Russian"],
        "localizer": "localizer_ua"
    },
    "3DScanner": {
        "country": "Ukraine", 
        "languages":["English", "Ukrainian", "Russian"],
        "localizer": "localizer_ua"
    },
    "Center 3D Print": {
        "country": "Poland", 
        "languages":["English", "Polish", "German", "Ukrainian", "Russian"],
        "localizer": "localizer_pl"
    },
    "EXPERT3D": {
        "country": "Spain", 
        "languages": ["English", "Spanish (Castilian es-ES)"],
        "localizer": "localizer_es"
    },
    "Expert-3DPrinter": {
        "country": "USA", 
        "languages": ["American English", "US Spanish"],
        "localizer": "localizer_us"
    }
}

def get_user_input():
    """Pre-flight меню для оператора: вибір джерела даних"""
    print("\n" + "="*60)
    print("🛠️ СИСТЕМА ГЕНЕРАЦІЇ GEO-КОНТЕНТУ OPENCART 🛠️")
    print("="*60)
    product_name = input("Введіть назву продукту (напр. Creality K1 Max): ")
    
    print("\nДоступні сайти:")
    for i, site in enumerate(SITES_CONFIG.keys(), 1):
        print(f"{i}. {site}")
    
    site_choice = input(f"Оберіть сайт (введіть точну назву зі списку): ")
    if site_choice not in SITES_CONFIG:
        print(f"❌ Помилка: Сайт '{site_choice}' не знайдено! Зупинка.")
        exit(1)

    print("\nЯке джерело даних використаємо для цього продукту?")
    print("1. Вставити готовий текст")
    print("2. Вказати URL-адреси (через кому)")
    print("3. Завантажити PDF (вказати шлях до файлу)")
    print("4. Автоматичний пошук (Агент сам шукатиме в Google)")
    
    data_choice = input("Оберіть варіант (1-4): ")
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
        urls_input = input("Введіть URL(и) офіційних сторінок/Wiki через кому: ")
        urls = [url.strip() for url in urls_input.split(",") if url.strip()]
        print("⏳ Парсимо URL...")
        raw_text = extract_text_from_urls(urls)
        
    elif data_choice == '3':
        pdf_path = input("Введіть повний шлях до PDF файлу: ")
        print("⏳ Читаємо PDF...")
        raw_text = extract_text_from_pdf(pdf_path)
        
    elif data_choice == '4':
        use_auto_search = True
        print("🤖 Ок, агент Web Researcher сам шукатиме інформацію в мережі.")
        
    else:
        print("⚠️ Невірний вибір. Використовуємо автоматичний пошук.")
        use_auto_search = True

    return product_name, site_choice, raw_text, use_auto_search


def run_pipeline():
    # 1. Отримуємо дані
    product_name, target_site, raw_text, use_auto_search = get_user_input()
    site_info = SITES_CONFIG[target_site]

    # --- СТВОРЕННЯ СТРУКТУРИ ПАПОК ---
    # Генеруємо timestamp: DD-MM-YYYY-H-M
    timestamp = datetime.datetime.now().strftime("%d-%m-%Y-%H-%M")
    
    # Очищуємо назви від пробілів для безпеки файлової системи
    safe_site_name = target_site.replace(" ", "_")
    safe_product_name = product_name.replace(" ", "_")
    
    # Формуємо назву папки: назва-сайту-назва-товару-timestamp
    folder_name = f"{safe_site_name}-{safe_product_name}-{timestamp}"
    
    # Повний шлях до папки виводу: output/folder_name
    output_dir = os.path.join("output", folder_name)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n📂 Створено папку для результатів: {output_dir}")

    core_inputs = {
        'product_name': product_name,
        'site_name': target_site,
        'target_country': site_info['country'],
        'raw_source_text': raw_text,
        'language_instruction': "IMPORTANT: You MUST generate all content in Phase 1 (Marketing Copy, Specs, HTML) strictly in ENGLISH. Transcreation should happen only in Phase 2."
    }

    print("\n" + "="*60)
    print(f"🚀 ФАЗА 1: ЗБІР ДАНИХ ТА АНГЛІЙСЬКА ВЕРСТКА ({target_site})")
    print("="*60)
    
    core_crew_module = ECommerceContentCrew()
    
    if use_auto_search:
        print("\n" + "!"*60)
        print("🛑 HUMAN-IN-THE-LOOP CHECK: AUTO-SEARCH ENABLED")
        print(f"Product: {product_name}")
        print(f"Target Site: {target_site}")
        print("The agent will now search for official manufacturer data.")
        input("Press ENTER to authorize the search and extraction for PHASE 1... ")
        print("!"*60 + "\n")
        
       # Phase 1: Research and Core Content
    # We pass 'product_name' to dynamic task methods
        tasks_to_run = [
            core_crew_module.source_research_task(product_name),
            core_crew_module.tech_specs_extraction_task(product_name),
            core_crew_module.seo_strategy_task(),
            core_crew_module.copywriting_task(),
            core_crew_module.quality_assurance_task(),
            core_crew_module.html_integration_task()
        ]
    else:
        print(f"✅ Знайдено {len(raw_text)} символів сирого тексту. Пропускаємо етап пошуку!")
        tasks_to_run = [
            core_crew_module.tech_specs_extraction_task(),
            core_crew_module.seo_strategy_task(),
            core_crew_module.copywriting_task(),
            core_crew_module.quality_assurance_task(),
            core_crew_module.html_integration_task()
        ]

    active_core_crew = core_crew_module.create_crew(tasks_to_run)
    core_result = active_core_crew.kickoff(inputs=core_inputs)
    base_english_html = core_result.raw 
    print("✅ Базовий HTML (з GEO Microdata) успішно згенеровано!\n")

    # ФАЗА 2: Цикл локалізації
    localizer_agent_name = site_info['localizer']
    
    print("\n" + "="*60)
    print(f"🌍 ФАЗА 2: ЛОКАЛІЗАЦІЯ (Агент: {localizer_agent_name})")
    print("="*60)
    
    for language in site_info['languages']:
        print(f"\n🔄 Транскреація для мови: {language}...")
        
        localization_inputs = {
            'product_name': product_name,
            'site_name': target_site,
            'target_language': language,
            'base_html': base_english_html
        }
        
        loc_crew_module = LocalizationCrew(localizer_name=localizer_agent_name)
        loc_crew = loc_crew_module.crew()
        
        loc_result = loc_crew.kickoff(inputs=localization_inputs)
        
        # Формуємо назву файлу: folder_name_Language.html (щоб відповідати структурі)
        safe_lang = language.split(" ")[0] # Беремо перше слово (напр. "Spanish" з "Spanish (Castilian)")
        filename = f"{folder_name}_{safe_lang}.html"
        file_path = os.path.join(output_dir, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(loc_result.raw)
            
        print(f"💾 Збережено: {filename}")

    # --- АРХІВАЦІЯ (ZIP) ---
    print("\n📦 Створення ZIP-архіву...")
    
    # Створюємо архів у папці output (поруч з папкою проєкту)
    # base_name - це шлях + назва архіву (без .zip)
    zip_base_name = os.path.join("output", folder_name)
    
    # root_dir - яку папку архівуємо
    shutil.make_archive(zip_base_name, 'zip', output_dir)
    
    # Переміщуємо архів ВСЕРЕДИНУ створеної папки (як ви просили)
    # З: output/folder.zip -> В: output/folder/folder.zip
    src_zip = f"{zip_base_name}.zip"
    dst_zip = os.path.join(output_dir, f"{folder_name}.zip")
    shutil.move(src_zip, dst_zip)

    print(f"🎉 Готово! Всі файли та архів знаходяться тут:\n   👉 {output_dir}")

def run():
    """Entry point for the crew"""
    run_pipeline()

if __name__ == "__main__":
    run()