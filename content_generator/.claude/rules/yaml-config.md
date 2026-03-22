---
paths:
  - "src/content_generator/config/**/*.yaml"
---

# CrewAI YAML Config Rules

- Agent backstories define IDENTITY only — never put execution logic here
- Task `expected_output` must be specific and measurable, not vague
- Every task MUST have explicit `context` listing upstream dependencies
- Use `{variable}` placeholders matching `core_inputs` dict keys in `crew.py`
- Markers (`HOOK_SCHEMA_WRAP`, `EXPERT_INSIGHT_BLOCK`, etc.) are typed contracts — preserve exact names
- YAML indentation: 2 spaces, use `>` for multiline strings
