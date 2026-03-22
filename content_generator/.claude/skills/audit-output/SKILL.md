---
name: audit-output
description: Audit generated HTML files in output/ for all 8 mandatory sections, Schema.org Product microdata, heading hierarchy, and CSS compliance. Use when reviewing pipeline output quality.
context: fork
agent: Explore
disable-model-invocation: true
---

Audit the most recent HTML files in the output/ directory.

## Checklist

For each HTML file, verify:

1. **8 Mandatory Sections Present**
   - Snippet-Ready Hook (40-75 words) with `HOOK_SCHEMA_WRAP` or `itemprop` attributes
   - Key Specs Quick Table (3-4 rows)
   - Feature Deep-Dive (350-700 words, H2/H3 hierarchy)
   - Applications List (H2 + `<ul>`, 3-5 `<li>` items with workflow context)
   - Expert Verdict (80-120 words, styled block)
   - Technical Tip (60-100 words, in `<blockquote>`)
   - Full Technical Specifications table (ALL specs from source, zero omissions)
   - CTA section for target store

2. **Schema.org Compliance**
   - `itemscope itemtype="http://schema.org/Product"` on wrapper
   - `itemprop="name"`, `itemprop="description"` present
   - Specs table uses `itemprop="additionalProperty"` with `PropertyValue`

3. **HTML Quality**
   - Heading hierarchy: h2 → h3, never skip levels
   - Zero inline styles
   - CSS class names are product-agnostic (no brand names in classes)
   - Semantic elements: `<section>`, `<article>`, `<blockquote>`, `<table>`
   - No external links (zero tolerance)

4. **Content Quality**
   - No banned adjectives: "cutting-edge", "innovative", "state-of-the-art", "perfect", "ideal", "game-changer"
   - Metrics density: at least one specific number per 150 words
   - Expert Verdict cites at least one metric
   - Technical Tip is practitioner advice, not a feature description

## Output Format

Report as a structured checklist:
```
[PASS/FAIL] Section 1: Hook — {details}
[PASS/FAIL] Section 2: Key Specs — {details}
...
[PASS/FAIL] Schema.org — {details}
[PASS/FAIL] Heading hierarchy — {details}
[PASS/FAIL] No inline styles — {details}
[PASS/FAIL] No external links — {details}

VERDICT: {APPROVED / NEEDS_FIX} ({N} issues found)
```
