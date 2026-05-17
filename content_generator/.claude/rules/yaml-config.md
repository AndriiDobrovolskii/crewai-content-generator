---
paths:
  - "src/content_generator/config/**/*.yaml"
---

# CrewAI YAML Config Rules

- Agent backstories define IDENTITY only — never put execution logic here
- Task `expected_output` must be specific and measurable, not vague
- Every task MUST have explicit `context` listing upstream dependencies
- Use `{variable}` placeholders matching `core_inputs` dict keys in `crew.py`
- Active markers (`EXPERT_INSIGHT_BLOCK`, `BLOCKQUOTE_TIP`, `SPECS_TABLE_SECTION`, `CTA_SECTION`) are typed contracts — preserve exact names. `HOOK_SCHEMA_WRAP` is deprecated (v1) — reject if it appears in output
- YAML indentation: 2 spaces, use `>` for multiline strings
