---
name: engagement-audit
description: Audits on-site user engagement and retention barriers. Diagnoses mobile viewport configuration, presence of structured navigation landmarks (`<nav>`), prominent calls-to-action (CTAs), broken internal links, and page load latency.
license: MIT
allowed-tools: [bash, python]
---

# Engagement Audit

## Overview & Purpose
Getting discovered by an AI assistant or search engine is only half the battle. When users (or AI agents acting on a user's behalf) click through to a brand's website, poor mobile responsiveness, missing navigation, broken internal links, or absent calls-to-action cause immediate bounces.

The **Engagement Audit** skill evaluates user retention factors, ensuring that traffic converted from AI search results experiences a seamless, high-converting landing environment.

## Key Technical Features
- **Mobile Viewport Optimization Check**: Verifies `<meta name="viewport" content="width=device-width, initial-scale=1">` to ensure mobile visitors and browser agents receive a responsive, mobile-optimized layout.
- **Navigation Accessibility Audit**: Inspects for `<nav>` tags or `role="navigation"` regions containing valid internal links. Pages lacking discoverable navigation trap users on a single page.
- **Call-to-Action (CTA) Prominence**: Scans button and anchor elements for high-converting action phrasing ("sign up", "get started", "contact us", "buy now", "book demo", "subscribe", "download").
- **Broken Link Verification**: Samples internal links on the page and tests HTTP response statuses to detect 404 broken links that disrupt user journeys.
- **Load Latency & Document Weight Assessment**: Estimates document byte size and TTFB response latency as proxies for load-speed bounce risk.

## Input Parameters
- `url` *(required)*: The target page URL to evaluate.
- `timeout` *(optional)*: Maximum request timeout in seconds (defaults to 15s).
- `max_links_checked` *(optional)*: Number of internal links sampled for health checks (defaults to 8).

## Diagnostic Procedure
1. **Viewport Meta Inspection**: Audits HTML headers for standard mobile viewport tags.
2. **Navigation Region Check**: Verifies structured `<nav>` elements and link counts.
3. **CTA Phrase Pattern Matching**: Scans visible interactive elements for actionable converter verbs.
4. **Internal Link Health Sampling**: Executes concurrent HEAD/GET requests against internal links to identify broken URLs.
5. **Execution**: Emits findings via `scripts/engagement_check.py`.

## Output Structure
Emits findings prefixed with `EN-` adhering to the marketplace findings schema:
- `id`: e.g., `EN-001`, `EN-002`, `EN-003`
- `category`: `"engagement"`
- `title`: Problem title (e.g., "Missing/incorrect mobile viewport meta tag")
- `severity`: `"critical"`, `"high"`, `"medium"`, or `"low"`
- `evidence`: Specific DOM findings, missing viewport tags, or sampled broken link URLs
- `suggested_action`: Actionable UX and technical recommendations to boost user retention

