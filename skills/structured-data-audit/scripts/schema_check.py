#!/usr/bin/env python3
"""schema_check.py — Extract and validate structured data from a web page.

Usage:
    python schema_check.py <url>

Outputs JSON to stdout with keys:
    url, json_ld, opengraph, microdata, rdfa, findings
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Extraction
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


def _extract_structured(html: str, url: str) -> dict:
    """Use extruct to pull all structured data from *html*."""
    try:
        import extruct

        data = extruct.extract(html, base_url=url, errors="ignore",
                               uniform=True,
                               syntaxes=["json-ld", "opengraph", "microdata", "rdfa"])
    except ImportError:
        # Fallback: manual JSON-LD + OG extraction
        data = {"json-ld": [], "opengraph": [], "microdata": [], "rdfa": []}
        data["json-ld"] = _extract_jsonld_manual(html)
        data["opengraph"] = _extract_og_manual(html)
    return data


def _extract_jsonld_manual(html: str) -> list[dict]:
    """Fallback JSON-LD extraction when extruct is unavailable."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(tag.string or "")
            if isinstance(obj, list):
                items.extend(obj)
            else:
                items.append(obj)
        except (json.JSONDecodeError, TypeError):
            continue
    return items


def _extract_og_manual(html: str) -> list[dict]:
    """Fallback Open Graph extraction."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    og: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if prop.startswith("og:"):
            og[prop] = meta.get("content", "")
    return [og] if og else []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_IMPORTANT_SCHEMA_TYPES = {
    "Organization", "LocalBusiness", "Corporation", "WebSite", "WebPage",
    "Product", "Service", "Article", "BlogPosting", "FAQPage",
    "BreadcrumbList", "Person", "Event", "Review", "AggregateRating",
    "HowTo", "Recipe", "Course", "SoftwareApplication",
}

_REQUIRED_OG = {"og:title", "og:type", "og:url", "og:image"}


def _get_types(item: dict) -> set[str]:
    """Extract Schema.org @type(s) from a JSON-LD item."""
    t = item.get("@type", "")
    if isinstance(t, list):
        return set(t)
    return {t} if t else set()


def _validate_jsonld(items: list[dict]) -> list[dict]:
    """Return findings for JSON-LD quality issues."""
    findings: list[dict] = []

    if not items:
        findings.append({
            "title": "No JSON-LD structured data found",
            "severity": "high",
            "category": "structured-data",
            "evidence": "The page contains no <script type=\"application/ld+json\"> blocks.",
            "suggested_action": {
                "summary": "Add JSON-LD structured data describing the primary entity on this page (e.g. Organization, Product, Article).",
                "priority": "high",
            },
        })
        return findings

    # Check for important types
    all_types: set[str] = set()
    for item in items:
        all_types |= _get_types(item)

    has_important = all_types & _IMPORTANT_SCHEMA_TYPES
    if not has_important:
        findings.append({
            "title": "JSON-LD lacks common Schema.org types",
            "severity": "medium",
            "category": "structured-data",
            "evidence": f"Found @type(s): {', '.join(sorted(all_types)) or '(none)'}. None are commonly used Schema.org types.",
            "suggested_action": {
                "summary": "Use recognized Schema.org types such as Organization, Product, or Article to help AI systems understand page content.",
                "priority": "medium",
            },
        })

    # Check for missing name/description
    for item in items:
        types = _get_types(item)
        if not types:
            continue
        if not item.get("name") and not item.get("headline"):
            findings.append({
                "title": f"JSON-LD {', '.join(types)} missing 'name'",
                "severity": "medium",
                "category": "structured-data",
                "evidence": f"A JSON-LD block with @type {', '.join(types)} does not include a 'name' or 'headline' property.",
                "suggested_action": {
                    "summary": f"Add a 'name' property to the {', '.join(types)} JSON-LD block.",
                    "priority": "medium",
                },
            })

    # Check for @context
    for item in items:
        if "@type" in item and "@context" not in item:
            findings.append({
                "title": "JSON-LD block missing @context",
                "severity": "medium",
                "category": "structured-data",
                "evidence": "A JSON-LD block specifies @type but no @context (should be 'https://schema.org').",
                "suggested_action": {
                    "summary": "Add '\"@context\": \"https://schema.org\"' to each JSON-LD block.",
                    "priority": "medium",
                },
            })
            break  # one finding is enough

    return findings


def _validate_og(items: list[dict]) -> list[dict]:
    """Return findings for Open Graph metadata issues."""
    findings: list[dict] = []
    if not items or not any(items):
        findings.append({
            "title": "No Open Graph metadata found",
            "severity": "medium",
            "category": "structured-data",
            "evidence": "The page contains no Open Graph <meta property=\"og:...\"> tags.",
            "suggested_action": {
                "summary": "Add Open Graph tags (og:title, og:type, og:url, og:image) to improve link previews on social platforms and AI citations.",
                "priority": "medium",
            },
        })
        return findings

    og = items[0] if items else {}
    present_keys = set(og.keys())
    missing = _REQUIRED_OG - present_keys
    if missing:
        findings.append({
            "title": "Missing required Open Graph tags",
            "severity": "medium",
            "category": "structured-data",
            "evidence": f"Missing OG tags: {', '.join(sorted(missing))}. Present: {', '.join(sorted(present_keys))}.",
            "suggested_action": {
                "summary": f"Add the following Open Graph tags: {', '.join(sorted(missing))}.",
                "priority": "medium",
            },
        })

    # Check for empty values
    for key, val in og.items():
        if not val or not val.strip():
            findings.append({
                "title": f"Open Graph tag '{key}' is empty",
                "severity": "low",
                "category": "structured-data",
                "evidence": f"The tag <meta property=\"{key}\"> is present but has an empty content attribute.",
                "suggested_action": {
                    "summary": f"Provide a meaningful value for the '{key}' Open Graph tag.",
                    "priority": "low",
                },
            })

    return findings


def _check_meta_description(html: str) -> list[dict]:
    """Check <title> and <meta description>."""
    from bs4 import BeautifulSoup

    findings: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    if not title_tag or not (title_tag.string or "").strip():
        findings.append({
            "title": "Missing or empty <title> tag",
            "severity": "high",
            "category": "structured-data",
            "evidence": "The page has no <title> tag or its content is empty.",
            "suggested_action": {
                "summary": "Add a descriptive <title> tag (ideally 10–70 characters).",
                "priority": "high",
            },
        })
    else:
        tlen = len(title_tag.string.strip())
        if tlen < 10 or tlen > 70:
            findings.append({
                "title": f"<title> tag length outside ideal range ({tlen} chars)",
                "severity": "low",
                "category": "structured-data",
                "evidence": f"Title \"{title_tag.string.strip()[:60]}\" is {tlen} chars (ideal: 10–70).",
                "suggested_action": {
                    "summary": "Adjust the title to be descriptive and between 10–70 characters.",
                    "priority": "low",
                },
            })

    meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if not meta_desc or not (meta_desc.get("content") or "").strip():
        findings.append({
            "title": "Missing or empty meta description",
            "severity": "medium",
            "category": "structured-data",
            "evidence": "The page has no <meta name=\"description\"> or its content is empty.",
            "suggested_action": {
                "summary": "Add a descriptive meta description (50–160 characters) summarizing the page content.",
                "priority": "medium",
            },
        })

    return findings


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------


def audit(url: str) -> dict:
    """Run structured-data audit for *url*.  Returns result dict."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    try:
        html = _fetch_html(url)
    except Exception as exc:
        return {
            "url": url,
            "json_ld": [],
            "opengraph": [],
            "microdata": [],
            "rdfa": [],
            "findings": [{
                "title": "Could not fetch page for structured-data audit",
                "severity": "critical",
                "category": "structured-data",
                "evidence": f"HTTP request to {url} failed: {exc}",
                "suggested_action": {
                    "summary": "Ensure the page is accessible.",
                    "priority": "high",
                },
            }],
        }

    data = _extract_structured(html, url)
    findings: list[dict] = []

    findings.extend(_validate_jsonld(data.get("json-ld", [])))
    findings.extend(_validate_og(data.get("opengraph", [])))
    findings.extend(_check_meta_description(html))

    # Microdata / RDFa — just flag absence at info level
    if not data.get("microdata") and not data.get("rdfa"):
        # Not a finding by itself since JSON-LD is the preferred method
        pass

    return {
        "url": url,
        "json_ld": data.get("json-ld", []),
        "opengraph": data.get("opengraph", []),
        "microdata": data.get("microdata", []),
        "rdfa": data.get("rdfa", []),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python schema_check.py <url>", file=sys.stderr)
        sys.exit(1)
    result = audit(sys.argv[1])
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()