---
name: structured-data-audit
description: Audits whether a page presents its core facts in a machine-readable format an AI extractor can trust — schema.org JSON-LD blocks (Organization, Product, Article, FAQPage, LocalBusiness, BreadcrumbList), meta title/description, Open Graph and Twitter Card preview tags, and plain-text presence of key business facts (phone, hours, pricing). Use when diagnosing why a page's facts are missed or misquoted by AI assistants even though the page is fully crawlable.
license: MIT
allowed-tools: [bash, python]
---

# `skills/structured-data-audit/` — Machine-Readable Metadata Audit

> Marketplace: `brand-ai-readiness-audit` · Called by: `audit-orchestrator` (page-level check, run
> serially across every discovered page)
> Script: `scripts/structured_data_check.py`

## When to use
Use once a page is confirmed reachable and readable (see `crawl-render-audit`). This skill
answers the next question in the pipeline: given readable text, is the specific fact an assistant
would want to quote actually structured enough to extract with confidence, or does the assistant
have to infer it from unstructured prose?

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page URL to evaluate. |
| `timeout` | no | Max request timeout in seconds (default `15`). |

## Procedure (numbered, deterministic steps)
1. **Extract every `<script type="application/ld+json">` block** and attempt to parse each as
   JSON. Zero valid blocks → `high`-severity finding (the page has no machine-readable identity
   at all). Invalid/malformed JSON-LD is flagged separately from "none present."
2. **Cross-check schema types** found (`@type`) against the business-relevant vocabulary
   (`Organization`, `Product`, `Article`, `LocalBusiness`, `FAQPage`, `BreadcrumbList`, etc.) —
   present-but-irrelevant markup (e.g. only `BreadcrumbList`, nothing describing the entity or
   offer itself) is treated as a gap, not a pass.
3. **Audit `<title>`, `<meta name="description">`, and Open Graph tags** (`og:title`,
   `og:description`, `og:image`) — the fields conversational assistants most commonly reuse
   verbatim when generating a citation/preview. Missing, empty, or generic placeholder values
   ("Home", "Untitled") are flagged.
4. **Scan visible plain text** with targeted regex heuristics for essential facts — phone number,
   opening hours, price — that a brand would want an assistant to be able to quote directly.
   A fact that exists only inside an image, a canvas element, or a PDF does not count as present
   for this check (see `fact-extractability-audit` for the deeper version of that problem).
5. **Emit findings** via `scripts/structured_data_check.py`, called once per page by the
   orchestrator's serial page-crawling loop (never all discovered pages at once) — see
   `skills/audit-orchestrator/SKILL.md` for how per-page results are aggregated across the site.

## Output
Findings prefixed `SD-`, each with `id`, `category: "discoverability"`, `title`, `severity`
(`critical`/`high`/`medium`/`low`), `evidence` (counts of valid JSON-LD blocks / meta tags found),
and `suggested_action` with a `summary` and `priority` aimed at a web development team.
