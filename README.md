# 🚀 Brand AI Readiness Audit

### Adobe University Hackathon 2026 — Round 3

**A modular Agent Skill Marketplace for AI Discoverability + On-Site Engagement**

| | |
|---|---|
| **Team** | codezilla |
| **Members** | Priyanshu Thakur (Team Leader), Dheerendra Singh Lodhi, Vilas Patel |
| **Entrypoint skill** | `audit-orchestrator` |
| **Total skills** | 6 (1 entrypoint + 5 specialists) — **all 6 implemented and tested**, not skeletons |

---

## 📌 Table of Contents

1. [Our Submission](#-our-submission)
2. [What We Solve](#-what-we-solve)
3. [Our Core Approach](#-our-core-approach)
4. [Marketplace Architecture](#️-our-marketplace-architecture)
5. [Our Skills](#-our-skills)
6. [Evidence-Backed Findings](#-evidence-backed-findings)
7. [Testing & Validation](#-testing--validation)
8. [One Consolidated Report](#-one-consolidated-report)
9. [Why We Chose This Decomposition](#️-why-we-chose-this-decomposition)
10. [Generalization Over Examples](#-generalization-over-examples)
11. [Safety & Scope](#️-safety--scope)
12. [Repository Structure](#-repository-structure)
13. [Setup & How to Run](#-setup--how-to-run)
14. [Runtime & Submission Constraints](#️-runtime--submission-constraints)
15. [Rubric Alignment](#-rubric-alignment)
16. [What We Delivered](#-what-we-delivered)

---

## 👋 Our Submission

We built **Brand AI Readiness Audit** as a modular Agent Skill Marketplace that allows a general AI agent to audit a public website and identify the factors that can make a brand:

* difficult for AI systems to discover,
* difficult for AI systems to understand or cite,
* stale, ambiguous, or poorly corroborated,
* or difficult for visitors to understand and engage with after arrival.

Our goal is simple:

> **We don't just want to tell a brand that it is invisible. We want to identify why it is invisible, show evidence for the problem, and recommend what should be done about it.**

The hackathon asks us to encode the reasoning from Round 2 into reusable agent skills that generalize to websites we have never seen before. Our marketplace is designed around that requirement — and, as of this submission, every skill in it is a working, tested implementation rather than a scaffold we're still filling in.

---

## 🎯 What We Solve

We treat Brand AI Readiness as two connected problems:

### 1️⃣ AI Discoverability

Can automated systems:

**Reach → Read → Extract → Understand → Trust**

the information about a brand?

We therefore investigate issues such as:

* crawlability,
* JavaScript rendering gaps,
* missing or invalid structured data,
* facts that are difficult to extract,
* stale information,
* weak external corroboration,
* entity ambiguity and inconsistent identity signals.

### 2️⃣ On-Site Engagement

Even when AI systems successfully surface a brand, the user still has to interact with its website.

We therefore inspect signals around:

**Arrival → Orientation → Understanding → Action**

including:

* page performance,
* navigation,
* contextual orientation,
* content hierarchy,
* calls-to-action,
* and friction that can prevent the visitor from taking the next meaningful step.

The challenge explicitly requires coverage of both off-site discoverability and on-site engagement.

---

## 🧠 Our Core Approach

We designed the marketplace around **evidence-first auditing**.

Instead of producing generic recommendations such as:

> "Improve your SEO."

we aim to produce findings such as:

```text
Problem
   ↓
Observable evidence
   ↓
Severity
   ↓
Why it matters
   ↓
Specific recommended action
   ↓
Priority
```

This makes the output useful to someone who may not be an SEO or web-engineering expert.

The hackathon requires each finding to contain an `id`, `title`, `severity`, `evidence`, and `suggested_action`, along with site, timestamp, and severity counts in the report summary.

---

## 🏗️ Our Marketplace Architecture

We intentionally split the audit into focused skills rather than building one large monolithic skill.

```text
                         ┌──────────────────────┐
                         │     Audit Request    │
                         │      URL / Domain    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                    ┌────────────────────────────┐
                    │     AUDIT ORCHESTRATOR     │
                    │        ENTRYPOINT          │
                    └─────────────┬──────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
 ┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
 │ Crawl & Render  │     │ Structured Data  │     │ Content            │
 │ Audit           │     │ Audit            │     │ Extractability     │
 └─────────────────┘     └──────────────────┘     └────────────────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
          ┌──────────────────────┐   ┌──────────────────────┐
          │ Freshness &          │   │ Engagement Audit    │
          │ Corroboration        │   │                      │
          └──────────┬───────────┘   └──────────┬───────────┘
                     │                          │
                     └────────────┬─────────────┘
                                  ▼
                    ┌────────────────────────────┐
                    │ Merge → Deduplicate →      │
                    │ Score → Prioritize         │
                    └─────────────┬──────────────┘
                                  ▼
                    ┌────────────────────────────┐
                    │       FINAL REPORT         │
                    │ Evidence + Severity + Fixes│
                    └────────────────────────────┘
```

The hackathon specifically encourages multiple focused skills where the decomposition represents genuine separation of concerns, with exactly one designated entrypoint responsible for composing the final report.

---

## 🧩 Our Skills

### 🔗 1. Audit Orchestrator — Entry Point

**Location:** `skills/audit-orchestrator/`

This is the **only entrypoint** in our marketplace. It receives the audit request and coordinates the specialized skills.

Its responsibilities include:

* invoking the appropriate audit skills,
* collecting their findings,
* normalizing severity vocabulary (different skills may phrase severity slightly differently — the orchestrator maps synonyms like "major"/"blocker" onto one fixed scale),
* deduplicating overlapping findings — via an explicit, skill-declared `dedupe_key` where two specialists knowingly cover the same root cause, with a conservative fuzzy-title fallback otherwise,
* assigning stable finding IDs and priority ordering,
* adding proactive, non-defect recommendations,
* and producing the final structured audit report.

The orchestrator is the layer that turns multiple specialized analyses into **one coherent answer for the user**.

---

### 🌐 2. Crawl & Render Audit

**Location:** `skills/crawl-render-audit/`

We inspect whether important website content is accessible to automated systems. Our checks cover signals such as:

* `robots.txt` (including AI-crawler-specific disallow rules, e.g. a block scoped only to `GPTBot`),
* `sitemap.xml` presence and validity,
* HTTP status codes,
* raw HTML vs. headless-rendered DOM content — measuring whether a page's meaningful content only exists after JavaScript executes.

A key concern is content that appears complete to a human but is missing or substantially different in the raw representation available to simpler automated readers.

---

### 🏷️ 3. Structured Data Audit

**Location:** `skills/structured-data-audit/`

We inspect machine-readable representations of website information: JSON-LD blocks, Schema.org typing, and microdata as a fallback when no JSON-LD is present.

Our checks include JSON-LD syntactic validity, required vs. recommended fields per content type (`Article`, `Product`, `Organization`, `Event`, etc.), conflicting or unrecognized `@type` values, and malformed URL-like fields — always checked for syntactic correctness only, never dereferenced over the network.

Our objective is not to require structured data everywhere, but to identify cases where applicable machine-readable information could make important facts clearer and more reliable — and to flag unrecognized types as a proactive suggestion for review rather than an asserted defect, since Schema.org has far more valid types than any fixed list can enumerate.

---

### 📝 4. Content Extractability Audit

**Location:** `skills/content-extractability-audit/`

We examine whether important information can be extracted clearly from the site's actual content: unclear headings, facts that are difficult to isolate, important information locked inside non-text elements (e.g. a price rendered only inside an image with unhelpful alt text), weak text alternatives, ambiguous statements, and poor content structure.

Our guiding principle is:

> **Important facts should be explicit, readable, and easy to identify.**

This directly reflects the challenge background: information that is visible to a human is not necessarily equally accessible to automated systems. This skill deliberately avoids flagging missing commerce facts (like pricing) on pages that aren't commerce-oriented — a judgment call aimed squarely at avoiding false positives on unseen, non-commerce sites.

---

### 🔎 5. Freshness & Corroboration Audit

**Location:** `skills/freshness-corroboration-audit/`

We investigate whether important brand facts are current, internally consistent, and clearly associated with the correct entity.

Concretely, this skill checks: whether a page exposes *any* discoverable date signal at all; whether `dateModified` and `datePublished` are logically consistent; whether the most recent date signal is stale, with severity escalated when the page's own text uses currency language ("currently", "as of", "latest") alongside an old date; and — the literal corroboration check — whether the **same labeled fact** (price, phone number, version number) is stated with two different values across the site's own sampled pages.

We are explicit that "corroboration" here means **internal cross-page self-consistency**, not external fact-checking against a third-party source — this skill has no access to an external ground truth within the read-only guardrail, and asserting one without it would violate our commitment to never fabricate evidence. It reports the contradiction and lets a human resolve it.

---

### ⚡ 6. Engagement Audit

**Location:** `skills/engagement-audit/`

We analyze the experience after a visitor reaches the website: heading structure, a navigation landmark with a link back to the homepage, call-to-action presence and clarity, a contact/support link reachable from nav or footer, mobile viewport configuration, sampled dead internal links, and response latency.

CTA severity is judgment-aware the same way content-extractability is: a missing "Buy now" CTA is only weighted heavily on pages whose own text already signals commerce intent (cart/checkout/price/shop language), so a blog post or documentation page isn't penalized for not pushing a transaction it was never meant to.

This allows our marketplace to address the second half of the challenge rather than treating AI visibility as purely a technical crawling problem.

---

## 🔬 Evidence-Backed Findings

We want our findings to be **verifiable**, not speculative.

Each finding is structured around evidence:

```json
{
  "id": "F-001",
  "title": "Example finding",
  "severity": "high",
  "evidence": "Observable evidence supporting the finding.",
  "suggested_action": {
    "summary": "Specific action to address the underlying cause.",
    "priority": "high"
  }
}
```

Where possible, our evidence describes measurable observations such as:

```text
0/12 pages contain applicable structured data
```

rather than making unsupported statements such as:

```text
Structured data is poor.
```

Every check function in every skill's script pulls its `evidence` string directly from the fetched page — a literal excerpt, an exact parsed value, or a measured fact (fetch time, link status code) — never a paraphrase or an assumption about what a page "probably" contains. This is enforced as a hard rule across all 6 skills, not left to per-skill discretion.

---

## 🧪 Testing & Validation

We did not consider a skill "done" once its `SKILL.md` and script were written — each one was exercised against synthetic test fixtures before being treated as complete, so the rubric's "detection accuracy" criterion is backed by evidence, not just prose describing intended behavior.

**What we tested, per skill:**

* **`crawl-render-audit`** — a real headless Chromium browser (Playwright) was run against a synthetic JS-only page; raw HTML measured 5 words, the rendered DOM measured 85, correctly triggering a `critical` finding. The same logic run against a normal server-rendered page correctly produced no finding. A `robots.txt` with an AI-crawler-specific disallow rule was parsed correctly. All checks were also run end-to-end over real (local) HTTP, not just offline mocks.
* **`content-extractability-audit`** — walked through against a synthetic page with three deliberately planted defects (a price locked in an image with unhelpful alt text, a fact stated only as vague implication, a self-contradicting shipping threshold across two pages); all three were correctly caught, and the resulting findings were confirmed to merge cleanly through the orchestrator's report builder.
* **`engagement-audit`** — tested against a well-formed synthetic page (zero false positives, including after fixing an early test-fixture bug where unresolvable links masked the real result) and a deliberately broken one (multiple H1s, skipped heading levels, missing nav landmark, missing viewport meta, dead links — all 6+ defects caught). CTA logic was tested separately for the generic-text-only branch and the commerce-relevance branch, each confirmed to fire only under the intended condition.
* **`structured-data-audit`** — tested against pages with valid JSON-LD (zero findings), and a deliberately broken page covering invalid JSON syntax, an empty JSON-LD block, a missing `@context`, missing required fields for `Article`, a node mixing conflicting `@type` values, and a non-absolute URL field — all 8 expected findings fired correctly. A microdata-only page correctly suppressed the "no structured data" finding, and an unrecognized `@type` was correctly flagged as a proactive suggestion rather than an asserted defect.
* **`freshness-corroboration-audit`** — tested with a pinned audit date for reproducibility, against: a fresh page (zero findings), a stale page compounded with currency language (correctly escalated to `high`), a page with no date signal at all, a page with `dateModified` predating `datePublished`, and two pages stating the same price differently (correctly flagged) versus two pages agreeing (correctly silent).
* **`audit-orchestrator`** — its `report_builder.py` was tested against multi-skill fixture data including a near-duplicate finding from two different specialists. That test surfaced a real bug: a fuzzy title-matching fallback incorrectly merged two unrelated findings on the same page because both titles happened to share URL tokens. We fixed this by introducing an explicit, skill-declared `dedupe_key` mechanism (used for genuine overlaps, like both `crawl-render-audit` and `content-extractability-audit` independently noticing the same JS-only-content root cause) and re-verified the fix against the original failing case plus the full previous test suite.

**Failure-mode testing, applied consistently across all 5 specialist skills:** an unreachable target page produces a `critical` finding rather than crashing the audit; malformed CLI invocation exits non-zero with a clear error rather than silently producing an empty or wrong report — matching `report_builder.py`'s own fail-loud convention for malformed input.

**Honest limitation:** individual skills and the orchestrator's merge logic have each been validated in isolation and pairwise, but we have not yet run all six skills back-to-back against a single real, live, previously-unseen website in one pass. That full end-to-end dry run is the natural next validation step before final submission.

---

## 📊 One Consolidated Report

The user should not have to understand our internal skill architecture.

The individual skills perform specialized analysis, while the **Audit Orchestrator** presents the result as one consolidated report.

Our minimum output follows the challenge schema:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3
  },
  "findings": [
    {
      "id": "F-001",
      "title": "Example finding",
      "severity": "high",
      "evidence": "Evidence supporting the finding.",
      "suggested_action": {
        "summary": "What should be changed and how.",
        "priority": "high"
      }
    }
  ]
}
```

We can extend this structure where useful, while preserving the required fields.

---

## 🛠️ Why We Chose This Decomposition

We did not split the marketplace into multiple skills simply to increase the number of files.

Each skill owns a distinct reasoning problem:

```text
Crawl & Render
      ↓
Can the system reach and read the page?

Structured Data
      ↓
Are important entities/facts machine-readable?

Content Extractability
      ↓
Can important facts be clearly extracted?

Freshness & Corroboration
      ↓
Are those facts current, consistent and supported?

Engagement
      ↓
Can a visitor understand and act?

             ↓

      Audit Orchestrator
             ↓
   One actionable report
```

This gives us two advantages:

**Modularity** — individual checks can evolve without rewriting the entire audit. When we found the dedupe-merge bug described above, we fixed it in one file (`report_builder.py`) without touching any specialist skill.

**Composability** — the orchestrator can combine independent evidence into a single prioritized result, including catching genuine overlaps (like the shared `js-only-content` root cause two different specialists can each independently notice) without either skill needing to know about the other's existence.

---

## 🧪 Generalization Over Examples

We are deliberately not building rules around a handful of known websites.

The challenge states that the marketplace will be evaluated on **unseen websites**.

Therefore, our checks are based on patterns that can generalize across sites:

* accessibility of important resources,
* differences between raw and rendered content,
* machine-readable metadata,
* extractability of factual content,
* consistency and freshness,
* and visitor experience.

Concretely, every severity judgment that could vary by site type is computed from the page's *own* observable content, never a hardcoded assumption about what kind of site it is:

* a missing commerce CTA is only weighted heavily when the page's own text already signals commerce intent,
* a stale date is only escalated when the page's own text uses currency language,
* an unrecognized structured-data type is a proactive suggestion, not an asserted defect, since no fixed list can enumerate every valid Schema.org type.

Our objective is to detect **root causes**, not memorize website-specific characteristics.

---

## 🛡️ Safety & Scope

Our marketplace is intentionally **recommend-only**. It operates in a read-only manner and does not modify a live website.

### We do:

* inspect publicly accessible website information,
* analyze pages and metadata,
* collect evidence,
* identify potential problems,
* recommend prioritized fixes.

### We do not:

* modify websites,
* publish content,
* submit changes,
* access authenticated areas,
* perform destructive actions,
* bypass access controls,
* or intentionally abuse website resources.

Concretely: every specialist skill issues GET/HEAD requests only, respects `robots.txt` for any URL discovered beyond an explicitly provided page list, caps internal-link sampling (engagement-audit samples at most 8 links per audit) rather than crawling exhaustively, and never dereferences URLs found inside structured data over the network.

---

## 📁 Repository Structure

```text
brand-ai-readiness-audit/
│
├── marketplace.json
├── README.md
│
└── skills/
    │
    ├── audit-orchestrator/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── report_builder.py
    │
    ├── crawl-render-audit/
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── render_diff.py
    │   └── references/
    │       └── checklist.md
    │
    ├── structured-data-audit/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── schema_check.py
    │
    ├── content-extractability-audit/
    │   ├── SKILL.md
    │   └── references/
    │       └── heuristics.md
    │
    ├── freshness-corroboration-audit/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── corroborate.py
    │
    └── engagement-audit/
        ├── SKILL.md
        └── scripts/
            └── perf_check.py
```

Every file in this tree is real and populated — no empty placeholders remain.

---

## 🚀 Setup & How to Run

**Requirements:** Python 3.11+

**1. Install dependencies:**

```bash
python -m pip install requests beautifulsoup4 playwright
python -m playwright install chromium
```

`requests` + `beautifulsoup4` power every specialist's HTTP fetch and HTML parsing; `playwright` (Chromium) is used specifically by `crawl-render-audit` to compare raw HTML against a real rendered DOM. No pretrained model weights are used anywhere in the marketplace.

**2. Invoke the audit:**

Point any Agent-Skills-compatible runtime at the marketplace root and invoke the entrypoint declared in `marketplace.json`:

```text
Entrypoint: audit-orchestrator
Input:      a target URL (e.g. https://example.com)
Output:     one JSON audit report (see schema above)
```

The orchestrator handles calling all five specialist skills internally, merging and deduplicating their findings — no manual wiring required.

**3. Run an individual specialist directly (for testing/debugging):**

```bash
python skills/engagement-audit/scripts/perf_check.py https://example.com --out findings.json
python skills/structured-data-audit/scripts/schema_check.py https://example.com --out findings.json
python skills/freshness-corroboration-audit/scripts/corroborate.py https://example.com --now-iso 2026-08-31 --out findings.json
```

Each script accepts an optional `--pages <url> <url> ...` to sample specific pages instead of just the base URL — useful for `freshness-corroboration-audit`'s cross-page corroboration check, which only activates with 2+ pages.

The individual skills keep their detailed procedures and heuristics close to the concern they address, while executable checks are kept inside `scripts/` and supporting knowledge inside `references/`.

---

## ⏱️ Runtime & Submission Constraints

We designed the implementation with the challenge constraints in mind:

* **Runtime target:** under 5 minutes for a typical website
* **Submission:** one marketplace ZIP
* **Maximum ZIP size:** 50 MB
* **No pretrained model weights**
* **Read-only / recommend-only execution**

These are explicit Round 3 constraints. Our dependency footprint (`requests`, `beautifulsoup4`, `playwright`) is intentionally minimal to stay well under the size limit, and every check is a deterministic Python function rather than a model call, keeping runtime predictable per-page.

---

## 🏆 Rubric Alignment

We built directly against the published Round 3 rubric so a reviewer can check each criterion in one pass:

| Rubric Createrion | Where We Address It |
|---|---|
| **Detection accuracy** | Each of the 5 specialist skills targets one named, evidence-backed mechanism from the Round-2 appendix (crawl access, rendering, structured data, extractability, corroboration, engagement) — and every check was validated against synthetic test fixtures, not just described in prose. See [Testing & Validation](#-testing--validation) |
| **Suggested-action quality** | Every finding pairs `evidence` with a `suggested_action` that names the specific fix and its `priority`; `audit-orchestrator` also surfaces proactive, non-defect-based recommendations |
| **Output design** | Single fixed-schema JSON report (`site`, `audited_at`, `summary`, `findings[]`) — see [One Consolidated Report](#-one-consolidated-report) |
| **Skill-format & engineering hygiene** | All 6 skills are `agentskills.io`-compliant `SKILL.md` files with valid frontmatter; `marketplace.json` declares exactly one entrypoint; execution is deterministic and read-only; a real cross-skill dedupe bug was found and fixed during development (see [Testing & Validation](#-testing--validation)), not just theorized about |
| **Marketplace composition** | 5 specialists, each owning a distinct reasoning problem (see [Why We Chose This Decomposition](#️-why-we-chose-this-decomposition)), composed cleanly by a single orchestrator — not padding |
| **Generalization** | No hardcoded domains, selectors, or site-specific rules anywhere in the marketplace; every severity judgment that could vary by site type is computed from the page's own observable content — see [Generalization Over Examples](#-generalization-over-examples) |

---

## 🏆 What We Delivered

We wanted the final audit to answer a practical question:

> **"What is preventing this brand from being clearly discovered, understood, trusted, and engaged with—and what should we do next?"**

Our marketplace connects:

```text
Technical Signals
       ↓
Evidence
       ↓
Root Cause
       ↓
Severity
       ↓
Prioritized Recommendation
```

Rather than producing another generic website checklist, we built a **composable reasoning system** that turns observable website signals into actionable recommendations — six working, tested skills, one orchestrator, one consistent evidence-first report format.

---

## ❤️ Final Note

We designed this marketplace with one principle in mind:

> **Make the invisible problems visible—and make the fixes actionable.**

The result is a modular, evidence-first audit system where specialized skills work independently, each backed by real test fixtures rather than untested assumptions, while one orchestrator turns their findings into a clear report that a real brand team can act on.