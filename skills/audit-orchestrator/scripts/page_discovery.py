#!/usr/bin/env python3
"""
page-discovery

Finds a sample of internal pages to audit beyond the homepage.

Discovery strategy:
1. Sitemap URLs discovered from robots.txt.
2. /sitemap.xml
3. /sitemap_index.xml
4. Recursively follows sitemap indexes.
5. Supplements sitemap results with same-domain homepage links.

No JavaScript rendering, Playwright, Selenium, login bypass, or recursive
page crawling is performed here.

Public/static discovery only.
"""

import json
import sys
import urllib.parse as up
from collections import deque
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup


UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SKIP_EXT = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".avif",
    ".zip",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".mp4",
    ".webm",
    ".mp3",
    ".wav",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get_with_fallback(url, timeout, min_bytes=500):
    """
    Try the disclosed audit bot UA first.

    If the response is blocked, empty, or suspiciously small, retry once with
    a normal browser User-Agent.

    Returns:
        (response_or_none, used_fallback_ua)
    """

    first_response = None

    try:
        first_response = requests.get(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "*/*",
            },
            timeout=timeout,
            allow_redirects=True,
        )

        if (
            first_response.status_code < 400
            and len(first_response.content) >= min_bytes
        ):
            return first_response, False

    except requests.RequestException:
        pass

    try:
        fallback_response = requests.get(
            url,
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "*/*",
            },
            timeout=timeout,
            allow_redirects=True,
        )

        return fallback_response, True

    except requests.RequestException:
        return first_response, False


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _normalise_hostname(hostname):
    if not hostname:
        return ""

    hostname = hostname.lower().strip()

    if hostname.endswith("."):
        hostname = hostname[:-1]

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def _normalise_url(url):
    """
    Normalise URLs without destroying legitimate query parameters.

    Removes:
    - fragments
    - common tracking parameters
    - default HTTP/HTTPS ports
    - duplicate trailing slash where appropriate
    """

    if not url:
        return None

    url = url.strip()

    try:
        parsed = up.urlparse(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        hostname = _normalise_hostname(parsed.hostname)

        if not hostname:
            return None

        scheme = parsed.scheme.lower()

        # Preserve non-default ports.
        port = parsed.port

        if port:
            if not (
                (scheme == "http" and port == 80)
                or (scheme == "https" and port == 443)
            ):
                netloc = f"{hostname}:{port}"
            else:
                netloc = hostname
        else:
            netloc = hostname

        # Clean query parameters.
        query_items = up.parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )

        clean_query = []

        for key, value in query_items:
            key_lower = key.lower()

            if key_lower.startswith("utm_"):
                continue

            if key_lower in TRACKING_PARAMS:
                continue

            clean_query.append((key, value))

        query = up.urlencode(clean_query, doseq=True)

        path = parsed.path or "/"

        # Collapse repeated slashes.
        while "//" in path:
            path = path.replace("//", "/")

        # Keep root as "/".
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        return up.urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                query,
                "",
            )
        )

    except (ValueError, TypeError):
        return None


def _same_domain(url, hostname):
    parsed = up.urlparse(url)

    candidate = _normalise_hostname(parsed.hostname)

    expected = _normalise_hostname(hostname)

    return candidate == expected


def _is_page_url(url):
    """
    Reject obvious static assets and non-page resources.
    """

    if not url:
        return False

    try:
        parsed = up.urlparse(url)
        path = parsed.path.lower()

        for extension in SKIP_EXT:
            if path.endswith(extension):
                return False

        return True

    except Exception:
        return False


def _local(tag):
    return tag.split("}")[-1].lower()


# ---------------------------------------------------------------------------
# robots.txt sitemap discovery
# ---------------------------------------------------------------------------

def _from_robots(origin, timeout):
    """
    Extract Sitemap: URLs from robots.txt.
    """

    sitemap_urls = []

    robots_url = up.urljoin(origin, "/robots.txt")

    try:
        response, _ = _get_with_fallback(
            robots_url,
            timeout,
            min_bytes=20,
        )

        if response is None:
            return sitemap_urls

        if response.status_code >= 400:
            return sitemap_urls

        for line in response.text.splitlines():
            line = line.strip()

            if not line:
                continue

            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()

                normalised = _normalise_url(sitemap_url)

                if normalised:
                    sitemap_urls.append(normalised)

    except requests.RequestException:
        pass

    return sitemap_urls


# ---------------------------------------------------------------------------
# Sitemap parsing
# ---------------------------------------------------------------------------

def _parse_sitemap(content):
    """
    Parse a sitemap or sitemap index.

    Returns:
        {
            "type": "sitemapindex" | "urlset" | None,
            "items": [...]
        }
    """

    try:
        root = ET.fromstring(content)

    except ET.ParseError:
        return {
            "type": None,
            "items": [],
        }

    root_type = _local(root.tag)

    if root_type == "sitemapindex":

        items = []

        for sitemap_element in root:
            if _local(sitemap_element.tag) != "sitemap":
                continue

            for child in sitemap_element:
                if _local(child.tag) == "loc" and child.text:
                    items.append(child.text.strip())

        return {
            "type": "sitemapindex",
            "items": items,
        }

    if root_type == "urlset":

        items = []

        for url_element in root:
            if _local(url_element.tag) != "url":
                continue

            for child in url_element:
                if _local(child.tag) == "loc" and child.text:
                    items.append(child.text.strip())

        return {
            "type": "urlset",
            "items": items,
        }

    return {
        "type": None,
        "items": [],
    }


def _collect_from_sitemaps(
    sitemap_urls,
    hostname,
    timeout,
    max_urls,
    max_sitemaps=50,
):
    """
    Recursively process sitemap indexes.

    Stops when:
    - max_urls page candidates have been collected, or
    - max_sitemaps sitemap files have been processed.
    """

    page_urls = []

    sitemap_queue = deque()

    for sitemap_url in sitemap_urls:
        sitemap_queue.append(sitemap_url)

    visited_sitemaps = set()

    seen_pages = set()

    while sitemap_queue and len(visited_sitemaps) < max_sitemaps:

        sitemap_url = sitemap_queue.popleft()

        sitemap_url = _normalise_url(sitemap_url)

        if not sitemap_url:
            continue

        if sitemap_url in visited_sitemaps:
            continue

        visited_sitemaps.add(sitemap_url)

        try:
            response, _ = _get_with_fallback(
                sitemap_url,
                timeout,
                min_bytes=50,
            )

            if response is None:
                continue

            if response.status_code != 200:
                continue

            if not response.content:
                continue

            parsed = _parse_sitemap(response.content)

            if parsed["type"] == "sitemapindex":

                for child_sitemap in parsed["items"]:

                    child_sitemap = _normalise_url(child_sitemap)

                    if not child_sitemap:
                        continue

                    if child_sitemap in visited_sitemaps:
                        continue

                    sitemap_queue.append(child_sitemap)

            elif parsed["type"] == "urlset":

                for page_url in parsed["items"]:

                    page_url = _normalise_url(page_url)

                    if not page_url:
                        continue

                    if not _same_domain(page_url, hostname):
                        continue

                    if not _is_page_url(page_url):
                        continue

                    if page_url in seen_pages:
                        continue

                    seen_pages.add(page_url)
                    page_urls.append(page_url)

                    if len(page_urls) >= max_urls:
                        break

        except (
            requests.RequestException,
            ET.ParseError,
            ValueError,
        ):
            continue

        if len(page_urls) >= max_urls:
            break

    return page_urls


def _from_sitemap(origin, hostname, timeout, max_urls):
    """
    Discover sitemap URLs from:

    1. robots.txt
    2. /sitemap.xml
    3. /sitemap_index.xml

    Then recursively process sitemap indexes.
    """

    sitemap_candidates = []

    # robots.txt
    sitemap_candidates.extend(
        _from_robots(origin, timeout)
    )

    # Standard locations.
    sitemap_candidates.extend(
        [
            _normalise_url(up.urljoin(origin, "/sitemap.xml")),
            _normalise_url(up.urljoin(origin, "/sitemap_index.xml")),
        ]
    )

    # Deduplicate sitemap URLs.
    unique_sitemaps = []

    seen = set()

    for sitemap_url in sitemap_candidates:

        if not sitemap_url:
            continue

        if sitemap_url in seen:
            continue

        seen.add(sitemap_url)
        unique_sitemaps.append(sitemap_url)

    return _collect_from_sitemaps(
        unique_sitemaps,
        hostname=hostname,
        timeout=timeout,
        max_urls=max_urls,
    )


# ---------------------------------------------------------------------------
# Homepage links
# ---------------------------------------------------------------------------

def _from_homepage_links(homepage_url, homepage_html, hostname):
    """
    Extract same-domain links from the raw homepage HTML.

    No JavaScript is executed.
    """

    if not homepage_html:
        return []

    urls = []

    try:
        soup = BeautifulSoup(
            homepage_html,
            "html.parser",
        )

    except Exception:
        return urls

    for anchor in soup.find_all("a", href=True):

        href = anchor.get("href", "").strip()

        if not href:
            continue

        lower_href = href.lower()

        if lower_href.startswith(
            (
                "#",
                "mailto:",
                "tel:",
                "javascript:",
                "data:",
            )
        ):
            continue

        full_url = up.urljoin(
            homepage_url,
            href,
        )

        full_url = _normalise_url(full_url)

        if not full_url:
            continue

        if not _same_domain(full_url, hostname):
            continue

        if not _is_page_url(full_url):
            continue

        urls.append(full_url)

    return urls


# ---------------------------------------------------------------------------
# Main discovery function
# ---------------------------------------------------------------------------

def discover_pages(
    homepage_url,
    homepage_html,
    max_pages=10,
    timeout=15,
):
    """
    Return up to max_pages unique same-domain URLs.

    Homepage is always first.

    Compatible with run_audit.py:
        discover_pages(
            homepage_url,
            homepage_html,
            max_pages=10,
            timeout=15
        )
    """

    if max_pages <= 0:
        return []

    homepage = _normalise_url(homepage_url)

    if not homepage:
        return []

    parsed = up.urlparse(homepage)

    hostname = _normalise_hostname(
        parsed.hostname
    )

    origin = f"{parsed.scheme}://{parsed.netloc}"

    pages = [homepage]
    seen = {homepage}

    # ---------------------------------------------------------
    # 1. Sitemap discovery
    # ---------------------------------------------------------

    sitemap_pages = _from_sitemap(
        origin=origin,
        hostname=hostname,
        timeout=timeout,
        max_urls=max_pages * 5,
    )

    # ---------------------------------------------------------
    # 2. Homepage links
    # Always collect them as a supplement.
    # ---------------------------------------------------------

    homepage_pages = _from_homepage_links(
        homepage,
        homepage_html,
        hostname,
    )

    # ---------------------------------------------------------
    # 3. Merge sitemap + homepage links
    # ---------------------------------------------------------

    candidates = sitemap_pages + homepage_pages

    for candidate in candidates:

        candidate = _normalise_url(candidate)

        if not candidate:
            continue

        if candidate in seen:
            continue

        if not _same_domain(candidate, hostname):
            continue

        if not _is_page_url(candidate):
            continue

        seen.add(candidate)
        pages.append(candidate)

        if len(pages) >= max_pages:
            break

    return pages


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():

    if len(sys.argv) < 2:
        print(
            "usage: page_discovery.py <homepage_url> [max_pages]",
            file=sys.stderr,
        )
        sys.exit(1)

    homepage = sys.argv[1]

    try:
        max_pages = (
            int(sys.argv[2])
            if len(sys.argv) > 2
            else 10
        )
    except ValueError:
        print(
            "max_pages must be an integer",
            file=sys.stderr,
        )
        sys.exit(1)

    response, used_fallback = _get_with_fallback(
        homepage,
        timeout=15,
        min_bytes=500,
    )

    if response is None:
        print(
            json.dumps([]),
            file=sys.stderr,
        )
        sys.exit(1)

    homepage_html = response.text

    pages = discover_pages(
        homepage,
        homepage_html,
        max_pages=max_pages,
        timeout=15,
    )

    print(
        json.dumps(
            pages,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()