# 🛠️ Інструкція із запуску GEO Content Generation System

## 1. Структура проєкту

Код очікує таку структуру папок:

```
your-project/
├── .env                          ← API ключі
├── src/
│   └── content_generator/
│       ├── __init__.py           ← порожній файл
│       ├── crew.py               ← оркестрація агентів
│       ├── main.py               ← точка входу
│       ├── config/
│       │   ├── agents.yaml       ← конфіг агентів
│       │   └── tasks.yaml        ← конфіг задач
│       └── tools/
│           ├── __init__.py       ← порожній файл
│           ├── custom_tools.py   ← Similarity + US Converter
│           └── parsers.py        ← PDF + URL парсинг
└── output/                       ← створюється автоматично
```

## 2. Створення структури (з нуля)

```bash
# Створити папки
mkdir -p src/content_generator/config
mkdir -p src/content_generator/tools
mkdir -p output

# Створити __init__.py (порожні)
touch src/content_generator/__init__.py
touch src/content_generator/tools/__init__.py

# Скопіювати файли (якщо завантажили з Claude)
cp agents.yaml src/content_generator/config/
cp tasks.yaml  src/content_generator/config/
cp crew.py     src/content_generator/
cp main.py     src/content_generator/
cp custom_tools.py src/content_generator/tools/
cp parsers.py      src/content_generator/tools/
```

## 3. Встановлення залежностей

```bash
pip install crewai crewai-tools
pip install python-dotenv pydantic pyyaml
pip install requests beautifulsoup4
pip install PyPDF2
pip install selenium webdriver-manager
pip install google-search-results   # для SerperDevTool
```

Або одним рядком:
```bash
pip install crewai crewai-tools python-dotenv pydantic pyyaml requests beautifulsoup4 PyPDF2 selenium webdriver-manager google-search-results
```

## 4. Файл .env (API ключі)

Створіть `.env` у кореневій папці проєкту:

```env
# === ОБОВ'ЯЗКОВІ ===
OPENAI_API_KEY=sk-ваш-ключ-openai
SERPER_API_KEY=ваш-ключ-serper          # https://serper.dev (безкоштовний план — 2500 запитів)

# === ОПЦІОНАЛЬНІ (для Google Gemini як аналітик) ===
GEMINI_API_KEY=ваш-ключ-gemini          # https://aistudio.google.com/apikey

# === ОПЦІОНАЛЬНІ (override моделей) ===
# RESEARCHER_MODEL=gpt-4o-mini           # за замовчуванням
# ANALYST_MODEL=gemini/gemini-1.5-pro    # за замовчуванням
# WRITER_MODEL=gpt-4o                    # за замовчуванням
# FRONTEND_MODEL=gpt-4o                  # за замовчуванням
# LOCALIZER_MODEL=gpt-4o                 # за замовчуванням
```

### Де отримати ключі:
- **OpenAI**: https://platform.openai.com/api-keys
- **Serper** (пошук Google): https://serper.dev — безкоштовний план на 2500 запитів
- **Gemini** (опціонально): https://aistudio.google.com/apikey

> ⚠️ Якщо не хочете Gemini, змініть ANALYST_MODEL на gpt-4o:
> ```env
> ANALYST_MODEL=gpt-4o
> ```

## 5. Запуск

```bash
cd your-project

# Варіант A: напряму через Python
python src/content_generator/main.py

# Варіант B: якщо використовуєте uv
uv run src/content_generator/main.py
```

## 6. Що відбувається після запуску

Система покаже інтерактивне меню:

```
============================================================
🛠️  СИСТЕМА ГЕНЕРАЦІЇ GEO-КОНТЕНТУ OPENCART  🛠️
============================================================
Введіть назву продукту (напр. Creality K1 Max): _

Доступні сайти:
  1. 3DDevice (Ukraine) [🟢 UA=prod]
  2. 3DPrinter (Ukraine) [🟢 UA=prod]
  3. 3DScanner (Ukraine) [🟢 UA=prod]
  4. Center 3D Print (Poland) [🔵 UA=review]
  5. EXPERT3D (Spain) [🔵 UA=review]
  6. Expert-3DPrinter (USA) [🔵 UA=review]
Оберіть сайт: _

Яке джерело даних використаємо?
  1. Вставити готовий текст
  2. Вказати URL-адреси (через кому)
  3. Завантажити PDF (вказати шлях)
  4. Автоматичний пошук (агент шукатиме в Google)
Оберіть варіант (1-4): _
```

### Далі система працює у двох фазах:

**Фаза 1** (англійська база):
1. Аналіз техспек → структурований JSON
2. SEO-стратегія → бриф з H2/H3
3. Копірайтинг → англійський текст
4. QA перевірка → APPROVED/REJECTED
5. HTML верстка → OpenCart-ready HTML

**Фаза 2** (локалізація):
1. 📋 Крок 1: Українська версія (REVIEW) — завжди першою
2. 🌍 Крок 2: Решта мов (залежно від магазину)

## 7. Результат

У папці `output/` з'явиться:

```
output/
└── 3DDevice-Creality_K1_Max-15-03-2026-14-30/
    ├── ..._BASE_English.html         ← Англійська база
    ├── ..._Ukrainian.html            ← UA (review + production для UA магазинів)
    ├── ..._English.html              ← Англійська локалізована
    ├── ..._Russian.html              ← Російська
    └── ..._3DDevice-Creality_K1_Max-15-03-2026-14-30.zip
```

## 8. Типові проблеми

| Проблема | Рішення |
|---|---|
| `ModuleNotFoundError: content_generator` | Запускайте з кореня проєкту: `python src/content_generator/main.py` |
| `SERPER_API_KEY not found` | Перевірте `.env` файл і чи він у кореневій папці |
| `RateLimitError` від OpenAI | Зменшіть кількість паралельних задач або використайте дешевшу модель |
| Selenium crash | Переконайтесь що Chrome встановлено: `google-chrome --version` |
| PDF повертає порожній текст | Ймовірно скан. Потрібен OCR: `pip install pytesseract` |
| `KeyError: 'localizer_generic'` | Переконайтесь що використовуєте НОВІ agents.yaml та tasks.yaml |

## 9. Режим тренування

Якщо хочете навчити систему на прикладах з фідбеком:

```bash
python src/content_generator/main.py
# Обрати: 2. 🏋️ TRAINING MODE
```

⚠️ Тренування вимагає статичного тексту (опції 1-3), НЕ автопошук.