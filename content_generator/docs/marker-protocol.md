# HTML Marker Protocol — v2.0

**Status:** v2 supersedes v1. Breaking changes documented in §"Migration from v1".

## What This Is

Markers are typed handoff contracts between agents in the content pipeline.
The **copywriter** writes English copy with markers in the text; the
**image_intelligence_analyst** produces a typed storyboard (no markers,
strict JSON); the **frontend_developer** consumes both and converts them
to semantic HTML.

## Critical Architectural Rule

**The description body NEVER contains `itemtype="https://schema.org/Product"`.**

The OpenCart page template already emits a complete `schema.org/Product`
entity via page-level JSON-LD. A second Product entity in the description
body creates a duplicate that Google Search Console flags as
"Multiple top-level entities" and disqualifies the page from rich results.

**Safe schemas** that DO appear in the description body:

| Schema | Where | Why it's safe |
|---|---|---|
| `PropertyValue` | Every spec table `<tr>` | Extends the page-level Product without duplicating it |
| `FAQPage` | Optional FAQ section | Separate entity, not a Product |
| `HowTo` / `HowToStep` | Optional troubleshooting / setup procedure | Separate entity, not a Product |

**Forbidden schemas** in the description body:

| Schema | Reason |
|---|---|
| `Product` (any form) | CMS handles this at page level — duplicating creates GSC errors |
| `BreadcrumbList` | CMS generates this automatically |
| `VideoObject` | Belongs to page-level structured data |
| `ImageObject` | Belongs to page-level structured data |
| `Article` | Incompatible with product page context |

## Marker Inventory (v2)

| Marker | Producer | Section | Frontend Implementation | Required? |
|---|---|---|---|---|
| `EXPERT_INSIGHT_BLOCK` | copywriter | Expert Verdict | `<div class="expert-insight" style="background: #f9f9f9; padding: 15px; border-left: 4px solid #333; margin: 20px 0;"><strong>Expert Verdict:</strong> ...` | Always |
| `BLOCKQUOTE_TIP` | copywriter | Technical Tip | `<blockquote><strong>Expert Technical Tip:</strong> ...</blockquote>` | **Conditional** |
| `SPECS_TABLE_SECTION` | copywriter | Full Tech Specs | `<section class="specs">` with per-category `<h3>` + table; each `<tr>` carries PropertyValue microdata via `<th scope="row" itemprop="name">` / `<td itemprop="value">` | Always |
| `CTA_SECTION` | copywriter | Store CTA | Single `<p class="cta">` paragraph. NO `<ul>` advantages list, NO separate urgency block | Always |

**Removed in v2:**

| Marker | Reason for removal |
|---|---|
| `HOOK_SCHEMA_WRAP` | The hook is now a plain `<p>` without Schema.org/Product wrapper. CMS owns the Product entity at page level. |

**New in v2 (typed JSON contract, not a text marker):**

| Contract | Producer | Consumer | Schema |
|---|---|---|---|
| `ImageStoryboard` | image_intelligence_analyst | frontend_developer | Pydantic `ImageStoryboard` with per-item: `url`, `alt_text` (60–160 chars), `lead_in_paragraph`, `placement_anchor` (H2 text or `"HERO"`), `loading_strategy` (`"eager"` or `"lazy"`), `order` (int ≥1) |

## `BLOCKQUOTE_TIP` — Conditional Emission Rule

The Technical Tip section is **OPTIONAL** in v2. The copywriter emits the
`BLOCKQUOTE_TIP` marker **only if** the source material contains
practitioner-grade tip content. Acceptable triggers:

✅ **Emit** the Tip section when source contains:
- Explicit maintenance steps (e.g., "wipe the nozzle every 50 hours").
- Calibration nuance (e.g., "for dark matte surfaces, enable the reflective
  object mode").
- Material handling caution (e.g., "store dry below 25 °C, vacuum-seal").
- Configuration tip from a manufacturer's "tips & tricks" subsection.

❌ **OMIT** the Tip section when:
- Source only has generic product description.
- Tip would have to be fabricated to fill the slot.
- The closest source content is a generic capability claim, not actionable advice.

**The editor_qa task enforces this**: if a Tip is present but cannot be
traced to source data, QA rejects the draft.

**The frontend_developer task respects the copywriter's decision**: if
`BLOCKQUOTE_TIP` is absent in the draft, the frontend agent skips Section 6
entirely. It does NOT fabricate a tip to fill the visual slot.

## `ImageStoryboard` — Typed Contract

The image_intelligence_analyst produces a JSON object validated by the
`ImageStoryboard` Pydantic schema:

```python
class ImageStoryboardItem(BaseModel):
    url: str                       # exact URL from Official_Images
    alt_text: str                  # 60-160 chars, screen-reader-friendly
    lead_in_paragraph: str         # 1-3 sentences, contextually ties to anchor
    placement_anchor: str          # exact H2 text from draft, or "HERO"
    loading_strategy: Literal["eager", "lazy"]
    order: int                     # global order, starts at 1

class ImageStoryboard(BaseModel):
    items: list[ImageStoryboardItem]
```

**Invariants enforced by Pydantic validators:**

1. Exactly **one** item has `loading_strategy="eager"` and it is the
   item with the lowest `order` value (typically `order=1`).
2. All other items have `loading_strategy="lazy"`.
3. No duplicate URLs.
4. No empty `lead_in_paragraph`.
5. `placement_anchor="HERO"` items go between the Quick Specs Table and
   the first `<h2>` of the deep-dive. Other anchors are matched verbatim
   against H2 text in the copywriter's draft.

## Frontend HTML Skeleton (v2, no Product wrapper)

```html
<!-- Section 1: Hook (plain <p>, no microdata) -->
<p>The <strong>{Brand+Model}</strong> is a [Category] built for [Application],
  featuring <b>{metric 1}</b>, <b>{metric 2}</b>...</p>

<!-- Section 2: Quick Specs Table (3-4 killer specs, no thead) -->
<div class="table-responsive">
  <table class="table table-striped table-hover table-bordered">
    <tbody>
      <tr itemprop="additionalProperty" itemscope itemtype="https://schema.org/PropertyValue">
        <th scope="row" itemprop="name">{spec name}</th>
        <td itemprop="value">{spec value}</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- Section 3 (conditional): Video lead-in + embed -->
<p>{contextual lead-in paragraph}</p>
<div style="text-align:center;">
  <video width="100%" height="auto" controls
         style="max-width: 800px; border: 1px solid #ccc; border-radius: 8px;">
    <source src="{URL}" type="video/mp4">
    Your browser does not support video playback.
  </video>
</div>

<!-- Section 4: Deep-Dive (H2 anchors + interleaved storyboard images) -->
<h2>{benefit-driven question}</h2>
<p>{1-3 paragraphs using <b> for metrics, <strong> only for brand/USP}</p>

<p>{lead_in_paragraph from ImageStoryboard item}</p>
<img src="{url}" alt="{alt_text}"
     style="max-width: 100%; height: auto; display: block; margin: 15px 0;"
     loading="lazy">     <!-- omit loading for the order=1 image -->

<!-- ... more H2/H3 blocks ... -->

<!-- Section 5: Expert Verdict (always) -->
<div class="expert-insight"
     style="background: #f9f9f9; padding: 15px; border-left: 4px solid #333; margin: 20px 0;">
  <strong>Expert Verdict:</strong> {80-120 words}
</div>

<!-- Section 6: Technical Tip (CONDITIONAL — only if BLOCKQUOTE_TIP emitted) -->
<blockquote>
  <strong>Expert Technical Tip:</strong> {60-100 words}
</blockquote>

<!-- Section 7: Full Tech Specs -->
<section class="specs">
  <h2>Technical specifications of {product name}</h2>
  <h3>{category}</h3>
  <div class="table-responsive">
    <table class="table table-striped table-hover table-bordered">
      <tbody>
        <tr itemprop="additionalProperty" itemscope itemtype="https://schema.org/PropertyValue">
          <th scope="row" itemprop="name">{property}</th>
          <td itemprop="value">{value, no trailing period}</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
<hr>

<!-- Section 8: HowTo (conditional) -->
<section itemscope itemtype="https://schema.org/HowTo">
  <h2 itemprop="name">How to {task}</h2>
  <p itemprop="description">{brief}</p>
  <div itemprop="step" itemscope itemtype="https://schema.org/HowToStep">
    <h3 itemprop="name">{step title}</h3>
    <p itemprop="text">{step body}</p>
  </div>
</section>
<hr>

<!-- Section 9: FAQ (conditional) -->
<section itemscope itemtype="https://schema.org/FAQPage">
  <div itemprop="mainEntity" itemscope itemtype="https://schema.org/Question">
    <h3 itemprop="name">{question}</h3>
    <div itemprop="acceptedAnswer" itemscope itemtype="https://schema.org/Answer">
      <p itemprop="text">{answer}</p>
    </div>
  </div>
</section>
<hr>

<!-- Section 10: CTA (single paragraph) -->
<h2>Why choose {site_name}?</h2>
<p class="cta">{80-150 word paragraph; brand-rep sentence if applicable}</p>
```

## Semantic Rules (enforced by frontend_developer)

- **`<strong>`**: ONLY for brand names and main USPs.
  Max 2-3 per page total. Carries semantic importance for AI extractors.
- **`<b>`**: typographic accent for inline metrics ("60 kg", "0.5–1.2 m/s").
  Max 2-3 per paragraph. Carries no semantic weight.
- **`<ul>`**: feature and application lists. **Never** for key-value spec pairs.
- **`<ol>`**: numbered steps only (HowTo / troubleshooting).
- **No `<script>`**, no JSON-LD — inline microdata attributes only.
- **No `<h1>`** — heading hierarchy starts at `<h2>`.
- **No `<br>` tags** — use `<hr>` only after `</section>` closing tags.
- Spec table rows use `<th scope="row" itemprop="name">` (WCAG 1.3.1 +
  Schema.org microdata combined).

## Image Rules (enforced by both image_intelligence_analyst and frontend_developer)

- Every `<img>` MUST be immediately preceded by its `lead_in_paragraph` `<p>`.
- NO orphan images (no `<img>` without preceding lead-in `<p>`).
- NO consecutive `<img>` tags without intervening semantic text.
- First image (`order=1`, `loading_strategy="eager"`) gets NO `loading`
  attribute — it is the LCP candidate.
- All subsequent images REQUIRE `loading="lazy"`.
- Image URLs MUST come verbatim from `Official_Images` in `TechSpecsOutput` —
  never hallucinate.

## Self-Audit Checklist (frontend_developer runs before delivery)

Architectural correctness:
- [ ] Output starts with `<p>` (the hook), NOT with `<div class="...">`.
- [ ] No `itemtype="https://schema.org/Product"` anywhere.
- [ ] No `<div class="product-desc-wrap">`.
- [ ] No `HOOK_SCHEMA_WRAP` literal text leaked from copywriter.
- [ ] No `<br>` tags.
- [ ] `<hr>` only after `</section>` closings.

Accessibility:
- [ ] Every spec `<tr>` uses `<th scope="row" itemprop="name">` (not `<td>`).
- [ ] Every `<img>` has a non-empty `alt`.
- [ ] Heading hierarchy: h2 → h3, never skipping levels.

Microdata:
- [ ] Every spec `<tr>` carries PropertyValue.
- [ ] FAQ uses FAQPage (only if FAQ data present).
- [ ] HowTo uses HowTo + HowToStep (only if procedure data present).

Image integration:
- [ ] Every `<img>` has an immediately preceding lead-in `<p>`.
- [ ] First image has NO `loading="lazy"`.
- [ ] Images #2+ all have `loading="lazy"`.
- [ ] No two consecutive `<img>` tags without intervening semantic block.

Content:
- [ ] `<div class="expert-insight">` block present.
- [ ] `<blockquote>` tip present IFF copywriter emitted `BLOCKQUOTE_TIP`.
- [ ] `<p class="cta">` CTA paragraph present.
- [ ] No `<ul>` advantage list inside CTA, no separate urgency block.
- [ ] All spec values from source preserved (zero omissions).

Hygiene:
- [ ] No `<script>` tags, no JSON-LD.
- [ ] No Markdown artifacts (```html, **bold**).
- [ ] No external links to manufacturer / competitor stores.
- [ ] No inline styles except on `<img>`, `<video>`, `<div class="expert-insight">`.

## Migration from v1

| What changed | v1 | v2 | Action |
|---|---|---|---|
| Outer wrapper | `<div class="product-desc-wrap">…</div>` | None (output starts with `<p>`) | Remove from all tasks, marker-protocol, agents.yaml |
| Hook schema | `<div itemscope itemtype="…/Product"><h2 itemprop="name">…<p itemprop="description">` | Plain `<p>` | Remove `HOOK_SCHEMA_WRAP` marker entirely |
| Spec table cell | `<td itemprop="name">` | `<th scope="row" itemprop="name">` | Update all spec-table generation logic |
| Tip section | Always emitted | Conditional on source content | Update copywriter task; update QA fatal conditions |
| Image integration | Optional, no protocol | Mandatory typed `ImageStoryboard` contract | Add `image_intelligence_analyst` agent + task |
| CTA structure | `<p class="cta">` + `<ul>` + `<p><strong>urgency</strong></p>` | Single `<p class="cta">` only | Update copywriter Section 8; update frontend Section 10 |
| Spacing | `<br>` after `</p>` | `<hr>` only after `</section>` | Update frontend task description |
| SEO metadata | Embedded in copywriter context | Separate `seo_metadata.json` artifact via post-pipeline hook | Add `seo_metadata_extractor` agent + post hook |
