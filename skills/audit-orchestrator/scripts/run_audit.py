#!/usr/bin/env python3
"""
audit-orchestrator entrypoint.

Runs every sub-skill in the brand-ai-readiness-audit marketplace against a
target URL and composes their findings into a single audit report matching
the contest's required schema.

Usage:
    python run_audit.py <url> [--output report.json]
                              [--search-results search_results.json]
                              [--max-links 8] [--timeout 15]

`search_results.json` (optional) feeds the freshness-corroboration-audit and
entity-disambiguation-audit skills with web-search evidence the calling agent
gathered (see those skills' SKILL.md). Shape:
{
  "freshness": {"claims": [{"claim": "...", "corroborating_domains": [...]}]},
  "entity": {"name_collision_count": 0, "examples": []}
}
"""
import sys
import os
import json
import argparse
import importlib.util
import urllib.parse as up
from datetime import datetime, timezone

SKILLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _load(skill_name, script_name):
    path = os.path.join(SKILLS_DIR, skill_name, "scripts", script_name)
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{script_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_safely(check_id, fn, *args, **kwargs):
    try:
        res = fn(*args, **kwargs)
        if isinstance(res, dict):
            return res.get("findings", []), res.get("pages_crawled", 1), res.get("words_analyzed", 0), res.get("sampled_urls", []), None
        elif isinstance(res, list):
            return res, 1, 0, [], None
        return [], 1, 0, [], None
    except Exception as e:  # noqa: BLE001 - deliberately broad so one bad check doesn't kill the audit
        return [], 0, 0, [], str(e)


def run_full_audit(url, timeout=15, max_links=8, search_results=None, output_path=None):
    search_results = search_results or {}

    crawl_mod = _load("crawl-render-audit", "crawl_render_check.py")
    sd_mod = _load("structured-data-audit", "structured_data_check.py")
    fe_mod = _load("fact-extractability-audit", "fact_extractability_check.py")
    fr_mod = _load("freshness-corroboration-audit", "freshness_check.py")
    ed_mod = _load("entity-disambiguation-audit", "entity_check.py")
    en_mod = _load("engagement-audit", "engagement_check.py")

    all_findings = []
    checks_run = []
    check_errors = []
    max_pages_crawled = 1
    total_words_analyzed = 0
    all_sampled_urls = [url]

    checks = [
        ("crawl-render-audit", crawl_mod.run_check, {"timeout": timeout}),
        ("structured-data-audit", sd_mod.run_check, {"timeout": timeout}),
        ("fact-extractability-audit", fe_mod.run_check, {"timeout": timeout}),
        ("freshness-corroboration-audit", fr_mod.run_check,
         {"timeout": timeout, "search_results": search_results.get("freshness")}),
        ("entity-disambiguation-audit", ed_mod.run_check,
         {"timeout": timeout, "search_results": search_results.get("entity")}),
        ("engagement-audit", en_mod.run_check, {"timeout": timeout, "max_links_checked": max_links}),
    ]

    for skill_id, fn, kwargs in checks:
        findings, pages_count, words_count, sampled_urls, error = _run_safely(skill_id, fn, url, **kwargs)
        checks_run.append(skill_id)
        if pages_count > max_pages_crawled:
            max_pages_crawled = pages_count
        if words_count > total_words_analyzed:
            total_words_analyzed = words_count
        if sampled_urls:
            for s_url in sampled_urls:
                if s_url not in all_sampled_urls:
                    all_sampled_urls.append(s_url)

        if error:
            check_errors.append({"skill": skill_id, "error": error})
            all_findings.append({
                "id": f"{skill_id[:2].upper()}-ERR",
                "category": "meta",
                "title": f"{skill_id} check failed to complete",
                "severity": "medium",
                "evidence": f"Unhandled error while running {skill_id}: {error}",
                "suggested_action": {
                    "summary": f"Re-run the {skill_id} check; investigate the error before trusting "
                                "the completeness of this audit for that concern area.",
                    "priority": "medium",
                },
            })
        else:
            all_findings.extend(findings)

    site = up.urlparse(url).netloc or url

    # Dynamic Proactive Recommendations Engine (based on actual website signals)
    proactive_n = 0
    def pro_id():
        nonlocal proactive_n
        proactive_n += 1
        return f"PRO-{proactive_n:03d}"

    # 1. Dynamic Breadcrumb Opportunity
    deep_paths = [up.urlparse(u).path for u in all_sampled_urls if len(up.urlparse(u).path.strip("/").split("/")) >= 2]
    has_breadcrumb_finding = any("breadcrumb" in f.get("title", "").lower() or "breadcrumb" in f.get("evidence", "").lower() for f in all_findings)
    if deep_paths and not has_breadcrumb_finding:
        sample_path = deep_paths[0]
        all_findings.append({
            "id": pro_id(),
            "category": "discoverability",
            "title": "Proactive Opportunity: Implement BreadcrumbList JSON-LD for Site Hierarchy",
            "severity": "low",
            "evidence": f"Deep subpages detected (e.g. '{sample_path}'), but no schema.org BreadcrumbList markup was found across {len(all_sampled_urls)} sampled URLs.",
            "suggested_action": {
                "summary": f"Add BreadcrumbList JSON-LD schema on subpages like '{sample_path}' — this establishes explicit site architecture relationships for crawlers and AI search agents.",
                "priority": "low"
            }
        })

    # 2. Dynamic Voice AI / Speakable Specification Opportunity
    if total_words_analyzed > 300:
        has_speakable = any("speakable" in f.get("evidence", "").lower() for f in all_findings)
        if not has_speakable:
            all_findings.append({
                "id": pro_id(),
                "category": "discoverability",
                "title": "Proactive Opportunity: Add Speakable Specification for Voice AI Assistants",
                "severity": "low",
                "evidence": f"Site contains substantial readable content (~{total_words_analyzed} words analyzed), but lacks schema.org/Speakable specification.",
                "suggested_action": {
                    "summary": "Add 'speakable' JSON-LD markup or CSS selector attributes pointing to your primary 1-2 sentence brand summary — this guides voice assistants (ChatGPT Voice, Siri, Google Assistant) to quote exact text.",
                    "priority": "low"
                }
            })

    # 3. Dynamic Site Search Action Opportunity
    if len(all_sampled_urls) >= 3:
        has_search_action = any("searchaction" in f.get("evidence", "").lower() or "potentialaction" in f.get("evidence", "").lower() for f in all_findings)
        if not has_search_action:
            all_findings.append({
                "id": pro_id(),
                "category": "discoverability",
                "title": "Proactive Opportunity: Add SearchAction PotentialAction Schema",
                "severity": "low",
                "evidence": f"Multi-page site structure detected ({len(all_sampled_urls)} sampled pages), but no WebSite SearchAction schema was found.",
                "suggested_action": {
                    "summary": f"Add WebSite schema with potentialAction (SearchAction) pointing to '{site}/search?q={{search_term_string}}' to enable direct AI in-site query delegation.",
                    "priority": "low"
                }
            })

    # 4. Dynamic Wikidata Identity Anchor Opportunity
    has_wikidata = any("sameas" in f.get("title", "").lower() or "wikidata" in f.get("evidence", "").lower() for f in all_findings)
    if not has_wikidata:
        all_findings.append({
            "id": pro_id(),
            "category": "discoverability",
            "title": "Proactive Opportunity: Link Entity to Wikidata/Wikipedia via sameAs",
            "severity": "low",
            "evidence": f"No official Wikidata or Wikipedia sameAs identity link detected in Organization markup for {site}.",
            "suggested_action": {
                "summary": f"Include official Wikidata and Wikipedia URLs inside the Organization sameAs JSON-LD array for '{site}' to eliminate entity ambiguity across LLM knowledge bases.",
                "priority": "low"
            }
        })

    all_findings.sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 3))

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in all_findings:
        sev = f.get("severity", "low")
        if sev in counts:
            counts[sev] += 1

    report = {
        "site": site,
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "total_findings": len(all_findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "pages_crawled": max_pages_crawled,
            "total_words_analyzed": total_words_analyzed,
            "sampled_urls": all_sampled_urls,
        },
        "findings": all_findings,
        "checks_run": checks_run,
    }
    if check_errors:
        report["check_errors"] = check_errors

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    return report


def main():
    p = argparse.ArgumentParser(description="Run the full brand AI-readiness audit against a URL.")
    p.add_argument("url", help="Website URL to audit, e.g. https://example.com")
    p.add_argument("--output", default="audit_report.json", help="Path to write the JSON report")
    p.add_argument("--search-results", default=None,
                    help="Optional JSON file with agent-gathered web-search corroboration evidence")
    p.add_argument("--max-links", type=int, default=8, help="Internal links sampled for breakage check")
    p.add_argument("--timeout", type=int, default=15, help="HTTP request timeout in seconds")
    args = p.parse_args()

    if not args.url.startswith(("http://", "https://")):
        args.url = "https://" + args.url

    search_results = None
    if args.search_results:
        with open(args.search_results) as f:
            search_results = json.load(f)

    report = run_full_audit(
        args.url, timeout=args.timeout, max_links=args.max_links,
        search_results=search_results, output_path=args.output,
    )
    print(json.dumps(report, indent=2))
    print(f"\nReport written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
