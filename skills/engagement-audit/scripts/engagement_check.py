#!/usr/bin/env python3
"""engagement-audit: mobile viewport, nav, CTAs, broken links, page weight."""
import sys
import json
import time
import re
import urllib.parse as up

import requests
from bs4 import BeautifulSoup

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
CTA_WORDS = re.compile(
    r"\b(sign up|log in|buy( now)?|contact( us)?|get started|book( now)?|subscribe|"
    r"download|add to cart|request a demo|learn more|start free trial|join)\b", re.I)


def _finding(fid, title, severity, evidence, action_summary, priority):
    return {
        "id": fid,
        "category": "engagement",
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": priority},
    }


def run_check(url, timeout=15, max_links_checked=8):
    findings = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"EN-{n:03d}"

    try:
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        latency = time.time() - t0
    except requests.RequestException as e:
        return [_finding(nid(), "Page unreachable for engagement check", "critical",
                          f"Request error: {e}", "Fix connectivity/availability before auditing.",
                          "critical")]

    page_bytes = len(r.content)
    soup = BeautifulSoup(r.text, "lxml")
    parsed = up.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # 1. viewport
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    if not viewport or "width=device-width" not in (viewport.get("content") or ""):
        findings.append(_finding(
            nid(), "Missing/incorrect mobile viewport meta tag", "high",
            f"viewport meta present={bool(viewport)}, content={(viewport.get('content') if viewport else None)!r}.",
            "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> — without "
            "it mobile visitors get a desktop-scaled layout and bounce quickly.", "high"))

    # 2. navigation
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    nav_links = nav.find_all("a", href=True) if nav else []
    if not nav or len(nav_links) < 2:
        findings.append(_finding(
            nid(), "No discoverable site navigation", "medium",
            f"<nav>/role=navigation found={bool(nav)} with {len(nav_links)} link(s) inside.",
            "Add a persistent navigation region with links to key sections (product, pricing, "
            "about, contact) so visitors — and agents browsing on a user's behalf — can orient "
            "and go deeper instead of leaving.", "medium"))

    # 3. CTAs
    clickable_text = " ".join(
        el.get_text(" ") for el in soup.find_all(["a", "button"])
    )
    if not CTA_WORDS.search(clickable_text):
        findings.append(_finding(
            nid(), "No clear call-to-action found", "medium",
            "No button/link text matched common CTA phrasing (sign up, contact, buy, get started, "
            "book, subscribe, download, etc.).",
            "Add at least one prominent, specific call-to-action above the fold stating the next "
            "step you want a visitor to take.", "medium"))

    # 4. broken internal links (sampled)
    internal_links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = up.urljoin(url, href)
        if up.urlparse(full).netloc == parsed.netloc and full not in seen:
            seen.add(full)
            internal_links.append(full)

    sample = internal_links[:max_links_checked]
    broken = []
    for link in sample:
        try:
            lr = requests.head(link, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
            if lr.status_code >= 400 or lr.status_code == 405:
                # some servers reject HEAD; retry with GET on 405
                if lr.status_code == 405:
                    lr = requests.get(link, headers={"User-Agent": UA}, timeout=timeout)
                if lr.status_code >= 400:
                    broken.append((link, lr.status_code))
        except requests.RequestException:
            broken.append((link, "request_error"))

    if broken:
        findings.append(_finding(
            nid(), "Broken internal link(s) found", "high" if len(broken) > 1 else "medium",
            f"{len(broken)}/{len(sample)} sampled internal links are broken: "
            f"{broken[:5]}{'...' if len(broken) > 5 else ''}.",
            "Fix or remove broken internal links — each one is a dead end that ends a visitor's "
            "(or a browsing agent's) session on the spot.",
            "high" if len(broken) > 1 else "medium"))
    elif not internal_links:
        findings.append(_finding(
            nid(), "No internal links found on homepage", "medium",
            "Zero same-domain links found on the homepage.",
            "Link to key internal pages from the homepage so visitors have somewhere to go next.",
            "medium"))

    # 5. page weight / latency
    if latency > 3:
        findings.append(_finding(
            nid(), "Slow homepage load time", "medium",
            f"Initial response took {latency:.1f}s (>3s threshold).",
            "Improve server response time and reduce render-blocking resources — slow loads are "
            "one of the most common causes of immediate bounce.", "medium"))
    if page_bytes > 3_000_000:
        findings.append(_finding(
            nid(), "Heavy initial HTML document", "low",
            f"Homepage HTML document is {page_bytes / 1_000_000:.1f} MB.",
            "Audit for inlined base64 assets, unminified bundles, or unnecessary embedded data in "
            "the initial HTML document; move large assets to lazy-loaded resources.", "low"))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: engagement_check.py <url>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(run_check(sys.argv[1]), indent=2))
