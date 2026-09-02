---
name: engagement-audit
description: Checks the on-site engagement half of the problem — whether a visitor who does arrive (human or agent-driven browsing) can navigate, act, and stay: mobile viewport config, presence of clear navigation and calls-to-action, broken internal links, and page weight/load speed. Use this to cover 'why visitors bounce' rather than 'why they never arrive'.
license: MIT
allowed-tools: [bash, python]
---

# Engagement Audit

## When to use
Use alongside the discoverability skills — a marketplace audit isn't complete without this half.
This covers the on-site engagement side of the brief's Round-2 scope: keeping the visitor once they
arrive, not just getting them to arrive.

## Inputs
- `url` (required)
- `timeout` (optional, default 15s)
- `max_links_checked` (optional, default 8): number of sampled internal links to check for breakage.

## Procedure
1. Check for a mobile viewport meta tag — its absence causes poor mobile rendering, a major bounce
   driver.
2. Check for a `<nav>` (or role="navigation") element with multiple internal links — a page with no
   discoverable navigation traps visitors on a single page.
3. Scan for clear calls-to-action: buttons/links with actionable text ("sign up", "contact",
   "buy", "get started", "book", "subscribe", "download").
4. Sample internal links found on the homepage (up to `max_links_checked`) and check their status
   codes — broken internal links are a direct, low-effort-to-fix engagement killer.
5. Estimate page weight (bytes transferred for the HTML document) and response latency as a rough
   proxy for load-speed-driven bounce risk.
6. Check for a basic 404/error-page situation: if the homepage itself is unusually thin/broken,
   flag it (though `crawl-render-audit` also partially covers page health).
7. Emit findings via `scripts/engagement_check.py`.

## Output
Findings with `id` prefixed `EN-`, following the shared schema.
