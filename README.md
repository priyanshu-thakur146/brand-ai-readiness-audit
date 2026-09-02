# brand-ai-readiness-audit

Adobe University Hackathon 2026 — Round 3 submission.

An Agent Skill Marketplace that audits a website for **AI discoverability** (why a brand is/isn't
found or cited by AI assistants) and **on-site engagement** (why visitors who do arrive don't stay),
and emits a single structured report of evidence-backed findings and prioritized fixes.

Read-only / recommend-only: no skill modifies the target site.

## Skills in this marketplace

| Skill | Concern | Covers (see Round-2 appendix) |
|---|---|---|
| `audit-orchestrator` **(entrypoint)** | Composes every other skill's findings into the final report | — |
| `crawl-render-audit` | Can a crawler even get in and read the page? robots.txt blocks, missing sitemap, `noindex`, JS-render gap (content only assembled client-side) | A, C |
| `structured-data-audit` | Are facts stated in a form a machine can extract with certainty? JSON-LD validity, meta/OG tags, plain-text presence of price/contact facts | B, C |
| `fact-extractability-audit` | Even if readable, can a summarizer find the point? heading structure, generic-filler-only leads, facts locked in images/canvas/video/PDF, boilerplate ratio | C, F |
| `freshness-corroboration-audit` | Is content current, and is it said the same way elsewhere on the web? on-page freshness signals + agent-gathered cross-source corroboration scoring | D |
| `entity-disambiguation-audit` | Can the brand be told apart from others with the same name? `sameAs` links to Wikipedia/Wikidata/etc., name-ambiguity heuristics, NAP consistency | D |
| `engagement-audit` | Does a visitor who arrives stay? mobile viewport, navigation, calls-to-action, broken internal links, load speed | (on-site engagement half of Round 2) |

Each skill's `SKILL.md` documents its own `When to use` / `Inputs` / `Procedure` / `Output`, and each
is independently runnable — the entrypoint doesn't do anything the sub-skills couldn't do on their
own; it just composes them.

## How the entrypoint composes the others

`audit-orchestrator/scripts/run_audit.py` imports and calls each sub-skill's `run_check(url, ...)`
function directly, wraps each call so one failing check can't take down the whole audit (it's
recorded as a `*-ERR` finding instead), merges all findings, sorts by severity, computes the summary
block, and writes/prints the final JSON report matching the schema below.

`freshness-corroboration-audit` and `entity-disambiguation-audit` can optionally take agent-gathered
web-search evidence (via `--search-results`) for cross-source corroboration and name-collision
checks — those two concerns genuinely require live web search, which a plain script can't do on its
own, so the SKILL.md instructs the calling agent to gather that evidence first when it has search
access. The audit still runs and reports the gap if that evidence isn't supplied.

## Output schema (minimum)

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {"total_findings": 6, "critical": 1, "high": 2, "medium": 3, "low": 0},
  "findings": [
    {
      "id": "SD-001",
      "title": "No JSON-LD structured data on product pages",
      "severity": "high",
      "evidence": "...",
      "suggested_action": {"summary": "...", "priority": "high"}
    }
  ],
  "checks_run": ["crawl-render-audit", "structured-data-audit", "..."]
}
```

## Running it

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python skills/audit-orchestrator/scripts/run_audit.py https://example.com --output audit_report.json
```

With agent-gathered corroboration evidence:

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com \
    --search-results sample_search_results.json \
    --output audit_report.json
```

Any individual skill can also be run standalone, e.g.:

```bash
python skills/structured-data-audit/scripts/structured_data_check.py https://example.com
```

## Guardrails

- Recommend-only: no skill writes to, authenticates against, or otherwise alters the target site.
- Respects `robots.txt` disallow rules; only fetches the homepage plus a small sample (default 8)
  of internal links for the broken-link check in `engagement-audit`.
- No destructive, authenticated, or rate-abusing actions.
- Typical audit runtime: well under 5 minutes for a standard site.
