---
name: freshness-corroboration-audit
description: Audits content recency timestamps and evaluates cross-source web corroboration for key brand claims. Detects stale dates, missing publication/modified timestamps, and cross-checks factual claims against independent third-party sources (Crunchbase, Wikipedia, news outlets).
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# Freshness & Corroboration Audit

## Overview & Purpose
AI models prioritize current information and assign higher confidence to claims repeated consistently across independent, authoritative websites. A brand claim that exists only on its own homepage without third-party corroboration is fragile; a claim with stale timestamps (e.g. outdated pricing or job openings) risks being omitted or flagged as unreliable by AI fetchers.

The **Freshness & Corroboration Audit** skill assesses on-page recency signals and integrates agent web-search data to score independent corroboration across the web.

## Key Technical Features
- **On-Page Recency Detection**: Inspects `Last-Modified` HTTP response headers, `<meta property="article:modified_time">` tags, JSON-LD `dateModified` properties, and visible "Last updated" text strings.
- **Content Staleness Risk Scoring**: Identifies dates that are implausibly old for time-sensitive pages (pricing, event listings, career openings).
- **Cross-Source Corroboration Integration**: Accepts pre-gathered agent web-search evidence (`--search-results`) to verify how many independent domains corroborate key brand facts (founding date, headquarters, leadership, core offerings).

## Input Parameters
- `url` *(required)*: The target page URL to evaluate.
- `timeout` *(optional)*: Maximum request timeout in seconds (defaults to 15s).
- `--search-results <file>` *(optional)*: JSON evidence file provided by the calling agent containing claims and matching third-party domain references:
  ```json
  {
    "claims": [
      {"claim": "founded in 2015", "corroborating_domains": ["crunchbase.com", "techcrunch.com"]},
      {"claim": "HQ in Austin, TX", "corroborating_domains": []}
    ]
  }
  ```

## Diagnostic Procedure
1. **On-Page Timestamp Extraction**: Audits HTTP headers, meta tags, and visible DOM text for publication and modification dates.
2. **Staleness Evaluation**: Compares timestamps against content type expectations, flagging outdated or missing recency signals.
3. **Corroboration Scoring**: Evaluates claim support across independent domains (0 domains = fragile/unverifiable, 1 = weakly supported, 2+ = well-corroborated).
4. **Informational Fallback**: If no search results file is provided, emits an explicit informational finding highlighting that cross-source web corroboration was not performed.
5. **Execution**: Emits findings via `scripts/freshness_check.py`.

## Output Structure
Emits findings prefixed with `FR-` adhering to the marketplace findings schema:
- `id`: e.g., `FR-001`, `FR-002`
- `category`: `"discoverability"`
- `title`: Problem title (e.g., "No freshness/last-updated signal found")
- `severity`: `"critical"`, `"high"`, `"medium"`, `"low"`, or `"info"`
- `evidence`: Specific timestamp data or corroboration domain counts
- `suggested_action`: Actionable guidance for structured metadata and external PR/citation building

