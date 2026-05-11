# 🚀 DEPLOYMENT GUIDE — Cost Tracker Implementation

Покроковий план застосування. Виконуй **строго по порядку** — кожен крок має
verification gate перед переходом до наступного.

---

## 📦 Файли в цьому release

| Файл | Призначення | Куди копіювати |
|---|---|---|
| `pricing.yaml` | Stage 1 — pricing config | `src/content_generator/config/pricing.yaml` |
| `cost_tracker.py` | Stage 2 — main module | `src/content_generator/tools/cost_tracker.py` |
| `test_cost_tracker.py` | Stage 2 — unit tests | `tests/unit/test_cost_tracker.py` |
| `STAGE_0_PATCHES.md` | Stage 0 — config corrections | apply patches to `crew.py` + `docs/sites-config.md` |
| `STAGE_3_PATCHES.md` | Stage 3 — pipeline integration | apply patches to `pipeline_runner.py` |

---

## 🔢 КРОКИ — у строгій послідовності

### Step 1 · Apply STAGE_0_PATCHES.md

Чотири незалежних патчі у `crew.py` + `docs/sites-config.md`. Деталі у `STAGE_0_PATCHES.md`.

**Verification gate:**
```bash
grep -A 3 "Center 3D Print\|EXPERT3D" src/content_generator/crew.py | grep ua_is_production
# Очікую: True для обох

grep "ANALYST_MODEL" src/content_generator/crew.py
# Очікую: "gpt-4o" як default

uv run pytest tests/ -v
# Очікую: усі тести зелені
```

🛑 **Не йди далі якщо не зелене.** Якщо є тести які захардкодили `False` для C3D або EXPERT3D — оновити їх.

---

### Step 2 · Copy `pricing.yaml`

```bash
cp pricing.yaml src/content_generator/config/pricing.yaml
```

**Verification gate:**
```bash
ls -la src/content_generator/config/pricing.yaml
# Очікую: файл існує
```

⚠️ **Перед production**: відкрий `pricing.yaml` і верифікуй тарифи проти https://openai.com/api/pricing/. Стандартні значення можуть бути застарілими.

---

### Step 3 · Copy `cost_tracker.py`

```bash
cp cost_tracker.py src/content_generator/tools/cost_tracker.py
```

**Verification gate:**
```bash
uv run python -c "from content_generator.tools.cost_tracker import PipelineCostTracker; t = PipelineCostTracker(); print(list(t._pricing_models.keys()))"
# Очікую: ['gpt-4o', 'gpt-4o-mini', 'text-embedding-3-small', 'gemini-1.5-pro']
```

🛑 Якщо raise FileNotFoundError → перевір що pricing.yaml дійсно у `src/content_generator/config/`.

---

### Step 4 · Copy `test_cost_tracker.py`

```bash
mkdir -p tests/unit
cp test_cost_tracker.py tests/unit/test_cost_tracker.py
```

**Verification gate:**
```bash
uv run pytest tests/unit/test_cost_tracker.py -v
# Очікую: 22 passed in <1s
```

🛑 **Не йди далі якщо менше 22.**

---

### Step 5 · Apply STAGE_3_PATCHES.md

7 точкових патчів у `pipeline_runner.py`. Усі — strictly additive. Деталі у `STAGE_3_PATCHES.md`.

**Verification gate:**
```bash
# Імпорт без помилок
uv run python -c "from content_generator.pipeline_runner import run_pipeline_headless; print('OK')"
# Очікую: OK

# Регресія усього test suite
uv run pytest tests/ -v
# Очікую: усі тести зелені (включно з 22 новими test_cost_tracker)
```

🛑 Якщо існуючі тести впали — швидше за все patch створив дубльоване визначення; перевір diff'ом.

---

### Step 6 · Smoke test — реальний pipeline run

Запусти на найдешевшому магазині (3DDevice = 4 kickoff-и):

```bash
uv run src/content_generator/main.py
# - Обери 3DDevice
# - Будь-який спосіб входу даних (text паста — найшвидше)
# - Запусти
```

**Очікувана поведінка:**
- У console вкінці з'являється pretty cost report з emoji 💰
- У `output/<folder>/` з'являється `cost_report.json`
- `result["files"]["Cost Report"]` містить шлях до JSON

**Verification gate:**
```bash
# JSON валідний і має очікувану структуру
python -c "
import json
import glob
path = sorted(glob.glob('output/3DDevice*/cost_report.json'))[-1]
data = json.load(open(path, encoding='utf-8'))
assert 'kickoffs' in data
assert 'total_cost_usd' in data
assert float(data['total_cost_usd']) > 0
print(f'Total: \${data[\"total_cost_usd\"]} | Kickoffs: {len(data[\"kickoffs\"])}')
"
# Очікую: щось типу "Total: $0.0234 | Kickoffs: 4"
```

---

### Step 7 · Manual sanity check

1. Відкрий https://platform.openai.com/usage
2. Подивись скільки витрачено за останню годину
3. Порівняй з `total_cost_usd` у JSON

**Очікую:** ±10% розходження. Більше — bug у tracker або pricing.yaml застарілий.

---

## 🧯 Troubleshooting

### Symptom: `unknown_model: True` у JSON для kickoff'у
**Причина:** Модель у коді ≠ ключ у pricing.yaml
**Fix:** Додай модель до `pricing.yaml` АБО виправ `primary_model` argument у patch'і

### Symptom: `total_cost_usd: "0"` для kickoff'у
**Причина:** `crew.usage_metrics` повернуло None або без полів
**Fix:** Перевір CrewAI version (`pip show crewai`). Старіші версії можуть не мати `usage_metrics` як атрибут

### Symptom: tests fail з ImportError
**Причина:** `tests/unit/__init__.py` відсутній
**Fix:** `touch tests/__init__.py tests/unit/__init__.py`

### Symptom: patch 3.x не вставляється
**Причина:** Whitespace mismatch (tabs vs spaces, або CRLF vs LF)
**Fix:** Знайди достатньо унікальний фрагмент 5-7 рядків і вручну skopiюй з patch файлу

---

## 📊 Що ти отримаєш у звіті

Приклад `cost_report.json` для 3DDevice (4 kickoff-и):

```json
{
  "timestamp_utc": "2026-05-10T12:34:56+00:00",
  "product_name": "Bambu A1 Mini",
  "site": "3DDevice",
  "kickoffs": [
    {
      "crew_label": "Phase 1: Core",
      "primary_model": "gpt-4o",
      "tasks": [...],
      "aggregate_input_tokens": 12450,
      "aggregate_output_tokens": 8200,
      "aggregate_cost_usd": "0.113125"
    },
    {"crew_label": "Phase 2: Ukrainian", "aggregate_cost_usd": "0.024500"},
    {"crew_label": "Phase 2: English",   "aggregate_cost_usd": "0.022100"},
    {"crew_label": "Phase 2: Russian",   "aggregate_cost_usd": "0.024100"}
  ],
  "embeddings": [...],
  "external_apis": [...],
  "total_input_tokens": 38450,
  "total_output_tokens": 19800,
  "total_llm_cost_usd": "0.183825",
  "total_embedding_cost_usd": "0.000018",
  "total_external_api_cost_usd": "0.012000",
  "total_cost_usd": "0.195843"
}
```

І у консолі — pretty taблиця з тими ж даними.

---

## 🔮 Що НЕ включено у цей release (deferred)

| Feature | Чому defer | Куди він підключиться |
|---|---|---|
| Per-LLM-call attribution (Q2 рівень C) | Effort × value не виправдане для старту — рівні (a)+(b) дають 95% інсайту | LiteLLM `success_callback` на etапі 4 |
| Supabase persistence (Q4 d) | Stage 5 — після того як ти запустиш 3-5 продуктів і впевнишся у структурі звіту | Hook у `to_dict()` → `pipeline_runs` table upsert |
| SerperDev call counter | Потребує monkey-patch SerperDevTool — окрема робота | Нова утиліта `tools/api_call_counter.py` + wrap у `web_researcher` agent |
| Повний `STORE_CONTEXT` refactor MARKET_RULES | Path C hotfix покрив immediate problem; повний refactor — separate work-stream | Окрема ітерація після того як cost tracker стабільний у production |

---

## 🎯 Success criteria

✅ Усі 7 verification gates passed
✅ Smoke test на 3DDevice вивів cost_report.json з валідною структурою
✅ Manual sanity check показав ±10% збіг з OpenAI dashboard
✅ Регресія `pytest tests/` повністю зелена (45 існуючих + 22 нових = 67)

При досягненні всіх 4 critically — `cost_tracker` готовий до production.
