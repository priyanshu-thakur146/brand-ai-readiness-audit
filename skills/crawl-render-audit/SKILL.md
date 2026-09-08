---
name: crawl-render-audit
description: Audits whether a website can actually be reached, indexed, and read by AI crawlers and search engines. Checks robots.txt access rules for AI-agent user agents, XML sitemap discoverability, HTTP status/latency, noindex directives (meta + X-Robots-Tag), canonical link tags, and a JS render-gap heuristic that flags content trapped behind unrendered client-side JavaScript (SPA shells). Uses an adaptive dual-engine architecture — headless Playwright Chromium when available, with an automatic zero-crash fallback to static HTTP parsing. Use when diagnosing why a site is invisible to AI fetchers before any content-quality question even applies.
license: MIT
allowed-tools: [bash, python]
---

# `skills/crawl-render-audit/` — Crawlability & JS-Render-Gap Audit

> Marketplace: `brand-ai-readiness-audit` · Called by: `audit-orchestrator` (site-level check)
> Script: `scripts/crawl_render_check.py`

## When to use
Use this skill first, conceptually: per the Round-2 background (crawl → read → extract, in that
order), if a crawler can't get in or can't read the page, nothing downstream — structured data,
fact clarity, freshness — matters. Use this skill to answer "can an AI fetcher even see this
site at all?" for a homepage or any single page.

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page or domain to evaluate. |
| `timeout` | no | Max request/render timeout in seconds (default `15`). |

## Procedure (numbered, deterministic steps)
1. **Robots accessibility** — fetch `/robots.txt`; parse `User-agent` blocks and flag a `critical`
   finding if `Disallow: /` blocks `*` or a named AI agent (`GPTBot`, `ClaudeBot`,
   `PerplexityBot`, `Google-Extended`, `Googlebot`). Missing/unreachable `robots.txt` is a `low`/
   `medium` finding, not fatal on its own.
2. **Sitemap discoverability** — check `Sitemap:` in `robots.txt` and `/sitemap.xml` directly;
   flag `medium` if neither resolves to a valid `<urlset>`/`<sitemapindex>`.
3. **Fetch the page with the dual-engine renderer** (see below) and check:
   - HTTP status (`critical` if unreachable or ≥400),
   - server latency (`medium` if TTFB > 3s — slow responses risk crawler timeouts/deprioritization),
   - `X-Robots-Tag` response header and `<meta name="robots">` for `noindex` (`critical` either way),
   - a self-referencing `<link rel="canonical">` (`low` if absent — avoids duplicate-content
     ambiguity across parameterized URLs).
4. **JS render-gap heuristic** — strip `<script>/<style>/<noscript>`, count visible words in the
   raw response. If word count is very low (<15) or low (<50) **and** a known SPA shell root
   (`#root`, `#__next`, `#app`, `#___gatsby`, `#app-root`) is present, flag `critical`: the brand's
   real content only exists after client-side JavaScript runs, so a fetcher that doesn't execute
   JS gets nothing. 50–150 words is flagged `medium` ("thin visible text") without assuming an SPA
   is the cause. The finding records which rendering engine actually produced the word count and
   whether a substantive `<noscript>` fallback exists as partial mitigation.
5. **Proactive check (always runs, independent of any defect)** — probe `/llms.txt`, the emerging
   plain-text index convention for AI agents; if absent, emit an `info`-severity proactive
   suggestion (never counted as a "problem" in the summary) rather than a graded finding.

### Adaptive dual-engine rendering
This is the skill's core engineering feature:
1. **Engine 1 — headless Playwright Chromium.** If `playwright` is installed, launch headless
   Chromium with a real browser `User-Agent`, navigate with `wait_until="domcontentloaded"`, and
   read `page.content()` — i.e. the DOM *after* JavaScript has run, exactly what a JS-executing AI
   crawler would see.
2. **Engine 2 — static HTTP fallback.** If Playwright isn't installed, the binaries aren't
   present in the sandbox, or the launch throws for any reason, the exception is caught silently
   and the check falls back to a plain `requests.get()` (retried once with a browser `User-Agent`
   if the first attempt looks blocked or truncated) and parses the raw HTML with BeautifulSoup —
   i.e. exactly what a non-JS-executing crawler would see.

Running both perspectives — "what a JS-aware fetcher sees" vs. "what a plain HTTP fetcher sees" —
is what makes the render-gap check meaningful: the gap *between* those two views is the actual
signal, and the dual-engine design means the check degrades gracefully (never crashes the audit)
in a sandbox that lacks browser binaries while still using the more capable engine whenever it's
available.

## Output
Findings prefixed `CR-` (or `CR-P-` for proactive), each with `id`, `category: "discoverability"`,
`title`, `severity`, `evidence` (status codes, word counts, which render engine was used), and
`suggested_action` with a `summary` and `priority`.
