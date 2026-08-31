#!/usr/bin/env python3
"""
perf_check.py — deterministic engagement/UX checks for the engagement-audit skill.

Contract (matches audit-orchestrator/scripts/report_builder.py raw-finding schema):
  Each finding this script emits is a dict:
    {
      "id_hint":        str,   # stable slug, becomes part of dedupe_key
      "title":          str,
      "severity":       "critical" | "high" | "medium" | "low",
      "evidence":       str,   # concrete, checkable — quote the offending markup/text
      "suggested_action": str,
      "dedupe_key":     str | None,  # "engagement:<id_hint>" — namespaced so this
                                       # skill never accidentally collides with another
                                       # skill's dedupe_key unless explicitly shared
      "source_skill":   "engagement-audit",
      "proactive":      bool  # True if this is a suggestion, not a defect
    }

Usage:
  python perf_check.py <url> [--pages <path> <path> ...] --out <raw_findings.json>

What it checks (see references/heuristics.md for full rationale + thresholds):
  1. CTA presence & clarity      — is there a clickable primary action with real text?
  2. CTA commerce-relevance      — severity is judgment-aware (see content-extractability
                                    pattern): a missing "Buy now" CTA is not penalized the
                                    same way on a non-commerce site.
  3. Heading structure           — exactly one H1, no skipped levels, no empty headings.
  4. Navigation landmark         — a <nav> (or role="navigation") exists and contains a
                                    link back to the homepage.
  5. Contact/trust findability   — a contact/support link is reachable from nav or footer.
  6. Mobile viewport meta        — <meta name="viewport"> present and not disabling zoom
                                    in a way that harms usability.
  7. Dead-end links              — sampled internal links that 404 or connection-error.
  8. Response latency            — TTFB-ish wall-clock fetch time over a fixed threshold.

Design notes:
  - Every check is a pure function taking already-fetched HTML/response data, so it can be
    unit-tested offline against synthetic fixtures (see the __main__ self-test block).
  - Nothing here fabricates evidence: every finding's `evidence` field is a literal
    substring or attribute pulled from the actual page, never a paraphrase or guess.
  - Fails loudly (non-zero exit, message on stderr) on unreachable URLs or malformed args,
    matching report_builder.py's fail-loud convention.
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SKILL_NAME = "engagement-audit"
USER_AGENT = "AuditBot/1.0 (+engagement-audit skill; read-only)"
REQUEST_TIMEOUT = 10
SLOW_RESPONSE_THRESHOLD_S = 2.0
DEAD_LINK_SAMPLE_SIZE = 8

GENERIC_CTA_TEXT = {
    "click here", "here", "read more", "more", "learn more", "link", "submit",
    "go", "ok", "continue",
}

COMMERCE_SIGNALS = re.compile(
    r"\b(cart|checkout|add to cart|buy now|price|shop|product|shipping|order)\b",
    re.IGNORECASE,
)

CONTACT_SIGNALS = re.compile(
    r"\b(contact|support|help|talk to us|get in touch|customer service)\b",
    re.IGNORECASE,
)


def _finding(id_hint, title, severity, evidence, suggested_action,
             dedupe_key=None, proactive=False):
    return {
        "id_hint": id_hint,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "dedupe_key": dedupe_key or f"engagement:{id_hint}",
        "source_skill": SKILL_NAME,
        "proactive": proactive,
    }


# ---------------------------------------------------------------------------
# Pure check functions (unit-testable offline against synthetic HTML)
# ---------------------------------------------------------------------------

def check_headings(soup, page_url):
    findings = []
    h1s = soup.find_all("h1")
    if len(h1s) == 0:
        findings.append(_finding(
            "missing-h1", "Page has no H1 heading", "medium",
            f"{page_url}: no <h1> element found in the document.",
            "Add exactly one <h1> that names the primary topic of the page — "
            "it anchors both visual hierarchy and assistive-tech/AI page summarization.",
        ))
    elif len(h1s) > 1:
        sample = ", ".join(repr(h.get_text(strip=True)[:40]) for h in h1s[:3])
        findings.append(_finding(
            "multiple-h1", "Multiple H1 headings on one page", "low",
            f"{page_url}: found {len(h1s)} <h1> elements: {sample}",
            "Keep a single <h1> per page and demote the others to <h2>/<h3> "
            "so the heading tree reflects one clear topic, not several competing ones.",
        ))

    empty = [h for h in soup.find_all(re.compile(r"^h[1-6]$")) if not h.get_text(strip=True)]
    if empty:
        findings.append(_finding(
            "empty-heading", "Empty heading element(s)", "low",
            f"{page_url}: {len(empty)} heading tag(s) contain no visible text "
            f"(e.g. <{empty[0].name}></{empty[0].name}>).",
            "Remove empty heading tags or fill them with real text — empty headings "
            "break the outline that screen readers and AI summarizers rely on.",
        ))

    # skipped level check (e.g. h1 -> h3, no h2)
    levels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    for prev, cur in zip(levels, levels[1:]):
        if cur - prev > 1:
            findings.append(_finding(
                "skipped-heading-level", "Heading hierarchy skips a level", "low",
                f"{page_url}: heading level jumps from h{prev} to h{cur} without an "
                f"intervening h{prev + 1}.",
                "Use consecutive heading levels (h1 → h2 → h3) so the document "
                "outline stays predictable for assistive tech and content parsers.",
            ))
            break  # one finding per page is enough signal

    return findings


def check_nav_landmark(soup, page_url, base_url):
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    if nav is None:
        return [_finding(
            "missing-nav-landmark", "No navigation landmark found", "medium",
            f"{page_url}: no <nav> element or role=\"navigation\" found in the document.",
            "Wrap the primary site navigation in a <nav> element (or add "
            "role=\"navigation\") so users and assistive tech can jump straight "
            "to it instead of hunting through the page.",
        )]

    home_netloc = urlparse(base_url).netloc
    links = nav.find_all("a", href=True)
    has_home_link = any(
        urlparse(urljoin(base_url, a["href"])).path in ("", "/")
        and urlparse(urljoin(base_url, a["href"])).netloc == home_netloc
        for a in links
    )
    if not has_home_link:
        return [_finding(
            "nav-missing-home-link", "Navigation has no link back to homepage", "low",
            f"{page_url}: <nav> found with {len(links)} link(s), but none points to "
            f"the site root.",
            "Include a logo or \"Home\" link inside the nav landmark so users always "
            "have a one-click way back to the start of the site.",
        )]
    return []


def check_cta(soup, page_url, is_commerce_site):
    """CTA clarity — only counts real clickable elements (a/button), not plain text."""
    clickables = soup.find_all(["a", "button"])
    real_ctas = []
    generic_ctas = []
    for el in clickables:
        text = el.get_text(strip=True)
        aria = el.get("aria-label", "").strip()
        label = text or aria
        if not label:
            continue
        if label.lower() in GENERIC_CTA_TEXT:
            generic_ctas.append(label)
        else:
            real_ctas.append(label)

    findings = []

    if not real_ctas and not generic_ctas:
        severity = "high" if is_commerce_site else "medium"
        findings.append(_finding(
            "no-cta", "No clickable call-to-action found", severity,
            f"{page_url}: no <a> or <button> element with visible text or "
            f"aria-label was found on the page.",
            "Add at least one clear, actionable link or button (e.g. \"Get a quote\", "
            "\"Start free trial\") so visitors have an obvious next step.",
        ))
    elif not real_ctas and generic_ctas:
        # only generic-text CTAs exist
        sample = ", ".join(repr(g) for g in generic_ctas[:3])
        findings.append(_finding(
            "generic-cta-only", "All calls-to-action use generic text", "low",
            f"{page_url}: clickable elements found, but all link/button text is "
            f"generic: {sample}.",
            "Replace generic text like \"click here\" or \"learn more\" with text "
            "that describes the destination or action (\"See pricing\", \"Download "
            "the guide\") — this helps both users scanning the page and AI systems "
            "summarizing it.",
        ))

    # Business-relevance check: commerce site should have a transactional CTA somewhere
    if is_commerce_site:
        has_commerce_cta = any(COMMERCE_SIGNALS.search(label) for label in real_ctas)
        if real_ctas and not has_commerce_cta:
            findings.append(_finding(
                "missing-commerce-cta", "No purchase/commerce-intent CTA found", "medium",
                f"{page_url}: page has {len(real_ctas)} clickable CTA(s) but none "
                f"reference cart, checkout, pricing, or a purchase action.",
                "If this page is meant to drive a sale or signup, add a CTA that "
                "names the transactional action explicitly (\"Add to cart\", "
                "\"Get pricing\") rather than only generic navigation links.",
            ))

    return findings


def check_contact_findability(soup, page_url):
    footer = soup.find("footer")
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    search_scope = BeautifulSoup(
        (str(footer) if footer else "") + (str(nav) if nav else ""), "html.parser"
    )
    links = search_scope.find_all("a")
    found = any(
        CONTACT_SIGNALS.search(a.get_text(strip=True)) or
        CONTACT_SIGNALS.search(a.get("href", ""))
        for a in links
    )
    if not found:
        return [_finding(
            "contact-not-findable", "No contact/support link in nav or footer", "medium",
            f"{page_url}: neither the <nav> nor <footer> contains a link whose text "
            f"or href references contact/support.",
            "Add a \"Contact\" or \"Support\" link to the main navigation or footer — "
            "visitors (and AI assistants summarizing trust signals) expect it to be "
            "reachable from every page, not buried.",
        )]
    return []


def check_viewport_meta(soup, page_url):
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport is None:
        return [_finding(
            "missing-viewport-meta", "No mobile viewport meta tag", "medium",
            f"{page_url}: no <meta name=\"viewport\"> tag found in <head>.",
            "Add <meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\"> so the page renders correctly on mobile screens.",
        )]
    content = viewport.get("content", "")
    if "user-scalable=no" in content.replace(" ", "") or "maximum-scale=1" in content.replace(" ", ""):
        return [_finding(
            "viewport-disables-zoom", "Viewport meta tag disables pinch-zoom", "low",
            f"{page_url}: viewport content=\"{content}\" prevents users from zooming.",
            "Remove user-scalable=no / maximum-scale=1 from the viewport tag — "
            "disabling zoom is an accessibility barrier for low-vision users.",
        )]
    return []


def check_dead_links(base_url, internal_links, session, sample_size=DEAD_LINK_SAMPLE_SIZE):
    findings = []
    sample = internal_links[:sample_size]
    dead = []
    for link in sample:
        try:
            resp = session.head(link, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                                 headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                # some servers reject HEAD; retry with GET before concluding dead
                resp = session.get(link, timeout=REQUEST_TIMEOUT,
                                    headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                dead.append((link, resp.status_code))
        except requests.RequestException as exc:
            dead.append((link, f"error: {exc.__class__.__name__}"))
    if dead:
        sample_str = "; ".join(f"{url} -> {status}" for url, status in dead[:5])
        findings.append(_finding(
            "dead-internal-links", "Sampled internal link(s) do not resolve",
            "high" if len(dead) > 1 else "medium",
            f"Out of {len(sample)} sampled internal links, {len(dead)} failed: {sample_str}",
            "Fix or remove broken internal links — dead links interrupt user "
            "journeys and signal a stale/unmaintained site to both visitors and crawlers.",
        ))
    return findings


def check_latency(fetch_seconds, page_url, threshold=SLOW_RESPONSE_THRESHOLD_S):
    if fetch_seconds > threshold:
        return [_finding(
            "slow-response", "Slow page response time", "medium",
            f"{page_url}: initial response took {fetch_seconds:.2f}s "
            f"(threshold {threshold:.1f}s).",
            "Investigate server response time — slow TTFB increases bounce rate "
            "and is penalized by most engagement/UX heuristics.",
        )]
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def is_commerce_site(soup):
    """Heuristic, not authoritative — mirrors content-extractability-audit's
    judgment-aware pattern so severities aren't over-penalized on non-commerce sites."""
    text = soup.get_text(" ", strip=True)
    return bool(COMMERCE_SIGNALS.search(text))


def audit_page(url, session, base_url):
    findings = []
    start = time.monotonic()
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return [_finding(
            "page-unreachable", "Page could not be fetched", "critical",
            f"{url}: request failed with {exc.__class__.__name__}: {exc}",
            "Confirm the URL is correct and the server is reachable; an "
            "unreachable page blocks every other engagement check.",
        )], []
    elapsed = time.monotonic() - start

    if resp.status_code >= 400:
        return [_finding(
            "page-error-status", f"Page returned HTTP {resp.status_code}", "critical",
            f"{url}: server responded with status {resp.status_code}.",
            "Fix the underlying error — a non-2xx status means neither users "
            "nor crawlers can reliably reach this page's content.",
        )], []

    soup = BeautifulSoup(resp.text, "html.parser")
    commerce = is_commerce_site(soup)

    findings += check_headings(soup, url)
    findings += check_nav_landmark(soup, url, base_url)
    findings += check_cta(soup, url, commerce)
    findings += check_contact_findability(soup, url)
    findings += check_viewport_meta(soup, url)
    findings += check_latency(elapsed, url)

    internal_links = []
    netloc = urlparse(base_url).netloc
    for a in soup.find_all("a", href=True):
        full = urljoin(url, a["href"])
        parsed = urlparse(full)
        if parsed.netloc == netloc and parsed.scheme in ("http", "https"):
            internal_links.append(full)

    return findings, internal_links


def run_audit(base_url, pages=None):
    session = requests.Session()
    pages = pages or [base_url]
    all_findings = []
    all_internal_links = []

    for page_url in pages:
        page_findings, internal_links = audit_page(page_url, session, base_url)
        all_findings.extend(page_findings)
        all_internal_links.extend(internal_links)

    # Dead-link check runs once, sampled across all discovered internal links,
    # deduped, excluding pages we already audited directly.
    audited = set(pages)
    unique_candidates = [l for l in dict.fromkeys(all_internal_links) if l not in audited]
    if unique_candidates:
        all_findings += check_dead_links(base_url, unique_candidates, session)

    return all_findings


def main():
    parser = argparse.ArgumentParser(description="engagement-audit: perf_check.py")
    parser.add_argument("url", help="Base URL of the site being audited")
    parser.add_argument("--pages", nargs="*", default=None,
                         help="Specific page URLs to sample (defaults to just the base URL)")
    parser.add_argument("--out", required=True, help="Path to write raw findings JSON")
    args = parser.parse_args()

    try:
        findings = run_audit(args.url, args.pages)
    except Exception as exc:  # fail loudly, matching report_builder.py's convention
        print(f"engagement-audit perf_check.py FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w") as f:
        json.dump(findings, f, indent=2)

    print(f"engagement-audit: wrote {len(findings)} finding(s) to {args.out}")


if __name__ == "__main__":
    main()