# GEO Content Generator — CrewAI Multi-Agent System

E-commerce product content pipeline for 3D printing/scanning equipment.
Two-phase CrewAI orchestration: Phase 1 (Core Crew) → English HTML, Phase 2 (Localization Crew) → per-market adaptation.
Ukrainian always generated first; `ua_is_production` flag controls production vs review.

## Build & Run

```bash
uv run src/content_generator/main.py        # Primary (Windows + uv)
python src/content_generator/main.py         # Alternative
uv add <package>                             # Add dependency
```

## Project Structure

```Plaintext
src/content_generator/
├── main.py              # Entry point, menu, orchestration
├── crew.py              # Crews, Pydantic schemas, SITES_CONFIG, CTA_TEMPLATES, MARKET_RULES
├── config/
│   ├── agents.yaml      # Agent identities ONLY (role, goal, backstory)
│   └── tasks.yaml       # Task execution rules, expected_output, context chains
└── tools/
    ├── custom_tools.py  # ContentSimilarityTool, USMeasurementCalculatorTool
    └── parsers.py       # PDF/URL/Markdown extraction cascades
```

Output: `output/<ProductName>_<Site>_<timestamp>/`

## Detailed Documentation

Read the relevant doc when working on specific areas:

- Pipeline architecture: @docs/pipeline-architecture.md
- HTML marker protocol: @docs/marker-protocol.md
- Store config reference: @docs/sites-config.md

## Architecture Invariants

- Singleton agents — never instantiate same agent twice (breaks CrewAI memory)
- Explicit `context` on every task — implicit ordering causes silent data loss
- Backstories = identity only; execution rules go in tasks.yaml
- Pydantic output contracts for ALL inter-agent data (`TechSpecsOutput`, `QAVerdict`, `SEOBriefOutput`)
- One `localizer_generic` + `MARKET_RULES` dict — do NOT create per-market agents
- Flat scraping cascade (list of methods) — no nested try/except
- CSS classes must be product-agnostic (`product-desc-wrap`, NOT `premium-bambu-desc`)

## Code Style

- Python 3.10+, type hints on all function signatures
- Comments/prints in Ukrainian, docstrings in Ukrainian or English
- `logging.getLogger(__name__)` for errors — `print()` with emoji only for user progress
- CrewAI tools extend `BaseTool` with typed `args_schema`
- Single Responsibility: one API call per `BaseTool` subclass

## Content Pipeline (8 Mandatory Sections)

1. Snippet-Ready Hook (40-75 words, `HOOK_SCHEMA_WRAP`)
2. Key Specs Quick Table (3-4 rows)
3. Feature Deep-Dive (350-700 words, H2/H3)
4. Applications List (H2 + `<ul>`, 3-5 items)
5. Expert Verdict (80-120 words, `EXPERT_INSIGHT_BLOCK`)
6. Technical Tip (60-100 words, `BLOCKQUOTE_TIP`)
7. Full Technical Specifications (ALL specs, zero omissions, `SPECS_TABLE_SECTION`)
8. CTA (`CTA_SECTION`)

## Environment (.env)

Required: `OPENAI_API_KEY`, `SERPER_API_KEY`
Optional: `GEMINI_API_KEY`, `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`
Overrides: `RESEARCHER_MODEL`, `ANALYST_MODEL`, `WRITER_MODEL`, `FRONTEND_MODEL`, `LOCALIZER_MODEL`

## Compaction Rules

When compacting, ALWAYS preserve: list of modified files, Pydantic schema changes, YAML config edits, SITES_CONFIG mutations, and any failing test output.

## Do NOT

- Put execution rules in agent backstories
- Create separate agents per market/language
- Use inline CSS or brand-specific CSS class names in HTML
- Use `SerperDevTool` — DataForSEO tools replace it
- Omit `context` attribute on tasks
- Use nested try/except for scraping
- Guess specs — flag ambiguities instead
