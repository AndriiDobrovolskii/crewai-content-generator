# HTML Marker Protocol

## Agent-to-Agent Handoff Markers

Markers are typed contracts between the copywriter and frontend_developer agents.
The copywriter writes content with markers in the text; the frontend agent converts them to semantic HTML.

### Content Markers (copywriter → frontend)

| Marker | Section | Frontend Implementation |
| -------- | -------- | ---------------------- |
| `HOOK_SCHEMA_WRAP` | Snippet-Ready Hook | `<div itemscope itemtype="https://schema.org/Product">` with `itemprop="name"`, `itemprop="description"` |
| `EXPERT_INSIGHT_BLOCK` | Expert Verdict | `<div class="expert-insight"><strong>Expert Verdict:</strong> ...` |
| `BLOCKQUOTE_TIP` | Technical Tip | `<blockquote><strong>Expert Technical Tip:</strong> ...` |
| `SPECS_TABLE_SECTION` | Full Technical Specs | `<section class="specs">` with per-category `<h3>` + `<table>` blocks, each `<tr>` has `itemprop="additionalProperty"` PropertyValue microdata |
| `CTA_SECTION` | Store CTA | `<p class="cta">` body + `<ul>` advantages + `<p><strong>` urgency hook |

### Schema.org Microdata Structure

```html
<div class="product-desc-wrap">
  <!-- HOOK_SCHEMA_WRAP -->
  <div itemscope itemtype="https://schema.org/Product">
    <h2 itemprop="name">{product_name}</h2>
    <p itemprop="description">{40-75 word hook}</p>
  </div>

  <!-- Key Specs Quick Table -->
  <table class="table table-striped table-hover table-bordered">
    <tr><td>{feature}</td><td>{value}</td></tr>
  </table>

  <!-- Feature Deep-Dive -->
  <h2>{main differentiator question}</h2>
  <h3>{feature} — {benefit}</h3>
  <p>...</p>

  <!-- Applications -->
  <h2>{applications question}</h2>
  <ul><li><strong>{application}:</strong> {workflow benefit}</li></ul>

  <!-- EXPERT_INSIGHT_BLOCK -->
  <div class="expert-insight">
    <strong>Expert Verdict:</strong> {80-120 words}
  </div>

  <!-- BLOCKQUOTE_TIP -->
  <blockquote>
    <strong>Expert Technical Tip:</strong> {60-100 words}
  </blockquote>

  <!-- SPECS_TABLE_SECTION -->
  <section class="specs">
    <h2>Technical specifications of the {product_name}</h2>
    <h3>{category}</h3>
    <div class="table-responsive">
      <table class="table table-striped table-hover table-bordered">
        <tr itemprop="additionalProperty" itemscope itemtype="https://schema.org/PropertyValue">
          <td itemprop="name">{spec name}</td>
          <td itemprop="value">{spec value — NO trailing period}</td>
        </tr>
      </table>
    </div>
  </section>

  <!-- FAQ (conditional) -->
  <section class="supplemental-content" itemscope itemtype="https://schema.org/FAQPage">
    <h2>Frequently Asked Questions about {product_name}</h2>
    <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
      <h3 itemprop="name">{question}</h3>
      <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
        <p itemprop="text">{answer}</p>
      </div>
    </div>
  </section>

  <!-- CTA_SECTION -->
  <h2>Why choose {site_name}?</h2>
  <p class="cta">{80-150 words}</p>
  <ul><li>{advantage}</li></ul>
  <p><strong>{urgency hook}</strong></p>
</div>
```

### Semantic Rules (enforced by frontend agent)

- `<strong>` ONLY for exact metrics within paragraphs (max 2-3 per paragraph)
- `<ul>` for feature/application lists, NEVER for key-value spec pairs
- `<ol>` for numbered steps only (troubleshooting/HowTo)
- NO `<script>`, NO JSON-LD — inline microdata attributes only
- NEVER use `<h1>` — heading hierarchy starts at `<h2>`
- ALL images: `<img src="{exact_url}" alt="{text}" style="max-width: 100%; height: auto;">`
- Image URLs MUST come from `Official_Images` in TechSpecsOutput — never hallucinate

### Self-Audit Checklist (frontend agent runs before delivery)

- [ ] Wrapped in `<div class="product-desc-wrap">`
- [ ] Schema.org Product microdata on hook section
- [ ] Specs in `<section class="specs">` with PropertyValue per `<tr>`
- [ ] FAQ in `<section class="supplemental-content">` (if data exists)
- [ ] `<div class="expert-insight">` block present
- [ ] `<blockquote>` tip present
- [ ] `<p class="cta">` for CTA body
- [ ] Zero `<script>` tags
- [ ] Zero Markdown artifacts
- [ ] Zero external links
