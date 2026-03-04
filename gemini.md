# gemini.md - Project Constitution

## Data Schemas

### Input Payload (Operator Menu)
```json
{
  "product_name": "string",
  "site_choice": "string (from SITES_CONFIG)",
  "raw_text": "string (optional)",
  "use_auto_search": "boolean"
}
```

### Intermediate Payload (Analyst Output)
```json
{
  "Technical_Specifications": {
     "Category": { "Spec": "Value" }
  },
  "Support_Data": {
     "faqs": [{"Question": "...", "Answer": "..."}],
     "troubleshooting": [{"Step": "..."}]
  }
}
```

### Final Payload (Delivery)
- **Format**: HTML (OpenCart compliant)
- **Content**: SEO/GEO optimized description + Schema Microdata
- **Location**: local `output/{timestamp}/` ZIP

## Behavioral Rules
1. The "Data-First" Rule: Define schema before building tools.
2. Self-Annealing: Analyze, Patch, Test, and Update Architecture on failure.
3. Reliability > Speed: prioritized deterministic logic.
4. **Human-In-The-Loop (HITL)**: Mandatory review for all AI-generated research (Option 4) before proceeding to analysis.
5. **No YAML Edits**: Prohibited from modifying `agents.yaml` or `tasks.yaml` without explicit approval.

## Architectural Invariants
- 3-Layer Build: Architecture (SOPs), Navigation (Decision), Tools (Python).
- Use `.tmp/` for intermediates.
- Deterministic tools in `tools/`.

## Maintenance Log
*Initial creation 2026-03-04*
*Architecture Update 2026-03-04: Implemented A.N.T. Layer 1 (SOPs in architecture/), Layer 2 (Navigation in main.py), and Layer 3 (Deterministic logic in crew.py). Added Strict Language Enforcement and HITL Search protocols.*
