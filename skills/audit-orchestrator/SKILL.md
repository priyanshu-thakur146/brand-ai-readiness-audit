---
name: audit-orchestrator
description: Master entrypoint skill for the Brand AI-Readiness Audit Marketplace. Evaluates any target website across 6 specialized dimensions — technical crawlability, JS/SPA dynamic rendering, structured data clarity, fact extractability, brand entity disambiguation, and on-site user engagement. Operates with adaptive dual-engine rendering (headless Playwright Chromium with zero-crash sandbox HTTP fallback) to generate actionable, evidence-backed reports with prioritized recommendations.
license: MIT
allowed-tools: [bash, python, web_search, web_fetch]
---

# Brand AI-Readiness Audit — Orchestrator

## Overview & Purpose
When an AI assistant (ChatGPT, Claude, Perplexity, Gemini) answers user queries about a brand, it relies on real-time web retrieval, machine extraction, and cross-source verification. If a website's facts are locked behind client-side JavaScript, obscured by thin copy, or missing structured metadata, the brand becomes invisible or misrepresented in AI responses.

The **Audit Orchestrator** serves as the central intelligence hub of this marketplace. Given a domain or website URL, it systematically invokes six specialized audit skills, synthesizes their diagnostic findings, and produces a single, highly structured report tailored for executive decision-making and technical execution.

## Key Technical Strengths & Innovation
- **Adaptive Dual-Engine Rendering**: Automatically detects the runtime environment. In environments with Playwright support, it launches a headless Chromium browser to render modern Single Page Applications (Next.js, React, Vue, Gatsby) and bypass anti-bot challenges. If running in a lightweight or restricted sandbox without browser binaries, it seamlessly falls back to static HTTP parsing with browser header emulation — ensuring 100% crash-free execution.
- **Fail-Safe Skill Composition**: Employs isolated check execution so that unexpected network timeouts or edge-case errors in one skill never compromise the overall audit. Every finding is assigned an explicit severity (`critical`, `high`, `medium`, `low`, or `info`) backed by concrete technical evidence.
- **Dual-Focus Evaluation**: Simultaneously evaluates **Off-Site AI Discoverability** (how easily AI crawlers find, parse, and cite the brand) and **On-Site User Engagement** (how effectively the site retains visitors once they land).

## Input Arguments
- `url` *(required)*: The target website URL to audit (e.g., `https://example.com`).
- `search_results` *(optional)*: Pre-gathered web search data used by the entity disambiguation and freshness corroboration modules for cross-source validation.
- `output_path` *(optional)*: Destination file path for the generated JSON report (defaults to `audit_report.json`).

## Audit Execution Flow
1. **Orchestration**: Runs checks in sequence across all 6 core marketplace skills:
   - **Crawl & Render Audit (`CR-`)**: Tests crawler access (`robots.txt`, sitemaps, `noindex`), response latency, and client-side JS rendering gaps.
   - **Structured Data Audit (`SD-`)**: Validates schema.org JSON-LD blocks, Open Graph metadata, title/description tags, and key business facts.
   - **Fact Extractability Audit (`FE-`)**: Analyzes heading structure, lead paragraph clarity, non-text content traps (PDFs/images), and signal-to-boilerplate text ratio.
   - **Freshness & Corroboration Audit (`FR-`)**: Evaluates content recency timestamps, staleness risks, and external claim corroboration.
   - **Entity Disambiguation Audit (`ED-`)**: Verifies `sameAs` authority links (Wikidata, Wikipedia, LinkedIn) and NAP (name/address/phone) consistency to prevent brand identity confusion.
   - **On-Site Engagement Audit (`EN-`)**: Assesses mobile viewport optimization, navigation accessibility, call-to-action (CTA) prominence, broken internal links, and page load performance.
2. **Aggregation & Normalization**: Collects all findings, applies standardized severity sorting (`critical` → `high` → `medium` → `low`), and generates proactive optimization recommendations.
3. **Report Generation**: Emits a clean, schema-compliant JSON artifact ready for API integration, agent workflows, or dashboard visualization.

## Output Schema
Emits a structured JSON audit report following the marketplace standard:
```json
{
  "site": "example.com",
  "audited_at": "2026-09-07T14:30:00Z",
  "summary": {
    "pages_crawled": 1,
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0
  },
  "findings": [
    {
      "id": "SD-001",
      "category": "discoverability",
      "title": "Missing Organization JSON-LD markup",
      "severity": "high",
      "evidence": "Zero <script type=\"application/ld+json\"> blocks found on homepage.",
      "suggested_action": {
        "summary": "Add schema.org Organization markup with name, url, logo, and sameAs links.",
        "priority": "high"
      }
    }
  ],
  "checks_run": ["crawl-render-audit", "structured-data-audit", ...]
}
```

## Security & Operational Guardrails
- **Read-Only & Non-Destructive**: Performs purely read-only diagnostics; never modifies live websites, authenticates, or attempts intrusive actions.
- **Respectful Crawling**: Fully respects `robots.txt` directives and limits internal link sampling to preserve target server resources.
- **Self-Contained & Portable**: Zero external API dependencies required for core auditing, ensuring high execution speed and maximum portability across any AI agent sandbox.


