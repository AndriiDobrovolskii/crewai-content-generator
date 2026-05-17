---
name: audit-output
description: Audit generated HTML files in output/ for v2 architectural compliance, Schema.org microdata, image storyboard protocol, and content quality standards. Use when reviewing pipeline output quality.
context: fork
agent: Explore
disable-model-invocation: true
---

Audit the most recent HTML files in the output/ directory.

## Checklist

For each HTML file, verify:

1. **Architectural (FATAL — any failure = NEEDS_FIX)**
   - Output starts with `<p>` — NOT `<div>`, NOT markdown fence ` ```html `
   - NO `itemtype="https://schema.org/Product"` anywhere (CMS owns the Product entity)
   - NO `<div class="product-desc-wrap">` wrapper (v1 artifact, removed in v2)
   - NO `HOOK_SCHEMA_WRAP` literal text (deprecated v1 marker)
   - Spec rows use `<th scope="row" itemprop="name">` — never `<td itemprop="name">`
   - No `<h1>` — heading hierarchy starts at `<h2>`
   - No `<br>` tags; `<hr>` only after `</section>` closing tags
   - No `<script>` or JSON-LD blocks

2. **Image Protocol (v2 ImageStoryboard contract)**
   - Every `<img>` has immediately preceding lead-in `<p>` (no orphan images)
   - First image: NO `loading` attribute (LCP candidate — eager by default)
   - All subsequent images: `loading="lazy"` required
   - No two consecutive `<img>` tags without intervening semantic block

3. **Schema.org Microdata**
   - Every spec `<tr>` carries `itemprop="additionalProperty" itemscope itemtype="https://schema.org/PropertyValue"`
   - FAQ section (if present) uses `itemtype="https://schema.org/FAQPage"`
   - HowTo section (if present) uses `itemtype="https://schema.org/HowTo"` with `HowToStep`

4. **Semantic Markup**
   - `<strong>` only for brand names and main USPs (max 2–3 per page)
   - `<b>` only for inline metrics ("60 kg", "0.5–1.2 m/s") — max 2–3 per paragraph
   - `<ul>` for feature/application lists only — never for key-value spec pairs

5. **Mandatory Sections (7 core + conditionals)**
   - Hook `<p>` — 40–75 words, plain paragraph
   - Key Specs Quick Table — 3–4 rows
   - Feature Deep-Dive — H2/H3 hierarchy, 350–700 words
   - Applications List — `<h2>` + `<ul>`, 3–5 items
   - Expert Verdict — `<div class="expert-insight" style="...border-left: 4px solid #333...">` present
   - Technical Tip — `<blockquote>` ONLY if source had practitioner-grade data; absence is not a failure
   - Full Technical Specifications — `<section class="specs">`, ALL specs, zero omissions
   - CTA — single `<p class="cta">`, no `<ul>`, no separate urgency block
   - HowTo section (conditional) — present if `Support_Data.troubleshooting` non-empty
   - FAQ section (conditional) — present if `Support_Data.faqs` non-empty

6. **Phase 3 Artifact**
   - `seo_metadata.json` present in the same output directory
   - Each entry: `meta_title` ≤55 chars, `meta_description` ≤155 chars ending with `➔`
   - Currency symbol present in `meta_description`

7. **Content Quality**
   - No banned adjectives: "cutting-edge", "innovative", "state-of-the-art", "perfect", "ideal", "game-changer"
   - Metrics density: at least one specific number per 150 words
   - Expert Verdict cites at least one metric
   - No external links to manufacturer or competitor stores
   - No Markdown artifacts (` ```html `, `**bold**`)
   - No inline styles except on `<img>`, `<video>`, `<div class="expert-insight">`

## Output Format

Report as a structured checklist:
```
[PASS/FAIL] Architectural — {details}
[PASS/FAIL] Image Protocol — {details}
[PASS/FAIL] Schema.org Microdata — {details}
[PASS/FAIL] Semantic Markup — {details}
[PASS/FAIL] Mandatory Sections — {details}
[PASS/FAIL] Phase 3 Artifact (seo_metadata.json) — {details}
[PASS/FAIL] Content Quality — {details}

VERDICT: {APPROVED / NEEDS_FIX} ({N} issues found)
```
