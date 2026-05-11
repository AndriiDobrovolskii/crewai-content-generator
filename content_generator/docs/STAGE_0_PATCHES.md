# STAGE 0 — Config Patches (apply BEFORE cost tracker integration)

Чотири незалежних патчі. Кожен safe-applied окремо. Усі — strictly additive
для тих стейтів де поведінка вже коректна.

---

## Patch 0a — `SITES_CONFIG` config corrections

**Файл:** `src/content_generator/crew.py`

### Change 0a.1 — Center 3D Print

Знайди:
```python
    "Center 3D Print": {
        "country": "Poland",
        "languages": ["Polish", "German", "English", "Ukrainian", "Russian"],
        "localizer": "localizer_pl",
        "ua_is_production": False
    },
```

Заміни на:
```python
    "Center 3D Print": {
        "country": "Poland",
        "languages": ["Polish", "German", "English", "Ukrainian", "Russian"],
        "localizer": "localizer_pl",
        "ua_is_production": True
    },
```

### Change 0a.2 — EXPERT3D

Знайди:
```python
    "EXPERT3D": {
        "country": "Spain",
        "languages": ["Spanish (Castilian es-ES)"],
        "localizer": "localizer_es",
        "ua_is_production": False
    },
```

Заміни на:
```python
    "EXPERT3D": {
        "country": "Spain",
        "languages": ["Spanish (Castilian es-ES)", "Ukrainian"],
        "localizer": "localizer_es",
        "ua_is_production": True
    },
```

---

## Patch 0b — `MARKET_RULES["localizer_ua"]` hotfix

**Файл:** `src/content_generator/crew.py`

Знайди:
```python
    "localizer_ua": """
UKRAINIAN MARKET RULES (UA):
- Punctuation: word after colon (:) starts with lowercase, unless a proper noun.
- Logistics: Use Nova Poshta / Ukrposhta for delivery references.
- Audience: Ukrainian engineers, makers, small businesses.
- Terminology: Use professional Ukrainian 3D printing terminology.
- Do NOT default to Russian unless {target_language} explicitly requires it.
""",
```

Заміни на:
```python
    "localizer_ua": """
UKRAINIAN MARKET RULES (UA):
- Punctuation: word after colon (:) starts with lowercase, unless a proper noun.
- Logistics: PRESERVE delivery/carrier references from the source HTML.
  Do NOT substitute or hardcode Ukrainian-only carriers (Nova Poshta, Укрпошта).
  The source HTML already contains store-appropriate logistics from cta_context;
  your job is faithful Ukrainian translation, not market substitution.
- Audience: Ukrainian-speaking engineers, makers, small businesses (regardless of where the store ships from).
- Terminology: Use professional Ukrainian 3D printing terminology.
- Do NOT default to Russian unless {target_language} explicitly requires it.
""",
```

**Чому це критично:** EXPERT3D (Іспанія) і Center 3D Print (Польща) тепер мають
`ua_is_production=True`. Без цього hotfix'у українська версія для них містила б
"Nova Poshta" та "Укрпошта" — що **семантично хибно**, бо ці магазини шиплять з
Валенсії через GLS/Correos/FedEx та з Кракова через DPD/InPost відповідно.

---

## Patch 0c — `analyst_llm` default sync з реальністю

**Файл:** `src/content_generator/crew.py`

Знайди:
```python
analyst_llm = LLM(model=os.getenv("ANALYST_MODEL", "gemini/gemini-1.5-pro"))
```

Заміни на:
```python
analyst_llm = LLM(model=os.getenv("ANALYST_MODEL", "gpt-4o"))
```

**Чому:** Production уже використовує `gpt-4o` (per Q3 confirmation), але default у
коді досі `gemini/gemini-1.5-pro`. Якщо хтось запустить без `.env` — billing йде
на OpenAI, а думаєш що Gemini. Усуваємо config drift.

---

## Patch 0d — Sync `docs/sites-config.md`

**Файл:** `docs/sites-config.md`

Знайди:
```markdown
| Center 3D Print | Poland | Polish, German, English, Ukrainian, Russian | `localizer_pl` | No |
| EXPERT3D | Spain | Spanish (Castilian es-ES) | `localizer_es` | No |
```

Заміни на:
```markdown
| Center 3D Print | Poland | Polish, German, English, Ukrainian, Russian | `localizer_pl` | Yes |
| EXPERT3D | Spain | Spanish (Castilian es-ES), Ukrainian | `localizer_es` | Yes |
```

---

## ✓ Verification команди

```bash
# 0a + 0c
grep -A 3 "Center 3D Print\|EXPERT3D" src/content_generator/crew.py | grep ua_is_production
# Очікую: усі True (для перших трьох UA-stores + Center 3D Print + EXPERT3D)

# 0b
grep -A 1 "Logistics:" src/content_generator/crew.py | grep "localizer_ua" -A 3
# Очікую: "PRESERVE delivery/carrier references..." а НЕ "Use Nova Poshta..."

# 0c
grep "ANALYST_MODEL" src/content_generator/crew.py
# Очікую: "gpt-4o" як default (НЕ gemini/gemini-1.5-pro)

# 0d
grep -E "(Center 3D Print|EXPERT3D)" docs/sites-config.md
# Очікую: Yes у колонці UA Production для обох

# Регресія
uv run pytest tests/ -v
# Очікую: усі тести зелені. Якщо є тести які hardcode False для C3D або EXPERT3D — оновити.
```
