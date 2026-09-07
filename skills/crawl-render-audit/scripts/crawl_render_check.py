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


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _get(url, timeout, use_browser_ua=False):
    headers = {"User-Agent": BROWSER_UA if use_browser_ua else UA}
    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def _get_page_with_playwright_fallback(url, timeout):
    """
    Automatic & Selective rendering strategy:
    1. Try Playwright first if available in the environment to render full JS / React / Next.js DOM and bypass bot blocks.
    2. If Playwright is not installed, fails, or Chromium binaries are missing in sandbox, fall back seamlessly to HTTP requests without crashing.

    Returns:
        (html_content, status_code, latency, is_playwright_rendered, error_msg)
    """
    t0 = time.time()

    # Attempt Playwright rendering first if installed
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=BROWSER_UA,
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                }
            )
            response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            rendered_content = page.content()
            pw_status = response.status if response else 200
            browser.close()
            pw_latency = time.time() - t0
            if len(rendered_content) > 300:
                return rendered_content, 200, pw_latency, True, None
    except Exception:
        # Playwright not installed, missing binaries, or sandbox restriction
        pass

    # Fallback to standard HTTP requests gracefully without crashing
    static_html = ""
    status = 0
    latency = 0
    req_error = None

    try:
        r = _get(url, timeout)
        if r.status_code >= 400 or len(r.content) < 300:
            r = _get(url, timeout, use_browser_ua=True)
        static_html = r.text
        status = r.status_code
        latency = time.time() - t0
        return static_html, status, latency, False, None
    except requests.RequestException as e:
        req_error = str(e)
        return "", 0, 0, False, req_error


def _finding(fid, title, severity, evidence, action_summary, priority):
    return {
        "id": fid,
        "category": "discoverability",
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": priority},
    }


def _proactive(fid, title, evidence, action_summary):
    """
    A suggestion offered even though no defect was found — proactive
    improvements the brief explicitly asks for. Always severity 'info' so
    these never get counted as problems in the summary.
    """
    return {
        "id": fid,
        "category": "discoverability",
        "title": title,
        "severity": "info",
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": "info"},
        "proactive": True,
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

    # 3. homepage fetch, headers, meta robots & JS render analysis
    html, status_code, latency, is_playwright, req_error = _get_page_with_playwright_fallback(url, timeout)

    if req_error or status_code == 0:
        findings.append(_finding(
            nid(), "Homepage unreachable", "critical", f"Request error fetching {url}: {req_error or 'Connection failed'}",
            "Ensure the site resolves over HTTPS and responds without connection errors — an "
            "unreachable site is invisible to every crawler and AI fetcher.", "critical"))
        return findings

    if status_code >= 400:
        findings.append(_finding(
            nid(), "Homepage returns an error status", "critical",
            f"GET {url} returned HTTP {status_code}.",
            "Fix the underlying server/deploy issue so the homepage returns 200 for crawlers.",
            "critical"))
        return findings

    if latency > 3:
        findings.append(_finding(
            nid(), "Slow server response time", "medium",
            f"Homepage took {latency:.1f}s to respond (>3s).",
            "Improve TTFB (caching, CDN, server-side rendering) — slow responses cause crawlers "
            "and on-the-fly AI fetchers to time out or deprioritize the page.", "medium"))

    # Fetch headers via requests for header checks
    try:
        r_headers = _get(url, timeout).headers
    except Exception:
        r_headers = {}

    x_robots = r_headers.get("X-Robots-Tag", "")
    if "noindex" in x_robots.lower():
        findings.append(_finding(
            nid(), "X-Robots-Tag header excludes page from indexing", "critical",
            f"Response header X-Robots-Tag: {x_robots}",
            "Remove 'noindex' from the X-Robots-Tag header for pages meant to be publicly discoverable.",
            "critical"))

    soup = BeautifulSoup(html, "lxml")

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
    soup2 = BeautifulSoup(html, "lxml")
    ns = soup2.find_all("noscript")
    if ns and any(len(re.sub(r"\s+", " ", n.get_text(" ")).split()) > 20 for n in ns):
        noscript_has_content = True

    env_note = " (rendered with Playwright browser)" if is_playwright else " (analyzed using static HTTP parsing in sandbox)"

    if word_count < 50 and (spa_shell or word_count < 15):
        findings.append(_finding(
            nid(), "Content likely rendered client-side only (JS render gap)", "critical",
            f"Page content{env_note} contains only ~{word_count} words of visible text"
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
            f"Only ~{word_count} words of visible text found in HTML response{env_note}.",
            "Verify key facts (what the brand does, product details, pricing) are present as "
            "plain server-rendered text, not just implied by images or loaded asynchronously.",
            "medium"))

    # --- proactive suggestion (independent of any defect above) ---
    try:
        r = _get(up.urljoin(origin, "/llms.txt"), timeout)
        if r.status_code != 200:
            findings.append(_proactive(
                nid("CR-P"), "No llms.txt found (emerging AI-crawler convention)",
                f"GET /llms.txt returned status {r.status_code}.",
                "Consider publishing an llms.txt at the site root — a short, plain-text index of "
                "the site's key pages and facts written specifically for AI agents. It's not yet "
                "a universal standard, but costs little to add and gives assistants a direct, "
                "curated entry point instead of relying on inference."))
    except requests.RequestException:
        pass

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: crawl_render_check.py <url>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(run_check(sys.argv[1]), indent=2))

