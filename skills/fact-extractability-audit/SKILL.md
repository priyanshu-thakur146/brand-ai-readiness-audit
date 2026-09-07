---
name: fact-extractability-audit
description: Evaluates how easily automated text summarizers and LLM extractors can parse a web page's core claims. Diagnoses heading hierarchy (`h1`-`h6`), opening lead sentence clarity, non-text content traps (hero images, canvas, embedded videos, linked PDFs), and signal-to-boilerplate text ratios.
license: MIT
allowed-tools: [bash, python]
---

# Fact Extractability Audit

## Overview & Purpose
Even when a page is technically readable and indexed, AI summarizers frequently fail to extract the main value proposition if the primary claims are buried beneath vague marketing fluff, surrounded by navigation noise, or locked in non-text media.

The **Fact Extractability Audit** skill evaluates page content from the perspective of an automated text parser. It ensures that key facts are prominent, structurally outlined, and free from excessive boilerplate.

## Key Technical Features
- **Heading Outline Validation**: Inspects heading tags (`<h1>`-`<h6>`) for proper hierarchy. Flags missing or duplicate `<h1>` tags and skipped heading levels (e.g., `<h1>` directly to `<h4>`), which break document outline parsing.
- **Lead Sentence Clarity Scoring**: Analyzes the first ~150 words of body copy. Detects whether the opening lead contains concrete facts (nouns, numbers, specific offers) versus generic marketing filler ("welcome to", "we are passionate about").
- **Non-Text Media Risk Audit**: Scans for images lacking descriptive `alt` text, canvas elements, videos without transcripts, and unparsed linked PDFs containing critical facts.
- **Boilerplate Signal-to-Noise Ratio**: Calculates the ratio of main body text against navigation, footer, sidebar, and cookie banner containers to ensure AI parsers isolate the core content.

## Input Parameters
- `url` *(required)*: The target page URL to evaluate.
- `timeout` *(optional)*: Maximum request timeout in seconds (defaults to 15s).

## Diagnostic Procedure
1. **Heading Structure Analysis**: Evaluates hierarchy and tag sequence for outline integrity.
2. **Lead Clarity Detection**: Evaluates the initial paragraph for concrete value claims vs. low-value marketing copy.
3. **Media & Document Inventory**: Audits `<img>`, `<canvas>`, `<iframe>`, and `<a href="*.pdf">` elements for missing text alternatives.
4. **Boilerplate Calculation**: Compares main content DOM nodes against global navigation and header/footer wrappers.
5. **Execution**: Emits findings via `scripts/fact_extractability_check.py`.

## Output Structure
Emits findings prefixed with `FE-` adhering to the marketplace findings schema:
- `id`: e.g., `FE-001`, `FE-002` (or proactive landmark suggestion `FE-AGG-001`)
- `category`: `"discoverability"`
- `title`: Problem title (e.g., "Opening content is generic marketing copy with no concrete claim")
- `severity`: `"critical"`, `"high"`, `"medium"`, `"low"`, or `"info"`
- `evidence`: Empirical count of pattern matches, heading sequences, or boilerplate ratios
- `suggested_action`: Specific copywriting and HTML structural remediation advice

