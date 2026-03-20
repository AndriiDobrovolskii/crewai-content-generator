"""
Parsers for Content Extraction Pipeline v2.3

Каскадний парсинг: Requests + BS4 → Selenium.
Кожен метод зберігає зображення та відео як текстові маркери для LLM.

Ключові зміни v2.3:
- Markdown ingestion: extract_text_from_md() — single file з front matter extraction
- Markdown directory: extract_text_from_md_dir() — рекурсивний скан з exclude-паттернами
- YAML front matter → структурований префікс для tech_specs_analyst
- Markdown normalization: headers → рівневі маркери, syntax stripping, table preservation

Ключові зміни v2.2:
- Multi-PDF: extract_text_from_pdfs() — batch обробка кількох PDF з маркерами джерел

Ключові зміни v2.1:
- Firecrawl ВИДАЛЕНО (не використовується)
- Lazy imports для Selenium (не crash-ає якщо Chrome не встановлено)
- Flat cascade замість вкладених try/except
- Безпечніший junk-фільтр зображень (перевіряє ім'я файлу, не весь URL)
- WebDriverWait для Selenium (чекає на динамічний контент)
"""

import os
import re
import glob
import logging
from typing import Optional
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

# Markdown: PyYAML (для front matter extraction)
try:
    import yaml
except ImportError:
    yaml = None


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


def extract_text_from_pdfs(pdf_paths: list) -> str:
    """
    Каскадне витягнення тексту з КІЛЬКОХ PDF файлів.
    Дзеркалює патерн extract_text_from_urls(): список входів → per-file обробка → конкатенація.
    """
    if not pdf_paths:
        return "[ПОМИЛКА] Список PDF файлів порожній."

    combined_parts = []

    for pdf_path in pdf_paths:
        pdf_path = pdf_path.strip()
        if not pdf_path:
            continue

        print(f"\n⏳ Обробка PDF: {pdf_path}")
        page_text = extract_text_from_pdf(pdf_path)
        filename = os.path.basename(pdf_path)
        combined_parts.append(f"\n--- Джерело: {filename} ---\n{page_text}")

    if not combined_parts:
        return "[ПОМИЛКА] Жоден PDF не дав результату."

    result = "\n".join(combined_parts)
    print(f"\n📊 Підсумок: оброблено {len(pdf_paths)} PDF, загалом {len(result)} символів.")
    return result


# =====================================================================
# 📝 MARKDOWN EXTRACTION
# =====================================================================
# Контракт дзеркалює PDF/URL парсери:
# - extract_text_from_md()     → один файл
# - extract_text_from_md_dir() → рекурсивний batch з маркерами джерел
#
# Markdown — вже структурований текст, каскад методів не потрібен.
# Критичні точки: front matter extraction, syntax normalization,
# table preservation (LLM читає pipe tables нативно).
# =====================================================================

# Файли, які за замовчуванням виключаються з рекурсивного сканування
DEFAULT_MD_EXCLUDES = [
    'README.md', 'CHANGELOG.md', 'LICENSE.md', 'CONTRIBUTING.md',
    'CODE_OF_CONDUCT.md', 'SECURITY.md',
]

# Regex для YAML front matter: --- на початку файлу ... ---
_FRONT_MATTER_RE = re.compile(
    r'\A---[ \t]*\n(.*?\n)---[ \t]*\n',
    re.DOTALL
)

# Markdown syntax patterns для нормалізації
_MD_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
_MD_BOLD_RE = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')
_MD_ITALIC_RE = re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)')
_MD_STRIKE_RE = re.compile(r'~~(.+?)~~')
_MD_CODE_INLINE_RE = re.compile(r'`([^`]+)`')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_MD_CODE_BLOCK_RE = re.compile(r'```[\w]*\n(.*?)```', re.DOTALL)
_MD_BLOCKQUOTE_RE = re.compile(r'^>\s?', re.MULTILINE)
_MD_HR_RE = re.compile(r'^[-*_]{3,}\s*$', re.MULTILINE)


def _extract_front_matter(raw_text: str) -> tuple[Optional[dict], str]:
    """
    Витягує YAML front matter з початку MD-файлу.
    Defensive: якщо YAML не парситься або PyYAML відсутній — повертає None без crash.
    
    Returns:
        (metadata_dict | None, body_text_without_front_matter)
    """
    match = _FRONT_MATTER_RE.match(raw_text)
    if not match:
        return None, raw_text

    yaml_block = match.group(1)
    body = raw_text[match.end():]

    if yaml is None:
        logger.warning("PyYAML не встановлено — front matter буде проігноровано.")
        return None, body

    try:
        metadata = yaml.safe_load(yaml_block)
        if not isinstance(metadata, dict):
            # YAML парситься, але це не dict (наприклад, просто рядок)
            logger.warning(f"Front matter не є dict (тип: {type(metadata).__name__}), ігноруємо.")
            return None, body
        return metadata, body
    except yaml.YAMLError as e:
        logger.warning(f"Невалідний YAML front matter: {e}")
        return None, body


def _format_front_matter_prefix(metadata: dict) -> str:
    """
    Форматує front matter як структурований текстовий блок.
    Інжектується на початку raw_source_text — дає tech_specs_analyst безкоштовний контекст.
    """
    lines = ["--- Front Matter Metadata ---"]
    # Пріоритетні ключі (якщо є — виводимо першими)
    priority_keys = ['title', 'brand', 'category', 'model', 'sku', 'tags']
    seen = set()
    for key in priority_keys:
        if key in metadata:
            val = metadata[key]
            # tags/list → comma-separated
            if isinstance(val, list):
                val = ', '.join(str(v) for v in val)
            lines.append(f"{key.capitalize()}: {val}")
            seen.add(key)

    # Решта ключів (алфавітно)
    for key in sorted(metadata.keys()):
        if key not in seen:
            val = metadata[key]
            if isinstance(val, list):
                val = ', '.join(str(v) for v in val)
            lines.append(f"{key.capitalize()}: {val}")

    lines.append("--- End Front Matter ---\n")
    return "\n".join(lines)


def _normalize_markdown(body: str) -> str:
    """
    Конвертує Markdown-синтаксис у LLM-friendly plain text.
    
    Принципи:
    - Заголовки → рівневі маркери (аналітик бачить ієрархію)
    - Таблиці → залишаємо as-is (LLM парсить pipe tables нативно)
    - Bold/italic/strike → strip синтаксис, зберегти текст
    - Посилання → "text (url)"
    - Code blocks → зберегти вміст, прибрати огорожу
    """
    text = body

    # 1. Code blocks (до інших замін, щоб не зачіпати вміст блоків)
    text = _MD_CODE_BLOCK_RE.sub(r'\1', text)

    # 2. Зображення → MAS Protocol маркер [OFFICIAL_IMAGE: ...]
    #    (у поточному сценарії зображень немає, але підтримка на майбутнє)
    def _image_to_marker(m):
        alt = m.group(1).strip() or 'Product Image'
        url = m.group(2).strip()
        return f"\n[OFFICIAL_IMAGE: url='{url}', alt='{alt}']\n"
    text = _MD_IMAGE_RE.sub(_image_to_marker, text)

    # 3. Посилання → "text (url)"
    text = _MD_LINK_RE.sub(r'\1 (\2)', text)

    # 4. Заголовки → рівневі маркери
    def _heading_to_marker(m):
        level = len(m.group(1))
        title = m.group(2).strip()
        return f"\n=== HEADING LEVEL {level}: {title} ===\n"
    text = _MD_HEADING_RE.sub(_heading_to_marker, text)

    # 5. Bold / Italic / Strikethrough → plain text
    text = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_STRIKE_RE.sub(r'\1', text)

    # 6. Inline code → plain text
    text = _MD_CODE_INLINE_RE.sub(r'\1', text)

    # 7. Blockquotes → strip '>' prefix
    text = _MD_BLOCKQUOTE_RE.sub('', text)

    # 8. Horizontal rules → visual separator
    text = _MD_HR_RE.sub('\n---\n', text)

    # 9. Нормалізуємо зайві порожні рядки (max 2 підряд)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_text_from_md(md_path: str) -> str:
    """
    Витягнення тексту з одного Markdown файлу.
    
    Pipeline:
    1. Validate & read UTF-8
    2. Extract YAML front matter (якщо є) → structured prefix
    3. Normalize Markdown syntax → LLM-friendly plain text
    4. Concatenate prefix + body
    """
    if not os.path.isfile(md_path):
        return f"[ПОМИЛКА] Файл не знайдено: {md_path}"

    file_size_kb = os.path.getsize(md_path) / 1024
    print(f"\n📝 MD: {os.path.basename(md_path)} ({file_size_kb:.1f} KB)")

    # --- Read ---
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
    except UnicodeDecodeError:
        # Fallback для файлів без BOM або у Windows-кодуванні
        try:
            with open(md_path, 'r', encoding='utf-8-sig') as f:
                raw_content = f.read()
        except Exception as e:
            return f"[ПОМИЛКА] Не вдалося прочитати MD файл ({e}): {md_path}"

    if not raw_content.strip():
        return f"[ПОМИЛКА] MD файл порожній: {md_path}"

    # --- Front Matter ---
    metadata, body = _extract_front_matter(raw_content)

    parts = []
    if metadata:
        prefix = _format_front_matter_prefix(metadata)
        parts.append(prefix)
        fm_keys = list(metadata.keys())
        print(f"   📋 Front matter знайдено: {', '.join(fm_keys)}")
    else:
        print("   ℹ️ Front matter відсутній.")

    # --- Normalize ---
    normalized = _normalize_markdown(body)
    parts.append(normalized)

    result = "\n".join(parts)
    print(f"   ✅ Успішно — {len(result)} символів.")
    return result


def extract_text_from_md_dir(
    dir_path: str,
    exclude_patterns: Optional[list] = None
) -> str:
    """
    Рекурсивне витягнення тексту з директорії Markdown файлів.
    Дзеркалює патерн extract_text_from_pdfs(): per-file обробка → конкатенація з маркерами джерел.
    
    Args:
        dir_path: Шлях до кореневої директорії
        exclude_patterns: Список glob-паттернів або імен файлів для виключення.
                          За замовчуванням: README.md, CHANGELOG.md, LICENSE.md і т.д.
    """
    if not os.path.isdir(dir_path):
        return f"[ПОМИЛКА] Директорію не знайдено: {dir_path}"

    # Збираємо всі .md файли рекурсивно
    pattern = os.path.join(dir_path, '**', '*.md')
    all_md_files = glob.glob(pattern, recursive=True)

    if not all_md_files:
        return f"[ПОМИЛКА] У директорії не знайдено .md файлів: {dir_path}"

    # Формуємо exclude set
    excludes = set(exclude_patterns or DEFAULT_MD_EXCLUDES)

    # Фільтрація: виключаємо за ім'ям файлу або за glob-паттерном
    filtered_files = []
    for filepath in all_md_files:
        filename = os.path.basename(filepath)
        if filename in excludes:
            print(f"   ⏩ Пропущено (exclude): {filename}")
            continue
        # Додаткова перевірка: node_modules, .git, __pycache__
        rel_path = os.path.relpath(filepath, dir_path)
        skip_dirs = {'node_modules', '.git', '__pycache__', '.venv', 'venv'}
        if any(part in skip_dirs for part in rel_path.split(os.sep)):
            print(f"   ⏩ Пропущено (системна директорія): {rel_path}")
            continue
        filtered_files.append(filepath)

    if not filtered_files:
        return f"[ПОМИЛКА] Усі .md файли виключено фільтрами: {dir_path}"

    # Сортуємо для детермінованого порядку
    filtered_files.sort()

    print(f"\n📂 Знайдено {len(filtered_files)} MD файлів у {dir_path}")

    combined_parts = []
    for md_path in filtered_files:
        rel_name = os.path.relpath(md_path, dir_path)
        print(f"\n⏳ Обробка MD: {rel_name}")
        page_text = extract_text_from_md(md_path)
        combined_parts.append(f"\n--- Джерело: {rel_name} ---\n{page_text}")

    if not combined_parts:
        return "[ПОМИЛКА] Жоден MD файл не дав результату."

    result = "\n".join(combined_parts)
    print(f"\n📊 Підсумок: оброблено {len(filtered_files)} MD, загалом {len(result)} символів.")
    return result


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