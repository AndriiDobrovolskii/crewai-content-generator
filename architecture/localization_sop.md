# SOP: Localization & Transcreation (Phase 2)

## Goal
Localize the English HTML into target languages while preserving technical accuracy and SEO markup.

## Inputs
- `base_html`: Approved English output from Phase 1.
- `target_language`: Destination language.
- `site_name`: Brand context.

## Logic Flow
1. **Brand Protection**: Brand names and model names remain untranslated.
2. **Technical Integrity**: Metric units (mm, kg, °C) are preserved.
3. **Markup Preservation**: Schema.org attributes (`itemprop`, etc.) are NEVER translated.
4. **Transcreation**: Adaptive rewriting for the local market (e.g., shipping carriers).

## Edge Cases
- **US Market**: Requires Imperial units in parentheses via `USMeasurementCalculatorTool`.
- **UA/RU Market**: Follow specific capitalization rules after colons.
- **Same Language input**: Stylistic improvement only.

## Validation
- [ ] No translated HTML tags/attributes.
- [ ] Schema.org markup is intact.
- [ ] Brand names are correct.
