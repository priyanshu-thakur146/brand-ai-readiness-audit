#!/usr/bin/env python3
"""corroborate.py — Check content freshness and external corroboration signals.

Usage:
    python corroborate.py <url>

Outputs JSON to stdout with keys:
    url, freshness_signals, identity_signals, findings
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # ISO 8601
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
    # Common display dates
    re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}", re.I),
    re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
]

_COPYRIGHT_YEAR = re.compile(r"(?:©|&copy;|copyright)\s*(\d{4})", re.I)


def _fetch(url: str, *, timeout: int = 30):
    """Fetch URL and return (response, html)."""
    import requests

    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "BrandAuditBot/1.0 (+https://github.com/brand-audit)"},
    )
    resp.raise_for_status()
    return resp


def _extract_dates_from_html(html: str) -> list[str]:
    """Find date-like strings in visible HTML text."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")

    dates: list[str] = []
    for pat in _DATE_PATTERNS:
        dates.extend(pat.findall(text))
    return dates[:20]  # cap


def _extract_structured_dates(html: str) -> dict[str, list[str]]:
    """Extract dates from JSON-LD and meta tags."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, list[str]] = {"jsonld": [], "meta": []}

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(script.string or "")
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                for key in ("datePublished", "dateModified", "dateCreated",
                            "startDate", "endDate", "uploadDate"):
                    if key in item:
                        result["jsonld"].append(f"{key}: {item[key]}")
        except (json.JSONDecodeError, TypeError):
            continue

    # Meta tags (article:published_time etc.)
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if any(kw in prop.lower() for kw in ("date", "time", "modified", "published")):
            result["meta"].append(f"{prop}: {meta.get('content', '')}")

    return result


def _extract_copyright_year(html: str) -> int | None:
    """Extract copyright year from HTML."""
    match = _COPYRIGHT_YEAR.search(html)
    if match:
        return int(match.group(1))
    return None


def _extract_sameas(html: str) -> list[str]:
    """Extract sameAs links from JSON-LD."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(script.string or "")
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                sa = item.get("sameAs", [])
                if isinstance(sa, str):
                    links.append(sa)
                elif isinstance(sa, list):
                    links.extend(sa)
        except (json.JSONDecodeError, TypeError):
            continue
    return links


def _extract_social_links(html: str) -> list[str]:
    """Extract links to major social/external platforms."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    social_domains = {"twitter.com", "x.com", "facebook.com", "linkedin.com",
                      "instagram.com", "youtube.com", "github.com", "wikipedia.org",
                      "crunchbase.com", "wikidata.org"}
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            domain = urlparse(href).netloc.lower().lstrip("www.")
            if domain in social_domains:
                links.append(href)
        except Exception:
            continue
    return list(set(links))


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------


def audit(url: str) -> dict:
    """Run freshness & corroboration audit.  Returns result dict."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    findings: list[dict] = []
    freshness_signals: dict = {}
    identity_signals: dict = {}

    try:
        resp = _fetch(url)
        html = resp.text
    except Exception as exc:
        return {
            "url": url,
            "freshness_signals": {},
            "identity_signals": {},
            "findings": [{
                "title": "Could not fetch page for freshness audit",
                "severity": "critical",
                "category": "freshness-corroboration",
                "evidence": f"HTTP request to {url} failed: {exc}",
                "suggested_action": {
                    "summary": "Ensure the page is accessible.",
                    "priority": "high",
                },
            }],
        }

    # -- HTTP freshness headers --------------------------------------------
    last_modified = resp.headers.get("Last-Modified", "")
    etag = resp.headers.get("ETag", "")
    cache_control = resp.headers.get("Cache-Control", "")
    freshness_signals["last_modified"] = last_modified or None
    freshness_signals["etag"] = etag or None
    freshness_signals["cache_control"] = cache_control or None

    if not last_modified:
        findings.append({
            "title": "No Last-Modified HTTP header",
            "severity": "low",
            "category": "freshness-corroboration",
            "evidence": "The server does not send a Last-Modified header, making it harder for caches and crawlers to detect content changes.",
            "suggested_action": {
                "summary": "Configure the server to send Last-Modified headers reflecting when page content was last updated.",
                "priority": "low",
            },
        })

    # -- Structured dates --------------------------------------------------
    structured_dates = _extract_structured_dates(html)
    freshness_signals["structured_dates"] = structured_dates

    if not structured_dates["jsonld"] and not structured_dates["meta"]:
        findings.append({
            "title": "No machine-readable date information",
            "severity": "medium",
            "category": "freshness-corroboration",
            "evidence": "No datePublished, dateModified, or article timestamps found in JSON-LD or meta tags.",
            "suggested_action": {
                "summary": "Add datePublished and dateModified to JSON-LD structured data so AI systems can assess content freshness.",
                "priority": "medium",
            },
        })

    # -- Copyright year ----------------------------------------------------
    copyright_year = _extract_copyright_year(html)
    freshness_signals["copyright_year"] = copyright_year
    current_year = datetime.now(timezone.utc).year

    if copyright_year and copyright_year < current_year - 1:
        findings.append({
            "title": f"Outdated copyright year ({copyright_year})",
            "severity": "low",
            "category": "freshness-corroboration",
            "evidence": f"Copyright notice shows {copyright_year}, which is {current_year - copyright_year} year(s) behind the current year ({current_year}).",
            "suggested_action": {
                "summary": f"Update the copyright year to {current_year} (or use a dynamic year).",
                "priority": "low",
            },
        })

    # -- Visible dates in content ------------------------------------------
    visible_dates = _extract_dates_from_html(html)
    freshness_signals["visible_dates_sample"] = visible_dates[:5]

    # -- Identity / Corroboration ------------------------------------------
    sameas_links = _extract_sameas(html)
    social_links = _extract_social_links(html)
    identity_signals["sameas"] = sameas_links
    identity_signals["social_links"] = social_links

    if not sameas_links:
        findings.append({
            "title": "No sameAs identity links in structured data",
            "severity": "medium",
            "category": "freshness-corroboration",
            "evidence": "JSON-LD does not include 'sameAs' links to authoritative external profiles (Wikipedia, social media, Wikidata).",
            "suggested_action": {
                "summary": "Add 'sameAs' URLs in JSON-LD pointing to official social profiles, Wikipedia, or Wikidata to strengthen entity identity.",
                "priority": "medium",
            },
        })

    if not social_links and not sameas_links:
        findings.append({
            "title": "No external identity references found",
            "severity": "high",
            "category": "freshness-corroboration",
            "evidence": "The page contains no links to social profiles, Wikipedia, or other external sources that corroborate the brand's identity.",
            "suggested_action": {
                "summary": "Add links to official social media profiles and external authoritative sources to help AI systems verify entity identity.",
                "priority": "high",
            },
        })

    # -- Check canonical and consistent naming -----------------------------
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.find("link", rel="canonical")
    if not canonical:
        findings.append({
            "title": "No canonical URL specified",
            "severity": "low",
            "category": "freshness-corroboration",
            "evidence": "The page does not include a <link rel=\"canonical\"> tag.",
            "suggested_action": {
                "summary": "Add a canonical URL tag to prevent duplicate-content issues and clarify the authoritative URL.",
                "priority": "low",
            },
        })

    return {
        "url": url,
        "freshness_signals": freshness_signals,
        "identity_signals": identity_signals,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python corroborate.py <url>", file=sys.stderr)
        sys.exit(1)
    result = audit(sys.argv[1])
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()