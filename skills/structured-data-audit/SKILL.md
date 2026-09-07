---
name: structured-data-audit
description: Audits whether a website presents core brand facts in a machine-readable format that AI engines can extract with high confidence. Validates schema.org JSON-LD blocks, meta title/description tags, Open Graph previews, and scans visible text for key business facts (contact info, pricing, opening hours).
license: MIT
allowed-tools: [bash, python]
---

# Structured Data Audit

## Overview & Purpose
AI models and search engines prioritize facts that are explicitly structured over implied or unformatted text. When product details, pricing, organization identity, or article metadata lack machine-readable schema markup, AI assistants are forced to infer information — leading to misquoting or omission in AI summaries.

The **Structured Data Audit** skill inspects pages to ensure all key facts are backed by valid schema.org JSON-LD blocks and rich meta tags, maximizing machine extractability.

## Key Technical Features
- **JSON-LD Schema Validation**: Parses all `<script type="application/ld+json">` blocks, validating `@context`, valid JSON syntax, and target entity types (`Organization`, `Product`, `Article`, `FAQPage`, `LocalBusiness`, `BreadcrumbList`).
- **Metadata Coverage Analysis**: Inspects primary SEO title tags, meta descriptions, Open Graph (`og:title`, `og:description`, `og:image`), and Twitter Cards used by conversational AI agents for generating preview citations.
- **Plain-Text Fact Presence Check**: Scans body text using regex heuristics to confirm that essential business facts (contact phone numbers, opening hours, prices) exist in readable plain text rather than being trapped in images, canvas elements, or PDFs.

## Input Parameters
- `url` *(required)*: The target page URL to evaluate.
- `timeout` *(optional)*: Maximum request timeout in seconds (defaults to 15s).

## Diagnostic Procedure
1. **JSON-LD Extraction**: Extracts and parses all embedded JSON-LD blocks on the page. Flag missing or invalid JSON-LD as a high-severity discoverability gap.
2. **Schema Type Verification**: Cross-checks recognized schema.org types against expected business types (`Organization`, `Product`, `Article`, `LocalBusiness`).
3. **Meta & Open Graph Audit**: Evaluates `<title>`, `<meta name="description">`, and Open Graph tags for missing, empty, or generic default strings (e.g., "Home", "Untitled").
4. **Fact Availability Check**: Scans plain text for contact numbers, opening hours, and pricing signals. Flags instances where facts are absent from prose or trapped inside non-text elements.
5. **Execution**: Emits structured findings via `scripts/structured_data_check.py`.

## Output Structure
Emits findings prefixed with `SD-` adhering to the marketplace findings schema:
- `id`: e.g., `SD-001`, `SD-002`
- `category`: `"discoverability"`
- `title`: Problem title (e.g., "No JSON-LD structured data on the page")
- `severity`: `"critical"`, `"high"`, `"medium"`, or `"low"`
- `evidence`: Empirical count of valid JSON-LD blocks and meta tags found
- `suggested_action`: Targeted remediation advice for web development teams

