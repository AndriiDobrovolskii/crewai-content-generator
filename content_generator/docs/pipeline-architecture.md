# Pipeline Architecture

## Two-Phase Execution Model

### Phase 1: Core Content Crew (`ECommerceContentCrew`)

Sequential pipeline with 6 singleton agents and explicit context chaining:

```plaintext
url_discovery → content_extraction → tech_specs_extraction → seo_strategy → copywriting → quality_assurance → html_integration
       ↑                ↑                    ↑                      ↑              ↑                 ↑                ↑
  web_researcher   web_researcher    tech_specs_analyst      seo_strategist    copywriter       editor_qa    frontend_developer
```

Context chain (each task depends on upstream output):

- `content_extraction` ← `url_discovery`
- `tech_specs_extraction` ← `content_extraction` (if auto-search; else uses `raw_source_text`)
- `seo_strategy` ← `tech_specs`
- `copywriting` ← `tech_specs` + `seo_strategy`
- `quality_assurance` ← `tech_specs` + `copywriting`
- `html_integration` ← `tech_specs` + `qa`

Human-in-the-loop stops: `url_discovery` and `content_extraction` have `human_input=True`.

### Phase 2: Localization Crew (`LocalizationCrew`)

One parameterized crew per target language:

- Single agent: `localizer_generic`
- Market rules injected via `{market_rules}` from `MARKET_RULES` dict
- US market gets `USMeasurementCalculatorTool` automatically

### Ukrainian-First Pipeline

1. Ukrainian is ALWAYS generated first for every site
2. If `ua_is_production=True` (UA stores): Ukrainian output IS the production file
3. If `ua_is_production=False` (non-UA stores): Ukrainian output is `REVIEW_Ukrainian_*.html` (internal QA artifact)
4. Then remaining languages from `SITES_CONFIG[site]["languages"]` are generated sequentially

## LLM Routing

## Model Configuration

| Role | Default Model | Override Env Var | Rationale |
| ------ | --------------- | ------------------ | ----------- |
| Researcher | gpt-4o-mini | `RESEARCHER_MODEL` | Cheap, fast for search |
| Analyst | gemini-1.5-pro | `ANALYST_MODEL` | Large context for JSON extraction |
| Writer/SEO/QA | gpt-4o | `WRITER_MODEL` | High accuracy for creative + analytical |
| Frontend | gpt-4o | `FRONTEND_MODEL` | Precise HTML generation |
| Localizer | gpt-4o | `LOCALIZER_MODEL` | Nuanced language handling |

## Data Sources (main.py menu)

1. Raw text paste (manual input)
2. URL(s) — comma-separated, scraped via flat cascade
3. PDF file(s) — PyPDF2 → Gemini fallback
4. Auto search (URL discovery agent finds sources)
5. Single Markdown file
6. Markdown directory (recursive with exclude patterns)

## Pydantic Output Contracts

| Schema | Producer | Consumer | Purpose |
| -------- | ---------- | ---------- | --------- |
| `TechSpecsOutput` | tech_specs_analyst | copywriter, QA, frontend | Ground truth for all specs |
| `QAVerdict` | editor_qa | html_integration, main.py | APPROVED/REJECTED + checklist |
| `SEOBriefOutput` | seo_strategist | copywriter | Keywords, meta tags, H2/H3 outline |

## Filament Detection

`_is_filament()` checks product name for keywords (pla, petg, filament, spool, etc.).
If detected, additional material specs are required: Density, Melt Flow Index, Impact Strength, Heat Deflection, Diameter Tolerance.
