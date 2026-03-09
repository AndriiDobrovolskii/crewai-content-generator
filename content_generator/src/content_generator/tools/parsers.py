import os
import requests
from bs4 import BeautifulSoup
import PyPDF2
from urllib.parse import urljoin

# Для Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager # pip install webdriver-manager

# Для Firecrawl
from firecrawl import FirecrawlApp # pip install firecrawl-py

def extract_text_from_pdf(pdf_path: str) -> str:
    """Витягує текст з PDF файлу"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        return text
    except Exception as e:
        return f"[ПОМИЛКА] Не вдалося прочитати PDF: {e}"

def _preserve_media_and_get_text(soup: BeautifulSoup, base_url: str) -> str:
    """
    CRITICAL MAS PROTOCOL: Serializes <img> and <iframe> tags into LLM-readable text tokens 
    BEFORE extracting raw text. Prevents the "Blind LLM" hallucination loop.
    """
    # 1. Вичищаємо семантичне "сміття", яке забиває контекстне вікно LLM
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form", "button"]):
        element.extract()
        
    # 2. Токенізація Зображень (Image Serialization)
    for img in soup.find_all('img'):
        # Шукаємо реальний URL (обхід lazy-loading)
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
        
        # Ігноруємо base64 картинки (це зазвичай дрібний UI)
        if not src or src.startswith('data:'):
            img.extract()
            continue
            
        # Перетворюємо відносні посилання (/img/1.jpg) на абсолютні (https://...)
        abs_src = urljoin(base_url, src)
        
        # Агресивний фільтр сміттєвих UI картинок (Brand Safety Guardrail)
        lower_src = abs_src.lower()
        junk_keywords = ['icon', 'logo', 'spinner', 'avatar', 'badge', 'pixel', 'payment', 'social']
        if any(junk in lower_src for junk in junk_keywords):
            img.extract()
            continue
            
        alt = img.get('alt', 'Official Product Image').strip()
        
        # ЗАМІНЮЄМО HTML-тег на текстовий маркер для LLM
        token = f"\n[OFFICIAL_IMAGE: url='{abs_src}', alt='{alt}']\n"
        img.replace_with(token)
        
    # 3. Токенізація Відео (iFrame Serialization)
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src') or iframe.get('data-src') or ''
        if 'youtube' in src or 'vimeo' in src:
            token = f"\n[OFFICIAL_VIDEO_IFRAME: src='{src}']\n"
            iframe.replace_with(token)
        else:
            iframe.extract() # Видаляємо рекламні або трекінгові фрейми

    # 4. Повертаємо чистий текст разом з інтегрованими [МАРКЕРАМИ]
    return soup.get_text(separator=' ', strip=True)

def _scrape_with_firecrawl(url: str) -> str:
    """Метод 1: Парсинг через Firecrawl API (Гарантована уніфікація токенів)"""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY не знайдено в оточенні.")
    
    app = FirecrawlApp(api_key=api_key)
    # ВИПРАВЛЕНО: Ми вимагаємо HTML замість Markdown. Це дозволяє нам застосувати 
    # нашу власну токенізацію картинок і зберегти iframes, які Markdown часто видаляє.
    scraped_data = app.scrape_url(url, params={'formats': ['html']})
    html_content = scraped_data.get('html', '')
    
    if not html_content:
        raise ValueError("Firecrawl повернув порожній HTML.")
        
    soup = BeautifulSoup(html_content, 'html.parser')
    return _preserve_media_and_get_text(soup, base_url=url)

def _scrape_with_bs4(url: str) -> str:
    """Метод 2: Швидкий парсинг через Requests + Збереження Медіа"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status() 
    
    soup = BeautifulSoup(response.content, 'html.parser')
    text = _preserve_media_and_get_text(soup, base_url=url)
    
    if len(text) < 200:
        raise ValueError("Замало тексту. Ймовірно, сторінка рендериться через JavaScript (SPA).")
        
    return text

def _scrape_with_selenium(url: str) -> str:
    """Метод 3: 'Важкий танк' Selenium для JS-сайтів + Збереження Медіа"""
    options = Options()
    options.add_argument('--headless') 
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        return _preserve_media_and_get_text(soup, base_url=url)
    finally:
        driver.quit() 

def extract_text_from_urls(urls: list) -> str:
    """Каскадний парсинг URL-адрес із захистом від падінь"""
    combined_text = ""
    
    for url in urls:
        url = url.strip()
        print(f"\n⏳ Обробка URL: {url}")
        page_text = ""
        
        # Спроба 1: Firecrawl
        try:
            print("   ▶ Пробуємо Firecrawl API...")
            page_text = _scrape_with_firecrawl(url)
            print("   ✅ Firecrawl успішно відпрацював.")
        except Exception as e_firecrawl:
            print(f"   ⚠️ Firecrawl не впорався ({e_firecrawl}).")
            
            # Спроба 2: BeautifulSoup
            try:
                print("   ▶ Пробуємо BeautifulSoup...")
                page_text = _scrape_with_bs4(url)
                print("   ✅ BeautifulSoup успішно відпрацював.")
            except Exception as e_bs4:
                print(f"   ⚠️ BeautifulSoup не впорався ({e_bs4}).")
                
                # Спроба 3: Selenium
                try:
                    print("   ▶ Пробуємо Selenium (Headless Chrome)...")
                    page_text = _scrape_with_selenium(url)
                    print("   ✅ Selenium успішно відпрацював.")
                except Exception as e_selenium:
                    print(f"   ❌ УСІ МЕТОДИ ПРОВАЛИЛИСЯ для {url}: {e_selenium}")
                    page_text = f"[НЕ ВДАЛОСЯ СПАРСИТИ: {url}]"

        combined_text += f"\n--- Джерело: {url} ---\n{page_text}\n"
        
    return combined_text