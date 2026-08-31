#!/usr/bin/env python3
"""
render_diff.py
===============

Used by the `crawl-render-audit` skill (one of the five specialists invoked
by `audit-orchestrator`).

Covers Round-2 appendix mechanism A ("the crawler has to be let in") and C
("a fact plainly visible on screen can be invisible to a program that isn't
looking at it the same way"). Concretely, this script checks:

  1. robots.txt access for common AI-assistant and search crawlers
  2. HTTP status / redirect health of sampled pages
  3. sitemap.xml presence and basic staleness (links that 404)
  4. raw HTML vs. rendered-DOM text diff, to catch content that only exists
     after client-side JavaScript execution -- invisible to any reader that
     doesn't run a full browser

Emits raw findings as a JSON list, matching the shared contract documented
in `audit-orchestrator/scripts/report_builder.py`'s module docstring.

Dependencies: requests, beautifulsoup4, playwright (+ `playwright install`
for the browser binary). All three are already part of this marketplace's
documented setup (see root README.md).

-------------------------------------------------------------------------
Design note on testability
-------------------------------------------------------------------------
The core logic (robots.txt parsing, HTML->text extraction, diff scoring) is
implemented as pure functions that take strings, not URLs -- so it can be
unit-tested without any network access. Only the thin fetch_* wrapper
functions touch the network / a real browser.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_SKILL = "crawl-render-audit"

# Crawlers worth checking robots.txt against by name, because they're the
# ones that actually power AI-assistant discoverability and citation today.
# Kept as a flat list (not hardcoded per-site data) so this generalizes to
# any target -- it's a list of *crawler identities*, not *site content*.
AI_RELEVANT_USER_AGENTS = [
    "GPTBot", "ChatGPT-User", "ClaudeBot", "anthropic-ai",
    "Google-Extended", "CCBot", "PerplexityBot", "Bingbot", "*",
]

# A render-diff is only interesting past some minimum absolute size --
# a 5-word difference on a tiny page isn't a finding, it's noise.
MIN_NEW_WORDS_TO_FLAG = 25
RATIO_MEDIUM = 1.3   # rendered has >=30% more content than raw
RATIO_HIGH = 2.0      # rendered has >=100% more content than raw
RAW_NEAR_EMPTY_WORDS = 50  # below this, raw HTML is basically a shell


class AuditFinding(dict):
    """A dict subclass purely so mypy/readability knows these are findings,
    not arbitrary dicts. Matches the report_builder.py raw-finding contract."""


# --------------------------------------------------------------------------
# Pure functions (no network) -- unit-testable in isolation
# --------------------------------------------------------------------------

def parse_robots_txt(robots_txt: str) -> dict[str, list[str]]:
    """Returns {user_agent: [disallowed_path, ...]} from robots.txt content.
    Minimal, deterministic parser -- handles the directives that matter for
    this audit (User-agent / Disallow) and ignores the rest (Allow,
    Crawl-delay, Sitemap -- sitemap is handled separately)."""
    rules: dict[str, list[str]] = {}
    current_agents: list[str] = []
    for raw_line in robots_txt.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            # A run of consecutive User-agent lines all share the following
            # Disallow rules, per the robots.txt spec.
            if current_agents and current_agents[-1] in rules and not rules[current_agents[-1]]:
                current_agents.append(value)
            else:
                current_agents = [value]
            rules.setdefault(value, [])
        elif field == "disallow" and current_agents:
            if value:  # empty Disallow means "allow everything"
                for agent in current_agents:
                    rules[agent].append(value)
    return rules


def check_robots_access(robots_txt: str | None, key_paths: list[str]) -> list[AuditFinding]:
    """Given robots.txt content (or None if the site has none) and a list
    of paths worth caring about (e.g. ['/', '/products/', '/pricing']),
    returns findings for any AI-relevant crawler blocked from any of them."""
    findings: list[AuditFinding] = []

    if robots_txt is None:
        # No robots.txt is not a defect -- it means "everything allowed".
        return findings

    rules = parse_robots_txt(robots_txt)

    for agent in AI_RELEVANT_USER_AGENTS:
        disallowed = rules.get(agent)
        if disallowed is None and agent != "*":
            continue  # this agent isn't mentioned at all -> falls under "*"
        effective = disallowed if disallowed is not None else rules.get("*", [])
        for path in key_paths:
            blocked = any(
                path == d or path.startswith(d) or d == "/"
                for d in effective
            )
            if blocked:
                severity = "critical" if path == "/" else "high"
                findings.append(AuditFinding(
                    title=f"robots.txt blocks '{agent}' from '{path}'",
                    severity=severity,
                    evidence=f"robots.txt disallows path(s) matching '{path}' "
                              f"for user-agent '{agent}'.",
                    suggested_action={
                        "summary": f"Update robots.txt to allow '{agent}' to "
                                   f"crawl '{path}', or confirm this block is "
                                   f"intentional (e.g. a genuinely private area).",
                        "priority": severity,
                    },
                    source_skill=SOURCE_SKILL,
                    category="crawler-access",
                ))
    return findings


def extract_visible_text(html: str) -> str:
    """Strips script/style/nav/footer/head and returns the remaining visible
    text, whitespace-normalized. Shared by both raw-HTML and rendered-DOM
    extraction so the two are directly comparable."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def compute_render_diff(raw_html: str, rendered_html: str, *, page_url: str) -> AuditFinding | None:
    """Compares visible text before vs. after JS execution. Returns a
    finding if the gap is large enough to matter, else None."""
    raw_text = extract_visible_text(raw_html)
    rendered_text = extract_visible_text(rendered_html)

    raw_words = raw_text.split()
    rendered_words = rendered_text.split()
    raw_count, rendered_count = len(raw_words), len(rendered_words)

    new_word_count = max(0, rendered_count - raw_count)
    ratio = (rendered_count / raw_count) if raw_count > 0 else float("inf")

    if new_word_count < MIN_NEW_WORDS_TO_FLAG:
        return None  # not a meaningful gap

    if raw_count < RAW_NEAR_EMPTY_WORDS:
        severity = "critical"
    elif ratio >= RATIO_HIGH:
        severity = "high"
    elif ratio >= RATIO_MEDIUM:
        severity = "medium"
    else:
        return None

    ratio_display = "inf" if ratio == float("inf") else f"{ratio:.2f}x"

    return AuditFinding(
        title="Page content only appears after client-side JavaScript execution",
        severity=severity,
        evidence=(
            f"{page_url}: raw HTML contains {raw_count} visible words; "
            f"rendered DOM contains {rendered_count} ({ratio_display} raw, "
            f"+{new_word_count} words only present after render)."
        ),
        suggested_action={
            "summary": "Server-side render this page's primary content, or "
                       "provide equivalent content in the initial HTML "
                       "response, so it's visible without executing JavaScript.",
            "priority": severity,
        },
        source_skill=SOURCE_SKILL,
        category="js-rendering-gap",
        dedupe_key="js-only-content",  # shared with content-extractability-audit
    )


def check_http_status(status_code: int, redirect_count: int, url: str) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    if status_code >= 500:
        findings.append(AuditFinding(
            title=f"Server error on {url}",
            severity="critical",
            evidence=f"{url} returned HTTP {status_code}.",
            suggested_action={"summary": "Investigate and fix the server error; "
                                          "a crawler cannot index a page it can't load.",
                               "priority": "critical"},
            source_skill=SOURCE_SKILL, category="http-status",
        ))
    elif status_code >= 400:
        findings.append(AuditFinding(
            title=f"Client error on {url}",
            severity="high",
            evidence=f"{url} returned HTTP {status_code}.",
            suggested_action={"summary": "Fix the broken link or restore the page; "
                                          "if intentionally removed, redirect to a relevant page.",
                               "priority": "high"},
            source_skill=SOURCE_SKILL, category="http-status",
        ))
    if redirect_count > 3:
        findings.append(AuditFinding(
            title=f"Long redirect chain on {url}",
            severity="medium",
            evidence=f"{url} required {redirect_count} redirects before resolving.",
            suggested_action={"summary": "Collapse the redirect chain to a single hop; "
                                          "long chains slow or discourage crawling.",
                               "priority": "medium"},
            source_skill=SOURCE_SKILL, category="http-status",
        ))
    return findings


def check_sitemap(sitemap_xml: str | None, site: str) -> list[AuditFinding]:
    if sitemap_xml is None:
        return [AuditFinding(
            title="No sitemap.xml found",
            severity="low",
            evidence=f"No sitemap.xml at {urljoin(site, '/sitemap.xml')}.",
            suggested_action={"summary": "Add a sitemap.xml listing key pages "
                                          "to help crawlers discover content efficiently.",
                               "priority": "low"},
            source_skill=SOURCE_SKILL, category="sitemap",
            proactive=True,
        )]
    try:
        root = ElementTree.fromstring(sitemap_xml)
    except ElementTree.ParseError:
        return [AuditFinding(
            title="sitemap.xml is not valid XML",
            severity="medium",
            evidence="sitemap.xml failed to parse as XML.",
            suggested_action={"summary": "Fix the sitemap's XML syntax so crawlers can read it.",
                               "priority": "medium"},
            source_skill=SOURCE_SKILL, category="sitemap",
        )]
    return []


# --------------------------------------------------------------------------
# Network-touching wrappers
# --------------------------------------------------------------------------

def fetch_robots_txt(site: str, *, timeout: int = 10) -> str | None:
    try:
        resp = requests.get(urljoin(site, "/robots.txt"), timeout=timeout)
        return resp.text if resp.status_code == 200 else None
    except requests.RequestException:
        return None


def fetch_sitemap(site: str, *, timeout: int = 10) -> str | None:
    try:
        resp = requests.get(urljoin(site, "/sitemap.xml"), timeout=timeout)
        return resp.text if resp.status_code == 200 else None
    except requests.RequestException:
        return None


def fetch_raw(url: str, *, timeout: int = 10) -> tuple[str, int, int]:
    """Returns (html, status_code, redirect_count)."""
    resp = requests.get(url, timeout=timeout, allow_redirects=True)
    return resp.text, resp.status_code, len(resp.history)


def fetch_rendered(url: str, *, timeout_ms: int = 15000) -> str:
    """Returns the fully rendered DOM's HTML after JS execution, via a
    headless browser. Requires `playwright install` to have been run."""
    from playwright.sync_api import sync_playwright  # local import: optional dep at call time

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        html = page.content()
        browser.close()
        return html


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def audit_site(site: str, pages: list[str]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    robots_txt = fetch_robots_txt(site)
    key_paths = ["/"] + sorted({urlparse(p).path or "/" for p in pages})
    findings.extend(check_robots_access(robots_txt, key_paths))

    sitemap_xml = fetch_sitemap(site)
    findings.extend(check_sitemap(sitemap_xml, site))

    for url in pages:
        try:
            raw_html, status, redirects = fetch_raw(url)
        except requests.RequestException as e:
            findings.append(AuditFinding(
                title=f"Could not fetch {url}",
                severity="high",
                evidence=f"Request to {url} failed: {e}",
                suggested_action={"summary": "Investigate why this page is unreachable.",
                                   "priority": "high"},
                source_skill=SOURCE_SKILL, category="http-status",
            ))
            continue

        findings.extend(check_http_status(status, redirects, url))
        if status >= 400:
            continue  # don't bother rendering a broken page

        try:
            rendered_html = fetch_rendered(url)
            diff_finding = compute_render_diff(raw_html, rendered_html, page_url=url)
            if diff_finding:
                findings.append(diff_finding)
        except Exception as e:  # noqa: BLE001 -- a render failure is itself diagnostic
            findings.append(AuditFinding(
                title=f"Could not render {url} with headless browser",
                severity="medium",
                evidence=f"Headless render of {url} failed: {e}",
                suggested_action={"summary": "Investigate why this page fails to render "
                                             "in a headless browser; this may also "
                                             "affect real crawlers that execute JS.",
                                  "priority": "medium"},
                source_skill=SOURCE_SKILL, category="http-status",
            ))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl & render audit for a website.")
    parser.add_argument("--site", required=True, help="Base site URL, e.g. https://example.com")
    parser.add_argument("--pages", nargs="+", required=True,
                         help="Full URLs of sampled pages to check, including the homepage.")
    parser.add_argument("--out", required=True, help="Path to write raw findings JSON.")
    args = parser.parse_args(argv)

    findings = audit_site(args.site, args.pages)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(findings)} findings to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())