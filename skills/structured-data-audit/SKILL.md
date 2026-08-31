---
name: structured-data-audit
description: Use when auditing a webpage or site for Schema.org structured data issues — checks JSON-LD presence and syntactic validity, required/recommended fields per content type (Article, Product, Organization, Event, etc.), conflicting or unrecognized @type values, and malformed URL fields, falling back to microdata detection when no JSON-LD is present.
---

# structured-data-audit

## When to use

Invoke this skill (directly, or as one of the five specialists composed by
`audit-orchestrator`) whenever the task is to evaluate a page's **machine-readable
structured data** — Schema.org JSON-LD or microdata — as opposed to whether
its content is extractable from rendered text (`content-extractability-audit`),
crawlable at all (`crawl-render-audit`), engaging/navigable
(`engagement-audit`), or factually current (`freshness-corroboration-audit`).

This skill answers one question: *if a search engine or AI agent parses this
page's structured data instead of reading the visible text, does it get an
accurate, complete, syntactically valid picture of what the page is about?*

## Inputs

- `url` — the base URL of the site being audited.
- `pages` (optional) — a list of specific page URLs to sample. Defaults to
  just the base URL. Sample pages representative of distinct content types
  (an article page, a product page, the homepage) since required fields
  differ by `@type`.

## Procedure

1. **Fetch each sampled page** with a real HTTP request.
2. **Extract every `<script type="application/ld+json">` block**, parse each
   as JSON, and flatten `@graph` arrays and top-level lists into individual
   nodes. A block that fails to parse is itself a finding — a malformed
   JSON-LD block is silently ignored by every real consumer, so treat it as
   equivalent to that data being entirely absent, not merely a syntax nit.
3. **If zero JSON-LD blocks exist**, check for `itemscope`/`itemtype`
   microdata before concluding the page has no structured data at all —
   microdata is a valid (if older) fallback and should suppress the
   "no structured data" finding.
4. **For every parsed node**, check:
   - `@context` present (medium if missing)
   - `@type` present (high if missing — an untyped node is unusable)
   - required fields present for that `@type`, per the minimal table in this
     skill's rationale below (high if missing)
   - recommended fields present for that `@type` (low if missing)
   - `@type` doesn't mix clearly unrelated top-level entities in one node
     (e.g. `["Product", "Person"]` — usually a copy-paste error)
   - `@type` values are recognized Schema.org types, flagged as a proactive
     low-severity suggestion (not an assumed defect) when not
   - URL-like fields (`url`, `logo`, `@id`) are absolute, not relative paths;
     none are empty strings
5. **Never dereference URLs found in structured data over the network** —
   this skill checks syntactic validity only (is it an absolute URL, is it
   non-empty), it does not fetch `image`/`logo`/`sameAs` targets. That keeps
   the skill fast and avoids probing third-party assets, consistent with the
   read-only guardrail.
6. **Write one raw finding per genuine defect**, using the shared schema
   documented in `scripts/schema_check.py`'s docstring. Every `evidence`
   string is a literal excerpt of the offending JSON-LD (parsed keys,
   the raw error message, the exact type list) — never a paraphrase.
7. **Namespace all dedupe keys** as `structured-data:<id_hint>`. No overlap
   with another skill's dedupe key is currently declared — structured-data
   defects are a distinct concern from the other four skills' checks.
8. **Return the raw findings list** to whatever invoked this skill.

## Output

A JSON array of raw findings matching the schema in `scripts/schema_check.py`:

```json
{
  "id_hint": "missing-required-fields-article",
  "title": "Article node missing required field(s): headline, datePublished",
  "severity": "high",
  "evidence": "https://example.com/post: node #1 declares @type=\"Article\" but is missing ['headline', 'datePublished']. Present keys: ['@context', '@type', 'author']",
  "suggested_action": "Add ['headline', 'datePublished'] to this Article node ...",
  "dedupe_key": "structured-data:missing-required-fields-article",
  "source_skill": "structured-data-audit",
  "proactive": false
}
```

This skill never emits the contest's final report directly — assembly
belongs to `audit-orchestrator`'s `report_builder.py`.

## Severity ladder and rationale

| Severity | When |
|---|---|
| `critical` | The page itself is unreachable or errors out. |
| `high` | JSON-LD fails to parse (silently discarded by every real consumer), a node has no `@type` at all, or a required field for a detected type is missing. |
| `medium` | Missing `@context`, conflicting/unrelated `@type` values on one node, a non-absolute URL in a URL-like field, or zero structured data found anywhere (with no microdata fallback). |
| `low` | Empty JSON-LD blocks, missing recommended (not required) fields, empty-string URL fields. |
| `low` + `proactive: true` | An unrecognized `@type` — could be a valid rare type this skill's list doesn't track, or a typo; flagged for review, not asserted as a defect. |

**Required vs. recommended fields are deliberately conservative.** The
required-field table (`TYPE_REQUIRED_FIELDS` in the script) only lists fields
that major consumers — Google Rich Results, generic LLM page-summarization —
treat as load-bearing for that type (e.g. `Article` needs `headline` and
`datePublished`; `Product` needs `name`). Everything else Schema.org
technically allows but doesn't strictly require goes in the recommended
table and is scored `low`, so this skill doesn't over-penalize pages for
omitting genuinely optional fields — a false-positive risk the contest's
generalization criterion specifically penalizes.

**Unknown `@type` is `proactive`, not a defect**, because this skill's known-type
list is intentionally small (the common, high-traffic types) — Schema.org has
hundreds of valid types, and flagging every one this list doesn't recognize
as a hard defect would produce false positives on legitimate but less-common
markup. It's surfaced for human review instead of asserted as wrong.

**Conflicting-type detection is narrow by design** — it only flags a small,
explicit set of unrelated top-level entity groups (e.g. `Product` mixed with
`Person`), not any two-type combination, since many legitimate combinations
exist (e.g. `Product` + `Offer`-adjacent types via nesting). This avoids
false positives from combinations the skill doesn't have grounds to call
contradictory.

## Scope boundary with other skills

This skill does not check whether the *content itself* is extractable as
plain text (`content-extractability-audit`), whether the page renders
without JavaScript (`crawl-render-audit`), or whether dates/facts in
structured data are actually current (`freshness-corroboration-audit` — that
skill may separately flag a `datePublished` that's stale; this skill only
checks that the field is *present and well-formed*, not that its value is
*current*). No dedupe_key is currently shared with another skill.

## Guardrails

- **Read-only.** Only GET requests to the audited pages themselves.
- **No network calls beyond the audited page** — URL-like fields inside
  structured data are checked for syntactic validity only, never fetched.
- **Never fabricates evidence.** Every finding's evidence is a literal
  parsed value, exact error message, or exact key list from the actual
  JSON-LD — never a guess at what the page "probably" intends.
- **Fails loudly.** Unreachable pages produce a `critical` finding rather
  than crashing the whole audit; malformed CLI invocation exits non-zero.