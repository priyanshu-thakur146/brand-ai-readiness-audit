# Brand AI-Readiness Audit Marketplace

An enterprise-grade **Agent Skill Marketplace** that audits any brand website for **AI Discoverability** (why a brand is or isn't cited by ChatGPT, Claude, Perplexity, and Gemini) and **On-Site Engagement** (why visitors who arrive from search don't convert or stay).

It generates a single, evidence-backed diagnostic report with prioritized remediation steps — powered by an **adaptive dual-engine architecture** (Playwright Chromium DOM rendering with zero-crash sandbox HTTP fallback).

---

## Key Marketplace Innovations & Highlights

- **Adaptive Dual-Engine Rendering Architecture**:
  - **Headless Browser Execution**: Uses Playwright Chromium when available in the host environment to fully render modern Single Page Applications (Next.js, React, Vue, Gatsby SPAs), execute dynamic JavaScript, and bypass anti-bot WAF challenges.
  - **Zero-Crash Sandbox Fallback**: If running in a lightweight or restricted sandbox without browser binaries, the system catches launch exceptions gracefully and falls back to static HTTP parsing with browser header emulation — guaranteeing 100% crash-free execution.
- **Fail-Safe Marketplace Composition**:
  - Implements isolated check execution across 6 specialized skills. An unexpected timeout or network error in one module never crashes the audit run; partial results are safely captured as meta-findings.
- **Dual-Focus Evaluation**:
  - Evaluates both **Off-Site AI Discoverability** (crawlability, JS gaps, structured metadata, extractability, entity disambiguation, freshness corroboration) and **On-Site User Engagement** (mobile viewport responsiveness, navigation landmarks, call-to-action prominence, broken link sampling, page latency).

---

## Marketplace Skill Architecture

| Skill Folder | Core Technical Focus | Diagnostic Scope |
|---|---|---|
| [`audit-orchestrator`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/audit-orchestrator) **(Entrypoint)** | Master Orchestration & Composition | Coordinates all sub-skills, handles fail-safe error isolation, normalizes findings, and outputs the final report. |
| [`crawl-render-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/crawl-render-audit) | Crawlability & JS Render Gaps | Evaluates `robots.txt`, XML sitemaps, indexing directives (`noindex`), canonical links, and detects client-side rendering traps (Next.js/React root shells). |
| [`structured-data-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/structured-data-audit) | Machine-Readable Metadata | Validates schema.org JSON-LD blocks (`Organization`, `Product`, `Article`, `FAQPage`), meta descriptions, Open Graph preview tags, and plain-text fact availability. |
| [`fact-extractability-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/fact-extractability-audit) | LLM Content Extractability | Inspects heading hierarchy (`h1`-`h6`), opening lead sentence clarity, non-text media traps (images/canvas/PDFs), and signal-to-boilerplate text ratio. |
| [`freshness-corroboration-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/freshness-corroboration-audit) | Content Staleness & Corroboration | Checks HTTP/meta recency timestamps and scores cross-source web corroboration across third-party domains (Crunchbase, Wikipedia, news sources). |
| [`entity-disambiguation-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/entity-disambiguation-audit) | Brand Entity Authority Anchors | Audits `schema.org` `sameAs` authority profiles (Wikidata, Wikipedia, LinkedIn) and Name-Address-Phone (NAP) consistency to resolve brand name ambiguity. |
| [`engagement-audit`](file:///c:/Users/Lenovo/OneDrive/Documents/adobe-project/brand-ai-readiness-audit/skills/engagement-audit) | On-Site User & Agent Retention | Assesses mobile viewport tags, `<nav>` landmark accessibility, call-to-action (CTA) prominence, internal link health sampling (404 detection), and TTFB latency. |

---

## Output Schema Specification

The marketplace emits a clean, standardized JSON artifact ready for API consumption, dashboard visualization, or executive reporting:

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
    "low": 0,
    "proactive_suggestions": 1,
    "time_limit_seconds": 120,
    "execution_time_seconds": 5.58
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
  "proactive_suggestions": [
    {
      "id": "CR-P-006",
      "title": "No llms.txt found (emerging AI-crawler convention)",
      "suggested_action": "Consider publishing an llms.txt at the site root — a short, plain-text index written specifically for AI agents."
    }
  ],
  "checks_run": [
    "crawl-render-audit",
    "structured-data-audit",
    "fact-extractability-audit",
    "freshness-corroboration-audit",
    "entity-disambiguation-audit",
    "engagement-audit"
  ]
}
```

---

## Getting Started & Execution

### 1. Installation

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

*(Optionally install Playwright browser binaries for full dynamic JS rendering):*
```bash
python -m playwright install chromium
```

### 2. Running a Full Audit

Run the master orchestrator against any website:

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com --output audit_report.json
```

### 3. Running with Web Corroboration Evidence

Pass agent-gathered search results for deep cross-source verification:

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com \
    --search-results sample_search_results.json \
    --output audit_report.json
```

### 4. Running Individual Skills Independently

Every skill in the marketplace can be executed as a standalone module, e.g.:

```bash
python skills/crawl-render-audit/scripts/crawl_render_check.py https://example.com
python skills/structured-data-audit/scripts/structured_data_check.py https://example.com
```

---

## Operational Guardrails & Safety

- **Read-Only & Non-Destructive**: All audit checks perform purely read-only HTTP GET/HEAD requests and DOM parsing; no skill alters live target sites.
- **Respectful Crawling**: Fully respects `robots.txt` disallow directives and limits internal link health checks to small, non-disruptive samples.
- **Self-Contained Portability**: Every skill conforms to the open `agentskills.io` standard, requiring zero external server setup or proprietary model weights.

