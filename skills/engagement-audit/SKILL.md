---
name: engagement-audit
description: Audits on-site engagement and retention barriers for visitors who do land on the page — mobile viewport configuration, presence of a structured <nav> landmark, call-to-action phrase prominence, a sample of internal links checked for broken (404) status, and page weight/latency as a bounce-risk proxy. Use when a brand is being found and cited well but visitors who click through still don't stay or convert — the "on-site engagement" half of the Round-2 problem, distinct from the discoverability checks.
license: MIT
allowed-tools: [bash, python]
---

# `skills/engagement-audit/` — On-Site Engagement Audit

## When to use
Every other skill in this marketplace targets **off-site discoverability** — getting an AI
assistant or crawler to find and cite the brand at all. This skill targets the other half of the
Round-3 brief: once a visitor (human or an AI agent browsing on a user's behalf) actually clicks
through, does the page itself give them a reason and a way to stay? Use it whenever discoverability
looks fine but engagement or conversion still seems weak.

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page URL to evaluate. |
| `timeout` | no | Max request timeout in seconds (default `15`). |
| `max_links_checked` | no | Number of internal links sampled for a broken-link check (default `8`). |

## Procedure (numbered, deterministic steps)
1. **Mobile viewport check** — verify `<meta name="viewport" content="width=device-width,
   initial-scale=1">` is present; its absence means mobile visitors (an increasing share of
   AI-assistant-driven traffic) land on an unresponsive layout.
2. **Navigation landmark check** — look for a `<nav>` element or `role="navigation"` region
   containing real internal links; a page with no discoverable navigation traps a visitor on a
   single page with no obvious next step.
3. **Call-to-action prominence** — scan buttons and anchors for high-intent action phrasing
   ("sign up", "get started", "contact us", "buy now", "book demo", "subscribe", "download");
   their complete absence is flagged as a conversion barrier.
4. **Broken-link sampling** — sample up to `max_links_checked` internal links and issue read-only
   HEAD/GET requests to detect 404s that interrupt a visitor's journey mid-page. This is a bounded
   sample, not an exhaustive site crawl, so it stays fast and non-disruptive to the target server.
5. **Load-latency and weight assessment** — use response byte size and TTFB as inexpensive proxies
   for bounce risk from slow-loading pages.
6. **Emit findings** via `scripts/engagement_check.py` (a site-level check, run once against the
   homepage by the orchestrator).

## Output
Findings prefixed `EN-`, each with `id`, `category: "engagement"`, `title`, `severity`
(`critical`/`high`/`medium`/`low`), `evidence` (missing tags, sampled broken-link URLs), and
`suggested_action` with concrete UX/technical fixes aimed at improving visitor retention.
