---
name: content-extractability-audit
description: Audits a website for content-extractability problems — whether key brand facts (pricing, specs, contact info, policies, differentiators) are stated explicitly enough in plain, readable text that an AI assistant could quote or cite them, versus being buried in images, PDFs, video, vague prose, or unclear headings. Use as one of the five specialist skills invoked by audit-orchestrator when auditing a website's AI discoverability; do not invoke directly outside the marketplace's entrypoint.
license: MIT
allowed-tools: [bash, read, write]
---

# Content Extractability Audit

## When to use

Invoked by `audit-orchestrator` as one of five specialist skills. Focuses on
one specific mechanism (Round-2 appendix, B and C): a page can be fully
reachable and fully rendered, and still fail an AI assistant if the facts on
it aren't stated plainly enough to extract and quote. This skill assumes the
page is already reachable — crawl access itself is `crawl-render-audit`'s
concern, not this skill's.

## Inputs

- `site` (required): the normalized site URL, passed by `audit-orchestrator`.
- `raw_findings_path` (required): where to write this skill's output —
  `<scratch_dir>/raw_findings/content-extractability-audit.json`, per the
  shared contract documented in `audit-orchestrator/scripts/report_builder.py`.

## Procedure

Detailed pattern definitions, extraction heuristics, and severity guidance
live in `references/heuristics.md` — this section is the deterministic
step-by-step, kept lean per progressive disclosure.

### 1. Sample pages
Fetch the homepage. From its nav/footer links and (if present) sitemap.xml,
select up to 8 representative pages, prioritizing the page types most
likely to carry facts an assistant would want to cite: a product/service
page, a pricing page, a contact/about page, and an FAQ or policy page, if
they exist. Fewer than 8 available pages is fine — sample what exists.

### 2. Extract plain-text content per page
For each sampled page, fetch the **rendered** DOM (not just raw HTML — a
fact assembled by client-side JS is still a fact a human reader sees, and
this skill cares about extractability of what's *readable*, distinct from
crawl-render-audit's concern with what's *reachable* by a simple crawler).
Strip obvious boilerplate (nav, footer, cookie banners) and keep the main
content text.

### 3. Check for key fact types (see `references/heuristics.md` §1)
For each of the standard fact categories — pricing, contact/business info,
core product/service specs, policies (returns/shipping/privacy), and stated
differentiators/claims — attempt to locate the fact in the extracted plain
text using the patterns in the reference file. Record, per fact type and
per page where it's expected:
- **found in plain text** → no finding
- **found only in an image, PDF, or embedded video/audio with no
  transcript** → finding (see §2 of the reference file for the severity
  rule: user-facing critical facts like pricing score higher than
  secondary facts)
- **entirely absent from the sampled pages where it would be expected**
  → finding, but only if the fact type is one this business would
  plausibly need (e.g. don't flag "no pricing found" for a page that
  is clearly not a commerce site — use judgment, don't force a checklist
  match where it doesn't fit)

### 4. Check for buried or ambiguous facts
Using the heading- and prose-clarity heuristics in
`references/heuristics.md` §3, flag cases where a fact technically appears
in plain text but is meaningfully harder to extract than it needs to be:
vague section headings ("Learn More" instead of "Shipping Policy"), a key
fact stated only as an implication across multiple sentences rather than
directly, or a fact stated once in a way that contradicts itself elsewhere
on the same page.

### 5. Check for non-text lock-in
Using `references/heuristics.md` §2, specifically flag:
- Images whose `alt` text is empty, generic ("image1.jpg"), or doesn't
  convey the fact the image visually communicates (e.g. a pricing table
  rendered as an image with no equivalent text)
- PDFs linked as the *only* source for a fact that doesn't appear anywhere
  in HTML
- Video/audio content presenting facts with no accompanying transcript or
  caption text

### 6. Coordinate with crawl-render-audit on overlapping root causes
If a fact is missing from plain text **because it's only rendered via
client-side JavaScript that a simple reader wouldn't execute**, this is the
same underlying root cause `crawl-render-audit` may also detect from the
crawling side. Tag this specific finding with
`"dedupe_key": "js-only-content"` (and `"category": "js-rendering-gap"`) so
`audit-orchestrator`'s `report_builder.py` merges the two skills' evidence
into one finding instead of reporting it twice. Only use this shared key
for genuinely JS-rendering-caused gaps — not for images, PDFs, or prose
clarity issues, which are this skill's own distinct findings.

### 7. Write raw findings
Write every finding as a JSON list to `raw_findings_path`, matching the
contract in `report_builder.py`'s module docstring: `title`, `severity`,
`evidence` (a concrete observation, e.g. "Checked 6 sampled pages; pricing
table appears only as `/images/pricing-2026.png` with alt text
'pricing'"), `suggested_action` (`summary` + `priority`), `source_skill:
"content-extractability-audit"`, and `category`. Use `"proactive": true`
for suggestions made without a specific defect (see step 8).

### 8. Proactive suggestions (optional)
If no defects were found for a fact category but an improvement would
still strengthen extractability (e.g. facts are all in plain text, but a
concise summary/TL;DR block at the top of long pages would make the single
most important fact easier for an assistant to isolate), add one
`"proactive": true` finding. Do not manufacture proactive findings that
aren't grounded in something actually observed on the site.

## Output

A JSON list of raw findings (see step 7), written to
`raw_findings_path`. No other output — this skill does not compose the
final report; `audit-orchestrator` does.

## Guardrails

- Read-only. Fetch pages only; never submit forms or authenticate.
- Respect `robots.txt` for every URL fetched.
- Every `evidence` string must describe something actually observed in this
  run (a specific page, a specific missing/present fact) — never a generic
  or assumed statement.
- Don't force-fit checks that don't apply to the site's actual business
  type (see step 3) — a false positive here costs more than a miss, per
  the contest's evaluation criteria.