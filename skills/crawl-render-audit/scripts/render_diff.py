#!/usr/bin/env python3
"""render_diff.py — Compare raw HTML text with JavaScript-rendered text.

Usage:
    python render_diff.py <url>

Outputs JSON to stdout with keys:
    url, raw_text_length, rendered_text_length, diff_ratio, added_blocks, findings
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
from urllib.parse import urlparse, urljoin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Collapse whitespace and strip for consistent comparison."""
    return _WHITESPACE.sub(" ", text).strip()


def _visible_text_bs4(html: str) -> str:
    """Extract visible text from raw HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    # Remove script, style, and hidden elements
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return _normalise(soup.get_text(separator=" "))


def _fetch_raw(url: str, *, timeout: int = 30) -> tuple[int, str, list[str]]:
    """Fetch URL with requests.  Returns (status, html, redirect_chain)."""
    import requests

    redirects: list[str] = []
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "BrandAuditBot/1.0 (+https://github.com/brand-audit)"},
        allow_redirects=True,
    )
    for r in resp.history:
        redirects.append(r.url)
    return resp.status_code, resp.text, redirects


def _render_playwright(url: str, *, timeout: int = 30_000) -> str:
    """Render URL with Playwright and return visible inner text."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
            text = page.inner_text("body")
        finally:
            browser.close()
    return _normalise(text)


def _diff_blocks(raw_text: str, rendered_text: str, *, min_len: int = 40) -> list[str]:
    """Return blocks of text present in rendered but absent in raw.

    Simple approach: split rendered text into sentence-like chunks and check
    which ones do NOT appear (even as a substring) in the raw text.
    """
    raw_lower = raw_text.lower()
    blocks: list[str] = []
    for chunk in _SENTENCE_SPLIT.split(rendered_text):
        chunk = chunk.strip()
        if len(chunk) >= min_len and chunk.lower() not in raw_lower:
            blocks.append(chunk[:200])  # cap length for report readability
    return blocks


# ---------------------------------------------------------------------------
# Robots.txt & Sitemap helpers
# ---------------------------------------------------------------------------

_AI_BOTS = ["GPTBot", "ChatGPT-User", "anthropic-ai", "CCBot", "Google-Extended", "Googlebot"]


def _check_robots(origin: str) -> list[dict]:
    """Fetch and analyse robots.txt.  Returns findings list."""
    import requests

    findings: list[dict] = []
    robots_url = f"{origin}/robots.txt"
    try:
        resp = requests.get(robots_url, timeout=15,
                            headers={"User-Agent": "BrandAuditBot/1.0"})
    except Exception as exc:
        findings.append({
            "title": "robots.txt unreachable",
            "severity": "info",
            "category": "crawl-render",
            "evidence": f"Could not fetch {robots_url}: {exc}",
            "suggested_action": {
                "summary": "Ensure robots.txt is accessible at the site root.",
                "priority": "low",
            },
        })
        return findings

    if resp.status_code == 404:
        findings.append({
            "title": "No robots.txt found",
            "severity": "info",
            "category": "crawl-render",
            "evidence": f"GET {robots_url} returned 404.",
            "suggested_action": {
                "summary": "Consider adding a robots.txt to explicitly allow or guide crawlers.",
                "priority": "low",
            },
        })
        return findings

    body = resp.text
    current_agent = None
    for line in body.splitlines():
        line = line.strip()
        if line.lower().startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
        elif line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path == "/" and current_agent:
                sev = "critical" if current_agent == "*" else "high"
                findings.append({
                    "title": f"Broad crawl block for {current_agent}",
                    "severity": sev,
                    "category": "crawl-render",
                    "evidence": f"robots.txt contains 'Disallow: /' for User-agent: {current_agent}.",
                    "suggested_action": {
                        "summary": f"Remove or narrow the Disallow rule for {current_agent} to allow discovery of important pages.",
                        "priority": "high",
                    },
                })
            elif path and current_agent:
                # Check if important paths are blocked for AI bots
                if current_agent in _AI_BOTS or current_agent == "*":
                    important = any(seg in path.lower() for seg in
                                    ["/product", "/about", "/service", "/pricing", "/contact", "/blog"])
                    if important:
                        findings.append({
                            "title": f"Important path blocked for {current_agent}",
                            "severity": "high",
                            "category": "crawl-render",
                            "evidence": f"robots.txt disallows '{path}' for {current_agent}.",
                            "suggested_action": {
                                "summary": f"Review whether blocking '{path}' for {current_agent} is intentional — this may prevent AI systems from discovering key content.",
                                "priority": "high",
                            },
                        })

    # Check for AI-specific blocks
    for bot in _AI_BOTS:
        if bot.lower() in body.lower():
            # Already handled above, but flag if not caught
            pass

    return findings


def _check_sitemap(origin: str, robots_body: str = "") -> list[dict]:
    """Check for sitemap.xml.  Returns findings list."""
    import requests

    findings: list[dict] = []

    # Look for Sitemap directive in robots.txt
    sitemap_urls = []
    for line in robots_body.splitlines():
        if line.strip().lower().startswith("sitemap:"):
            sitemap_urls.append(line.split(":", 1)[1].strip())

    if not sitemap_urls:
        sitemap_urls = [f"{origin}/sitemap.xml"]

    found_valid = False
    for smap_url in sitemap_urls:
        try:
            resp = requests.get(smap_url, timeout=15,
                                headers={"User-Agent": "BrandAuditBot/1.0"})
            if resp.status_code == 200 and "<loc>" in resp.text.lower():
                found_valid = True
                break
        except Exception:
            continue

    if not found_valid:
        findings.append({
            "title": "No valid sitemap found",
            "severity": "medium",
            "category": "crawl-render",
            "evidence": f"No accessible sitemap.xml found at {origin}/sitemap.xml or via robots.txt Sitemap directives.",
            "suggested_action": {
                "summary": "Add a sitemap.xml listing important pages to help crawlers discover content efficiently.",
                "priority": "medium",
            },
        })

    return findings


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit(url: str) -> dict:
    """Run the full crawl-and-render audit for *url*.  Returns result dict."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    findings: list[dict] = []

    # -- robots.txt --------------------------------------------------------
    findings.extend(_check_robots(origin))

    # -- sitemap -----------------------------------------------------------
    import requests
    robots_body = ""
    try:
        r = requests.get(f"{origin}/robots.txt", timeout=15,
                         headers={"User-Agent": "BrandAuditBot/1.0"})
        if r.status_code == 200:
            robots_body = r.text
    except Exception:
        pass
    findings.extend(_check_sitemap(origin, robots_body))

    # -- Fetch raw HTML ----------------------------------------------------
    try:
        status, raw_html, redirects = _fetch_raw(url)
    except Exception as exc:
        findings.append({
            "title": "Target URL unreachable",
            "severity": "critical",
            "category": "crawl-render",
            "evidence": f"Could not fetch {url}: {exc}",
            "suggested_action": {
                "summary": "Ensure the URL is accessible and responds to HTTP GET requests.",
                "priority": "high",
            },
        })
        return {"url": url, "findings": findings}

    if status != 200:
        findings.append({
            "title": f"Non-200 HTTP status ({status})",
            "severity": "critical",
            "category": "crawl-render",
            "evidence": f"GET {url} returned HTTP {status}.",
            "suggested_action": {
                "summary": f"Fix the server to return HTTP 200 for this page (currently {status}).",
                "priority": "high",
            },
        })

    if len(redirects) > 3:
        findings.append({
            "title": "Excessive redirect chain",
            "severity": "medium",
            "category": "crawl-render",
            "evidence": f"{len(redirects)} redirects before reaching final URL: {' → '.join(redirects[:5])}",
            "suggested_action": {
                "summary": "Reduce the redirect chain to at most 1–2 hops.",
                "priority": "medium",
            },
        })

    raw_text = _visible_text_bs4(raw_html)

    # Check for meta robots noindex
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw_html, "html.parser")
    meta_robots = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
    if meta_robots:
        content = (meta_robots.get("content") or "").lower()
        if "noindex" in content:
            findings.append({
                "title": "Page marked as noindex",
                "severity": "high",
                "category": "crawl-render",
                "evidence": f"<meta name=\"robots\" content=\"{meta_robots.get('content')}\"> found in HTML head.",
                "suggested_action": {
                    "summary": "Remove the noindex directive if this page should be discoverable by search engines and AI systems.",
                    "priority": "high",
                },
            })

    # Check for empty body
    if len(raw_text) < 50:
        findings.append({
            "title": "Very little text in raw HTML body",
            "severity": "critical",
            "category": "crawl-render",
            "evidence": f"Only {len(raw_text)} characters of visible text found in raw HTML. Page content may depend entirely on JavaScript.",
            "suggested_action": {
                "summary": "Ensure critical content is present in server-rendered HTML, not loaded exclusively via JavaScript.",
                "priority": "high",
            },
        })

    # -- Render with Playwright -------------------------------------------
    rendered_text = ""
    playwright_available = True
    try:
        rendered_text = _render_playwright(url)
    except ImportError:
        playwright_available = False
        findings.append({
            "title": "Playwright not available — render diff skipped",
            "severity": "info",
            "category": "crawl-render",
            "evidence": "Playwright is not installed; raw-vs-rendered comparison could not be performed.",
            "suggested_action": {
                "summary": "Install Playwright (`pip install playwright && python -m playwright install`) to enable render-diff analysis.",
                "priority": "low",
            },
        })
    except Exception as exc:
        findings.append({
            "title": "Headless rendering failed",
            "severity": "info",
            "category": "crawl-render",
            "evidence": f"Playwright rendering failed: {exc}",
            "suggested_action": {
                "summary": "Investigate whether the page blocks headless browsers or has rendering errors.",
                "priority": "low",
            },
        })

    # -- Compute diff ------------------------------------------------------
    diff_ratio = 0.0
    added_blocks: list[str] = []
    if rendered_text and raw_text:
        raw_len = max(len(raw_text), 1)
        rendered_len = len(rendered_text)
        diff_ratio = (rendered_len - raw_len) / raw_len if rendered_len > raw_len else 0.0
        added_blocks = _diff_blocks(raw_text, rendered_text)

        if diff_ratio > 0.40:
            findings.append({
                "title": "Significant content hidden behind JavaScript",
                "severity": "high",
                "category": "crawl-render",
                "evidence": (
                    f"Raw HTML contains {raw_len:,} chars of text; rendered page contains "
                    f"{rendered_len:,} chars ({diff_ratio:.0%} more). "
                    f"{len(added_blocks)} content block(s) appear only after JS execution."
                ),
                "suggested_action": {
                    "summary": "Implement server-side rendering (SSR) or pre-rendering for critical content so it is available without JavaScript.",
                    "priority": "high",
                },
            })
        elif diff_ratio > 0.15:
            findings.append({
                "title": "Moderate content added by JavaScript",
                "severity": "medium",
                "category": "crawl-render",
                "evidence": (
                    f"Raw HTML contains {raw_len:,} chars; rendered page contains "
                    f"{rendered_len:,} chars ({diff_ratio:.0%} more)."
                ),
                "suggested_action": {
                    "summary": "Consider server-side rendering for important content blocks that currently require JavaScript.",
                    "priority": "medium",
                },
            })

    return {
        "url": url,
        "raw_text_length": len(raw_text),
        "rendered_text_length": len(rendered_text),
        "diff_ratio": round(diff_ratio, 4),
        "added_blocks": added_blocks[:10],  # cap for readability
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python render_diff.py <url>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    result = audit(url)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()  # trailing newline


if __name__ == "__main__":
    main()