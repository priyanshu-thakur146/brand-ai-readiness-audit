---
name: structured-data-audit
description: Checks whether a page states its key facts in a form a machine can unambiguously extract — valid JSON-LD/schema.org markup, meta title/description, Open Graph tags, and plain-text presence of core facts like name/price/address/hours. Use this on any page whose facts (product, organization, article) an AI assistant might need to quote.
license: MIT
allowed-tools: [bash, python]
---

# Structured Data Audit

## When to use
Use after `crawl-render-audit` confirms the page is reachable and readable. This corresponds to
Appendix C of the brief: the more explicitly and unambiguously a fact is stated in plain, readable
text or standard markup, the more likely a machine extracts it correctly.

## Inputs
- `url` (required)
- `timeout` (optional, default 15s)

## Procedure
1. Fetch the page and parse all `<script type="application/ld+json">` blocks.
2. For each block, verify it is valid JSON, uses `"@context": "https://schema.org"`, and has a
   recognized `@type` (Organization, Product, Article, FAQPage, LocalBusiness, BreadcrumbList, etc.).
   Flag pages with zero valid JSON-LD as a high-severity discoverability gap.
3. Check `<title>` and `<meta name="description">` — flag if missing, empty, or generic
   (e.g. "Home", boilerplate CMS defaults).
4. Check Open Graph (`og:title`, `og:description`, `og:image`) and Twitter Card tags — these are
   what many assistants/aggregators use for quick summaries and previews.
5. Scan visible text for plain-text presence of core identity facts (name, address, phone, hours,
   price) using pattern heuristics, and flag when such facts appear to exist only inside an image,
   a canvas element, or a downloadable PDF with no corresponding text equivalent.
6. Emit findings via `scripts/structured_data_check.py`.

## Output
Findings with `id` prefixed `SD-`, following the shared schema.
