---
name: engagement-audit
description: >
  Analyses the visitor experience after arriving at a website.  Checks page
  performance, navigation structure, content hierarchy, calls-to-action,
  and friction between arriving and taking meaningful action.
dependencies:
  - engagement-audit
---

# Engagement Audit

## Purpose

Even when AI systems successfully surface a brand, the visitor still has to
**interact with the website**.  This skill inspects the experience from
arrival to action.

## When to Use

Invoke this skill when you need to answer:

* Is the page fast enough to retain visitors?
* Can visitors orient themselves quickly (navigation, landmarks)?
* Is content hierarchy clear (headings, structure)?
* Are there clear calls-to-action?
* Is the page mobile-friendly?

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit |

## Outputs

A JSON array of **findings**, each containing:

```json
{
  "id":    "EA-001",
  "title": "Short description of the issue",
  "severity": "critical | high | medium | low | info",
  "category": "engagement",
  "evidence": "Observable, verifiable evidence.",
  "suggested_action": {
    "summary": "What the site owner should do.",
    "priority": "high | medium | low"
  }
}
```

## Procedure

### Step 1 — Fetch with timing

Use the helper script:

```bash
python scripts/perf_check.py <url>
```

The script fetches the page and measures response time, HTML size, and
resource counts.

### Step 2 — Performance analysis

Check:
* **Response time**: > 3s = high, > 1s = medium
* **HTML size**: > 500 KB = medium
* **Resource count**: > 80 resources (scripts + CSS + images) = medium
* **Viewport meta**: missing = high (not mobile-friendly)

### Step 3 — Navigation structure

Check:
* `<nav>` element presence
* Total link count (0 links = high severity)
* Semantic landmarks: `<header>`, `<main>`, `<footer>`
* Skip navigation link for accessibility

### Step 4 — Content hierarchy

Check:
* H1 count (exactly 1 is ideal)
* Heading hierarchy (no skipped levels)
* Whether headings are descriptive

### Step 5 — Calls-to-action

Look for:
* Buttons (`<button>`)
* Form submit inputs
* Links with action words (buy, sign up, contact, get started, etc.)
* Forms

Flag if zero CTAs are found.

### Step 6 — Mobile and accessibility basics

Check:
* Viewport meta tag
* Touch-friendly link/button sizing (if detectable from CSS)
* Font size declarations that are not too small

### Step 7 — Compile findings

Collect all findings with measurable evidence (timing, counts, presence/absence).

## References

The script `scripts/perf_check.py` handles automated performance and
structure checks.  The agent should supplement with contextual observations.