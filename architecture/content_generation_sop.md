# SOP: Core Content Generation (Phase 1)

## Goal
Generate a high-quality, SEO/GEO optimized product description in English.

## Inputs
- `product_name`: Target product.
- `site_name`: Destination e-commerce site.
- `raw_source_text`: Confirmed manufacturer data.
- `target_country`: Logistics/market context.

## Logic Flow
1. **Tech Extraction**: Analyst extracts raw specs into a nested JSON.
2. **SEO Strategy**: Strategist creates a brief with "Answer-First" requirement.
3. **Copywriting**: Copywriter writes English prose based on the brief and specs.
4. **QA**: Editor verifies >80% uniqueness and zero hallucinations.
5. **HTML**: Dev formats into OpenCart-compliant HTML with inline Microdata.

## Edge Cases
- **Non-English Input**: Logic must explicitly translate to English during extraction/writing.
- **Empty Specs**: Omit category if no data exists.
- **Microdata Stripping**: Use ONLY inline attributes, NO script tags.

## Validation
- [ ] Output starts with 40-75 word summary.
- [ ] Technical table is present and correctly formatted.
- [ ] Language is strictly English.
