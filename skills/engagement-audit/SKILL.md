---
name: engagement-audit
description: Use when auditing a webpage or site for on-page engagement and usability issues that cause visitors to bounce or fail to act — checks heading structure, navigation landmarks, call-to-action clarity and business relevance, contact/trust findability, mobile viewport configuration, dead internal links, and response latency.
---

# engagement-audit

## When to use

Invoke this skill (directly, or as one of the five specialists composed by
`audit-orchestrator`) whenever the task is to evaluate whether a page's
**structure and on-page signals help or hurt visitor engagement** — as
opposed to whether its content is machine-extractable (`content-extractability-audit`),
crawlable/renderable (`crawl-render-audit`), marked up with structured data
(`structured-data-audit`), or factually current (`freshness-corroboration-audit`).

This skill answers one question: *if a real visitor (or an AI assistant
navigating on a user's behalf) lands here, is there a clear, working path to
the next action?*

## Inputs

- `url` — the base URL of the site being audited.
- `pages` (optional) — a list of specific page URLs to sample. Defaults to
  just the base URL if not provided. Sample 3–5 representative pages
  (homepage, one category/listing page, one detail page) when possible —
  engagement defects are often page-type-specific, not site-wide.

## Procedure

1. **Fetch each sampled page** with a real HTTP request (not a cached copy).
   Record wall-clock fetch time for the latency check.
2. **Classify commerce-relevance** for each page using on-page signals
   (mentions of cart/checkout/price/shop/order) — this is a heuristic, not
   authoritative, and exists so severity is judgment-aware rather than
   penalizing a non-commerce page for lacking a "Buy now" button. This
   mirrors the same judgment-aware pattern used by `content-extractability-audit`.
3. **Run the structural checks** against the parsed HTML:
   - heading structure (single H1, no empty headings, no skipped levels)
   - navigation landmark present, with a link back to the homepage
   - at least one clickable CTA with real (non-generic) text
   - commerce-relevant pages have a transactional CTA, not just navigation links
   - contact/support link reachable from nav or footer
   - mobile viewport meta tag present and not disabling zoom
4. **Sample internal links** discovered on the audited pages (cap at 8) and
   check each resolves without a 4xx/connection error.
5. **Write one raw finding per genuine defect**, using the shared schema
   (see `scripts/perf_check.py` docstring for the exact contract). Every
   `evidence` string must be a literal excerpt or fact pulled from the actual
   page — never a paraphrase or an assumption about what the page "probably"
   contains.
6. **Namespace all dedupe keys** as `engagement:<id_hint>` so this skill's
   findings never silently collide with another skill's dedupe key unless a
   cross-skill overlap is deliberately coordinated (none currently declared —
   engagement checks are structural/UX and don't currently overlap with the
   content-extractability or crawl-render skills' concerns).
7. **Emit at most one proactive suggestion** (not a defect finding) if the
   page is otherwise clean but has an obvious, low-risk improvement — e.g. a
   commerce page with only one CTA per page could benefit from a secondary
   CTA. Mark these `"proactive": true` so `report_builder.py` can group them
   separately from defects.
8. **Return the raw findings list** to whatever invoked this skill (directly,
   or `audit-orchestrator`'s scratch directory, per its documented contract).

## Output

A JSON array of raw findings, each matching the schema documented at the top
of `scripts/perf_check.py`:

```json
{
  "id_hint": "missing-nav-landmark",
  "title": "No navigation landmark found",
  "severity": "medium",
  "evidence": "https://example.com/: no <nav> element or role=\"navigation\" found in the document.",
  "suggested_action": "Wrap the primary site navigation in a <nav> element ...",
  "dedupe_key": "engagement:missing-nav-landmark",
  "source_skill": "engagement-audit",
  "proactive": false
}
```

This skill never emits the contest's final fixed-schema report directly —
that assembly step belongs to `audit-orchestrator`'s `report_builder.py`,
which this skill's output is designed to feed into unmodified.

## Severity ladder

| Severity | Meaning for this skill |
|---|---|
| `critical` | The page itself is unreachable or errors out — every other engagement signal is moot. |
| `high` | Multiple sampled internal links are dead, or a commerce page has zero CTA at all. |
| `medium` | A structural element that materially hurts findability/conversion is missing (nav landmark, contact link, viewport meta, commerce CTA, single dead link). |
| `low` | Hygiene issues that don't block a visitor but weaken the experience (multiple H1s, skipped heading levels, generic-only CTA text, nav missing a home link). |

Nothing besides total unreachability escalates to `critical` — engagement
defects degrade experience rather than break it outright, so one noisy UX
nit can't inflate a page's overall audit severity the way an actually-broken
page should.

## Why CTA severity is judgment-aware (commerce vs. non-commerce)

A blog post or documentation page has no obligation to push a transaction.
Flagging "no purchase CTA" on such a page as `high` would be a false
positive the contest's generalization criterion specifically penalizes.

- **No clickable CTA at all** — flagged everywhere, but `high` only if the
  page itself shows commerce signals (cart/checkout/price/shop/order in its
  own text); `medium` otherwise.
- **No transactional CTA specifically** (`missing-commerce-cta`) — only
  fires when the page's *own content* already signals commerce. This is a
  self-referential check, not an external assumption about the site type —
  matching the "no hardcoded domain assumptions, generalize from observable
  signals" principle.

**Generic-CTA-only** fires only when *every* clickable element's text is
generic (click here, read more, etc.) — a page with one clear CTA plus an
incidental "click here" elsewhere is fine; flagging every generic phrase
individually would be noise proportional to page length, not actual harm.

**Dead-link sampling** is capped at 8 discovered links (first-8, deterministic
— same input always samples the same links) to respect the runtime budget
and no-rate-abuse guardrail. One dead link is `medium`; more than one in a
small sample implies a systemic problem, so it's `high`.

**Heading and viewport checks stay at `low`/`medium`, never `high`** — these
rarely stop a human visitor outright (the browser still renders the page);
the harm is to assistive tech and machine summarization, which is real but
indirect compared to a fully dead CTA or unreachable page.

## Scope boundary with other skills

This skill does not diff raw HTML vs. rendered DOM (`crawl-render-audit`),
verify factual accuracy (`freshness-corroboration-audit`), check Schema.org/
JSON-LD markup (`structured-data-audit`), or check whether specific facts are
buried in prose or locked in non-text elements (`content-extractability-audit`).
Its `contact-not-findable` check is about *navigational* findability (is a
link present in nav/footer) — not *textual* extractability (is the phone
number itself parseable text), which is the other skill's concern.

No dedupe_key is currently shared with another skill — all keys are
namespaced `engagement:<id_hint>` and kept skill-local. If a genuine overlap
with another skill is identified later, coordinate an explicit shared key
the way `content-extractability-audit` and `crawl-render-audit` did for
`"js-only-content"` — don't rely on fuzzy title-matching alone, since that's
what caused the false-merge bug in `report_builder.py`.

## Guardrails

- **Read-only.** This skill only issues GET/HEAD requests; it never submits
  forms, creates accounts, or triggers checkout/payment flows even when
  probing whether a commerce CTA exists.
- **Respects `robots.txt`** for any URL fetched beyond the explicitly-provided
  page list (the dead-link sampling step) — it does not fetch a disallowed
  path even if discovered via an on-page link.
- **No rate abuse.** Internal link sampling is capped at 8 URLs per audit,
  fetched sequentially, not in a hammering burst.
- **Never fabricates evidence.** Every finding's evidence field is a literal
  substring, attribute value, or measured fact (e.g. fetch time) — this skill
  does not infer or guess at what a page "likely" contains when a check
  cannot directly observe it; in that case, it emits no finding rather than a
  speculative one.
- **Fails loudly.** Unreachable pages, timeouts, and non-2xx responses on an
  audited page produce a `critical` finding (`page-unreachable` /
  `page-error-status`) rather than crashing the whole audit or silently
  skipping the page.