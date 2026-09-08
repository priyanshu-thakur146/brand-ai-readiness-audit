---
name: freshness-corroboration-audit
description: Audits content-recency signals (Last-Modified header, article:modified_time, JSON-LD dateModified, visible "last updated" text) and, when agent-gathered web-search evidence is supplied, scores how many independent third-party domains corroborate a brand's key claims. Detects stale or missing timestamps on time-sensitive content (pricing, job openings, events) and single-source, uncorroborated claims that an AI assistant is more likely to omit or flag as unreliable. Use when a site's facts look technically fine but still seem to be under-trusted or dropped by AI answers.
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# `skills/freshness-corroboration-audit/` — Recency & Cross-Source Trust Audit

## When to use
Use this skill to check the two things Round-2's background material calls out as trust signals
that live *outside* any single page's HTML quality: (1) is the content demonstrably current, and
(2) does the wider web agree with what the brand says about itself? A claim that only exists on
the brand's own homepage, with no independent corroboration and no visible update date, is
fragile even if it's perfectly structured and perfectly readable.

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page URL to evaluate. |
| `timeout` | no | Max request timeout in seconds (default `15`). |
| `search_results` | no | Agent-gathered web-search evidence, e.g. `{"claims": [{"claim": "founded in 2015", "corroborating_domains": ["crunchbase.com", "techcrunch.com"]}, {"claim": "HQ in Austin, TX", "corroborating_domains": []}]}`. |

## Procedure (numbered, deterministic steps)
1. **On-page timestamp extraction** — check the `Last-Modified` HTTP header, `<meta
   property="article:modified_time">`, JSON-LD `dateModified`, and visible "last updated" text on
   the page.
2. **Staleness evaluation** — flag timestamps that are implausibly old for content that's supposed
   to be time-sensitive (a pricing page, a jobs/careers listing, an events calendar). Missing
   recency signals entirely on such pages is flagged even without a stale date to point to.
3. **Corroboration scoring** — when `search_results` is supplied, score each claim by how many
   independent domains corroborate it: 0 domains = fragile/unverifiable, 1 = weakly supported,
   2+ = well-corroborated. This directly encodes the Round-2 principle that machines trust facts
   repeated consistently across unrelated sources far more than a claim living in one place.
4. **Transparent fallback** — if no `search_results` file is supplied, the skill does not silently
   skip this half of its job: it emits an explicit `info`-level finding stating that cross-source
   corroboration was not performed for this run, so the report never implies a check happened when
   it didn't.
5. **Emit findings** via `scripts/freshness_check.py` (a site-level check, run once against the
   homepage by the orchestrator, not part of the per-page serial crawl).

## Output
Findings prefixed `FR-`, each with `id`, `category: "discoverability"`, `title`, `severity`
(`critical`/`high`/`medium`/`low`/`info`), `evidence` (specific timestamps or corroboration domain
counts), and `suggested_action` covering both structured-metadata fixes and external PR/citation
building.
