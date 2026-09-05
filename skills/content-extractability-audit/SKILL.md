---
name: content-extractability-audit
description: >
  Examines whether important information on a web page can be clearly extracted
  by automated systems. Checks heading quality, alt text, semantic markup,
  text structure, and whether key facts are explicit and accessible.
dependencies:
  - content-extractability-audit
---

# Content Extractability Audit

## Purpose

Determine whether the **important facts** on a page are **explicit, readable,
and easy to identify** by automated systems.  Content that is visible to a
human is not necessarily equally accessible to AI agents or search engines.

## When to Use

Invoke this skill when you need to answer:

* Are headings clear and hierarchical?
* Do images have meaningful alt text?
* Is important information buried in images, PDFs, or non-text elements?
* Does the page use semantic HTML landmarks?
* Can key facts (name, contact, pricing) be extracted as plain text?

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit |

## Outputs

A JSON array of **findings**, each containing:

```json
{
  "id":    "CEA-001",
  "title": "Short description of the issue",
  "severity": "critical | high | medium | low | info",
  "category": "content-extractability",
  "evidence": "Observable, verifiable evidence.",
  "suggested_action": {
    "summary": "What the site owner should do.",
    "priority": "high | medium | low"
  }
}
```

## Procedure

### Step 1 — Fetch the page

Fetch the target URL and parse the HTML with BeautifulSoup.

### Step 2 — Heading quality

Check:
* Exactly one `<h1>` present
* Heading hierarchy is sequential (h1 → h2 → h3, no skips)
* Headings contain meaningful text (not "Section 1" or empty)
* Headings are 3–100 characters

### Step 3 — Image accessibility

For every `<img>` tag:
* Check for non-empty `alt` attribute
* Check that alt text is descriptive (> 5 chars, not just "image" or a filename)
* Calculate percentage of images with meaningful alt text
* Flag if < 50% have alt text (high), < 80% (medium)

### Step 4 — Text structure

Analyse:
* **Text-to-markup ratio**: visible text ÷ total HTML size.  Below 0.10 → medium
* **Paragraph quality**: average paragraph length > 20 words
* **Language attribute**: `<html lang="...">` is set

### Step 5 — Semantic landmarks

Check for:
* `<header>`, `<main>`, `<nav>`, `<footer>` elements
* `<article>` for long-form content
* `<title>` tag present and descriptive
* `<meta name="description">` present

### Step 6 — Fact extractability

Look for:
* Contact information (phone, email, address) as text, not only in images
* Key facts (pricing, hours, locations) as text
* Brand / product name appears explicitly in text (not only logo image)

### Step 7 — Link quality

Check:
* Links have descriptive text (not "click here" or "read more")
* Internal anchor links (`#section`) point to existing IDs

### Step 8 — Compile findings

Aggregate all findings with evidence.  Reference `references/heuristics.md`
for the complete heuristic list and severity mappings.

## References

See `references/heuristics.md` for the full heuristics table.