# Crawl & Render Audit — Checklist Reference

Supporting detail for `crawl-render-audit/SKILL.md`. Documents *why* the
thresholds in `scripts/render_diff.py` are set where they are, and how to
handle edge cases the script surfaces as ambiguous.

---

## §1. robots.txt — crawler identities checked

The script checks these user-agent identities specifically, because they're
the crawlers that actually feed today's AI assistants and search-adjacent
citation systems (not an exhaustive list of every bot that has ever existed
— a deliberately short, high-relevance list, matching Round-2's framing of
"how assistants like ChatGPT use sources"):

| Agent | Why it matters |
|---|---|
| `GPTBot`, `ChatGPT-User` | OpenAI's crawlers — training and live browsing |
| `ClaudeBot`, `anthropic-ai` | Anthropic's crawlers |
| `Google-Extended` | Governs use in Google's AI features, separate from classic search indexing |
| `CCBot` | Common Crawl — feeds many downstream models' training data |
| `PerplexityBot` | Perplexity's live-answer crawler |
| `Bingbot` | Powers Bing/Copilot |
| `*` | The fallback that applies to any crawler not explicitly named |

A site can allow `Googlebot` (classic search) while blocking
`Google-Extended` (AI features) — these are different identities on
purpose, and the script checks each independently rather than assuming
"allowed for search" implies "allowed for AI."

**No robots.txt found at all** is treated as "everything is allowed" (the
correct default per the robots.txt spec), not a finding.

## §2. Render-diff thresholds — rationale

The script flags a page only when the gap between raw and rendered visible
text crosses one of these lines:

- **Absolute floor**: fewer than 25 new words appearing only after
  rendering is treated as noise (dynamic timestamps, a cookie banner,
  minor UI chrome) — not flagged, regardless of ratio.
- **`critical`**: raw HTML has fewer than 50 visible words *and* the
  absolute-floor gap is crossed. This is the "empty shell" pattern — the
  page is essentially a blank `<div id="app">` for anything that doesn't
  execute JavaScript, which describes most simple crawlers and many
  citation-focused readers.
- **`high`**: rendered content is at least 2x the raw content (and floor
  crossed). Substantial content exists but only after render — a simple
  reader gets a significantly incomplete picture.
- **`medium`**: rendered content is 1.3x–2x raw content. A real but more
  modest gap — some content is JS-only, but a meaningful base of readable
  content exists without it.
- **Below 1.3x**: not flagged. Ordinary UI interactivity (a modal, a form
  validation message) commonly injects some text without indicating a
  discoverability problem.

These thresholds are about the **shape of the gap** (a page that's
structurally empty without JS vs. one with minor JS-added chrome) — they
don't reference any specific site's content, so they generalize.

**False-positive guard**: the diff only fires on pages that returned a
successful HTTP status. A broken page (4xx/5xx) is reported as its own
finding and skipped for render-diffing — comparing "nothing" to "an error
page" isn't a meaningful JS-rendering signal.

## §3. Handling fetch/render failures

If a page can't be fetched (network error, timeout) or can't be rendered
(headless browser crash, JS error that prevents `networkidle`), the script
writes a `medium`- or `high`-severity finding describing the failure itself
rather than skipping the page silently. A page that can't even be rendered
by a well-behaved headless browser is diagnostic in its own right — real
crawlers likely have the same problem.

## §4. Sitemap checks — why "missing" is `low`/proactive, not a hard defect

Search engines and AI crawlers can discover pages via links even without a
sitemap; a sitemap is a *convenience* that improves discovery efficiency,
not a strict requirement for crawlability. Treating "no sitemap" as a
low-severity proactive suggestion (rather than a defect on par with a
robots.txt block) keeps severity honest — conflating "missing nice-to-have"
with "actively broken" would understate genuinely critical findings
elsewhere in the same report.

An **unparseable** sitemap (present but invalid XML) is different: it
signals something is actively broken (a build process generating malformed
output, for instance) and is scored `medium`.

## §5. What this skill deliberately does NOT check

To keep this skill's scope clean and avoid overlap with the other four
specialists:

- **Whether the content itself is well-written or complete** —
  `content-extractability-audit`'s job.
- **Whether structured data (JSON-LD, schema.org) is present or valid** —
  `structured-data-audit`'s job.
- **Whether facts are current or corroborated elsewhere on the web** —
  `freshness-corroboration-audit`'s job.
- **Page performance or visitor navigation/engagement** —
  `engagement-audit`'s job (note: page *load* performance for a human
  visitor is engagement's concern; this skill's HTTP/render checks are
  about crawler *access*, a related but distinct question).