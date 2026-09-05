#!/usr/bin/env python3
"""entity-disambiguation-audit: sameAs coverage, name-ambiguity risk, basic NAP consistency."""
import sys
import json
import re

import requests
from bs4 import BeautifulSoup

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
DISAMBIGUATING_HOSTS = ["wikipedia.org", "wikidata.org", "linkedin.com", "crunchbase.com"]
PHONE_RE = re.compile(r"(\+?\d[\d\-\.\s\(\)]{7,}\d)")

try:
    import enchant  # optional dictionary check; not required
    _DICT = enchant.Dict("en_US")
except Exception:
    _DICT = None

COMMON_WORDS_FALLBACK = {
    "apple", "shell", "amazon", "target", "delta", "united", "current", "square",
    "block", "meta", "arm", "wave", "spring", "orange", "mint",
}


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


def _extract_org_jsonld(soup):
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or s.get_text() or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        flat = []
        for item in items:
            if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                flat.extend(item["@graph"])
            elif isinstance(item, dict):
                flat.append(item)
        for item in flat:
            t = item.get("@type", "")
            t = t.lower() if isinstance(t, str) else " ".join(x.lower() for x in t if isinstance(x, str))
            if "organization" in t or "localbusiness" in t:
                return item
    return None


def run_check(url, timeout=15, search_results=None):
    findings = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"ED-{n:03d}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException as e:
        return [_finding(nid(), "Page unreachable for entity check", "critical",
                          f"Request error: {e}", "Fix connectivity/availability before auditing.",
                          "critical")]

    soup = BeautifulSoup(r.text, "lxml")
    org = _extract_org_jsonld(soup)

    name = None
    if org:
        name = org.get("name")
    if not name:
        og_site = soup.find("meta", property="og:site_name")
        name = og_site.get("content") if og_site else None
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True) if title else None

    same_as = (org.get("sameAs") if org else None) or []
    if isinstance(same_as, str):
        same_as = [same_as]
    disambiguating_links = [u for u in same_as if any(h in u for h in DISAMBIGUATING_HOSTS)]

    ambiguity_risk = False
    reason = ""
    if name:
        stripped = re.sub(r"[^a-zA-Z]", "", name).lower()
        if len(stripped) <= 4:
            ambiguity_risk = True
            reason = f"short name ({name!r})"
        elif _DICT and _DICT.check(stripped):
            ambiguity_risk = True
            reason = f"name ({name!r}) is a common dictionary word"
        elif stripped in COMMON_WORDS_FALLBACK:
            ambiguity_risk = True
            reason = f"name ({name!r}) is a common/generic word"

    collision_count = 0
    collision_examples = []
    if search_results:
        collision_count = search_results.get("name_collision_count", 0)
        collision_examples = search_results.get("examples", [])

    if not org:
        findings.append(_finding(
            nid(), "No Organization/LocalBusiness entity markup to anchor identity", "medium",
            "No schema.org Organization or LocalBusiness JSON-LD block found.",
            "Add an Organization JSON-LD block with name, url, logo, and sameAs — without it there "
            "is no machine-readable anchor for 'who this brand is' at all.", "medium"))
    elif not disambiguating_links:
        severity = "high" if (ambiguity_risk or collision_count >= 2) else "medium"
        evidence = f"Organization JSON-LD has no sameAs entries linking to {DISAMBIGUATING_HOSTS}."
        if ambiguity_risk:
            evidence += f" Elevated risk: {reason}."
        if collision_count:
            evidence += f" Agent research found {collision_count} other entities sharing this " \
                         f"name (e.g. {collision_examples[:2]})."
        findings.append(_finding(
            nid(), "No disambiguating sameAs links on the brand entity", severity, evidence,
            "Add sameAs links to the brand's Wikipedia/Wikidata entry (create one if none exists "
            "and the brand is notable enough), and official LinkedIn/Crunchbase profiles — this is "
            "the single strongest signal for telling assistants 'this is the specific entity you "
            "mean, not the other one with the same name'.", "high" if severity == "high" else "medium"))

    if collision_count >= 2 and disambiguating_links:
        findings.append(_finding(
            nid(), "Name collisions exist despite some disambiguation signals", "medium",
            f"Agent research found {collision_count} other entities sharing this name "
            f"(e.g. {collision_examples[:2]}), though sameAs links are present.",
            "Consider a more distinctive on-page description clarifying industry/category early "
            "in the content, in addition to existing sameAs links, to reduce residual confusion.",
            "medium"))

    # basic NAP consistency: compare phone in footer text vs JSON-LD telephone
    jsonld_phone = org.get("telephone") if org else None
    footer = soup.find("footer")
    footer_text = footer.get_text(" ") if footer else ""
    footer_phone_match = PHONE_RE.search(footer_text)
    if jsonld_phone and footer_phone_match:
        norm = lambda s: re.sub(r"\D", "", s)
        if norm(jsonld_phone) and norm(footer_phone_match.group(1)) and \
           norm(jsonld_phone)[-7:] != norm(footer_phone_match.group(1))[-7:]:
            findings.append(_finding(
                nid(), "Phone number inconsistent between footer and structured data", "medium",
                f"JSON-LD telephone={jsonld_phone!r} vs footer text contains {footer_phone_match.group(1)!r}.",
                "Reconcile the phone number so structured data and visible text agree — "
                "inconsistent NAP data is a classic corroboration/trust red flag.", "medium"))

    # --- proactive suggestion (independent of any defect above) ---
    if disambiguating_links:
        missing_hosts = [h for h in DISAMBIGUATING_HOSTS if not any(h in u for u in disambiguating_links)]
        if missing_hosts:
            findings.append(_proactive(
                nid(), "sameAs coverage could be broadened",
                f"Disambiguating sameAs links present ({disambiguating_links}), but none reference: "
                f"{missing_hosts}.",
                "Beyond what's already linked, add sameAs entries for the remaining well-known "
                "profile types where they exist for this brand — more independent, authoritative "
                "anchors make entity resolution more robust, not just 'present or absent'."))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: entity_check.py <url> [--search-results file.json]", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    sr = None
    if "--search-results" in sys.argv:
        idx = sys.argv.index("--search-results")
        with open(sys.argv[idx + 1]) as f:
            sr = json.load(f)
    print(json.dumps(run_check(url, search_results=sr), indent=2))
