# Content Extractability — Heuristics Reference

This document lists the heuristics used by the **content-extractability-audit**
skill to judge whether important information can be clearly extracted from a
page's HTML content.

---

## Heading Quality

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| H1 presence | Page has exactly one `<h1>` | medium |
| Heading hierarchy | Headings follow a logical order (h1 → h2 → h3), no skipped levels | low |
| Descriptive headings | Headings contain meaningful text (not "Section 1", "Untitled") | medium |
| Heading length | Headings are between 3 and 100 characters | low |

## Text Structure

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| Text-to-markup ratio | Visible text ÷ total HTML size > 0.10 | medium |
| Paragraph length | Average paragraph > 20 words (indicates real content, not stubs) | low |
| List usage | Important enumerations use `<ul>/<ol>` instead of plain text with dashes | info |
| Table headers | Data tables have `<th>` elements | low |

## Image Accessibility

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| Alt text presence | All `<img>` tags have non-empty `alt` attributes | high |
| Alt text quality | Alt text is descriptive (> 5 chars, not just "image" or filename) | medium |
| Decorative images | Images with `role="presentation"` or empty alt are acceptable | info |
| Image count vs alt count | Percentage of images with meaningful alt text | high (< 50%), medium (50-80%) |

## Link Quality

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| Descriptive link text | Links use descriptive text, not "click here" or "read more" | medium |
| Internal link coverage | Key pages are linked from the audited page | low |
| Broken anchor links | In-page anchors (`#section`) point to existing IDs | low |

## Semantic Markup

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| Landmark elements | Page uses `<header>`, `<main>`, `<nav>`, `<footer>` | medium |
| Article structure | Long-form content wrapped in `<article>` | low |
| Language attribute | `<html lang="...">` is set | medium |
| Title tag | `<title>` is present and descriptive (10–70 chars) | high |
| Meta description | `<meta name="description">` is present and descriptive (50–160 chars) | medium |

## Fact Extractability

| Heuristic | What to check | Severity |
|-----------|---------------|----------|
| Contact information | Phone/email/address are in text, not only in images | high |
| Key facts in text | Pricing, hours, locations exist as text, not only in images/PDFs | high |
| Ambiguous pronouns | Content avoids excessive "we", "our", "it" without clear antecedents near key facts | low |
| Entity naming | Brand/product name appears explicitly (not only in logo image) | medium |