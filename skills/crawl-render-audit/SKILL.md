---
name: crawl-render-audit
description: Checks whether a website can even be reached and read by a crawler in the first place — robots.txt / meta-robots blocks, sitemap presence, response health, and whether the page's real content only exists after client-side JavaScript runs (a render gap that leaves crawlers and AI fetchers seeing an empty shell). Use this first, before any other content-level check, since a page that fails to load or render has nothing else worth auditing.
license: MIT
allowed-tools: [bash, python]
---

# Crawl & Render Audit

## When to use
Use as the first check in any AI-discoverability audit. This corresponds to Appendix A/C of the
brief: for a page to be visible to a machine at all, the crawler must (1) be let in, and (2) be able
to read what's on the page. This skill tests both gates.

## Inputs
- `url` (required): the site or page to audit.
- `timeout` (optional, default 15s): request timeout.

## Procedure
1. Fetch `/robots.txt`. Parse it for `Disallow` rules that would block the homepage or the whole
   site for common AI/search agents (`*`, `Googlebot`, `GPTBot`, `ClaudeBot`, `PerplexityBot`, etc.).
2. Fetch `/sitemap.xml` (and check robots.txt for a `Sitemap:` line). Flag if missing — sitemaps are
   a cheap, high-leverage signal that helps crawlers find and prioritize pages.
3. Fetch the homepage. Record status code, response latency, and any `X-Robots-Tag` header or
   `<meta name="robots" content="noindex">` tag that would exclude the page from indexing.
4. Check for a canonical link (`<link rel="canonical">`) — its absence lets duplicate/parameterized
   URLs fragment authority for the same content.
5. Estimate the render gap: strip `<script>`/`<style>` from the raw HTML and measure how much
   readable text remains. Cross-check for known SPA shell patterns (`id="root"`, `id="__next"`,
   `id="app"`) paired with very little body text — a strong signal the real content is assembled by
   JavaScript after load and is invisible to crawlers/fetchers that don't execute JS. Also check for
   a `<noscript>` fallback that would mitigate this.
6. Emit one finding per problem found (with evidence + severity) run via `scripts/crawl_render_check.py`.

## Output
A list of findings following the marketplace's shared schema (see the entrypoint skill), each with
`id` prefixed `CR-`, `title`, `severity`, `evidence`, and `suggested_action`.
