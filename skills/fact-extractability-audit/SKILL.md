---
name: fact-extractability-audit
description: Checks whether the page's important facts are easy for a summarizer to pull out — clear heading hierarchy, a scannable lead/summary near the top, facts not locked inside images/canvas/video/PDF without a text equivalent, and a healthy signal-to-filler ratio. Use this to catch the "content is technically readable but a machine still can't find the point" failure mode described in Appendix C and F of the brief.
license: MIT
allowed-tools: [bash, python]
---

# Fact Extractability Audit

## When to use
Use alongside `structured-data-audit`. Appendix C says a machine is far more likely to correctly
extract a fact that is stated explicitly and unambiguously in plain text; Appendix F makes the same
point about email summarizers dropping content that's buried under filler or locked in a non-text
form. This skill generalizes that reasoning to any page.

## Inputs
- `url` (required)
- `timeout` (optional, default 15s)

## Procedure
1. Parse the heading structure (`h1`-`h6`). Flag missing/duplicate `h1`, and flag skipped levels
   (e.g. `h1` straight to `h4`) which make it harder for an extractor to build a reliable outline.
2. Check the first ~150 words of visible body text for a clear, concrete lead sentence (heuristic:
   presence of a subject + a concrete noun/number early on) vs. generic marketing filler
   ("welcome to", "we are passionate about", "learn more") with no concrete claim.
3. Inventory non-text content that may carry facts: images without `alt` text, `<canvas>` elements,
   embedded `<video>`/`<iframe>` without a text transcript or caption nearby, and linked PDFs with
   no on-page text summary. Flag when these appear central to the page (e.g. large hero images with
   no alt text on a page otherwise thin on text).
4. Estimate a coarse boilerplate ratio: proportion of visible text inside nav/footer/cookie-banner-like
   containers vs. main content, as a proxy for how much "signal" surrounds the real facts.
5. Emit findings via `scripts/fact_extractability_check.py`.

## Output
Findings with `id` prefixed `FE-`, following the shared schema.
