# Crawl & Render — Signal Checklist

This checklist enumerates the signals inspected by the **crawl-render-audit**
skill.  The agent should evaluate every applicable signal and skip those that
do not apply to the target page.

---

## Crawlability Signals

| # | Signal | What to check | Severity if failing |
|---|--------|---------------|---------------------|
| 1 | `robots.txt` exists | `{origin}/robots.txt` returns 200 | info |
| 2 | Broad bot blocks | `Disallow: /` for `*` or major AI/search bots | critical |
| 3 | Selective blocks | Important paths disallowed | high |
| 4 | AI-bot-specific blocks | Explicit blocks for `GPTBot`, `ChatGPT-User`, `anthropic-ai`, `CCBot`, `Google-Extended` | high |
| 5 | `X-Robots-Tag` header | `noindex` or `nofollow` in HTTP headers | high |
| 6 | Meta robots tag | `<meta name="robots" content="noindex">` in HTML | high |

## Sitemap Signals

| # | Signal | What to check | Severity if failing |
|---|--------|---------------|---------------------|
| 7 | Sitemap exists | `{origin}/sitemap.xml` or `Sitemap:` in robots.txt | medium |
| 8 | Sitemap parseable | Valid XML with `<loc>` entries | high |
| 9 | Sitemap freshness | `<lastmod>` dates are recent (< 1 year) | low |

## HTTP & Access Signals

| # | Signal | What to check | Severity if failing |
|---|--------|---------------|---------------------|
| 10 | HTTP status | Target URL returns 200 | critical |
| 11 | Redirect depth | Fewer than 4 redirects | medium |
| 12 | HTTPS | Page served over HTTPS | medium |
| 13 | Canonical tag | `<link rel="canonical">` present and correct | low |

## Rendering Signals

| # | Signal | What to check | Severity if failing |
|---|--------|---------------|---------------------|
| 14 | JS-dependent content | Diff ratio between raw HTML text and rendered text | high (> 40%), medium (15-40%) |
| 15 | Critical content in JS | Navigation, headings, pricing only in rendered DOM | high |
| 16 | Noscript fallback | `<noscript>` provides meaningful fallback content | low |
| 17 | Empty body | Raw `<body>` contains minimal or no text | critical |