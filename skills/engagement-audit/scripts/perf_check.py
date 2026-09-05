#!/usr/bin/env python3
"""perf_check.py — Analyse on-site engagement signals for a web page.

Usage:
    python perf_check.py <url>

Outputs JSON to stdout with keys:
    url, performance, navigation, content_hierarchy, cta, findings
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_html(url: str, *, timeout: int = 30) -> str:
    import requests

    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "BrandAuditBot/1.0 (+https://github.com/brand-audit)"},
    )
    resp.raise_for_status()
    return resp.text


def _fetch_with_timing(url: str, *, timeout: int = 30) -> tuple[str, float, int]:
    """Fetch and return (html, elapsed_seconds, content_length)."""
    import requests

    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "BrandAuditBot/1.0 (+https://github.com/brand-audit)"},
    )
    resp.raise_for_status()
    return resp.text, resp.elapsed.total_seconds(), len(resp.content)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_performance(html: str, elapsed: float, content_bytes: int) -> tuple[dict, list[dict]]:
    """Check basic performance signals."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    findings: list[dict] = []
    perf: dict = {}

    # Page size
    perf["html_size_bytes"] = content_bytes
    perf["response_time_seconds"] = round(elapsed, 3)

    if content_bytes > 500_000:
        findings.append({
            "title": "Large HTML document",
            "severity": "medium",
            "category": "engagement",
            "evidence": f"HTML response is {content_bytes:,} bytes ({content_bytes/1024:.0f} KB). Large pages load slowly on mobile.",
            "suggested_action": {
                "summary": "Reduce HTML size by deferring non-critical content, removing inline styles/scripts, or paginating.",
                "priority": "medium",
            },
        })

    if elapsed > 3.0:
        findings.append({
            "title": "Slow server response time",
            "severity": "high",
            "category": "engagement",
            "evidence": f"Server responded in {elapsed:.2f}s (target: < 1s for good UX).",
            "suggested_action": {
                "summary": "Improve server response time through caching, CDN, or backend optimization.",
                "priority": "high",
            },
        })
    elif elapsed > 1.0:
        findings.append({
            "title": "Moderate server response time",
            "severity": "medium",
            "category": "engagement",
            "evidence": f"Server responded in {elapsed:.2f}s (ideal: < 0.5s).",
            "suggested_action": {
                "summary": "Consider server-side caching or a CDN to reduce response time.",
                "priority": "medium",
            },
        })

    # Count external resources
    scripts = soup.find_all("script", src=True)
    stylesheets = [l for l in soup.find_all("link", rel="stylesheet")]
    images = soup.find_all("img")
    perf["external_scripts"] = len(scripts)
    perf["stylesheets"] = len(stylesheets)
    perf["images"] = len(images)

    total_resources = len(scripts) + len(stylesheets) + len(images)
    if total_resources > 80:
        findings.append({
            "title": "High number of page resources",
            "severity": "medium",
            "category": "engagement",
            "evidence": f"Page references {total_resources} resources ({len(scripts)} scripts, {len(stylesheets)} CSS, {len(images)} images).",
            "suggested_action": {
                "summary": "Reduce resource count by combining files, lazy-loading images, and deferring non-critical scripts.",
                "priority": "medium",
            },
        })

    # Viewport meta tag (mobile friendliness)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    perf["has_viewport_meta"] = viewport is not None
    if not viewport:
        findings.append({
            "title": "Missing viewport meta tag",
            "severity": "high",
            "category": "engagement",
            "evidence": "No <meta name=\"viewport\"> tag found. The page may not render correctly on mobile devices.",
            "suggested_action": {
                "summary": "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to the <head>.",
                "priority": "high",
            },
        })

    return perf, findings


def _check_navigation(html: str) -> tuple[dict, list[dict]]:
    """Check navigation structure."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    findings: list[dict] = []
    nav_info: dict = {}

    # <nav> elements
    navs = soup.find_all("nav")
    nav_info["nav_elements"] = len(navs)

    if not navs:
        findings.append({
            "title": "No <nav> landmark element",
            "severity": "medium",
            "category": "engagement",
            "evidence": "The page contains no <nav> element. Navigation may be present but not semantically marked.",
            "suggested_action": {
                "summary": "Wrap site navigation in a <nav> element for accessibility and semantic clarity.",
                "priority": "medium",
            },
        })

    # Internal links
    all_links = soup.find_all("a", href=True)
    nav_info["total_links"] = len(all_links)

    if len(all_links) == 0:
        findings.append({
            "title": "Page has no links",
            "severity": "high",
            "category": "engagement",
            "evidence": "No <a> tags with href found. Visitors have no navigation path from this page.",
            "suggested_action": {
                "summary": "Add navigation links to help visitors explore related content.",
                "priority": "high",
            },
        })

    # Header and footer landmarks
    has_header = soup.find("header") is not None
    has_footer = soup.find("footer") is not None
    has_main = soup.find("main") is not None
    nav_info["has_header"] = has_header
    nav_info["has_footer"] = has_footer
    nav_info["has_main"] = has_main

    if not has_main:
        findings.append({
            "title": "No <main> landmark element",
            "severity": "medium",
            "category": "engagement",
            "evidence": "The page does not use a <main> element to identify primary content.",
            "suggested_action": {
                "summary": "Wrap the primary page content in a <main> element for accessibility and content identification.",
                "priority": "medium",
            },
        })

    # Skip navigation link
    skip_link = soup.find("a", href=re.compile(r"#(main|content|skip)", re.I))
    nav_info["has_skip_link"] = skip_link is not None

    return nav_info, findings


def _check_content_hierarchy(html: str) -> tuple[dict, list[dict]]:
    """Check heading and content hierarchy."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    findings: list[dict] = []
    hierarchy: dict = {}

    headings = []
    for level in range(1, 7):
        tags = soup.find_all(f"h{level}")
        for tag in tags:
            headings.append({"level": level, "text": tag.get_text(strip=True)[:80]})

    hierarchy["headings"] = headings
    h1_count = sum(1 for h in headings if h["level"] == 1)

    if h1_count == 0:
        findings.append({
            "title": "No H1 heading found",
            "severity": "medium",
            "category": "engagement",
            "evidence": "The page has no <h1> element. Visitors and AI systems may not immediately understand the page topic.",
            "suggested_action": {
                "summary": "Add a single descriptive <h1> heading that clearly states the page topic.",
                "priority": "medium",
            },
        })
    elif h1_count > 1:
        findings.append({
            "title": f"Multiple H1 headings ({h1_count})",
            "severity": "low",
            "category": "engagement",
            "evidence": f"The page has {h1_count} <h1> elements. Best practice is exactly one.",
            "suggested_action": {
                "summary": "Use a single <h1> for the page title; demote others to <h2> or lower.",
                "priority": "low",
            },
        })

    # Check heading hierarchy (skipped levels)
    levels_used = [h["level"] for h in headings]
    for i in range(1, len(levels_used)):
        if levels_used[i] > levels_used[i - 1] + 1:
            findings.append({
                "title": f"Skipped heading level (h{levels_used[i-1]} → h{levels_used[i]})",
                "severity": "low",
                "category": "engagement",
                "evidence": f"Heading hierarchy jumps from h{levels_used[i-1]} to h{levels_used[i]}, skipping h{levels_used[i-1]+1}.",
                "suggested_action": {
                    "summary": "Maintain a sequential heading hierarchy (h1 → h2 → h3) for clarity.",
                    "priority": "low",
                },
            })
            break  # one finding is enough

    return hierarchy, findings


def _check_cta(html: str) -> tuple[dict, list[dict]]:
    """Check for calls-to-action."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    findings: list[dict] = []
    cta_info: dict = {}

    # Buttons and inputs
    buttons = soup.find_all("button")
    submit_inputs = soup.find_all("input", type=re.compile(r"submit|button", re.I))
    cta_links = []

    # Links that look like CTAs (contain action words)
    cta_words = re.compile(
        r"\b(buy|sign\s*up|subscribe|get\s+started|contact|register|download|"
        r"try|learn\s+more|request|book|schedule|apply|join|start|order)\b",
        re.I,
    )
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if cta_words.search(text):
            cta_links.append(text[:60])

    forms = soup.find_all("form")
    cta_info["buttons"] = len(buttons)
    cta_info["submit_inputs"] = len(submit_inputs)
    cta_info["cta_links"] = cta_links[:10]
    cta_info["forms"] = len(forms)

    total_ctas = len(buttons) + len(submit_inputs) + len(cta_links)
    if total_ctas == 0:
        findings.append({
            "title": "No clear call-to-action found",
            "severity": "high",
            "category": "engagement",
            "evidence": "No buttons, submit inputs, or CTA-style links detected on the page.",
            "suggested_action": {
                "summary": "Add clear calls-to-action (e.g., 'Get Started', 'Contact Us') so visitors know what step to take next.",
                "priority": "high",
            },
        })

    return cta_info, findings


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------


def audit(url: str) -> dict:
    """Run engagement audit for *url*.  Returns result dict."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    try:
        html, elapsed, content_bytes = _fetch_with_timing(url)
    except Exception as exc:
        return {
            "url": url,
            "performance": {},
            "navigation": {},
            "content_hierarchy": {},
            "cta": {},
            "findings": [{
                "title": "Could not fetch page for engagement audit",
                "severity": "critical",
                "category": "engagement",
                "evidence": f"HTTP request to {url} failed: {exc}",
                "suggested_action": {
                    "summary": "Ensure the page is accessible.",
                    "priority": "high",
                },
            }],
        }

    findings: list[dict] = []

    perf, perf_findings = _check_performance(html, elapsed, content_bytes)
    findings.extend(perf_findings)

    nav, nav_findings = _check_navigation(html)
    findings.extend(nav_findings)

    hierarchy, hier_findings = _check_content_hierarchy(html)
    findings.extend(hier_findings)

    cta, cta_findings = _check_cta(html)
    findings.extend(cta_findings)

    return {
        "url": url,
        "performance": perf,
        "navigation": nav,
        "content_hierarchy": hierarchy,
        "cta": cta,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python perf_check.py <url>", file=sys.stderr)
        sys.exit(1)
    result = audit(sys.argv[1])
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()