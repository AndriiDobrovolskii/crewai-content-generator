# Store Configuration Reference

## SITES_CONFIG

Single source of truth for all store parameters. Defined in `crew.py`.

| Store | Country | Languages | Localizer Key | UA Production |
| ------- | -------- | ----------- | --------------- | --------------- |
| 3DDevice | Ukraine | Ukrainian, English, Russian | `localizer_ua` | Yes |
| 3DPrinter | Ukraine | Ukrainian, English, Russian | `localizer_ua` | Yes |
| 3DScanner | Ukraine | Ukrainian, English, Russian | `localizer_ua` | Yes |
| Center 3D Print | Poland | Polish, German, English, Ukrainian, Russian | `localizer_pl` | No |
| EXPERT3D | Spain | Spanish (Castilian es-ES) | `localizer_es` | No |
| Expert-3DPrinter | USA | American English, US Spanish | `localizer_us` | No |

### ua_is_production flag

- `True`: Ukrainian output is the production file (named `Ukrainian_{product}.html`)
- `False`: Ukrainian output is review-only (named `REVIEW_Ukrainian_{product}.html`), generated before other languages for QA purposes

## MARKET_RULES

Injected into `{market_rules}` placeholder in `localization_task`. Each key maps to a block of market-specific rules.

| Key | Target | Key Rules |
| ----- | -------- | ----------- |
| `localizer_ua` | Ukraine | Lowercase after colon, Nova Poshta/Ukrposhta, Ukrainian 3D printing terminology |
| `localizer_pl` | Poland/EU | DPD/InPost, EU warranty, PL/DE/EN/UA multilingual support |
| `localizer_es` | Spain | Castilian es-ES, tuteo, "envío urgente 24/48h", es-ES vocabulary |
| `localizer_us` | USA | Imperial conversions (inches, lbs) via tool, UPS/FedEx, punchy active voice, keep °C/mm for precision specs |
| `review_ua` | Internal | No market adaptation, pure translation for QA |

### US Market — Measurement Conversion Rules

Critical: the `localizer_us` key triggers `USMeasurementCalculatorTool` attachment.

CONVERT to Imperial (metric in parentheses):

- Dimensions / Build Volume → inches
- Weight → lbs

KEEP strictly in Metric:

- Layer Thickness
- Filament/Nozzle Diameter
- Temperature (°C — NEVER Fahrenheit)
- Print Speed

## CTA_TEMPLATES

Store-specific advantages and urgency hooks for the CTA section. Defined in `crew.py`.

Each entry has:

- `store_advantages`: list of 5 factual selling points
- `urgency_hook`: single urgency sentence

These are injected into `{cta_context}` in `core_inputs` and used by the copywriter for Section 8 (CTA).

### Brand Representative Check

If `{product_name}` contains a brand from the official representative list (e.g., Shining3D for EXPERT3D), the copywriter MUST include:
> "As an official representative of [Brand Name], we guarantee the best price, authorized service, and official warranty."
