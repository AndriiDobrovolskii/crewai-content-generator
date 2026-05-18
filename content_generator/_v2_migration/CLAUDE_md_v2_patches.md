# CLAUDE.md — v2.0 Documentation Patches

Surgical updates to `content_generator/CLAUDE.md` to reflect the v2 architecture.

---

## PATCH 1 — Replace "Content Pipeline (8 Mandatory Sections)" block

### Find this block:

```markdown
## Content Pipeline (8 Mandatory Sections)

1. Snippet-Ready Hook (40-75 words, `HOOK_SCHEMA_WRAP`)
2. Key Specs Quick Table (3-4 rows)
3. Feature Deep-Dive (350-700 words, H2/H3)
4. Applications List (H2 + `<ul>`, 3-5 items)
5. Expert Verdict (80-120 words, `EXPERT_INSIGHT_BLOCK`)
6. Technical Tip (60-100 words, `BLOCKQUOTE_TIP`)
7. Full Technical Specifications (ALL specs, zero omissions, `SPECS_TABLE_SECTION`)
8. CTA (`CTA_SECTION`)
```

### Replace with:

```markdown
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
```

---

## PATCH 2 — Replace "Architecture Invariants" block (additions only)

### Find this block:

```markdown
## Architecture Invariants

- Singleton agents — never instantiate same agent twice (breaks CrewAI memory)
- Explicit `context` on every task — implicit ordering causes silent data loss
- Backstories = identity only; execution rules go in tasks.yaml
- Pydantic output contracts for ALL inter-agent data (`TechSpecsOutput`, `QAVerdict`, `SEOBriefOutput`)
- One `localizer_generic` + `MARKET_RULES` dict — do NOT create per-market agents
- Flat scraping cascade (list of methods) — no nested try/except
- CSS classes must be product-agnostic (`product-desc-wrap`, NOT `premium-bambu-desc`)
```

### Replace with:

```markdown
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
```

---

## PATCH 3 — Replace "Do NOT" block

### Find this block:

```markdown
## Do NOT

- Put execution rules in agent backstories
- Create separate agents per market/language
- Use inline CSS or brand-specific CSS class names in HTML
- Use `SerperDevTool` — DataForSEO tools replace it
- Omit `context` attribute on tasks
- Use nested try/except for scraping
- Guess specs — flag ambiguities instead
```

### Replace with:

```markdown
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
```

---

## PATCH 4 — Update "Project Structure" diagram (annotation only)

### Find this block:

```markdown
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

### Replace with:

```markdown
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

---

## PATCH 5 — Update pipeline-architecture.md context chain diagram

### Find this block in `docs/pipeline-architecture.md`:

```plaintext
url_discovery → content_extraction → tech_specs_extraction → seo_strategy → copywriting → quality_assurance → html_integration
       ↑                ↑                    ↑                      ↑              ↑                 ↑                ↑
  web_researcher   web_researcher    tech_specs_analyst      seo_strategist    copywriter       editor_qa    frontend_developer
```

### Replace with:

```plaintext
url_discovery → content_extraction → tech_specs_extraction → seo_strategy → copywriting → quality_assurance → image_intelligence → html_integration
       ↑                ↑                    ↑                      ↑              ↑                 ↑                  ↑                       ↑
  web_researcher   web_researcher    tech_specs_analyst      seo_strategist    copywriter       editor_qa     image_intel_analyst       frontend_developer
                                                                                                                  (NEW v2)
```

### Also append to the same file, after the existing "Phase 2" section:

```markdown
### Phase 3: SEO Metadata Post-Hook (v2)

After ALL language HTML files (Phase 1 EN base + Phase 2 localizations) are
written to disk, `run_seo_metadata_post_hook(...)` runs the `SEOMetadataCrew`
once. The crew has a single agent (`seo_metadata_extractor`) and produces a
Pydantic-validated `SEOMetadataBundle` written to `output_dir/seo_metadata.json`.

Inputs:
- `product_name`, `site_name`, `currency_symbol`
- `finalized_html_by_language`: `{iso_code: html_string}` for every language

Per-language output entry:
- `h1`: clean `[Brand] [Model]`
- `meta_title`: ≤55 chars, ends with `| {site_name}`
- `meta_description`: ≤155 chars, includes currency + 1 hard spec,
  ends with localized `Buy now ➔`

Pydantic validators enforce length, ISO code format, CTA arrow presence,
and forbidden-emoji exclusion at write time — not at review time.
```

### Update "Pydantic Output Contracts" table:

```markdown
## Pydantic Output Contracts

| Schema | Producer | Consumer | Purpose |
|---|---|---|---|
| `TechSpecsOutput` | tech_specs_analyst | copywriter, QA, image_intel, frontend | Ground truth for all specs |
| `QAVerdict` | editor_qa | image_intel, html_integration, main.py | APPROVED/REJECTED + checklist |
| `SEOBriefOutput` | seo_strategist | copywriter | Keywords, meta tags, H2/H3 outline |
| `ImageStoryboard` | image_intelligence_analyst | frontend_developer | Per-image: alt, lead-in, anchor, loading strategy, order |
| `SEOMetadataBundle` | seo_metadata_extractor | post-pipeline JSON artifact | Per-language h1/meta_title/meta_description |
```
