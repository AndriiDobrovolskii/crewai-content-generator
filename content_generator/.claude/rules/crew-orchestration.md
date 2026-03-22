---
paths:
  - "src/content_generator/crew.py"
  - "src/content_generator/main.py"
---

# Crew Orchestration Rules

- Agents are singletons — instantiate once in `__init__`, reuse across tasks
- Deduplicate agents for Crew via `seen_ids = set()` pattern
- All inter-agent data uses Pydantic models (`TechSpecsOutput`, `QAVerdict`, `SEOBriefOutput`)
- `SITES_CONFIG` is single source of truth for store params — never hardcode
- `CTA_TEMPLATES` and `MARKET_RULES` injected via `core_inputs` / `get_inputs()`
- Ukrainian-first: always generate UA before other languages
- `ua_is_production` determines if UA is production or review artifact
- LLM per role: cheap for search, expensive for writing — override via `.env`
- `Process.sequential` with `memory=True, cache=True` for all Crews
- Windows UTF-8: stdout/stderr wrappers at top of main.py are mandatory
