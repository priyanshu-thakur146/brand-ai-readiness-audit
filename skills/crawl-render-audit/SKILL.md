---
name: crawl-render-audit
description: Audits whether automated crawlers (including AI-assistant crawlers like GPTBot and ClaudeBot) can reach a website's pages at all, and whether the page content they'd see matches what a human sees in a browser. Checks robots.txt access, HTTP status/redirect health, sitemap.xml presence, and diffs raw HTML against client-side-rendered DOM to catch JavaScript-only content. Use as one of the five specialist skills invoked by audit-orchestrator when auditing a website's AI discoverability; do not invoke directly outside the marketplace's entrypoint.
license: MIT
allowed-tools: [bash, read, write]
---

# Crawl & Render Audit

## When to use

Invoked by `audit-orchestrator` as one of five specialist skills. Covers
Round-2 appendix mechanism A ("the crawler has to be let in") and the crawl
side of mechanism C (content that's technically present but only after
JavaScript execution, which a simple reader never runs). This is the first
gate a page has to pass — if a crawler can't reach or read a page at all,
whether its structured data or prose is well-written is moot. The other
specialists (`structured-data-audit`, `content-extractability-audit`) assume
this gate has already passed.

## Inputs

- `site` (required): the normalized site URL, passed by `audit-orchestrator`.
- `raw_findings_path` (required): where to write this skill's output —
  `<scratch_dir>/raw_findings/crawl-render-audit.json`.

## Procedure

All checks below are implemented as deterministic, testable functions in
`scripts/render_diff.py` — this skill's job is to sample the right pages and
invoke that script correctly, not to reimplement the logic inline. Detailed
threshold rationale lives in `references/checklist.md`.

### 1. Sample pages
Fetch the homepage. Attempt `sitemap.xml`; if present, take up to 8 URLs
from it, prioritizing pages likely to carry facts an assistant would cite
(product/service pages, pricing, contact). If no sitemap exists, fall back
to following homepage nav links to build the same sample size. Always
include the homepage itself in the sample.

### 2. Run the audit script
Invoke:

```bash
python3 scripts/render_diff.py \
  --site "<normalized site>" \
  --pages <space-separated list of sampled page URLs> \
  --out "<scratch_dir>/raw_findings/crawl-render-audit.json"
```

This single invocation performs all of the following, and writes findings
directly in the shared raw-finding format:

1. **robots.txt check** — fetches `/robots.txt` and checks whether any
   AI-relevant crawler (GPTBot, ClaudeBot, Google-Extended, CCBot,
   PerplexityBot, Bingbot, or the wildcard `*`) is disallowed from the
   homepage or any sampled page's path. A block on `/` is `critical`; a
   block on a specific sampled path is `high`. No robots.txt at all is not
   a defect (default is "everything allowed").
2. **sitemap.xml check** — missing sitemap is a `low`-severity, proactive
   suggestion (not a hard defect — crawlers can still discover pages via
   links). An unparseable sitemap is a `medium` defect.
3. **HTTP status check**, per sampled page — `5xx` is `critical`, `4xx` is
   `high`, a redirect chain longer than 3 hops is `medium`.
4. **Render diff**, per sampled page that returned a successful status —
   fetches the raw HTML (no JS) and the fully-rendered DOM (headless
   Chromium, JS executed), extracts visible text from both, and compares
   word counts. A gap large enough to matter (see
   `references/checklist.md` §2 for the exact thresholds) produces a
   finding tagged `category: "js-rendering-gap"` and
   `dedupe_key: "js-only-content"` — this shared key lets
   `audit-orchestrator`'s `report_builder.py` merge this finding with any
   matching one from `content-extractability-audit`, since they can
   describe the same root cause from two angles.

### 3. Handle script failure
If the script exits non-zero or a page can't be fetched/rendered at all,
that failure is itself written as a finding (the script does this
automatically — see `references/checklist.md` §3) rather than causing the
whole skill to abort silently.

### 4. No manual post-processing needed
Unlike some checks that require judgment calls on ambiguous cases, every
check in this skill is threshold-based and deterministic. The script's
output file is this skill's final output — no additional filtering or
rewriting step.

## Output

A JSON list of raw findings (written by `render_diff.py` to
`raw_findings_path`), matching the contract in
`audit-orchestrator/scripts/report_builder.py`'s docstring. No other
output — this skill does not compose the final report.

## Guardrails

- **Respect `robots.txt`.** This skill fetches `/robots.txt` itself first
  and should not crawl paths disallowed for a generic/unnamed crawler
  identity beyond what's needed to perform the checks above (fetching
  `robots.txt` and `sitemap.xml` themselves, and the sampled pages, is the
  audit's own legitimate, non-abusive traffic).
- **No rate-abusive crawling.** Sample at most ~8 pages; don't crawl a
  site exhaustively.
- **Headless rendering only for auditing, never for interaction.** The
  headless browser loads pages read-only — it never clicks, submits forms,
  or authenticates.
- **Every `evidence` string must cite the specific URL and specific numbers
  observed** (word counts, status codes, blocked paths) — never a vague
  claim like "some pages have issues."