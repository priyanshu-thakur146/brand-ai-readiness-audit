#!/usr/bin/env python3
"""crawl-render-audit: crawlability + JS-render-gap checks.

Can be run standalone:
    python crawl_render_check.py https://example.com
or imported:
    from crawl_render_check import run_check
    findings = run_check("https://example.com")
"""
import sys
import json
import time
import re
import urllib.parse as up

import requests
from bs4 import BeautifulSoup

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
AI_AGENT_TOKENS = ["*", "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Googlebot"]
SPA_ROOT_IDS = ["root", "__next", "app", "___gatsby", "app-root"]


def _get(url, timeout):
    return requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)


def _finding(fid, title, severity, evidence, action_summary, priority):
    return {
        "id": fid,
        "category": "discoverability",
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": priority},
    }


def run_check(url, timeout=15):
    findings = []
    parsed = up.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    n = 0

    def nid(prefix="CR"):
        nonlocal n
        n += 1
        return f"{prefix}-{n:03d}"

    # 1. robots.txt
    blocked_agents = []
    sitemap_in_robots = False
    try:
        r = _get(up.urljoin(origin, "/robots.txt"), timeout)
        if r.status_code == 200 and r.text.strip():
            current_agents = []
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "user-agent":
                    current_agents = [val]
                elif key == "disallow" and val == "/":
                    for a in current_agents:
                        if a in AI_AGENT_TOKENS or a == "*":
                            blocked_agents.append(a)
                elif key == "sitemap":
                    sitemap_in_robots = True
            if blocked_agents:
                findings.append(_finding(
                    nid(), "robots.txt blocks crawlers from the entire site", "critical",
                    f"robots.txt disallows '/' for user-agent(s): {sorted(set(blocked_agents))}.",
                    "Remove the blanket Disallow rule (or scope it to genuinely private paths only) "
                    "so AI/search crawlers can index the site at all.", "critical"))
        else:
            findings.append(_finding(
                nid(), "No robots.txt found", "low",
                f"GET /robots.txt returned status {r.status_code}.",
                "Add a robots.txt that explicitly allows crawling and points to the sitemap; "
                "its absence isn't fatal but removes a cheap, explicit signal of intent.", "low"))
    except requests.RequestException as e:
        findings.append(_finding(
            nid(), "robots.txt could not be fetched", "medium", f"Request error: {e}",
            "Ensure /robots.txt is reachable over HTTPS without redirects or timeouts.", "medium"))

    # 2. sitemap.xml
    try:
        r = _get(up.urljoin(origin, "/sitemap.xml"), timeout)
        if r.status_code != 200 or "<urlset" not in r.text and "<sitemapindex" not in r.text:
            if not sitemap_in_robots:
                findings.append(_finding(
                    nid(), "No discoverable XML sitemap", "medium",
                    f"/sitemap.xml returned status {r.status_code} and robots.txt has no Sitemap: line.",
                    "Publish an XML sitemap (or sitemap index) covering canonical pages and reference "
                    "it in robots.txt so crawlers can find and prioritize content efficiently.", "medium"))
    except requests.RequestException:
        if not sitemap_in_robots:
            findings.append(_finding(
                nid(), "Sitemap unreachable and not declared in robots.txt", "medium",
                "GET /sitemap.xml failed and robots.txt has no Sitemap: directive.",
                "Publish a reachable XML sitemap and declare it in robots.txt.", "medium"))

    # 3. homepage fetch, headers, meta robots
    try:
        t0 = time.time()
        r = _get(url, timeout)
        latency = time.time() - t0
        if r.status_code >= 400:
            findings.append(_finding(
                nid(), "Homepage returns an error status", "critical",
                f"GET {url} returned HTTP {r.status_code}.",
                "Fix the underlying server/deploy issue so the homepage returns 200 for crawlers.",
                "critical"))
            return findings  # nothing else worth checking

        if latency > 3:
            findings.append(_finding(
                nid(), "Slow server response time", "medium",
                f"Homepage took {latency:.1f}s to respond (>3s).",
                "Improve TTFB (caching, CDN, server-side rendering) — slow responses cause crawlers "
                "and on-the-fly AI fetchers to time out or deprioritize the page.", "medium"))

        x_robots = r.headers.get("X-Robots-Tag", "")
        if "noindex" in x_robots.lower():
            findings.append(_finding(
                nid(), "X-Robots-Tag header excludes page from indexing", "critical",
                f"Response header X-Robots-Tag: {x_robots}",
                "Remove 'noindex' from the X-Robots-Tag header for pages meant to be publicly discoverable.",
                "critical"))

        soup = BeautifulSoup(r.text, "lxml")

        meta_robots = soup.find("meta", attrs={"name": re.compile("robots", re.I)})
        if meta_robots and "noindex" in (meta_robots.get("content") or "").lower():
            findings.append(_finding(
                nid(), "Meta robots tag excludes page from indexing", "critical",
                f'<meta name="robots" content="{meta_robots.get("content")}"> present on homepage.',
                "Remove the noindex directive from pages you want AI assistants and search engines to cite.",
                "critical"))

        canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
        if not canonical or not canonical.get("href"):
            findings.append(_finding(
                nid(), "No canonical link tag", "low",
                "No <link rel=\"canonical\"> found on the homepage.",
                "Add a self-referencing canonical tag on every indexable page to consolidate ranking "
                "signals and avoid duplicate-content ambiguity.", "low"))

        # 4. render-gap heuristic
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        visible_text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
        word_count = len(visible_text.split())

        body = soup.find("body")
        spa_shell = False
        if body:
            for rid in SPA_ROOT_IDS:
                el = body.find(id=rid)
                if el is not None:
                    spa_shell = True
                    break

        noscript_has_content = False
        soup2 = BeautifulSoup(r.text, "lxml")
        ns = soup2.find_all("noscript")
        if ns and any(len(re.sub(r"\s+", " ", n.get_text(" ")).split()) > 20 for n in ns):
            noscript_has_content = True

        if word_count < 50 and (spa_shell or word_count < 15):
            findings.append(_finding(
                nid(), "Content likely rendered client-side only (JS render gap)", "critical",
                f"Raw HTML (before JS execution) contains only ~{word_count} words of visible text"
                + (" and a client-app root element (SPA shell) was detected." if spa_shell else "."),
                "Server-side render (SSR) or statically pre-render the core content — product info, "
                "prices, articles — so it is present in the initial HTML response. Frameworks like "
                "Next.js/Nuxt/Remix, or a prerendering layer, fix this without abandoning the SPA "
                + ("(a <noscript> fallback with substantive text is present as a partial mitigation)"
                   if noscript_has_content else "(no <noscript> fallback with substantive text was found)")
                + ".", "critical"))
        elif word_count < 150:
            findings.append(_finding(
                nid(), "Thin visible text in raw HTML", "medium",
                f"Only ~{word_count} words of visible text found in the raw HTML response.",
                "Verify key facts (what the brand does, product details, pricing) are present as "
                "plain server-rendered text, not just implied by images or loaded asynchronously.",
                "medium"))

    except requests.RequestException as e:
        findings.append(_finding(
            nid(), "Homepage unreachable", "critical", f"Request error fetching {url}: {e}",
            "Ensure the site resolves over HTTPS and responds without connection errors — an "
            "unreachable site is invisible to every crawler and AI fetcher.", "critical"))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: crawl_render_check.py <url>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(run_check(sys.argv[1]), indent=2))
