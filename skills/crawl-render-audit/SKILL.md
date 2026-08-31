---
name: crawl-render-audit
description: >
  Audits whether a website's content is accessible to automated crawlers and
  identifies differences between server-delivered HTML and JavaScript-rendered DOM.
  Checks robots.txt, sitemap.xml, HTTP status codes, and raw-vs-rendered content gaps.
dependencies:
  - crawl-render-audit
---

# Crawl & Render Audit

## Purpose

Determine whether important website content is **reachable and readable** by
automated systems (search-engine bots, AI agents, feed readers).

A page that looks complete to a human in a browser may be invisible or
substantially different when fetched as raw HTML.  This skill detects those gaps.

## When to Use

Invoke this skill when you need to answer:

* Can bots crawl the site?  (`robots.txt` / HTTP status)
* Is there a sitemap?
* Does important content require JavaScript to appear?
* Are there meaningful differences between raw HTML and rendered DOM?

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit (e.g. `https://example.com`) |

## Outputs

A JSON array of **findings**, each containing:

```json
{
  "id":    "CRA-001",
  "title": "Short description of the issue",
  "severity": "critical | high | medium | low | info",
  "category": "crawl-render",
  "evidence": "Observable, verifiable evidence.",
  "suggested_action": {
    "summary": "What the site owner should do.",
    "priority": "high | medium | low"
  }
}
```

## Procedure

### Step 1 — Resolve the base URL

Normalise the input URL to include the scheme (`https://` default).
Extract the domain for robots / sitemap checks.

### Step 2 — Check robots.txt

Fetch `{origin}/robots.txt`.

* If missing (404/timeout) → **info** finding: no robots.txt found.
* If present, check whether important paths are disallowed for common
  bot user-agents (`*`, `Googlebot`, `GPTBot`, `anthropic-ai`,
  `CCBot`, `ChatGPT-User`).
* Any broad `Disallow: /` → **critical** finding.
* Selective disallows on important paths → **high** finding.

### Step 3 — Check sitemap.xml

Fetch `{origin}/sitemap.xml` (also check robots.txt for `Sitemap:` directives).

* Missing sitemap → **medium** finding.
* Sitemap present but contains errors or zero URLs → **high** finding.
* Sitemap present and valid → no finding.

### Step 4 — Fetch raw HTML and check HTTP status

Fetch the target URL with `requests`.

* Non-200 status → **critical** finding.
* Redirect chains longer than 3 hops → **medium** finding.
* Missing or weak `Content-Type` → **low** finding.
* Record the raw HTML text content (visible text stripped from tags).

### Step 5 — Render with headless browser

Use the helper script `scripts/render_diff.py` to:

1. Fetch raw HTML text via `requests`.
2. Render the page with Playwright (headless Chromium).
3. Extract visible text from the rendered DOM.
4. Compute the difference.

```bash
python scripts/render_diff.py <url>
```

The script outputs JSON with `raw_text_length`, `rendered_text_length`,
`diff_ratio`, and `added_blocks` (text present only after rendering).

### Step 6 — Evaluate render diff

* If `diff_ratio` > 0.40 (rendered page has 40%+ more text than raw) →
  **high** finding: significant content hidden behind JavaScript.
* If `diff_ratio` between 0.15 and 0.40 → **medium** finding.
* If specific important blocks (navigation, pricing, product info) appear
  only in rendered text → note in evidence.

### Step 7 — Compile findings

Collect all findings from Steps 2–6 into the output JSON array.  Each
finding must include concrete evidence (URLs fetched, status codes received,
character counts, diff ratios) rather than generic statements.

## References

See `references/checklist.md` for the full signal checklist used by this skill.