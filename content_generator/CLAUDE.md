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
├── crew.py              # ECommerceContentCrew, LocalizationCrew, SEOMetadataCrew (v2),
│                        # Pydantic schemas (TechSpecsOutput, QAVerdict, SEOBriefOutput,
│                        # ImageStoryboard, SEOMetadataBundle), SITES_CONFIG,
│                        # CTA_TEMPLATES, MARKET_RULES, run_seo_metadata_post_hook
├── config/
│   ├── agents.yaml      # 8 agent identities: web_researcher, tech_specs_analyst,
│   │                    # seo_strategist, copywriter, editor_qa,
│   │                    # image_intelligence_analyst (v2), frontend_developer,
│   │                    # localizer_generic, seo_metadata_extractor (v2)
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
- Pydantic output contracts for ALL inter-agent data (`TechSpecsOutput`,
  `QAVerdict`, `SEOBriefOutput`, `ImageStoryboard`, `SEOMetadataBundle`)
- One `localizer_generic` + `MARKET_RULES` dict — do NOT create per-market agents
- Flat scraping cascade (list of methods) — no nested try/except
- **CMS owns the Product schema.** Description body MUST NOT emit
  `itemtype="https://schema.org/Product"`. Safe schemas in body:
  PropertyValue (on spec rows), FAQPage, HowTo.
- Spec rows use `<th scope="row" itemprop="name">` — combines WCAG 1.3.1
  with Schema.org microdata. NEVER `<td itemprop="name">`.
- `<strong>` vs `<b>` are distinct: `<strong>` carries semantic importance
  (brands, USPs only, max 2-3 per page); `<b>` is typographic accent for
  inline metrics (max 2-3 per paragraph).
- First image is LCP candidate — `loading="eager"` (no attribute). All
  others MUST be `loading="lazy"`.
- Every `<img>` MUST be preceded by a contextual lead-in `<p>`. No orphan
  images, no consecutive images.
- BLOCKQUOTE_TIP is CONDITIONAL — emitted only if source has
  practitioner-grade tip content. Never fabricated.
- SEO metadata is a **separate artifact** (`seo_metadata.json`) produced
  by `run_seo_metadata_post_hook` AFTER all language HTML files are written.

## Code Style

- Python 3.10+, type hints on all function signatures
- Comments/prints in Ukrainian, docstrings in Ukrainian or English
- `logging.getLogger(__name__)` for errors — `print()` with emoji only for user progress
- CrewAI tools extend `BaseTool` with typed `args_schema`
- Single Responsibility: one API call per `BaseTool` subclass

## Content Pipeline (7 core + 1 conditional sections)

1. Snippet-Ready Hook (40-75 words, **plain `<p>`**, NO Product wrapper)
2. Key Specs Quick Table (3-4 rows, PropertyValue microdata via `<th scope="row" itemprop="name">`)
3. Feature Deep-Dive (350-700 words, H2/H3, interleaved storyboard images)
4. Applications List (H2 + `<ul>`, 3-5 items)
5. Expert Verdict (80-120 words, `EXPERT_INSIGHT_BLOCK`)
6. **CONDITIONAL** — Technical Tip (60-100 words, `BLOCKQUOTE_TIP`).
   Emitted only if source has practitioner-grade tip material; never fabricated.
7. Full Technical Specifications (ALL specs, zero omissions, `SPECS_TABLE_SECTION`,
   PropertyValue microdata)
8. **CONDITIONAL** — HowTo (numbered procedure from Support_Data.troubleshooting)
9. **CONDITIONAL** — FAQ (FAQPage from Support_Data.faqs)
10. CTA (single `<p class="cta">` paragraph, brand-rep sentence if applicable)

**Architectural constraint (v2):** The description body NEVER contains
`itemtype="https://schema.org/Product"`. The OpenCart page template emits a
complete schema.org/Product entity via page-level JSON-LD — a second Product
inside the body creates a duplicate-entity GSC error.

## Environment (.env)

Required: `OPENAI_API_KEY`, `SERPER_API_KEY`
Optional: `GEMINI_API_KEY`, `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`
Overrides: `RESEARCHER_MODEL`, `ANALYST_MODEL`, `WRITER_MODEL`, `FRONTEND_MODEL`, `LOCALIZER_MODEL`

## Compaction Rules

When compacting, ALWAYS preserve: list of modified files, Pydantic schema changes, YAML config edits, SITES_CONFIG mutations, and any failing test output.

## Do NOT

- Put execution rules in agent backstories
- Create separate agents per market/language
- Emit `itemtype="https://schema.org/Product"` in the description body
  (page-level JSON-LD already covers this — duplicates break GSC rich results)
- Emit `<div class="product-desc-wrap">` wrapper
  (CMS handles the container; the wrapper is a v1 artifact)
- Use `<td itemprop="name">` for spec rows
  (must be `<th scope="row" itemprop="name">` for WCAG + microdata)
- Use `<br>` tags for spacing (use `<hr>` only after `</section>`)
- Fabricate a Technical Tip section to fill the slot
  (Tip is conditional; skip when source has no practitioner content)
- Insert orphan images (every `<img>` needs a preceding lead-in `<p>`)
- Use `loading="lazy"` on the first image (LCP regression)
- Use `SerperDevTool` — DataForSEO tools replace it
- Omit `context` attribute on tasks
- Use nested try/except for scraping
- Guess specs — flag ambiguities instead
