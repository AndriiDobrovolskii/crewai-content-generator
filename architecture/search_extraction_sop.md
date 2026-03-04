# SOP: Search & Extraction (HITL)

## Goal
Find 100% reliable manufacturer data and prepare it for analysis.

## Logic Flow
1. **Search**: Researcher uses Serper/Firecrawl to find official URLs.
2. **HITL Stop**: Script pauses. Operator MUST verify URLs.
3. **Scraping**: Extract text using cascaded tools (Firecrawl -> BS4 -> Selenium).
4. **Text Cleaning**: Remove JS, footers, and noise.

## Edge Cases
- **No Official Source**: Stop and inform user.
- **Anti-Bot Blocking**: Selenium fallback with custom User-Agent.

## Validation
- [ ] Source URL is the manufacturer.
- [ ] Extracted text has >200 chars.
