import os
import requests
from bs4 import BeautifulSoup
import PyPDF2

# Для Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager # pip install webdriver-manager

# Для Firecrawl (pip install firecrawl-py)
from firecrawl import FirecrawlApp

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

def _scrape_with_firecrawl(url: str) -> str:
    """Метод 1: Парсинг через Firecrawl API (Найкраще для LLM)"""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY не знайдено в оточенні.")
    
    app = FirecrawlApp(api_key=api_key)
    scraped_data = app.scrape_url(url, params={'formats': ['markdown']})
    return scraped_data.get('markdown', '')

def _scrape_with_bs4(url: str) -> str:
    """Метод 2: Швидкий парсинг через Requests + BeautifulSoup"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status() # Викине помилку, якщо статус 403, 404 тощо
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Вичищаємо "сміття"
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.extract()
        
    text = soup.get_text(separator=' ', strip=True)
    
    # Якщо тексту підозріло мало (менше 200 символів), швидше за все це JS-рендер
    if len(text) < 200:
        raise ValueError("Замало тексту. Ймовірно, сторінка рендериться через JavaScript.")
        
    return text

def _scrape_with_selenium(url: str) -> str:
    """Метод 3: 'Важкий танк' Selenium для JS-сайтів та обходу простого блокування"""
    options = Options()
    options.add_argument('--headless') # Запуск без графічного вікна
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # webdriver_manager сам завантажить потрібну версію ChromeDriver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        
        # Отримуємо HTML після того, як JS відпрацював
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.extract()
            
        return soup.get_text(separator=' ', strip=True)
    finally:
        driver.quit() # Обов'язково закриваємо браузер, щоб не забити оперативну пам'ять

def extract_text_from_urls(urls: list) -> str:
    """Каскадний парсинг URL-адрес"""
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
                
                # Спроба 3: Selenium (Останній рубіж)
                try:
                    print("   ▶ Пробуємо Selenium (Headless Chrome)...")
                    page_text = _scrape_with_selenium(url)
                    print("   ✅ Selenium успішно відпрацював.")
                except Exception as e_selenium:
                    print(f"   ❌ УСІ МЕТОДИ ПРОВАЛИЛИСЯ для {url}: {e_selenium}")
                    page_text = f"[НЕ ВДАЛОСЯ СПАРСИТИ: {url}]"

        combined_text += f"\n--- Джерело: {url} ---\n{page_text}\n"
        
    return combined_text