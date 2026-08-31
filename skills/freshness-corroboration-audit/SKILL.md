---
name: freshness-corroboration-audit
description: Use when auditing a webpage or site for content-freshness and internal-consistency issues — checks whether pages expose a discoverable date, whether dateModified/datePublished are logically consistent, whether content is stale relative to language implying it's current, and whether the same labeled fact (price, phone number, version) is stated consistently across the site's own sampled pages.
---

# freshness-corroboration-audit

## When to use

Invoke this skill (directly, or as one of the five specialists composed by
`audit-orchestrator`) whenever the task is to evaluate **how current a page's
content is, and whether the site agrees with itself** — as opposed to
whether content is extractable (`content-extractability-audit`), crawlable
(`crawl-render-audit`), engaging (`engagement-audit`), or carries valid
structured-data markup (`structured-data-audit`; that skill checks that a
`datePublished` field is *present and well-formed* — this skill checks
whether its *value* is stale or self-contradictory).

This skill answers two distinct questions:
1. *Does this page tell a reader (or an AI agent) how current it is, and is
   that date internally consistent and not stale relative to language
   implying currency?*
2. *Do the site's own pages agree with each other on facts they both state?*

## Important scope boundary: "corroboration" is internal, not external

This skill does **not** fetch or compare against any third-party/external
source to fact-check claims — that would require an external ground truth
this skill has no access to within the read-only, no-third-party-lookup
guardrail, and fabricating a "verified true/false" verdict without one would
violate the never-fabricate-evidence requirement. "Corroboration" here means
strictly **internal cross-page self-consistency**: when the site's own pages
state the same labeled fact (price, phone number, version number)
differently, that's a checkable, deterministic contradiction regardless of
which value (if either) is correct.

## Inputs

- `url` — the base URL of the site being audited.
- `pages` (optional) — a list of page URLs to sample. **Cross-page
  corroboration only runs when 2+ pages are provided** — with a single page,
  this skill still runs the date-presence/logic/staleness checks, just not
  the cross-page fact comparison.
- `now_iso` (optional) — pins "today" for reproducible runs; defaults to
  real UTC today.
- `stale_days` (optional) — threshold in days before a date signal counts as
  stale; defaults to ~18 months (540 days).

## Procedure

1. **Fetch each sampled page** with a real HTTP request.
2. **Extract date signals from three sources**, in this priority order for
   "most recent date" purposes: JSON-LD `datePublished`/`dateModified`,
   relevant `<meta>` tags (`article:published_time`, `article:modified_time`,
   etc.), then a small set of explicit date patterns (ISO 8601,
   `Month D, YYYY`, `M/D/YYYY`) matched in visible text. Date parsing is
   pattern-based and explicit, never a fuzzy guess — a misparsed date
   producing a false staleness finding is worse than missing a real one.
3. **If no date signal exists anywhere**, emit a `medium` finding — this is
   itself a freshness problem: neither a human reader nor an AI agent can
   judge how current the content is.
4. **Check internal date logic**: if both `datePublished` and
   `dateModified` are present in JSON-LD and `dateModified` predates
   `datePublished`, that's a direct self-contradiction — `high` severity.
5. **Check staleness**: take the single most recent date signal found. If
   its age exceeds `stale_days`, emit a finding. Severity is `high` if the
   page's own text also uses currency language ("currently", "as of",
   "latest", "this year") alongside that old date — the mismatch between
   what the text claims and what the date shows is the sharper signal;
   `medium` if the date is merely old with no currency-language claim
   compounding it.
6. **Extract labeled facts** from visible text on each sampled page: price
   (`$NN.NN` patterns), phone number, version number. These are the fact
   types with a clear, low-ambiguity regex and genuine risk of drifting out
   of sync across pages (e.g. a pricing page and a homepage CTA).
7. **Cross-page corroboration** (only with 2+ pages): for each fact label,
   if a page shows exactly *one* distinct value for that label, record it.
   If two or more pages each show a single, different value for the same
   label, that's a `high`-severity mismatch. Pages with multiple different
   values for the same label internally (e.g. a page listing several
   products at several prices) are deliberately excluded from this
   comparison — that's normal multi-item content, not a fact this check has
   grounds to compare.
8. **Write one raw finding per genuine issue**, using the shared schema
   documented in `scripts/corroborate.py`'s docstring. Every `evidence`
   string quotes the literal date string, the literal fact value, and the
   literal URL(s) involved — never a paraphrase or inferred summary.
9. **Namespace all dedupe keys** as `freshness:<id_hint>`. No dedupe_key
   overlap with another skill is currently declared.
10. **Return the raw findings list** to whatever invoked this skill.

## Output

A JSON array of raw findings matching the schema in `scripts/corroborate.py`:

```json
{
  "id_hint": "cross-page-mismatch-price",
  "title": "Inconsistent price across sampled pages",
  "severity": "high",
  "evidence": "Sampled pages each show a single, different price value: https://example.com/pricing -> 29.99; https://example.com/ -> 39.99",
  "suggested_action": "Confirm which price value is correct and update the other page(s) to match ...",
  "dedupe_key": "freshness:cross-page-mismatch-price",
  "source_skill": "freshness-corroboration-audit",
  "proactive": false
}
```

This skill never emits the contest's final report directly — assembly
belongs to `audit-orchestrator`'s `report_builder.py`.

## Severity ladder and rationale

| Severity | When |
|---|---|
| `critical` | The page itself is unreachable or errors out. |
| `high` | `dateModified` predates `datePublished` (direct self-contradiction); stale content combined with currency language on the page; cross-page fact mismatch (contradicts the site's own other page). |
| `medium` | No date signal found anywhere; stale content with no currency-language claim compounding it. |
| `low` | *(reserved — this skill currently has no low-severity findings; every check here represents either a missing signal or a direct contradiction, not a cosmetic nit)* |

**Staleness threshold (`stale_days`, default ~18 months) is deliberately
generous and configurable**, not hardcoded to a specific site's expected
publishing cadence — a documentation page and a news article have very
different reasonable staleness windows, and the contest's generalization
criterion penalizes an assumption that doesn't hold across unseen sites. The
invoking orchestrator can override `--stale-days` per audit if a specific
content type warrants a tighter or looser threshold; the default is a
conservative middle ground that avoids flagging genuinely evergreen content.

**Currency language escalates severity, it doesn't create the finding.** A
stale date alone is `medium` — plenty of legitimately old content (an
archived blog post, a historical reference page) is fine to leave as-is. The
finding only escalates to `high` when the page's *own text* claims to be
current ("as of", "currently") while showing an old date — that's the
combination that actually misleads a reader, not staleness in isolation.

**Cross-page fact comparison is narrow by design** (price, phone, version
only) and requires each compared page to have a *single* distinct value for
that label — this avoids false positives on pages that legitimately list
multiple prices/numbers (e.g. a pricing-tiers page), which would otherwise
create constant noise unrelated to genuine inconsistency.

## Scope boundary with other skills

This skill does not check whether a `datePublished` field is *present and
schema-valid* (`structured-data-audit`'s job) — only whether its *value* is
stale or self-contradictory once found. It does not check whether content is
locked in non-text elements (`content-extractability-audit`) or whether the
page renders without JavaScript (`crawl-render-audit`). No dedupe_key is
currently shared with another skill.

## Guardrails

- **Read-only.** Only GET requests to the audited pages themselves — never
  fetches any third-party page to "verify" a fact's real-world accuracy.
- **Never fabricates a ground truth.** This skill does not claim to know
  which of two conflicting values is correct — it reports the contradiction
  and lets a human resolve it, consistent with never asserting evidence it
  cannot directly observe.
- **Deterministic date parsing.** Only explicit, listed date formats are
  parsed; anything else is treated as "no date signal" rather than guessed
  at, to avoid false-positive staleness findings from a misparsed string.
- **Fails loudly.** Unreachable pages produce a `critical` finding rather
  than crashing the whole audit; malformed CLI invocation exits non-zero.