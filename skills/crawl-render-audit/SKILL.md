---
name: crawl-render-audit
description: Audits whether a website can be successfully reached, indexed, and parsed by AI crawlers and search engines. Diagnoses robots.txt access rules, XML sitemap presence, indexing directives (noindex / X-Robots-Tag), canonical links, server latency, and client-side JavaScript rendering gaps (React, Next.js, Vue, Gatsby SPAs). Powered by an adaptive dual-engine architecture featuring Playwright Chromium DOM rendering with zero-crash sandbox HTTP fallback.
license: MIT
allowed-tools: [bash, python]
---

# Crawl & Render Audit

## Overview & Purpose
For a brand to be discovered, summarized, or cited by AI assistants (such as ChatGPT, Claude, Perplexity, and Gemini), AI crawlers must be able to (1) access the website without blockages and (2) extract readable content from the initial server payload.

The **Crawl & Render Audit** skill evaluates these foundational access gates. It identifies technical blockages that render pages completely invisible to automated fetchers or trap content behind unrendered client-side JavaScript.

## Core Technical Features & Dual-Engine Architecture
- **Playwright Headless Chromium Engine**: Automatically leverages Playwright when available to execute JavaScript, hydrate client-side DOMs (Single Page Applications like Next.js, React, Vue, Gatsby), and bypass anti-bot WAF challenges.
- **Resilient Sandbox Fallback**: If Playwright is not installed or browser execution is restricted in a lightweight sandbox environment, the engine catches launch exceptions gracefully and falls back to static HTTP parsing with browser header emulation — guaranteeing 100% crash-free execution.
- **JS Render Gap Detection**: Measures the difference between raw HTML visible text and post-execution DOM text, explicitly flagging SPA shell root elements (`<div id="__next">`, `<div id="root">`, `<div id="app">`, `___gatsby`) paired with thin text.

## Input Parameters
- `url` *(required)*: The target page or domain URL to evaluate.
- `timeout` *(optional)*: Maximum request/render timeout in seconds (defaults to 15s).

## Diagnostic Procedure
1. **Robots Accessibility**: Fetches `/robots.txt` and evaluates `Disallow` rules targeting general and AI-specific user agents (`*`, `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`, `Googlebot`).
2. **Sitemap Discovery**: Checks `/sitemap.xml` and `robots.txt` `Sitemap:` directives to ensure crawlers have a clear content index.
3. **Response & Indexing Health**: Evaluates HTTP status codes, server latency (flagging TTFB > 3s), `X-Robots-Tag` headers, and `<meta name="robots" content="noindex">` directives.
4. **Canonical Signal Validation**: Verifies self-referencing `<link rel="canonical">` tags to prevent authority fragmentation across parameterized URLs.
5. **JavaScript Render Gap Analysis**: Strips non-content tags, measures visible word count, detects SPA root shells, and checks for `<noscript>` fallbacks.
6. **Emerging AI Standards**: Scans for `/llms.txt` at the root directory to offer proactive guidance for emerging AI indexing standards.

## Output Structure
Emits structured findings with unique `CR-` prefixes adhere to the marketplace finding schema:
- `id`: e.g., `CR-001`, `CR-002` (or proactive `CR-P-001`)
- `category`: `"discoverability"`
- `title`: Concise diagnostic headline
- `severity`: `"critical"`, `"high"`, `"medium"`, `"low"`, or `"info"`
- `evidence`: Empirical data detailing response codes, word counts, or render engine used
- `suggested_action`: Actionable, prioritized recommendation for technical teams


