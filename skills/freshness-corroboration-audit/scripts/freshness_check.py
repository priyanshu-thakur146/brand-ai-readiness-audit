#!/usr/bin/env python3
"""freshness-corroboration-audit: on-page date signals + agent-supplied corroboration scoring."""
import sys
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser  # python-dateutil

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
LAST_UPDATED_RE = re.compile(
    r"(last updated|updated on|published on|posted on)\s*[:\-]?\s*([A-Za-z0-9,\s\/\-]{6,25})", re.I)
STALE_DAYS_TIME_SENSITIVE = 365


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
    return {
        "id": fid,
        "category": "discoverability",
        "title": title,
        "severity": "info",
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": "info"},
        "proactive": True,
    }


def _try_parse(s):
    try:
        return dateparser.parse(s, fuzzy=True)
    except (ValueError, OverflowError):
        return None


def run_check(url, timeout=15, search_results=None):
    findings = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"FR-{n:03d}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException as e:
        return [_finding(nid(), "Page unreachable for freshness check", "critical",
                          f"Request error: {e}", "Fix connectivity/availability before auditing.",
                          "critical")]

    now = datetime.now(timezone.utc)

    # 1. HTTP Last-Modified header
    last_mod_header = r.headers.get("Last-Modified")
    header_dt = _try_parse(last_mod_header) if last_mod_header else None

    soup = BeautifulSoup(r.text, "lxml")
    meta_mod = soup.find("meta", property="article:modified_time") or soup.find(
        "meta", property="og:updated_time")
    meta_dt = _try_parse(meta_mod.get("content")) if meta_mod and meta_mod.get("content") else None

    text = re.sub(r"\s+", " ", soup.get_text(" "))
    visible_match = LAST_UPDATED_RE.search(text)
    visible_dt = _try_parse(visible_match.group(2)) if visible_match else None

    best_dt = meta_dt or visible_dt or header_dt
    source = "article:modified_time meta tag" if meta_dt else (
        "visible 'last updated' text" if visible_dt else (
            "Last-Modified HTTP header" if header_dt else None))

    if best_dt is None:
        findings.append(_finding(
            nid(), "No freshness/last-updated signal found", "low",
            "No article:modified_time meta tag, visible 'last updated' text, or Last-Modified "
            "header was found.",
            "For time-sensitive pages (pricing, listings, events, docs) add a visible 'last "
            "updated' date and an article:modified_time meta tag so assistants can judge recency "
            "before repeating claims.", "low"))
    else:
        if best_dt.tzinfo is None:
            best_dt = best_dt.replace(tzinfo=timezone.utc)
        age_days = (now - best_dt).days
        if age_days > STALE_DAYS_TIME_SENSITIVE:
            findings.append(_finding(
                nid(), "Content freshness signal is stale", "medium",
                f"Most recent freshness signal ({source}) is dated {best_dt.date()} "
                f"({age_days} days old).",
                "If the underlying facts (pricing, availability, specs) are still accurate, "
                "update the timestamp; if they've changed, update the content itself — a visibly "
                "stale date makes assistants less likely to trust and repeat the claim.", "medium"))

    # 2/3. corroboration
    if search_results and isinstance(search_results, dict) and search_results.get("claims"):
        for claim in search_results["claims"]:
            domains = claim.get("corroborating_domains", []) or []
            claim_text = claim.get("claim", "")
            if len(domains) == 0:
                findings.append(_finding(
                    nid(), f"Claim not corroborated elsewhere: \"{claim_text}\"", "high",
                    "Zero independent domains found stating this claim during agent-run "
                    "corroboration research.",
                    "Get this fact placed on independent, authoritative sources the brand doesn't "
                    "control (press coverage, directories, partner sites, Wikidata) — single-source "
                    "claims are the ones assistants are most likely to omit or hedge on.", "high"))
            elif len(domains) == 1:
                findings.append(_finding(
                    nid(), f"Claim weakly corroborated: \"{claim_text}\"", "low",
                    f"Only one independent domain ({domains[0]}) also states this claim.",
                    "Seek a second independent, credible source for this claim to strengthen "
                    "cross-source trust signals.", "low"))
    else:
        findings.append(_finding(
            nid(), "Corroboration research not performed for this run", "low",
            "No --search-results input was supplied, so cross-source agreement for this brand's "
            "key claims was not evaluated.",
            "Have the calling agent web-search 3-5 of the page's key factual claims (founding "
            "date, HQ, pricing, leadership) and re-run this check with --search-results to score "
            "corroboration.", "low"))

    # --- proactive suggestion (independent of any defect above) ---
    if best_dt is not None:
        findings.append(_proactive(
            nid(), "Consider a machine-readable dateModified in JSON-LD",
            f"A freshness signal was found ({source}, dated {best_dt.date()}), but it lives in "
            "a meta tag/visible text/HTTP header rather than structured data.",
            "In addition to what's already present, add 'dateModified' (and 'datePublished') to "
            "the page's Article/WebPage JSON-LD block — assistants that parse structured data "
            "directly get an unambiguous, typed timestamp instead of having to interpret text."))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: freshness_check.py <url> [--search-results file.json]", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    sr = None
    if "--search-results" in sys.argv:
        idx = sys.argv.index("--search-results")
        with open(sys.argv[idx + 1]) as f:
            sr = json.load(f)
    print(json.dumps(run_check(url, search_results=sr), indent=2))
