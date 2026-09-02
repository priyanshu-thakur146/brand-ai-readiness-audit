---
name: audit-orchestrator
description: Entrypoint skill for the Brand AI-Readiness Audit marketplace. Given a website URL, runs the crawl-render, structured-data, fact-extractability, freshness-corroboration, entity-disambiguation, and engagement skills, then composes their findings into a single structured audit report (evidence + severity + prioritized suggested actions) covering both AI discoverability and on-site engagement. Use this skill when asked to audit a brand/website's AI readiness end-to-end.
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# Brand AI-Readiness Audit — Orchestrator (entrypoint)

## When to use
This is the single entrypoint for the marketplace. Invoke it with a website URL and it produces the
complete audit report. It does not perform novel checks itself — it composes the outputs of the
other five focused skills in this marketplace.

## Inputs
- `url` (required): the website/brand to audit.
- `search_results` (optional): pre-gathered web-search evidence for the
  `freshness-corroboration-audit` and `entity-disambiguation-audit` skills (see their SKILL.md files).
  If the calling agent has live web-search access, it should gather this before invoking the
  orchestrator for a materially stronger report; if not, the audit still runs and flags the gap.
- `output_path` (optional): where to write the JSON report.

## Procedure
1. Run each sub-skill's check against `url`:
   - `crawl-render-audit` → crawlability + JS-render-gap findings
   - `structured-data-audit` → JSON-LD / meta / plain-text-fact findings
   - `fact-extractability-audit` → heading structure / lead clarity / non-text-fact findings
   - `freshness-corroboration-audit` → staleness + cross-source corroboration findings
   - `entity-disambiguation-audit` → sameAs / name-ambiguity / NAP findings
   - `engagement-audit` → mobile viewport / nav / CTA / broken-link / load-speed findings
2. If any sub-check errors, record it as a finding rather than aborting the whole audit (a partial
   report is more useful than none — see `scripts/run_audit.py`).
3. Merge all findings into one list, preserving each skill's `id` prefix for traceability
   (`CR-`, `SD-`, `FE-`, `FR-`, `ED-`, `EN-`).
4. Compute the summary block (`total_findings`, and counts by severity: `critical`, `high`,
   `medium`, plus `low` as an additional field).
5. Sort findings so `critical` → `high` → `medium` → `low`, so the most actionable items surface
   first for a non-expert reading the report.
6. Emit the final report matching the required schema:
   ```json
   {
     "site": "example.com",
     "audited_at": "2026-09-20T14:32:00Z",
     "summary": {"total_findings": N, "critical": N, "high": N, "medium": N, "low": N},
     "findings": [
       {
         "id": "SD-001",
         "title": "...",
         "severity": "high",
         "evidence": "...",
         "suggested_action": {"summary": "...", "priority": "high"}
       }
     ],
     "checks_run": ["crawl-render-audit", "structured-data-audit", ...]
   }
   ```
7. Write the report to `output_path` (default `audit_report.json`) and print it to stdout.

## Output
A single JSON audit report as above — the marketplace's final deliverable for a given site.

## Guardrails
Read-only. No sub-skill modifies the target site, authenticates, or performs destructive/rate-abusing
actions. Respects `robots.txt` disallow rules encountered during the audit itself (the orchestrator
does not crawl beyond the homepage + a small sample of internal links for the broken-link check).
