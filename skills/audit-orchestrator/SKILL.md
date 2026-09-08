---
name: audit-orchestrator
description: Entrypoint skill of the brand-ai-readiness-audit marketplace. Given a website URL, it discovers pages via sitemap and homepage-link crawling, invokes all six specialist audit skills, aggregates their findings across pages with serial (one-page-at-a-time) crawling under a wall-clock time budget, and composes a single schema-compliant audit report with findings, severities, evidence, and prioritized suggested actions. Use this skill when asked to run a full AI-discoverability and on-site-engagement audit of a website.
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# `skills/audit-orchestrator/` — Master Entrypoint Skill

> Marketplace: `brand-ai-readiness-audit` · Entrypoint: **yes** (declared in `marketplace.json`)
> Script: `scripts/run_audit.py` (composition logic) + `scripts/page_discovery.py` (page discovery)

## When to use
Invoke this skill whenever an agent is asked to audit a brand's website for **AI discoverability**
(why AI assistants don't find, fetch, or cite it) or **on-site engagement** (why visitors who do
arrive don't stay) — or both. This is the single skill an agent should call; it internally
composes the other five skills in this marketplace (`crawl-render-audit`,
`structured-data-audit`, `fact-extractability-audit`, `freshness-corroboration-audit`,
`entity-disambiguation-audit`, `engagement-audit`) and is the only skill that emits the final
audit report.

Do not call this skill to modify, publish, or authenticate against the target site — it is
strictly recommend-only (see Guardrails).

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target website to audit, e.g. `https://example.com`. |
| `search_results` | no | Pre-gathered web-search evidence (JSON) used by `freshness-corroboration-audit` and `entity-disambiguation-audit` for cross-source verification. Keys: `freshness`, `entity`. |
| `output_path` | no | File path to write the JSON report to (default `audit_report.json`). |
| `timeout` | no | Per-request HTTP timeout in seconds (default `5`). |
| `max_links` | no | Internal links sampled by `engagement-audit` (default `8`). |
| `max_pages` | no | Upper bound on pages discovered/crawled (default `400`; pass `None`/omit for "as many as the time budget allows"). |
| `time_limit` | no | Wall-clock audit budget in seconds (default `120`). The orchestrator never exceeds this — it degrades gracefully instead of failing. |

## Procedure (numbered, deterministic steps)
1. **Load every skill module** in the marketplace (`crawl-render-audit`, `structured-data-audit`,
   `fact-extractability-audit`, `freshness-corroboration-audit`, `entity-disambiguation-audit`,
   `engagement-audit`, plus the bundled `page_discovery` helper) directly from their
   `skills/<id>/scripts/` folders — no external service or network call is needed to resolve the
   marketplace.
2. **Run site-level checks** once against the homepage: `crawl-render-audit`,
   `freshness-corroboration-audit`, `entity-disambiguation-audit`, `engagement-audit`. Each runs
   inside a `try/except` isolation boundary (see "Fail-safe composition" below) so one skill's
   crash never aborts the audit.
3. **Discover additional same-domain pages** (see "Page discovery" below): parse `robots.txt` for
   `Sitemap:` directives, fetch `/sitemap.xml` and `/sitemap_index.xml`, recursively resolve
   sitemap indexes, and supplement with same-domain `<a href>` links pulled from the raw homepage
   HTML (no JavaScript execution). Static assets (images, CSS, JS, fonts, archives) are filtered
   out; tracking query parameters and URL fragments are normalized away so the same page isn't
   counted twice.
4. **Run page-level checks with serial crawling** (see below): `structured-data-audit` and
   `fact-extractability-audit` are executed **one discovered page at a time**, in order, checking
   the remaining time budget before every single page. The loop stops the instant the time budget
   is exhausted — it never batches or parallelizes page fetches, so the number of pages actually
   sampled is a deterministic function of `time_limit`, not a fixed, arbitrary page count.
5. **Aggregate repeated findings across pages**: identical issues raised on multiple pages are
   merged into one `*-AGG-###` finding, with evidence listing how many of the pages checked show
   it (e.g. `9/10 pages checked show this issue`). If a defect appears on ≥80% of a sample of 3+
   pages, its severity is escalated one level (e.g. `medium` → `high`) — a site-wide pattern is a
   bigger problem than a one-off.
6. **Normalize and sort** every finding (from both site-level and page-level checks) by severity
   (`critical` → `high` → `medium` → `low` → `info`), tally `proactive_suggestions` separately so
   they never inflate the problem count, and record any `check_errors` transparently rather than
   hiding a partial run.
7. **Emit the final audit report** (schema below) to `output_path` and return it to the caller.

### Fail-safe composition
Every sub-skill call is wrapped so an unhandled exception in one check (a timeout, a malformed
page, a DNS failure) becomes a single `medium`-severity `*-ERR` finding instead of crashing the
whole audit — the remaining skills still run and the report still ships.

### Serial page crawling
Page-level checks are deliberately **serial, not concurrent**: the orchestrator visits one
discovered page, runs a check, records the result, checks the clock, and only then moves to the
next page. This is a conscious engineering trade-off for a hackathon-grade, sandboxed audit tool:
it keeps load on the target server minimal and predictable (never issuing bursts of concurrent
requests, in the spirit of "respect the target site"), makes total runtime a transparent function
of `time_limit`, and keeps the whole run reproducible and easy to reason about for graders. The
reported `pages_crawled` count in the output is therefore the true number of pages the audit
actually finished checking within budget — not an aspirational target.

### Adaptive dual-engine rendering
`crawl-render-audit` (invoked as a site-level check) tries a headless Playwright Chromium engine
first when it is installed, to hydrate JavaScript-heavy Single Page Applications (Next.js, React,
Vue, Gatsby) the same way a modern AI crawler might. If Playwright is unavailable, fails to
launch, or the sandbox has no browser binaries, it catches the failure and falls back to plain
HTTP + `BeautifulSoup` parsing with a real browser `User-Agent` — so the orchestrator never
crashes or stalls because a heavier rendering engine isn't present in the grading environment.
Every render-gap finding records which engine actually produced the evidence.

## Output
Emits one schema-compliant JSON audit report (superset of the contest's minimum schema):
```json
{
  "site": "example.com",
  "audited_at": "2026-09-07T14:30:00Z",
  "summary": {
    "pages_crawled": 7,
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0,
    "proactive_suggestions": 1,
    "time_limit_seconds": 120,
    "execution_time_seconds": 5.58
  },
  "findings": [
    {
      "id": "SD-001",
      "category": "discoverability",
      "title": "Missing Organization JSON-LD markup",
      "severity": "high",
      "evidence": "Zero <script type=\"application/ld+json\"> blocks found on homepage.",
      "suggested_action": { "summary": "Add schema.org Organization markup with name, url, logo, and sameAs links.", "priority": "high" }
    }
  ],
  "proactive_suggestions": [ { "id": "CR-P-001", "title": "...", "suggested_action": "..." } ],
  "checks_run": ["crawl-render-audit", "structured-data-audit", "fact-extractability-audit", "freshness-corroboration-audit", "entity-disambiguation-audit", "engagement-audit"],
  "pages_sampled": ["https://example.com", "https://example.com/products"],
  "check_errors": []
}
```
`findings[].id`, `title`, `severity`, `evidence`, `suggested_action` and the summary's
severity-count fields match the contest's required minimum schema exactly; every extra field
(`category`, `proactive`, `pages_sampled`, `checks_run`, `check_errors`) is additive.

## Guardrails
- **Read-only, recommend-only**: never writes to, authenticates against, or alters the target
  site. All suggested actions are recommendations for a human/dev team to apply.
- **Respects `robots.txt`** disallow rules and keeps per-page and per-check timeouts bounded.
- **No destructive, rate-abusing, or authenticated-area actions.**
- **Deterministic within a run**: given the same site and the same time budget, the orchestration
  order and aggregation logic are identical every time.
