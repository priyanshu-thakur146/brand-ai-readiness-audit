---
name: structured-data-audit
description: >
  Extracts and validates machine-readable structured data from a web page,
  including JSON-LD, Schema.org, Open Graph, microdata, and RDFa.
  Identifies missing, incomplete, or invalid structured information.
dependencies:
  - structured-data-audit
---

# Structured Data Audit

## Purpose

Determine whether important entities and facts on a page are represented in
**machine-readable structured data** that AI systems, search engines, and
social platforms can consume directly.

## When to Use

Invoke this skill when you need to answer:

* Does the page have JSON-LD / Schema.org structured data?
* Are the structured data entries valid and complete?
* Does the page include Open Graph metadata?
* Is there a mismatch between visible content and structured data?

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit |

## Outputs

A JSON array of **findings**, each containing:

```json
{
  "id":    "SDA-001",
  "title": "Short description of the issue",
  "severity": "critical | high | medium | low | info",
  "category": "structured-data",
  "evidence": "Observable, verifiable evidence.",
  "suggested_action": {
    "summary": "What the site owner should do.",
    "priority": "high | medium | low"
  }
}
```

## Procedure

### Step 1 — Fetch the page

Fetch the target URL and extract the raw HTML.

### Step 2 — Extract structured data

Use the helper script to extract all structured data formats:

```bash
python scripts/schema_check.py <url>
```

The script uses `extruct` (with a `BeautifulSoup` fallback) to pull:
- JSON-LD blocks
- Open Graph meta tags
- Microdata
- RDFa

### Step 3 — Validate JSON-LD

For each JSON-LD block, check:

* Is `@context` set to `https://schema.org`?
* Is `@type` a recognised Schema.org type?
* Are required properties present (`name`, `description`, `url`)?
* Are there important types missing given the page content?
  (e.g. a product page without `Product` schema)

### Step 4 — Validate Open Graph

Check for the four required Open Graph tags:

* `og:title`
* `og:type`
* `og:url`
* `og:image`

Flag missing or empty values.

### Step 5 — Check meta tags

Verify:
* `<title>` is present and 10–70 characters
* `<meta name="description">` is present and 50–160 characters

### Step 6 — Cross-check with visible content

Where possible, compare structured data values against visible page content
to identify inconsistencies (e.g. different names, missing descriptions).

### Step 7 — Compile findings

Collect all findings with concrete evidence (what was found, what was missing,
what the values were).

## References

The script `scripts/schema_check.py` handles extraction and basic validation.
The skill agent should use its judgement to add contextual findings beyond
what the script detects.