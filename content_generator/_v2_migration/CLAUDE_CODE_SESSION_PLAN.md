# Claude Code Session Plan — v2 Architecture Migration

**Goal:** migrate the content generation pipeline from v1 (with Schema.org
Product wrapper in body, mandatory Tip, no image protocol) to v2 (CMS owns
Product schema, conditional Tip, typed ImageStoryboard, SEO metadata
post-hook) so output matches the `holabot-*.html` reference files.

**Operating principle:** sessions are organized by risk. Lower-risk
sessions run first because they are reversible without state corruption.
Critical sessions run only after lower-risk validation passes.

---

## Stage 0 — Pre-flight (one-time, do this first)

Create a working branch and freeze the baseline:

```bash
cd C:\Work\crewAI-content-generator\content_generator
git checkout -b v2-output-alignment
git status   # confirm clean tree before patching

# Run baseline pytest to capture current pass rate
uv run pytest tests/ -v --tb=short > pre_v2_test_baseline.txt 2>&1
```

Verify `pre_v2_test_baseline.txt` shows 45 tests passing (the existing
suite). If any test fails before patching, STOP and fix that first.

---

## Stage 1 — ZERO-RISK: Documentation patches

**Why first:** Markdown changes cannot break the pipeline. Updating docs
before code locks down the architectural intent for every subsequent edit.

**Files:** `CLAUDE.md`, `docs/marker-protocol.md`, `docs/pipeline-architecture.md`

### Session 1.1 — Apply CLAUDE.md patches

```text
Read /mnt/user-data/outputs/CLAUDE_md_v2_patches.md. Apply patches 1-5
to CLAUDE.md verbatim. Use str_replace for each Find/Replace block.
Run `uv run python -c "import content_generator.crew"` to confirm the
module still imports (sanity check on no accidental code touches).
```

### Session 1.2 — Replace marker-protocol.md

```text
Replace content_generator/docs/marker-protocol.md entirely with the
contents of /mnt/user-data/outputs/marker-protocol_v2.md. Do not preserve
any v1 marker references in this file.
```

### Session 1.3 — Update pipeline-architecture.md context diagram

```text
Apply PATCH 5 from /mnt/user-data/outputs/CLAUDE_md_v2_patches.md to
docs/pipeline-architecture.md: update the context chain diagram to
include image_intelligence and append the Phase 3 SEO Metadata Post-Hook
section + update the Pydantic Output Contracts table.
```

**Stage 1 verification:**

```bash
# Doc patches don't break anything — sanity-check imports only
uv run python -c "import content_generator.crew; print('OK')"
uv run pytest tests/ -v --tb=short | tail -5
# Expected: 45 passed (same as baseline)
```

If pass count drops, revert Stage 1 immediately:
```bash
git diff --stat
git checkout -- CLAUDE.md docs/marker-protocol.md docs/pipeline-architecture.md
```

---

## Stage 2 — LOW-RISK: agents.yaml replacement

**Why second:** YAML is consumed at agent instantiation. If a key is
malformed, the error fires at startup, not silently mid-pipeline.

**File:** `src/content_generator/config/agents.yaml`

### Session 2.1 — Replace agents.yaml

```text
Replace src/content_generator/config/agents.yaml entirely with
/mnt/user-data/outputs/agents_v2.yaml. This adds two new agents
(image_intelligence_analyst, seo_metadata_extractor) and updates the
frontend_developer backstory. The other 6 agents are preserved verbatim.

After replacement:
1. Verify YAML parses: uv run python -c "import yaml; yaml.safe_load(open('src/content_generator/config/agents.yaml'))"
2. DO NOT instantiate crews yet — tasks.yaml has not been updated.
```

**Stage 2 verification:**

```bash
uv run python -c "import yaml; print(list(yaml.safe_load(open('src/content_generator/config/agents.yaml')).keys()))"
# Expected output includes:
#   web_researcher, tech_specs_analyst, seo_strategist, copywriter,
#   editor_qa, image_intelligence_analyst, frontend_developer,
#   localizer_generic, seo_metadata_extractor
# (9 agents total — was 7 in v1)
```

If keys are missing or order corrupted, revert:
```bash
git checkout -- src/content_generator/config/agents.yaml
```

---

## Stage 3 — MEDIUM-RISK: Pydantic schemas (crew.py BLOCK 1)

**Why third:** Schemas are pure data validation logic with no I/O.
Failures here surface immediately in unit tests, not in a running pipeline.

**File:** `src/content_generator/crew.py`

### Session 3.1 — Insert BLOCK 1 (new Pydantic schemas)

```text
Read /mnt/user-data/outputs/crew_v2_patches.py. Apply BLOCK 1 to
src/content_generator/crew.py by inserting the ImageStoryboardItem,
ImageStoryboard, SEOMetadataEntry, and SEOMetadataBundle classes
immediately ABOVE the existing `class QAVerdict(BaseModel):` line.

The pydantic and typing imports at the top of the BLOCK 1 must merge
with crew.py's existing imports (do not duplicate `from pydantic import`).
```

### Session 3.2 — Add unit tests for new schemas

```text
Append the contents of BLOCK 10 (TestImageStoryboard,
TestSEOMetadataBundle classes from /mnt/user-data/outputs/crew_v2_patches.py)
to tests/unit/test_crew_schemas.py. Uncomment the test code (it is
currently commented out in the patches file).
```

**Stage 3 verification:**

```bash
uv run pytest tests/unit/test_crew_schemas.py -v
# Expected: previous tests pass + new TestImageStoryboard and
# TestSEOMetadataBundle classes pass (≈15 new tests).

# Schema import sanity:
uv run python -c "from content_generator.crew import ImageStoryboard, SEOMetadataBundle; print('OK')"
```

If tests fail, the error is contained to schema definitions. Fix in
isolation before continuing.

---

## Stage 4 — CRITICAL: tasks.yaml replacement (the big one)

**Why fourth:** This is the largest behavioral change. The new tasks.yaml
materializes the v2 output format. Once applied, the pipeline will produce
v2-compliant HTML on the next run.

**File:** `src/content_generator/config/tasks.yaml`

### Session 4.1 — Replace affected tasks in tasks.yaml

```text
Open src/content_generator/config/tasks.yaml. Read
/mnt/user-data/outputs/tasks_v2.yaml.

For each task in tasks_v2.yaml, REPLACE the corresponding task in
tasks.yaml entirely:
  - copywriting_task
  - quality_assurance_task
  - image_intelligence_task (NEW — does not exist in tasks.yaml; append)
  - html_integration_task
  - localization_task
  - seo_metadata_extraction_task (NEW — does not exist; append)

Preserve all OTHER tasks in tasks.yaml verbatim:
  - url_discovery_task
  - content_extraction_task
  - tech_specs_extraction_task
  - seo_strategy_task

CRITICAL: tasks.yaml uses `{variable}` placeholders that must match
core_inputs keys in crew.py. The new tasks reference:
  - {currency_symbol}      ← from SITES_CONFIG[site]["currency_symbol"]
  - {target_languages}     ← list of ISO codes
  - {finalized_html_by_language}  ← dict
These keys must be supplied by SEOMetadataCrew.get_inputs(); verify
crew_v2_patches.py BLOCK 6 supplies them all.
```

**Stage 4 verification:**

```bash
# YAML parse + key check
uv run python -c "import yaml; t = yaml.safe_load(open('src/content_generator/config/tasks.yaml')); print(list(t.keys()))"
# Expected output:
#   url_discovery_task, content_extraction_task, tech_specs_extraction_task,
#   seo_strategy_task, copywriting_task, quality_assurance_task,
#   image_intelligence_task, html_integration_task, localization_task,
#   seo_metadata_extraction_task
# (10 tasks total — was 8 in v1)

# Run schema tests again (no breakage)
uv run pytest tests/unit/test_crew_schemas.py -v
```

If parse fails, revert:
```bash
git checkout -- src/content_generator/config/tasks.yaml
```

---

## Stage 5 — CRITICAL: crew.py orchestration patches

**Why fifth:** The crew.py changes wire up the new agents/tasks defined
in Stages 2-4. Until these patches land, the new YAML configs are dead code.

**File:** `src/content_generator/crew.py`

### Session 5.1 — Wire up image_intelligence_analyst in ECommerceContentCrew

```text
Open src/content_generator/crew.py. Read
/mnt/user-data/outputs/crew_v2_patches.py.

Apply BLOCK 2: inside `ECommerceContentCrew.__init__`, immediately
AFTER the `self._frontend_developer = Agent(...)` block, insert the
`self._image_intelligence_analyst = Agent(...)` singleton initializer.

Apply BLOCK 3: add the new `image_intelligence_task(self) -> Task:`
method between `quality_assurance_task()` and `html_integration_task()`.

Apply BLOCK 4: REPLACE the existing `html_integration_task()` method
body. The only change is adding `self._require_task('image_intelligence')`
to the context list.
```

### Session 5.2 — Add SEOMetadataCrew + post_pipeline_hook

```text
Apply BLOCK 6 to crew.py: insert the SEOMetadataCrew class ABOVE the
existing MARKET_RULES = {...} block.

Apply BLOCK 7 to crew.py: append the `run_seo_metadata_post_hook(...)`
function at the bottom of crew.py as a module-level function.

Apply BLOCK 9 to crew.py: add a `currency_symbol` field to each entry
in SITES_CONFIG. Mapping:
  - 3DDevice, 3DPrinter, 3DScanner → "грн"
  - EXPERT3D, Impresora-3D       → "€"
  - Expert-3DPrinter             → "$"
  - Center 3D Print              → "zł"   (or "€" if the SITES_CONFIG
                                          entry shows EU pricing)
```

### Session 5.3 — Update Phase 1 task list in main.py and pipeline_runner.py

```text
Apply BLOCK 5: in both src/content_generator/main.py and
src/content_generator/pipeline_runner.py, find the section that builds
the Phase 1 tasks_to_run list. Insert
`core_crew_module.image_intelligence_task()` between
`core_crew_module.quality_assurance_task()` and
`core_crew_module.html_integration_task()`.

Both files build the list independently — patch both.
```

### Session 5.4 — Wire up the post-pipeline hook in pipeline_runner.py

```text
Apply BLOCK 8: in src/content_generator/pipeline_runner.py, inside
run_pipeline_headless(), AFTER the "Крок 2: решта мов" for-loop
completes (i.e., after all language HTML files have been saved), BEFORE
the "Cost report" block, insert the SEO metadata hook invocation as
shown in BLOCK 8.

Implementation requires a `_label_to_iso(lang_label, site_info)` helper
function — implement it as a small helper that maps user-friendly
language labels ("Ukrainian", "Spanish") to ISO codes ("uk-UA", "es-ES")
by looking up site_info["languages_iso"] if present, falling back to a
hardcoded map for common labels.

Apply the same pattern in src/content_generator/main.py if its
orchestration mirrors pipeline_runner.py.
```

**Stage 5 verification:**

```bash
# 1. Import sanity — should resolve all new symbols
uv run python -c "from content_generator.crew import ECommerceContentCrew, LocalizationCrew, SEOMetadataCrew, ImageStoryboard, SEOMetadataBundle, run_seo_metadata_post_hook; print('OK')"

# 2. Re-run all unit tests
uv run pytest tests/ -v --tb=short

# 3. Crew instantiation smoke test (no kickoff yet)
uv run python -c "
from content_generator.crew import ECommerceContentCrew
crew = ECommerceContentCrew()
tasks = [
    crew.tech_specs_extraction_task(),
    crew.seo_strategy_task(),
    crew.copywriting_task(),
    crew.quality_assurance_task(),
    crew.image_intelligence_task(),
    crew.html_integration_task(),
]
print(f'Built {len(tasks)} tasks. Image task agent:', tasks[4].agent.role)
"
# Expected: "Built 6 tasks. Image task agent: ... Visual Storyboard Director ..."
```

If instantiation fails with KeyError on agents_config or tasks_config,
the YAML keys do not match the crew.py references. Re-check Stages 2 and 4.

---

## Stage 6 — INTEGRATION SMOKE TEST: real product end-to-end

**Why sixth:** Only after all patches land can we test the full pipeline
on a real product. This is the first place where output quality is
verified against the `holabot-*.html` reference files.

### Session 6.1 — Run pipeline on PUDU HolaBot for EXPERT3D

```text
Run the pipeline on a known product matching the reference output:
  product_name: "PUDU HolaBot"
  site: "EXPERT3D"
  source_type: "markdown" or "urls" — whichever you have local source for.

Use the GUI (gui.py) or main.py menu. Wait for full completion of:
  Phase 1: EN base HTML
  Phase 2: Ukrainian (review), Spanish localization
  Phase 3 (NEW): seo_metadata.json
  ZIP archive

Expected output files in output_dir/:
  - <ProductName>_<Site>_<timestamp>_English.html
  - <ProductName>_<Site>_<timestamp>_REVIEW_Ukrainian.html
  - <ProductName>_<Site>_<timestamp>_Spanish.html
  - seo_metadata.json  ← NEW v2
  - cost_report.json
  - <full>.zip
```

### Session 6.2 — Audit EN HTML against reference holabot-en.html

```text
Compare the generated English HTML against
/mnt/user-data/uploads/holabot-en.html (the target reference).

Use the .claude/skills/audit-output/ skill to run the audit. Confirm:
  - Output starts with <p>, NOT with <div class="product-desc-wrap">
  - No itemtype="https://schema.org/Product" anywhere
  - All spec rows use <th scope="row" itemprop="name">
  - Every <img> has a preceding lead-in <p>
  - First image has no loading="lazy"
  - Subsequent images have loading="lazy"
  - <strong> reserved for brand+USP; <b> for inline metrics
  - Spec count matches Technical_Specifications JSON
  - <blockquote> Technical Tip present only if source had practitioner data
    (PUDU HolaBot reference does NOT have it — verify absence)
  - <hr> only after </section>
  - CTA is single <p class="cta">, no <ul>, no urgency block

Document any divergence as a follow-up ticket.
```

### Session 6.3 — Validate seo_metadata.json

```text
Open the generated seo_metadata.json. Verify:
  - "site_name" == "EXPERT3D"
  - "seo_data" has one entry per language in the output (3 entries for
    EXPERT3D: en-ES, es-ES, uk-UA)
  - Each entry's meta_title <= 55 chars (count exactly)
  - Each entry's meta_description <= 155 chars and ends with ➔
  - meta_description includes the € symbol for EXPERT3D
  - h1 has no marketing fluff
  - No flag emojis, no 📦 in any field

If Pydantic validation passed at write time, all of these are
automatically true. This step is a final manual sanity check.
```

---

## Stage 7 — POLISH: cleanup and final tests

### Session 7.1 — Remove HOOK_SCHEMA_WRAP residue

```text
Grep the entire repository for "HOOK_SCHEMA_WRAP":
  grep -rn "HOOK_SCHEMA_WRAP" .

Each match must be removed or refactored to a comment explaining it
was the v1 marker. Likely remaining hits:
  - docs/STAGE_3_PATCHES.md (historical — leave with deprecation note)
  - any test fixtures (update or delete)
  - .claude/agents/html-auditor.md (remove from checklist)
  - .claude/skills/audit-output/ (update audit criteria)
```

### Session 7.2 — Audit .claude/agents/html-auditor.md

```text
Open .claude/agents/html-auditor.md. Update the "What to check" section:

REMOVE these checks:
  - "Outer wrapper: <div class=\"product-desc-wrap\">"
  - "Schema.org Product: itemscope itemtype=\"https://schema.org/Product\" on hook"

ADD these checks:
  - Output starts with <p> (not <div>)
  - NO itemtype="https://schema.org/Product" anywhere
  - Spec rows use <th scope="row" itemprop="name"> (not <td>)
  - Every <img> has immediately preceding lead-in <p>
  - First image: no loading="lazy"
  - Subsequent images: loading="lazy" required
  - <strong> only for brand/USP; <b> for inline metrics
  - <hr> only after </section>; no <br> tags
  - <blockquote> Tip present ONLY if source had practitioner data
  - CTA is single <p class="cta">; no <ul>, no urgency block
  - seo_metadata.json present in output_dir (Phase 3 artifact)
```

### Session 7.3 — Update .claude/skills/audit-output/SKILL.md

```text
Apply the same checklist updates from Session 7.2 to
.claude/skills/audit-output/SKILL.md. The skill is consulted whenever
a user asks Claude Code to audit a generated HTML file — it must
reflect the v2 contract.
```

### Session 7.4 — Full test suite + run cost report

```bash
# Full suite — should be 45 baseline + ~15 new schema tests = ~60
uv run pytest tests/ -v --tb=short

# Compare against baseline
diff pre_v2_test_baseline.txt <(uv run pytest tests/ -v --tb=short 2>&1)
# Only "+N passed" deltas expected (more tests now). No regressions.

# Cost-aware test run — verify Phase 3 cost is registered
uv run python -c "
from content_generator.tools.cost_tracker import PipelineCostTracker
t = PipelineCostTracker()
print('Tracker pricing models:', list(t._pricing_models.keys()))
"
```

### Session 7.5 — Commit and review

```bash
git add -A
git status   # review the full diff
git diff --stat   # ensure all expected files changed
git commit -m "v2: align output with holabot reference

Breaking changes:
- Remove schema.org/Product wrapper from description body
  (CMS handles at page level; avoids GSC duplicate entity)
- Remove <div class=\"product-desc-wrap\"> outer container
- Replace <td itemprop=\"name\"> with <th scope=\"row\" itemprop=\"name\">
  on all spec rows (WCAG 1.3.1 + microdata combined)
- Make BLOCKQUOTE_TIP conditional (no fabrication)
- Single-paragraph CTA (no <ul> advantages, no urgency block)
- Replace <br>-spacing with <hr> after </section>

New components:
- image_intelligence_analyst agent + ImageStoryboard Pydantic schema
- seo_metadata_extractor agent + SEOMetadataBundle Pydantic schema
- run_seo_metadata_post_hook → seo_metadata.json artifact
- 7 new unit tests for new schemas
- Conditional HowTo and FAQ sections (only when source has data)

Output matches holabot-en.html / holabot-es.html / holabot-ua.html
reference files."
```

---

## Rollback procedure (if anything in Stages 4-7 breaks production)

```bash
# Hard reset to baseline
git reset --hard HEAD~1

# Or selectively revert files
git checkout main -- src/content_generator/config/tasks.yaml
git checkout main -- src/content_generator/config/agents.yaml
git checkout main -- src/content_generator/crew.py
git checkout main -- docs/marker-protocol.md

# Verify baseline restored
uv run pytest tests/ -v --tb=short | tail -5
# Expected: same pass count as pre_v2_test_baseline.txt
```

---

## Decision log

| Decision | Rationale |
|---|---|
| `<th scope="row" itemprop="name">` over `<td itemprop="name">` | WCAG 1.3.1 (Info and Relationships) requires `<th scope="row">` for row headers. Combining microdata on the `<th>` preserves Schema.org PropertyValue while gaining accessibility. |
| Conditional BLOCKQUOTE_TIP | User confirmed reference HTML files do not contain Tip section. Mandatory Tip would force fabrication when source has no practitioner content — direct GEO trust risk. |
| Image agent AFTER QA, BEFORE html_integration | Image agent needs approved H2 anchors from copywriter (for placement_anchor matching). Running before QA means storyboard could anchor to text that gets rejected. |
| SEOMetadataCrew as separate post-hook, not extension of LocalizationCrew | Single source of truth for SEO metadata. Keeps localization_task signature stable. Allows re-running just the SEO step without regenerating HTML. |
| `loading="eager"` implemented as absence of `loading` attribute | HTML5 spec: omitting `loading` defaults to eager. Adding `loading="eager"` explicitly is allowed but adds bytes — for the LCP image we want minimal markup. |
| `<strong>` (semantic) vs `<b>` (typographic) distinction | HTML5 Living Standard: `<strong>` carries semantic importance, `<b>` is stylistic. AI extractors (Perplexity, SearchGPT) prioritize `<strong>` for QA citation. Reserving `<strong>` for brand+USP (max 2-3 per page) prevents semantic dilution. |
