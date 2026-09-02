---
name: freshness-corroboration-audit
description: Checks whether the page's factual claims are current (not stale) and independently corroborated elsewhere on the web. Use this on pages making factual claims (pricing, specs, leadership, availability) that an assistant would need to trust before repeating — this is the skill that most needs the calling agent's own web-search tool, not just static page analysis.
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# Freshness & Corroboration Audit

## When to use
Use after the other content checks. This corresponds to Appendix D of the brief: a fact repeated
consistently across independent sources is trusted and repeated back; a fact that lives in only one
place, or is visibly stale, is fragile.

## Inputs
- `url` (required)
- `timeout` (optional, default 15s)
- `--search-results <file>` (optional): a JSON file the **calling agent** produces by web-searching
  for the brand's key claims (e.g. `"<brand> pricing"`, `"<brand> founded"`, `"<brand> address"`)
  and recording, for each claim, which independent domains state the same fact. This skill cannot
  perform live web search itself in a plain script context — that's the calling agent's job, using
  whatever search tool it has (this marketplace declares `web_search`/`web_fetch` as needed tools
  for that reason). Format:
  ```json
  {
    "claims": [
      {"claim": "founded in 2015", "corroborating_domains": ["crunchbase.com", "techcrunch.com"]},
      {"claim": "HQ in Austin, TX", "corroborating_domains": []}
    ]
  }
  ```

## Procedure
1. On the page itself, look for explicit freshness signals: `Last-Modified` HTTP header,
   `<meta property="article:modified_time">`, and visible "Last updated" / "Published on" text.
   Flag dates that are implausibly old for time-sensitive content (pricing, job listings, event
   pages) or entirely absent from evergreen-looking claims.
2. If the calling agent has performed corroboration research and supplied `--search-results`, score
   each claim: 0 independent domains = fragile/unverifiable (flag), 1 = weakly supported, 2+ =
   well-corroborated (no finding needed).
3. If no `--search-results` file is supplied, still run step 1, and emit one informational finding
   noting that corroboration research was not performed for this run (so the gap is visible in the
   report rather than silently skipped).
4. Emit findings via `scripts/freshness_check.py`.

## Output
Findings with `id` prefixed `FR-`, following the shared schema.
