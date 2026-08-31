---
name: audit-orchestrator
description: >
  The single entrypoint for the Brand AI Readiness Audit marketplace.
  Receives a target URL, coordinates all five specialist audit skills,
  merges their findings, deduplicates, normalises severity, and produces
  one consolidated JSON audit report.
dependencies:
  - audit-orchestrator
  - crawl-render-audit
  - structured-data-audit
  - content-extractability-audit
  - freshness-corroboration-audit
  - engagement-audit
---

# Audit Orchestrator — Entrypoint

## Purpose

This is the **only entrypoint** in the Brand AI Readiness Audit marketplace.

It coordinates all five specialist skills and produces **one consolidated
audit report** that answers:

> *"What is preventing this brand from being clearly discovered, understood,
> trusted, and engaged with — and what should be done next?"*

## When to Use

Invoke this skill whenever a user requests a website audit.  You do **not**
need to invoke the specialist skills directly — this orchestrator handles
all coordination.

## Inputs

| Parameter | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `url`     | string | yes      | The target URL to audit (e.g. `https://example.com`) |

## Outputs

A single JSON report matching this schema:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0,
    "info": 0
  },
  "findings": [
    {
      "id": "F-001",
      "title": "Description of the finding",
      "severity": "high",
      "category": "crawl-render",
      "evidence": "Observable evidence supporting the finding.",
      "suggested_action": {
        "summary": "What should be changed and how.",
        "priority": "high"
      }
    }
  ]
}
```

## Procedure

### Step 1 — Validate the input URL

Normalise the URL (add `https://` if missing).  Extract the domain for
the report's `site` field.

### Step 2 — Run all five specialist audits

Invoke each specialist skill in sequence (or in parallel if the runtime
supports it).  Each skill has a helper script that can be run directly:

#### 2a. Crawl & Render Audit

```bash
python skills/crawl-render-audit/scripts/render_diff.py <url>
```

Checks crawlability, robots.txt, sitemap, HTTP status, and
raw-vs-rendered content differences.

#### 2b. Structured Data Audit

```bash
python skills/structured-data-audit/scripts/schema_check.py <url>
```

Extracts and validates JSON-LD, Open Graph, microdata, and RDFa.

#### 2c. Content Extractability Audit

This skill uses agent reasoning against the page HTML rather than
a standalone script.  The agent should fetch the page and apply the
heuristics from `skills/content-extractability-audit/references/heuristics.md`.

Check: heading quality, alt text, semantic landmarks, text-to-markup
ratio, fact extractability, link quality.

#### 2d. Freshness & Corroboration Audit

```bash
python skills/freshness-corroboration-audit/scripts/corroborate.py <url>
```

Checks date signals, HTTP freshness headers, sameAs identity links,
social profiles, and corroboration signals.

#### 2e. Engagement Audit

```bash
python skills/engagement-audit/scripts/perf_check.py <url>
```

Checks performance, navigation, content hierarchy, and calls-to-action.

### Step 3 — Collect all findings

Gather the `findings` arrays from each specialist result.

### Step 4 — Merge and build the report

Use the report builder:

```bash
python scripts/report_builder.py <cra_output.json> <sda_output.json> <fca_output.json> <ea_output.json>
```

Or pipe combined findings via stdin:

```bash
echo '[...combined results...]' | python scripts/report_builder.py --stdin
```

The report builder will:
1. **Deduplicate** findings with identical titles and categories.
2. **Normalise** severity values to `critical | high | medium | low | info`.
3. **Sort** findings by severity (critical first), then by priority.
4. **Assign IDs** sequentially: `F-001`, `F-002`, etc.
5. **Build the summary** with severity counts.

### Step 5 — Add proactive recommendations

After the automated checks, the agent should consider adding **proactive
recommendations** — positive-direction suggestions that are not tied to a
specific defect.  Examples:

* "Consider adding FAQ structured data to surface common questions in AI responses."
* "Consider implementing a knowledge panel by linking to a Wikidata entity."

These should use `severity: "info"` and `priority: "low"`.

### Step 6 — Return the final report

Output the complete JSON report.  The report should be self-contained —
a reader should be able to understand every finding without needing to
know which specialist skill produced it.

## Constraints

* **Runtime target**: under 5 minutes for a typical website.
* **Read-only**: no modifications to the target website.
* **No hardcoded domains**: all checks must generalize to any website.
* **Evidence-first**: every finding must include observable evidence.

## References

* `scripts/report_builder.py` — report merging and consolidation
* `skills/crawl-render-audit/SKILL.md` — crawlability and rendering
* `skills/structured-data-audit/SKILL.md` — structured data
* `skills/content-extractability-audit/SKILL.md` — content quality
* `skills/freshness-corroboration-audit/SKILL.md` — freshness and identity
* `skills/engagement-audit/SKILL.md` — visitor engagement