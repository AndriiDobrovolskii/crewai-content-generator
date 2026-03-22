---
name: generate
description: Run the GEO content generation pipeline for a product. Use when asked to generate product descriptions, run the pipeline, or create content.
disable-model-invocation: true
---

Run the content generation pipeline:

1. Confirm with the user: product name, target site (from SITES_CONFIG), data source type
2. Verify target site exists in `SITES_CONFIG` keys in crew.py
3. Check `.env` has required keys: `OPENAI_API_KEY`, `SERPER_API_KEY`
4. Execute: `uv run src/content_generator/main.py`
5. Monitor output for errors (look for `[ФАТАЛЬНА ПОМИЛКА]` or `REJECTED` from QA agent)
6. After completion, list files in the output directory
7. If `ua_is_production` is False for the target site, note that Ukrainian output is review-only
