"""
Parsers for Content Extraction Pipeline v2.1

Каскадний парсинг: Requests + BS4 → Selenium.
Кожен метод зберігає зображення та відео як текстові маркери для LLM.

Ключові зміни v2.1:
- Firecrawl ВИДАЛЕНО (не використовується)
- Lazy imports для Selenium (не crash-ає якщо Chrome не встановлено)
- Flat cascade замість вкладених try/except
- Безпечніший junk-фільтр зображень (перевіряє ім'я файлу, не весь URL)
- WebDriverWait для Selenium (чекає на динамічний контент)
"""

import os
import re
import logging
from urllib.parse import urljoin, urlparse
from pathlib import PurePosixPath

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# PDF: PyPDF2
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None


# =====================================================================
# 📄 PDF EXTRACTION (PyPDF2 → Gemini fallback)
# =====================================================================
# Каскад:
# 1. PyPDF2 — швидкий, безкоштовний, працює для текстових PDF
# 2. Google Gemini — для сканованих PDF (OCR через vision API)
# =====================================================================

# Мінімальна кількість символів з PyPDF2, щоб вважати результат достатнім.
# Якщо менше — ймовірно скан, переходимо на Gemini.
MIN_PDF_TEXT_LENGTH = 100

# Модель Gemini для обробки PDF (можна override через env)
GEMINI_PDF_MODEL = os.getenv("GEMINI_PDF_MODEL", "gemini-2.0-flash")


def _extract_pdf_with_pypdf2(pdf_path: str) -> tuple[str, int]:
    """
    Спроба 1: PyPDF2 (швидкий, локальний).
    Повертає (текст, кількість_сторінок).
    """
    if PyPDF2 is None:
        raise ImportError("PyPDF2 не встановлено. Виконайте: pip install PyPDF2")

    text_parts = []
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        total_pages = len(reader.pages)

        for i, page in enumerate(reader.pages):
            extracted = page.extract_text()
            if extracted and extracted.strip():
                text_parts.append(extracted)
            else:
                logger.warning(f"  Сторінка {i + 1}/{total_pages} — текст не знайдено.")

    return "\n".join(text_parts), total_pages


def _extract_pdf_with_gemini(pdf_path: str) -> str:
    """
    Спроба 2: Google Gemini (для сканованих PDF).
    Використовує vision API для розпізнавання тексту, таблиць та зображень.
    """
    # Lazy import — не crash-ає якщо google-generativeai не встановлено
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeai не встановлено. Виконайте: "
            "pip install google-generativeai"
        )

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY або GOOGLE_API_KEY не знайдено в .env. "
            "Отримайте ключ: https://aistudio.google.com/apikey"
        )

    genai.configure(api_key=api_key)

    # Завантажуємо PDF через File API
    print(f"   📤 Завантажуємо PDF у Gemini ({os.path.basename(pdf_path)})...")
    uploaded_file = genai.upload_file(
        path=pdf_path,
        display_name=os.path.basename(pdf_path),
        mime_type="application/pdf"
    )

    model = genai.GenerativeModel(GEMINI_PDF_MODEL)

    # Промпт оптимізований для extraction техспек 3D-принтерів
    prompt = (
        "Extract ALL text content from this PDF document. "
        "This is a technical datasheet or product specification for 3D printing equipment.\n\n"
        "STRICT EXTRACTION RULES:\n"
        "1. Extract ALL technical specifications exactly as written (numbers, units, tolerances).\n"
        "2. Preserve table structures — output tables as plain text with | delimiters.\n"
        "3. Extract FAQ sections, troubleshooting guides, and maintenance instructions.\n"
        "4. For each product image you see, output a marker: "
        "[OFFICIAL_IMAGE: url='image_from_pdf', alt='description of what you see']\n"
        "5. Do NOT summarize or paraphrase — extract VERBATIM text.\n"
        "6. Do NOT add your own commentary or analysis.\n"
        "7. Output in ENGLISH. If the PDF is in another language, translate while extracting.\n\n"
        "Begin extraction:"
    )

    print(f"   🤖 Gemini ({GEMINI_PDF_MODEL}) обробляє PDF...")
    response = model.generate_content(
        [uploaded_file, prompt],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,  # Мінімальна креативність для точного extraction
            max_output_tokens=8192,
        )
    )

    # Очищаємо завантажений файл з Gemini
    try:
        genai.delete_file(uploaded_file.name)
    except Exception:
        pass  # Не критично якщо не вдалось видалити

    text = response.text
    if not text or len(text.strip()) < MIN_PDF_TEXT_LENGTH:
        raise ValueError(f"Gemini повернув замало тексту ({len(text)} символів).")

    return text


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Каскадне витягнення тексту з PDF:
    1. PyPDF2 (швидкий, безкоштовний)
    2. Gemini fallback (для сканованих PDF)
    """
    if not os.path.isfile(pdf_path):
        return f"[ПОМИЛКА] Файл не знайдено: {pdf_path}"

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"\n📄 PDF: {os.path.basename(pdf_path)} ({file_size_mb:.1f} MB)")

    # --- Спроба 1: PyPDF2 ---
    try:
        print("   ▶ Пробуємо PyPDF2...")
        text, total_pages = _extract_pdf_with_pypdf2(pdf_path)

        if len(text.strip()) >= MIN_PDF_TEXT_LENGTH:
            print(f"   ✅ PyPDF2 — успішно ({len(text)} символів з {total_pages} сторінок).")
            return text
        else:
            print(
                f"   ⚠️ PyPDF2: замало тексту ({len(text.strip())} символів з {total_pages} сторінок). "
                "Ймовірно сканований PDF."
            )
    except Exception as e:
        print(f"   ⚠️ PyPDF2 не впорався: {e}")

    # --- Спроба 2: Gemini ---
    try:
        print("   ▶ Пробуємо Google Gemini (OCR/Vision)...")
        text = _extract_pdf_with_gemini(pdf_path)
        print(f"   ✅ Gemini — успішно ({len(text)} символів).")
        return text
    except ImportError as e:
        print(f"   ⚠️ {e}")
        return (
            f"[ПОМИЛКА] PDF сканований, а Gemini недоступний. "
            f"Встановіть: pip install google-generativeai та додайте GEMINI_API_KEY в .env"
        )
    except Exception as e:
        print(f"   ❌ Gemini не впорався: {e}")
        return f"[ПОМИЛКА] Не вдалося витягнути текст з PDF жодним методом. Остання помилка: {e}"


# =====================================================================
# 🖼️ MEDIA TOKENIZATION (спільна для всіх scrapers)
# =====================================================================

# Junk-фільтр працює по ІМЕНІ ФАЙЛУ, а не по всьому URL.
# Це запобігає помилковому видаленню зображень типу "silicon-valley-printer.jpg"
# (старий фільтр через `in` по URL ловив "icon" всередині "silicon").
JUNK_FILENAME_PATTERNS = re.compile(
    r'(^icon[_\-s]|logo|spinner|avatar|badge|pixel|payment|social|'
    r'arrow|chevron|caret|close[-_]btn|hamburger|menu[-_]icon|'
    r'star[-_]rating|rating[-_]star|placeholder)',
    re.IGNORECASE
)

# Мінімальний розмір зображення (якщо розміри вказані в атрибутах)
MIN_IMAGE_DIMENSION = 80  # px


def _is_junk_image(img_tag, abs_src: str) -> bool:
    """Визначає, чи є зображення UI-сміттям."""
    # Перевіряємо base64 (дрібний UI)
    if abs_src.startswith('data:'):
        return True

    # Перевіряємо ім'я файлу (не весь URL)
    parsed = urlparse(abs_src)
    filename = PurePosixPath(parsed.path).name.lower()

    if JUNK_FILENAME_PATTERNS.search(filename):
        return True

    # Перевіряємо розміри якщо є (маленькі = іконки)
    try:
        width = int(img_tag.get('width', 0))
        height = int(img_tag.get('height', 0))
        if 0 < width < MIN_IMAGE_DIMENSION or 0 < height < MIN_IMAGE_DIMENSION:
            return True
    except (ValueError, TypeError):
        pass

    return False


def _preserve_media_and_get_text(soup: BeautifulSoup, base_url: str) -> str:
    """
    MAS Protocol: Серіалізує <img> та <iframe> у текстові маркери для LLM
    ДО витягнення тексту. Запобігає "Blind LLM" hallucination loop.
    """
    # 1. Видаляємо семантичне сміття
    for element in soup(["script", "style", "nav", "footer", "header",
                         "aside", "noscript", "svg", "form", "button"]):
        element.extract()

    # 2. Токенізація зображень
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''

        if not src:
            img.extract()
            continue

        abs_src = urljoin(base_url, src)

        if _is_junk_image(img, abs_src):
            img.extract()
            continue

        alt = img.get('alt', '').strip() or 'Official Product Image'
        token = f"\n[OFFICIAL_IMAGE: url='{abs_src}', alt='{alt}']\n"
        img.replace_with(token)

    # 3. Токенізація відео (тільки YouTube/Vimeo)
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src') or iframe.get('data-src') or ''
        if any(provider in src for provider in ('youtube', 'vimeo', 'youtu.be')):
            token = f"\n[OFFICIAL_VIDEO_IFRAME: src='{src}']\n"
            iframe.replace_with(token)
        else:
            iframe.extract()

    # 4. Чистий текст + маркери
    return soup.get_text(separator=' ', strip=True)


# =====================================================================
# 🕷️ SCRAPING METHODS
# =====================================================================

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Мінімальна кількість символів щоб вважати парсинг успішним
MIN_CONTENT_LENGTH = 200


def _scrape_with_requests(url: str) -> str:
    """Метод 1: Requests + BeautifulSoup — швидкий, для статичних сайтів."""
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
    response.raise_for_status()

    # Автодетект кодування (requests іноді помиляється з ISO-8859-1)
    if response.encoding and response.encoding.lower() == 'iso-8859-1':
        response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.content, 'html.parser')
    text = _preserve_media_and_get_text(soup, base_url=url)

    if len(text) < MIN_CONTENT_LENGTH:
        raise ValueError(
            f"Замало тексту ({len(text)} символів). "
            "Ймовірно, сторінка рендериться через JavaScript (SPA)."
        )

    return text


def _scrape_with_selenium(url: str) -> str:
    """Метод 2: Selenium (headless Chrome) — для JS-rendered сайтів."""
    # Lazy imports — не crash-ає якщо Chrome або selenium не встановлені
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        raise ImportError(
            "Selenium не встановлено. Виконайте: "
            "pip install selenium webdriver-manager"
        )

    options = Options()
    options.add_argument('--headless=new')  # Новий headless mode (Chrome 109+)
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(f'user-agent={DEFAULT_HEADERS["User-Agent"]}')

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.set_page_load_timeout(30)
        driver.get(url)

        # Чекаємо на завантаження динамічного контенту (max 10 сек)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            logger.warning(
                f"Selenium: timeout очікування body для {url}, "
                "продовжуємо з тим що є."
            )

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        text = _preserve_media_and_get_text(soup, base_url=url)

        if len(text) < MIN_CONTENT_LENGTH:
            raise ValueError(f"Selenium: замало контенту ({len(text)} символів).")

        return text
    finally:
        driver.quit()


# =====================================================================
# 🔄 КАСКАДНИЙ ПАРСИНГ (Flat pattern)
# =====================================================================

# Впорядкований список методів парсингу
SCRAPING_METHODS = [
    ("Requests + BS4", _scrape_with_requests),
    ("Selenium (Headless Chrome)", _scrape_with_selenium),
]


def _scrape_url(url: str) -> str:
    """
    Пробує методи парсингу послідовно (flat cascade).
    Повертає текст з першого успішного методу.
    """
    errors = []

    for method_name, method_func in SCRAPING_METHODS:
        try:
            print(f"   ▶ Пробуємо {method_name}...")
            text = method_func(url)
            print(f"   ✅ {method_name} — успішно ({len(text)} символів).")
            return text
        except Exception as e:
            error_msg = f"{method_name}: {e}"
            errors.append(error_msg)
            print(f"   ⚠️ {error_msg}")

    # Усі методи провалилися
    error_summary = "; ".join(errors)
    print(f"   ❌ УСІ МЕТОДИ ПРОВАЛИЛИСЯ для {url}")
    logger.error(f"Failed to scrape {url}: {error_summary}")
    return f"[НЕ ВДАЛОСЯ СПАРСИТИ: {url}] Помилки: {error_summary}"


def extract_text_from_urls(urls: list) -> str:
    """Каскадний парсинг списку URL-адрес із захистом від падінь."""
    if not urls:
        return "[ПОМИЛКА] Список URL порожній."

    combined_parts = []

    for url in urls:
        url = url.strip()
        if not url:
            continue

        print(f"\n⏳ Обробка URL: {url}")
        page_text = _scrape_url(url)
        combined_parts.append(f"\n--- Джерело: {url} ---\n{page_text}")

    if not combined_parts:
        return "[ПОМИЛКА] Жоден URL не дав результату."

    result = "\n".join(combined_parts)
    print(f"\n📊 Підсумок: оброблено {len(urls)} URL, загалом {len(result)} символів.")
    return result