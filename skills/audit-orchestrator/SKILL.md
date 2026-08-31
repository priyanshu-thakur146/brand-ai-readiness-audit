---
name: audit-orchestrator
description: Entrypoint skill for the Brand AI-Readiness Audit marketplace. Given a website URL, invokes the five specialist audit skills (crawl-render-audit, structured-data-audit, content-extractability-audit, freshness-corroboration-audit, engagement-audit), collects their raw findings, merges and deduplicates them, and emits a single fixed-schema audit report (findings with evidence, severity, and suggested actions, plus a severity-count summary). Use this skill whenever a user asks to audit, evaluate, or diagnose a website's AI discoverability or on-site engagement — this is the only skill in the marketplace that should be invoked directly; it composes the other five.
license: MIT
allowed-tools: [bash, read, write]
---

# Audit Orchestrator

## When to use

Use this skill when asked to audit a website for AI discoverability (why an AI
assistant might fail to find, cite, or correctly represent the brand) or
on-site engagement (why a visitor who arrives doesn't stay). This is the
**single entrypoint** for the marketplace — the user or calling agent invokes
only this skill; it is responsible for invoking the other five internally
and never expects the caller to wire them up manually.

Do not use this skill to modify a website, submit forms, log in, or take
any action beyond reading and reporting. This marketplace is read-only /
recommend-only end to end — see "Guardrails" below.

## Inputs

- `site` (required): a URL or bare domain, e.g. `https://example.com` or
  `example.com`. Normalize bare domains to `https://` before crawling.
- Nothing else is required. If the target requires authentication to reach
  meaningful content, treat that as a finding in its own right (a brand's
  most important content should not require login to be discoverable) —
  do not attempt to authenticate.

## Procedure

Follow these steps in order. The procedure is deterministic: given the same
site content, it should produce the same report.

### 1. Normalize the input
Resolve `site` to a canonical `https://` URL. Confirm the host resolves and
responds (a simple `HEAD`/`GET`). If the site is unreachable entirely, stop
and emit a report with a single `critical` finding stating the site could
not be reached, rather than attempting partial analysis of nothing.

### 2. Set up a shared scratch directory
Create a working directory for this run, e.g. `./audit_run/<timestamp>/`,
with a `raw_findings/` subdirectory. Each of the five specialist skills
writes its output there as its own JSON file:

```
audit_run/<timestamp>/raw_findings/
  crawl-render-audit.json
  structured-data-audit.json
  content-extractability-audit.json
  freshness-corroboration-audit.json
  engagement-audit.json
```

This keeps every specialist skill's output independently inspectable and
lets `report_builder.py` (step 4) consume them without any skill needing to
know about the others.

### 3. Invoke the five specialist skills
Invoke each of the following skills in turn, passing the normalized `site`.
Each specialist skill is independent — none depends on another's output —
so if the runtime supports it, they may run in parallel. Each must write
its raw findings (a JSON list matching the contract in
`scripts/report_builder.py`'s module docstring) to its file in
`raw_findings/`.

1. `crawl-render-audit` — can automated systems reach and read the page?
2. `structured-data-audit` — is the page's data machine-readable?
3. `content-extractability-audit` — can specific facts be cleanly extracted?
4. `freshness-corroboration-audit` — is the content current and corroborated?
5. `engagement-audit` — does a visitor who arrives actually stay?

**If a specialist skill fails or times out:** do not fail the entire audit.
Record a `medium`-severity finding of the form `"<skill-name> could not
complete: <reason>"` with `source_skill: "audit-orchestrator"`, write it as
that skill's raw findings file (a one-item list), and continue. A partial
report is more useful than no report, and a failed check is itself
diagnostic information worth surfacing.

**Coordinating overlapping findings:** crawl-render-audit and
content-extractability-audit, in particular, can both legitimately flag the
same underlying problem (e.g. content that only exists after client-side
JS execution). When a specialist skill's instructions anticipate this kind
of overlap with another skill, it should tag the finding with a shared,
explicit `dedupe_key` (see the specialist skill's own `SKILL.md`) so the two
reports merge cleanly into one finding rather than double-counting the same
root cause. See `report_builder.py`'s docstring for the exact contract.

### 4. Merge, deduplicate, and build the report
Run the bundled script against the scratch directory:

```bash
python3 scripts/report_builder.py \
  --site "<normalized site, no scheme, e.g. example.com>" \
  --raw-dir "audit_run/<timestamp>/raw_findings" \
  --out "audit_run/<timestamp>/report.json"
```

This script (see `scripts/report_builder.py` for full documentation):
- validates every raw finding is evidence-backed and well-formed, failing
  loudly (non-zero exit) rather than silently dropping a malformed finding
- normalizes severity synonyms across skills
- merges near-duplicate findings (via explicit `dedupe_key` or, as a
  fallback, fuzzy title matching within the same `category`), combining
  their evidence and keeping the worse severity
- sorts findings deterministically (worst severity first, defects before
  proactive suggestions, then alphabetical) and assigns stable `F-001`,
  `F-002`, ... ids
- emits the final `summary` block and `findings[]` array

If `report_builder.py` exits non-zero, do not fabricate a report to paper
over the error — surface the stderr message, since it means a specialist
skill emitted malformed output and that is a bug worth fixing, not hiding.

### 5. Add proactive, non-defect suggestions (if not already covered)
Before finalizing, check whether any specialist skill already surfaced
proactive suggestions (findings marked `"proactive": true` in their raw
output — see each specialist's own `SKILL.md`). If an obvious, high-value
proactive improvement relevant to this site was not raised by any
specialist (e.g. no skill checked for `sameAs` entity links but the site
has none), append one more raw finding to the relevant specialist's file
with `"proactive": true` and re-run step 4. Do not invent proactive
suggestions unrelated to what was actually observed on the site.

### 6. Return the report
Return the final JSON object from `report.json` as the skill's output.
Do not wrap it in additional prose, markdown, or commentary — the report
itself is the deliverable and must remain valid, parseable JSON matching
the schema below.

## Output

A single JSON object, always containing at minimum:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": { "total_findings": 6, "critical": 1, "high": 2, "medium": 3 },
  "findings": [
    {
      "id": "F-001",
      "title": "No JSON-LD structured data on product pages",
      "severity": "high",
      "evidence": "Crawled 12 product pages; 0/12 contain schema.org markup.",
      "suggested_action": {
        "summary": "Add Product/Offer JSON-LD to every product page.",
        "priority": "high"
      }
    }
  ]
}
```

`report_builder.py` may add a small number of additive, non-breaking
extension fields (e.g. `"proactive": true`, `"source_skills": [...]` when a
finding was corroborated by more than one specialist) — these never replace
or omit any required field.

## Guardrails

- **Read-only, recommend-only, always.** Never submit forms, never
  authenticate, never write to the target site, never take any action
  beyond fetching and reading publicly accessible pages.
- **Respect `robots.txt`.** If crawling is disallowed for a path, do not
  crawl it — note the restriction as a finding if relevant, don't bypass it.
- **No rate-abusive crawling.** Space out requests; a typical audit should
  complete well under the 5-minute runtime budget without hammering the
  target site.
- **Never fabricate evidence.** Every finding's `evidence` field must
  describe something actually observed during this run. If a specialist
  skill could not verify something, that is itself a finding ("could not
  determine X because Y"), not a guess dressed up as a fact.