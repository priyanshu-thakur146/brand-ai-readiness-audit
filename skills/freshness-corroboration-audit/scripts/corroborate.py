#!/usr/bin/env python3
"""
corroborate.py — deterministic freshness/date and cross-page corroboration checks
for the freshness-corroboration-audit skill.

Contract (matches audit-orchestrator/scripts/report_builder.py raw-finding schema):
  Each finding is a dict:
    {
      "id_hint": str, "title": str, "severity": "critical"|"high"|"medium"|"low",
      "evidence": str, "suggested_action": str,
      "dedupe_key": "freshness:<id_hint>",
      "source_skill": "freshness-corroboration-audit",
      "proactive": bool,
    }

Usage:
  python corroborate.py <url> [--pages <path> <path> ...] --out <raw_findings.json>
                              [--now-iso <YYYY-MM-DD>] [--stale-days <int>]

What it checks (see SKILL.md for full rationale):
  1. Date signal presence   — does the page expose *any* discoverable date
     (JSON-LD datePublished/dateModified, <meta> tags, or visible text
     matching common date patterns)?
  2. Internal date logic    — is dateModified before datePublished (a direct
     self-contradiction)?
  3. Staleness              — is the most recent date signal older than a
     configurable threshold, escalated when the page's own text uses
     currency language ("as of", "currently", "latest", "this year")
     alongside an old date?
  4. Cross-page numeric fact consistency — when multiple pages are sampled,
     does the same labeled fact (price, phone number, version number) appear
     with two different values across pages? This is the literal
     "corroboration" check: two of the site's own pages should agree with
     each other.

Design notes:
  - This skill deliberately does NOT fetch or compare against any external/
    third-party source — "corroboration" here means internal cross-page
    self-consistency, which is checkable deterministically and offline. It
    does not claim to verify real-world factual accuracy, which would
    require an external ground truth this skill cannot access within the
    read-only, no-third-party-lookup guardrail.
  - All date parsing is explicit and pattern-based (ISO 8601 + a small set of
    common human-readable formats), not a fuzzy NLP guess — false positives
    from misparsed dates would be worse than a missed one.
  - `--now-iso` lets the invoking skill/orchestrator pin "today" for
    reproducible, deterministic test runs; defaults to real UTC today.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

SKILL_NAME = "freshness-corroboration-audit"
USER_AGENT = "AuditBot/1.0 (+freshness-corroboration-audit skill; read-only)"
REQUEST_TIMEOUT = 10
DEFAULT_STALE_DAYS = 540  # ~18 months; overridable via --stale-days

CURRENCY_LANGUAGE = re.compile(
    r"\b(as of|currently|current(ly)?|this year|latest|up[- ]to[- ]date|now offering|"
    r"right now)\b",
    re.IGNORECASE,
)

# ISO 8601 (date or datetime) and a few common human-readable forms.
DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}[\+\-Z][\d:]*)?\b"),
    re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|"
               r"October|November|December)\s+\d{1,2},?\s+\d{4}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
]

# Labeled facts worth cross-page consistency checking: (label_regex, value_regex)
FACT_PATTERNS = {
    "price": re.compile(r"\$\s?(\d[\d,]*\.?\d{0,2})"),
    "phone": re.compile(r"\b(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})\b"),
    "version": re.compile(r"\bv(?:ersion)?\.?\s?(\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE),
}


def _finding(id_hint, title, severity, evidence, suggested_action, proactive=False):
    return {
        "id_hint": id_hint,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "dedupe_key": f"freshness:{id_hint}",
        "source_skill": SKILL_NAME,
        "proactive": proactive,
    }


def _parse_date(raw):
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%B %d, %Y", "%B %d %Y",
                "%m/%d/%Y"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Signal extraction (pure functions)
# ---------------------------------------------------------------------------

def extract_jsonld_dates(soup):
    """Returns dict: {'datePublished': datetime|None, 'dateModified': datetime|None}
    pulled from any JSON-LD block, plus the raw strings for evidence."""
    result = {"datePublished": (None, None), "dateModified": (None, None)}
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = parsed if isinstance(parsed, list) else \
            parsed.get("@graph", [parsed]) if isinstance(parsed, dict) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateModified"):
                if key in node and isinstance(node[key], str) and result[key][0] is None:
                    dt = _parse_date(node[key])
                    if dt:
                        result[key] = (dt, node[key])
    return result


def extract_meta_dates(soup):
    result = {}
    meta_names = {
        "article:published_time": "datePublished",
        "article:modified_time": "dateModified",
        "date": "datePublished",
        "last-modified": "dateModified",
    }
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if prop and content and prop.lower() in meta_names:
            key = meta_names[prop.lower()]
            if key not in result:
                dt = _parse_date(content)
                if dt:
                    result[key] = (dt, content)
    return result


def extract_visible_text_dates(soup, limit=5):
    text = soup.get_text(" ", strip=True)
    found = []
    for pattern in DATE_PATTERNS:
        for m in pattern.finditer(text):
            dt = _parse_date(m.group(0))
            if dt:
                found.append((dt, m.group(0)))
            if len(found) >= limit:
                break
    return found


def check_date_presence(jsonld_dates, meta_dates, visible_dates, page_url):
    has_any = (
        jsonld_dates["datePublished"][0] or jsonld_dates["dateModified"][0]
        or meta_dates.get("datePublished") or meta_dates.get("dateModified")
        or visible_dates
    )
    if not has_any:
        return [_finding(
            "no-date-signal", "No discoverable date signal on page", "medium",
            f"{page_url}: no datePublished/dateModified in JSON-LD, no relevant "
            f"<meta> tags, and no recognizable date pattern in visible text.",
            "Add a visible \"Last updated\" date or a datePublished/dateModified "
            "field in structured data — without any date signal, readers and AI "
            "agents can't judge how current this content is.",
        )]
    return []


def check_date_logic(jsonld_dates, page_url):
    pub_dt, pub_raw = jsonld_dates["datePublished"]
    mod_dt, mod_raw = jsonld_dates["dateModified"]
    if pub_dt and mod_dt and mod_dt < pub_dt:
        return [_finding(
            "date-modified-before-published", "dateModified predates datePublished",
            "high",
            f"{page_url}: datePublished=\"{pub_raw}\" but dateModified=\"{mod_raw}\" "
            f"is earlier.",
            "Fix the date logic — dateModified should never be earlier than "
            "datePublished; this is either a copy-paste error or a stale "
            "modified-date value that was never updated.",
        )]
    return []


def _most_recent_date(jsonld_dates, meta_dates, visible_dates):
    candidates = []
    for src in (jsonld_dates, meta_dates):
        for key in ("dateModified", "datePublished"):
            entry = src.get(key)
            if entry and entry[0]:
                candidates.append(entry)
    candidates.extend(visible_dates)
    if not candidates:
        return None, None
    dt, raw = max(candidates, key=lambda pair: pair[0])
    return dt, raw


def check_staleness(jsonld_dates, meta_dates, visible_dates, soup, page_url, now, stale_days):
    dt, raw = _most_recent_date(jsonld_dates, meta_dates, visible_dates)
    if dt is None:
        return []
    age_days = (now - dt).days
    if age_days < stale_days:
        return []

    text = soup.get_text(" ", strip=True)
    has_currency_language = bool(CURRENCY_LANGUAGE.search(text))
    severity = "high" if has_currency_language else "medium"
    currency_note = (
        " Page text also uses currency language (e.g. \"currently\"/\"as of\"/"
        "\"latest\") alongside this stale date, which sharpens the mismatch."
        if has_currency_language else ""
    )
    return [_finding(
        "stale-content", f"Most recent date signal is {age_days} days old", severity,
        f"{page_url}: most recent date found is \"{raw}\" ({age_days} days before "
        f"the audit date).{currency_note}",
        "Review this page's content for accuracy and either update it with a "
        "fresh date, or, if the content is genuinely evergreen, avoid currency "
        "language (\"currently\", \"as of\", \"latest\") that implies it's "
        "actively maintained.",
    )]


def extract_facts(soup):
    text = soup.get_text(" ", strip=True)
    facts = {}
    for label, pattern in FACT_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            facts[label] = matches
    return facts


def check_cross_page_corroboration(page_facts, page_urls):
    """page_facts: list of dicts (one per page) from extract_facts.
    Flags when the SAME label has a SINGLE consistent value on each page
    individually, but that value DIFFERS between pages — a deliberately
    conservative check to avoid flagging pages that simply list multiple
    prices/phone numbers for different products/departments."""
    findings = []
    if len(page_facts) < 2:
        return findings

    for label in FACT_PATTERNS:
        single_valued = {}  # page_url -> value, only if that page has exactly one distinct value
        for url, facts in zip(page_urls, page_facts):
            values = set(facts.get(label, []))
            if len(values) == 1:
                single_valued[url] = next(iter(values))

        distinct_values = set(single_valued.values())
        if len(distinct_values) > 1:
            sample = "; ".join(f"{u} -> {v}" for u, v in list(single_valued.items())[:4])
            findings.append(_finding(
                f"cross-page-mismatch-{label}",
                f"Inconsistent {label} across sampled pages", "high",
                f"Sampled pages each show a single, different {label} value: {sample}",
                f"Confirm which {label} value is correct and update the other "
                f"page(s) to match — inconsistent facts across a site's own pages "
                f"undermine trust and give AI agents summarizing the site "
                f"contradictory information to reconcile.",
            ))
    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def audit_page(url, session, now, stale_days):
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return [_finding(
            "page-unreachable", "Page could not be fetched", "critical",
            f"{url}: request failed with {exc.__class__.__name__}: {exc}",
            "Confirm the URL is correct and the server is reachable; an "
            "unreachable page blocks every freshness check.",
        )], {}

    if resp.status_code >= 400:
        return [_finding(
            "page-error-status", f"Page returned HTTP {resp.status_code}", "critical",
            f"{url}: server responded with status {resp.status_code}.",
            "Fix the underlying error before freshness can be evaluated at all.",
        )], {}

    soup = BeautifulSoup(resp.text, "html.parser")
    jsonld_dates = extract_jsonld_dates(soup)
    meta_dates = extract_meta_dates(soup)
    visible_dates = extract_visible_text_dates(soup)

    findings = []
    findings += check_date_presence(jsonld_dates, meta_dates, visible_dates, url)
    findings += check_date_logic(jsonld_dates, url)
    findings += check_staleness(jsonld_dates, meta_dates, visible_dates, soup, url, now, stale_days)

    facts = extract_facts(soup)
    return findings, facts


def run_audit(base_url, pages=None, now_iso=None, stale_days=DEFAULT_STALE_DAYS):
    session = requests.Session()
    pages = pages or [base_url]
    now = datetime.strptime(now_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc) \
        if now_iso else datetime.now(timezone.utc)

    all_findings = []
    all_facts = []
    for page_url in pages:
        page_findings, facts = audit_page(page_url, session, now, stale_days)
        all_findings.extend(page_findings)
        all_facts.append(facts)

    all_findings += check_cross_page_corroboration(all_facts, pages)
    return all_findings


def main():
    parser = argparse.ArgumentParser(description="freshness-corroboration-audit: corroborate.py")
    parser.add_argument("url", help="Base URL of the site being audited")
    parser.add_argument("--pages", nargs="*", default=None,
                         help="Specific page URLs to sample (defaults to just the base URL)")
    parser.add_argument("--out", required=True, help="Path to write raw findings JSON")
    parser.add_argument("--now-iso", default=None,
                         help="Pin 'today' as YYYY-MM-DD for reproducible runs (default: real UTC today)")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                         help=f"Days before a date signal is considered stale (default {DEFAULT_STALE_DAYS})")
    args = parser.parse_args()

    try:
        findings = run_audit(args.url, args.pages, args.now_iso, args.stale_days)
    except Exception as exc:
        print(f"freshness-corroboration-audit corroborate.py FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w") as f:
        json.dump(findings, f, indent=2)

    print(f"freshness-corroboration-audit: wrote {len(findings)} finding(s) to {args.out}")


if __name__ == "__main__":
    main()