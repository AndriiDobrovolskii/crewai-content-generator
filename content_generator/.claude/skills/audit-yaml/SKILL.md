---
name: audit-yaml
description: Review agents.yaml and tasks.yaml for CrewAI architectural violations. Use when refactoring YAML configs or after major changes.
context: fork
agent: Explore
disable-model-invocation: true
---

Audit `src/content_generator/config/agents.yaml` and `src/content_generator/config/tasks.yaml` for architectural violations.

## Violation Categories

1. **Backstory Contamination**: Agent backstories containing execution rules, output format specs, or step-by-step instructions (these belong in tasks.yaml)
2. **Missing Context Chain**: Tasks without explicit `context` attribute listing upstream dependencies
3. **Vague Expected Output**: `expected_output` that lacks measurable criteria (word counts, section names, format markers)
4. **Role Ambiguity**: Agent roles too generic (e.g., "Writer" instead of "Semantic Conversion Strategist")
5. **Placeholder Mismatch**: `{variable}` placeholders in YAML that don't match `core_inputs` keys in crew.py
6. **Marker Inconsistency**: Handoff markers (HOOK_SCHEMA_WRAP, EXPERT_INSIGHT_BLOCK, etc.) referenced in tasks but not documented or vice versa

## Output Format

```
VIOLATION #{n}: [{category}] 
  File: {filename}, Line ~{line}
  Issue: {description}
  Fix: {recommended action}
```

End with: `TOTAL: {n} violations found. Severity: {CRITICAL/MODERATE/CLEAN}`
