---
paths:
  - "src/content_generator/tools/**/*.py"
---

# Tools & Parsers Rules

- Each `BaseTool` subclass handles exactly ONE operation (Single Responsibility)
- Always define `args_schema` with a Pydantic `BaseModel`
- Flat scraping cascade: list of methods iterated, not nested try/except
- PDF: PyPDF2 → Gemini fallback. Threshold: `MIN_PDF_TEXT_LENGTH = 100`
- Markdown: preserve pipe tables (LLMs read them natively), strip formatting syntax
- Images → `[OFFICIAL_IMAGE: url='...', alt='...']` markers — never embed base64
- Lazy imports for heavy deps (Selenium, google.generativeai)
- Logging: `logger` for errors, `print()` with emoji for user-facing progress
