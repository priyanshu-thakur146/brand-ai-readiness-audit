---
name: fact-extractability-audit
description: Evaluates how easily an automated summarizer or LLM extractor can parse a page's actual claims, independent of structured markup. Checks heading hierarchy (h1-h6), whether the opening ~150 words state a concrete fact versus generic marketing filler, non-text media traps (images without alt text, canvas, embedded video without transcript, linked PDFs) that hide facts from text parsers, and the signal-to-boilerplate ratio between main content and navigation/footer/cookie-banner noise. Use when a page is crawlable and has some structured data, but its real claims still seem to get lost or diluted.
license: MIT
allowed-tools: [bash, python]
---

# `skills/fact-extractability-audit/` — LLM Content-Extractability Audit

## When to use
`structured-data-audit` checks whether a fact has explicit machine-readable markup.
`fact-extractability-audit` checks the layer beneath that: even with perfect prose and no schema
at all, is the *plain text itself* organized so a summarizer can find the one sentence that
matters? Per the Round-2 background, the more explicitly and unambiguously a fact is stated in
plain readable text, the more likely a machine extracts it correctly — this skill operationalizes
that principle.

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page URL to evaluate. |
| `timeout` | no | Max request timeout in seconds (default `15`). |

## Procedure (numbered, deterministic steps)
1. **Heading outline validation** — walk `<h1>`–`<h6>` in document order. Flag a missing or
   duplicated `<h1>`, and flag skipped levels (`<h1>` straight to `<h4>`) — both break the document
   outline a summarizer relies on to know which text is the main claim versus a sub-detail.
2. **Lead-sentence clarity scoring** — take the first ~150 words of visible body copy and check
   whether it opens with a concrete claim (a specific noun, number, or offer) versus generic
   filler ("welcome to", "we are passionate about"). A page that buries its actual value
   proposition below three paragraphs of tone-setting copy is functionally the same problem as
   missing structured data: the fact is technically present but effectively unextractable.
3. **Non-text media risk audit** — inventory `<img>` tags missing descriptive `alt` text, bare
   `<canvas>` elements, `<iframe>`/video embeds without a transcript, and links to `.pdf` files
   that carry facts a text-only parser will never open. Each is a place a real fact can be
   "plainly visible to a human, yet invisible to the machine" (Round-2 background, section C).
4. **Boilerplate signal-to-noise ratio** — compare the word count of the identified main-content
   region against navigation, header/footer, and sidebar/cookie-banner containers; a page that's
   mostly chrome and little substance dilutes whatever real content exists.
5. **Emit findings** via `scripts/fact_extractability_check.py`, run once per page inside the
   orchestrator's serial, one-page-at-a-time crawl loop.

## Output
Findings prefixed `FE-` (aggregate site-wide patterns use `FE-AGG-###`), each with `id`,
`category: "discoverability"`, `title`, `severity` (`critical`/`high`/`medium`/`low`/`info`),
`evidence` (pattern-match counts, heading sequences, boilerplate ratios), and `suggested_action`
with concrete copywriting/HTML remediation advice.
