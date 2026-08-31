---
name: freshness-corroboration-audit
description: >
  Investigates whether important brand facts are current, consistent,
  externally corroborated, and clearly associated with the correct entity.
  Checks date signals, sameAs identity, social links, and content freshness.
dependencies:
  - freshness-corroboration-audit
---

# Freshness & Corroboration Audit

## Purpose

Determine whether the information on a page is **current, consistent, and
externally supported**.  Information repeated consistently across independent
sources provides stronger support than a claim that exists in only one place.

## When to Use

Invoke this skill when you need to answer:

* Is the content up-to-date?
* Are there machine-readable freshness signals (dates, Last-Modified)?
* Does the page link to authoritative external profiles?
* Is entity identity clear and verifiable (sameAs, social profiles)?
* Is the copyright year current?

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit |

## Outputs

A JSON array of **findings**, each containing:

```json
{
  "id":    "FCA-001",
  "title": "Short description of the issue",
  "severity": "critical | high | medium | low | info",
  "category": "freshness-corroboration",
  "evidence": "Observable, verifiable evidence.",
  "suggested_action": {
    "summary": "What the site owner should do.",
    "priority": "high | medium | low"
  }
}
```

## Procedure

### Step 1 — Fetch the page

Fetch the target URL.  Record HTTP response headers, especially:
* `Last-Modified`
* `ETag`
* `Cache-Control`

### Step 2 — Check HTTP freshness headers

Use the helper script:

```bash
python scripts/corroborate.py <url>
```

The script checks:
* Presence of `Last-Modified` header
* HTTP freshness signals

### Step 3 — Extract structured date information

From JSON-LD:
* `datePublished`
* `dateModified`
* `dateCreated`

From meta tags:
* `article:published_time`
* `article:modified_time`

Flag if no machine-readable dates are found.

### Step 4 — Check copyright year

Look for copyright notices in the page footer.
* If copyright year is > 1 year behind current year → low finding.

### Step 5 — Check entity identity signals

Look for:
* `sameAs` links in JSON-LD (to Wikipedia, social profiles, Wikidata)
* Links to social media profiles on the page
* Canonical URL tag

Flag if no external identity references exist.

### Step 6 — Assess corroboration potential

The agent should use its judgement to assess:
* Whether the brand name is unique or ambiguous
* Whether visible claims (awards, certifications, statistics) could
  benefit from external source links
* Whether the site mentions partnerships or affiliations without linking
  to the partner's site

### Step 7 — Compile findings

Collect all findings with concrete evidence.

## References

The script `scripts/corroborate.py` handles automated checks.
The agent should supplement with contextual analysis.