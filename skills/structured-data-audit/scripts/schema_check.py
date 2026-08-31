#!/usr/bin/env python3
"""
schema_check.py — deterministic structured-data checks for the structured-data-audit skill.

Contract (matches audit-orchestrator/scripts/report_builder.py raw-finding schema):
  Each finding is a dict:
    {
      "id_hint": str, "title": str, "severity": "critical"|"high"|"medium"|"low",
      "evidence": str, "suggested_action": str,
      "dedupe_key": "structured-data:<id_hint>",
      "source_skill": "structured-data-audit",
      "proactive": bool,
    }

Usage:
  python schema_check.py <url> [--pages <path> <path> ...] --out <raw_findings.json>

What it checks (see SKILL.md for full rationale):
  1. JSON-LD presence          — any <script type="application/ld+json"> at all?
  2. JSON-LD validity          — does each block parse as valid JSON?
  3. Required top-level keys   — @context and @type present on every JSON-LD node?
  4. Type-specific completeness — for common types (Article, Product, Organization,
     FAQPage, BreadcrumbList, Event), are the fields Google/major consumers treat as
     required or strongly recommended present?
  5. Duplicate conflicting @type — same node declares contradictory unrelated types?
  6. Microdata fallback         — if no JSON-LD found, is there at least itemscope/
     itemtype microdata, so the page isn't emitting zero structured data at all?
  7. Broken self-referential URLs — url/@id/image fields that are non-absolute or
     empty strings (a common authoring mistake), checked for form only, not fetched.

Design notes:
  - Pure functions on already-parsed HTML/JSON so they're unit-testable offline.
  - Every evidence string is a literal excerpt of the offending JSON-LD/microdata,
    never a paraphrase.
  - No network calls beyond fetching the page itself — image/URL fields are checked
    for syntactic validity only, not dereferenced, keeping this skill fast and
    within the read-only guardrail (no probing third-party asset URLs).
"""

import argparse
import json
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SKILL_NAME = "structured-data-audit"
USER_AGENT = "AuditBot/1.0 (+structured-data-audit skill; read-only)"
REQUEST_TIMEOUT = 10

# Minimal required/strongly-recommended fields per common schema.org type.
# Deliberately conservative: only fields that major consumers (Google Rich
# Results, generic LLM-agent parsers) treat as load-bearing for that type.
TYPE_REQUIRED_FIELDS = {
    "Article": ["headline", "datePublished"],
    "NewsArticle": ["headline", "datePublished"],
    "BlogPosting": ["headline", "datePublished"],
    "Product": ["name"],
    "Organization": ["name"],
    "LocalBusiness": ["name", "address"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "Event": ["name", "startDate"],
    "Recipe": ["name", "recipeIngredient", "recipeInstructions"],
}

# Recommended-but-not-required fields, checked at lower severity.
TYPE_RECOMMENDED_FIELDS = {
    "Article": ["author", "image", "dateModified"],
    "NewsArticle": ["author", "image", "dateModified"],
    "BlogPosting": ["author", "image", "dateModified"],
    "Product": ["image", "description", "offers"],
    "Organization": ["url", "logo"],
    "LocalBusiness": ["telephone"],
    "Event": ["location", "endDate"],
}

KNOWN_SCHEMA_TYPES = set(TYPE_REQUIRED_FIELDS) | set(TYPE_RECOMMENDED_FIELDS) | {
    "WebSite", "WebPage", "Person", "ImageObject", "Offer", "AggregateOffer",
    "PostalAddress", "Review", "AggregateRating", "VideoObject", "HowTo",
    "ItemList", "ListItem", "SearchAction", "ContactPoint",
}


def _finding(id_hint, title, severity, evidence, suggested_action, proactive=False):
    return {
        "id_hint": id_hint,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "dedupe_key": f"structured-data:{id_hint}",
        "source_skill": SKILL_NAME,
        "proactive": proactive,
    }


def _short(obj, n=180):
    s = json.dumps(obj) if not isinstance(obj, str) else obj
    return s if len(s) <= n else s[:n] + "..."


# ---------------------------------------------------------------------------
# Pure check functions
# ---------------------------------------------------------------------------

def extract_jsonld_blocks(soup, page_url):
    """Returns (parsed_nodes, parse_error_findings). Flattens @graph and lists."""
    nodes = []
    findings = []
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})

    if not scripts:
        return nodes, findings, 0

    for i, script in enumerate(scripts):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            findings.append(_finding(
                "empty-jsonld-block", "Empty JSON-LD script block", "low",
                f"{page_url}: <script type=\"application/ld+json\"> block #{i+1} has no content.",
                "Remove the empty JSON-LD block or populate it with real structured data.",
            ))
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(_finding(
                "invalid-jsonld-syntax", "JSON-LD block fails to parse", "high",
                f"{page_url}: block #{i+1} raised {exc.__class__.__name__}: {exc}. "
                f"Content starts: {_short(raw.strip(), 120)}",
                "Fix the JSON syntax error — a malformed JSON-LD block is silently "
                "ignored by every consumer (search engines, AI agents), so the "
                "structured data it was meant to provide is effectively absent.",
            ))
            continue

        # Normalize: could be a dict, a list of dicts, or a dict with @graph
        candidates = []
        if isinstance(parsed, list):
            candidates = parsed
        elif isinstance(parsed, dict) and "@graph" in parsed and isinstance(parsed["@graph"], list):
            candidates = parsed["@graph"]
        elif isinstance(parsed, dict):
            candidates = [parsed]

        for node in candidates:
            if isinstance(node, dict):
                nodes.append(node)

    return nodes, findings, len(scripts)


def check_context_and_type(nodes, page_url):
    findings = []
    for i, node in enumerate(nodes):
        if "@context" not in node:
            findings.append(_finding(
                "missing-context", "JSON-LD node missing @context", "medium",
                f"{page_url}: node #{i+1} ({_short(node.get('@type', 'unknown type'))}) "
                f"has no \"@context\" key.",
                "Add \"@context\": \"https://schema.org\" to every top-level JSON-LD "
                "node — without it, consumers cannot reliably resolve the vocabulary "
                "the type names refer to.",
            ))
        if "@type" not in node:
            findings.append(_finding(
                "missing-type", "JSON-LD node missing @type", "high",
                f"{page_url}: node #{i+1} has keys {list(node.keys())[:6]} but no \"@type\".",
                "Add an explicit \"@type\" (e.g. \"Article\", \"Product\") — without it "
                "the node is unusable structured data; consumers can't tell what "
                "kind of entity it describes.",
            ))
    return findings


def check_type_completeness(nodes, page_url):
    findings = []
    for i, node in enumerate(nodes):
        raw_type = node.get("@type")
        if raw_type is None:
            continue
        types = raw_type if isinstance(raw_type, list) else [raw_type]

        for t in types:
            if not isinstance(t, str):
                continue
            required = TYPE_REQUIRED_FIELDS.get(t)
            if required:
                missing = [f for f in required if f not in node or node[f] in (None, "", [])]
                if missing:
                    findings.append(_finding(
                        f"missing-required-fields-{t.lower()}",
                        f"{t} node missing required field(s): {', '.join(missing)}",
                        "high",
                        f"{page_url}: node #{i+1} declares @type=\"{t}\" but is "
                        f"missing {missing}. Present keys: {list(node.keys())[:8]}",
                        f"Add {missing} to this {t} node — these are the fields major "
                        f"structured-data consumers (search rich results, AI page "
                        f"summarizers) treat as load-bearing for {t}; without them the "
                        f"markup is present but functionally incomplete.",
                    ))

            recommended = TYPE_RECOMMENDED_FIELDS.get(t)
            if recommended:
                missing_rec = [f for f in recommended if f not in node or node[f] in (None, "", [])]
                if missing_rec:
                    findings.append(_finding(
                        f"missing-recommended-fields-{t.lower()}",
                        f"{t} node missing recommended field(s): {', '.join(missing_rec)}",
                        "low",
                        f"{page_url}: node #{i+1} (@type=\"{t}\") omits recommended "
                        f"field(s) {missing_rec}.",
                        f"Consider adding {missing_rec} — not required, but strengthens "
                        f"how completely this {t} node is understood by consumers.",
                    ))
    return findings


def check_unknown_types(nodes, page_url):
    findings = []
    unknown_seen = set()
    for node in nodes:
        raw_type = node.get("@type")
        if raw_type is None:
            continue
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        for t in types:
            if isinstance(t, str) and t not in KNOWN_SCHEMA_TYPES and t not in unknown_seen:
                # Only flag if it doesn't look like a namespaced/custom extension
                # (heuristic: schema.org types are single CamelCase words).
                if re.fullmatch(r"[A-Z][A-Za-z0-9]*", t):
                    unknown_seen.add(t)
    if unknown_seen:
        findings.append(_finding(
            "unrecognized-schema-type", "Unrecognized schema.org @type used", "low",
            f"{page_url}: type(s) not in this skill's known-type list: "
            f"{sorted(unknown_seen)}.",
            "Verify these @type values against https://schema.org/docs/full.html — "
            "either they're a valid but less-common type this skill doesn't track "
            "(no action needed), or a typo that silently produces unrecognized markup.",
            proactive=True,
        ))
    return findings


def check_conflicting_types(nodes, page_url):
    """Flags a node whose @type list mixes clearly unrelated top-level entities,
    e.g. ["Product", "Person"] — a common copy-paste authoring mistake."""
    unrelated_groups = [
        {"Product", "Person", "Organization", "Event", "Recipe"},
    ]
    findings = []
    for i, node in enumerate(nodes):
        raw_type = node.get("@type")
        if not isinstance(raw_type, list) or len(raw_type) < 2:
            continue
        for group in unrelated_groups:
            hits = [t for t in raw_type if t in group]
            if len(hits) > 1:
                findings.append(_finding(
                    "conflicting-types", "Node declares multiple unrelated @type values",
                    "medium",
                    f"{page_url}: node #{i+1} declares @type={raw_type}, mixing "
                    f"unrelated top-level entities {hits}.",
                    "Split this into separate JSON-LD nodes, one per entity — a "
                    "single node claiming to be both e.g. a Product and a Person "
                    "is contradictory and consumers may discard it entirely.",
                ))
    return findings


def check_no_structured_data(nodes, soup, page_url, jsonld_script_count):
    """If there's zero JSON-LD, check for microdata as a fallback signal before
    concluding the page has no structured data at all."""
    if nodes or jsonld_script_count > 0:
        return []
    microdata_items = soup.find_all(attrs={"itemscope": True})
    if microdata_items:
        return []  # has microdata fallback, not a total absence
    return [_finding(
        "no-structured-data", "No structured data (JSON-LD or microdata) found",
        "medium",
        f"{page_url}: no <script type=\"application/ld+json\"> blocks and no "
        f"itemscope/itemtype microdata attributes found anywhere in the document.",
        "Add JSON-LD structured data appropriate to this page's content type "
        "(Article, Product, Organization, etc.) — without it, search engines and "
        "AI agents must infer the page's meaning from unstructured text alone.",
    )]


def check_broken_url_fields(nodes, page_url):
    """Syntactic check only — does not dereference the URL over the network."""
    url_like_keys = {"url", "image", "logo", "@id", "sameAs"}
    findings = []
    seen = set()
    for node in nodes:
        for key in url_like_keys & node.keys():
            values = node[key] if isinstance(node[key], list) else [node[key]]
            for v in values:
                if not isinstance(v, str):
                    continue
                if key == "image" and isinstance(node[key], dict):
                    continue
                if v.strip() == "":
                    finding_id = f"empty-url-field-{key}"
                    if finding_id in seen:
                        continue
                    seen.add(finding_id)
                    findings.append(_finding(
                        finding_id, f"Empty string in \"{key}\" field", "low",
                        f"{page_url}: a JSON-LD node has \"{key}\": \"\" (empty string).",
                        f"Remove the \"{key}\" field entirely if there's no real value, "
                        f"rather than leaving it as an empty string.",
                    ))
                elif not v.startswith(("http://", "https://", "//")) and key in ("url", "logo", "@id"):
                    finding_id = f"non-absolute-url-{key}"
                    if finding_id in seen:
                        continue
                    seen.add(finding_id)
                    findings.append(_finding(
                        finding_id, f"Non-absolute URL in \"{key}\" field", "medium",
                        f"{page_url}: \"{key}\": \"{v}\" is not an absolute URL "
                        f"(missing scheme/host).",
                        f"Use a full absolute URL (https://...) for \"{key}\" — "
                        f"relative paths in structured data are ambiguous to "
                        f"off-page consumers that don't know the page's base URL.",
                    ))
    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def audit_page(url, session):
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return [_finding(
            "page-unreachable", "Page could not be fetched", "critical",
            f"{url}: request failed with {exc.__class__.__name__}: {exc}",
            "Confirm the URL is correct and the server is reachable; an "
            "unreachable page blocks every structured-data check.",
        )]

    if resp.status_code >= 400:
        return [_finding(
            "page-error-status", f"Page returned HTTP {resp.status_code}", "critical",
            f"{url}: server responded with status {resp.status_code}.",
            "Fix the underlying error before structured data on this page can "
            "be evaluated at all.",
        )]

    soup = BeautifulSoup(resp.text, "html.parser")
    nodes, parse_findings, script_count = extract_jsonld_blocks(soup, url)

    findings = list(parse_findings)
    findings += check_no_structured_data(nodes, soup, url, script_count)
    findings += check_context_and_type(nodes, url)
    findings += check_type_completeness(nodes, url)
    findings += check_conflicting_types(nodes, url)
    findings += check_unknown_types(nodes, url)
    findings += check_broken_url_fields(nodes, url)

    return findings


def run_audit(base_url, pages=None):
    session = requests.Session()
    pages = pages or [base_url]
    all_findings = []
    for page_url in pages:
        all_findings.extend(audit_page(page_url, session))
    return all_findings


def main():
    parser = argparse.ArgumentParser(description="structured-data-audit: schema_check.py")
    parser.add_argument("url", help="Base URL of the site being audited")
    parser.add_argument("--pages", nargs="*", default=None,
                         help="Specific page URLs to sample (defaults to just the base URL)")
    parser.add_argument("--out", required=True, help="Path to write raw findings JSON")
    args = parser.parse_args()

    try:
        findings = run_audit(args.url, args.pages)
    except Exception as exc:
        print(f"structured-data-audit schema_check.py FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w") as f:
        json.dump(findings, f, indent=2)

    print(f"structured-data-audit: wrote {len(findings)} finding(s) to {args.out}")


if __name__ == "__main__":
    main()