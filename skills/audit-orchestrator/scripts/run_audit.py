#!/usr/bin/env python3
"""
audit-orchestrator entrypoint.

Runs every sub-skill in the brand-ai-readiness-audit marketplace against a
target site and composes their findings into a single audit report.


Usage:
    python run_audit.py <url>
   
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.parse as up
from datetime import datetime, timezone

import requests


SKILLS_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
    )
)

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def _load(skill_name, script_name):
    path = os.path.join(
        SKILLS_DIR,
        skill_name,
        "scripts",
        script_name,
    )

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Skill script not found: {path}"
        )

    spec = importlib.util.spec_from_file_location(
        f"{skill_name}_{script_name}",
        path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Unable to load skill: {skill_name}/{script_name}"
        )

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod


def _run_safely(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)

        if result is None:
            result = []

        return result, None

    except Exception as exc:
        return [], str(exc)


def _error_finding(skill_id, error):
    return {
        "id": f"{skill_id[:2].upper()}-ERR",
        "category": "meta",
        "title": f"{skill_id} check failed to complete",
        "severity": "medium",
        "evidence": (
            f"Unhandled error while running {skill_id}: {error}"
        ),
        "suggested_action": {
            "summary": (
                f"Re-run the {skill_id} check and investigate the error "
                "before trusting the completeness of this audit."
            ),
            "priority": "medium",
        },
    }


def run_full_audit(
    url,
    timeout=5,
    max_links=8,
    max_pages=400,
    time_limit=120,
    search_results=None,
    output_path=None,
):
    # max_pages=None means "no page-count cap" — crawl as many pages as
    # the time_limit allows.  Callers may still pass an explicit integer
    # if they want an additional upper bound.
    if max_pages is None:
        max_pages = 10_000_000  # effectively unlimited

    start_time = time.monotonic()
    deadline = start_time + time_limit

    def remaining_time():
        return max(
            0,
            deadline - time.monotonic()
        )

    search_results = search_results or {}

    # ---------------------------------------------------------
    # Load skills
    # ---------------------------------------------------------

    crawl_mod = _load(
        "crawl-render-audit",
        "crawl_render_check.py",
    )

    sd_mod = _load(
        "structured-data-audit",
        "structured_data_check.py",
    )

    fe_mod = _load(
        "fact-extractability-audit",
        "fact_extractability_check.py",
    )

    fr_mod = _load(
        "freshness-corroboration-audit",
        "freshness_check.py",
    )

    ed_mod = _load(
        "entity-disambiguation-audit",
        "entity_check.py",
    )

    en_mod = _load(
        "engagement-audit",
        "engagement_check.py",
    )

    disc_mod = _load(
        "audit-orchestrator",
        "page_discovery.py",
    )

    all_findings = []
    checks_run = []
    check_errors = []

    # ---------------------------------------------------------
    # Site-level checks
    # ---------------------------------------------------------

    site_checks = [
        (
            "crawl-render-audit",
            crawl_mod.run_check,
            {
                "timeout": min(
                    timeout,
                    max(1, int(remaining_time()))
                )
            },
        ),
        (
            "freshness-corroboration-audit",
            fr_mod.run_check,
            {
                "timeout": min(
                    timeout,
                    max(1, int(remaining_time()))
                ),
                "search_results": search_results.get(
                    "freshness"
                ),
            },
        ),
        (
            "entity-disambiguation-audit",
            ed_mod.run_check,
            {
                "timeout": min(
                    timeout,
                    max(1, int(remaining_time()))
                ),
                "search_results": search_results.get(
                    "entity"
                ),
            },
        ),
        (
            "engagement-audit",
            en_mod.run_check,
            {
                "timeout": min(
                    timeout,
                    max(1, int(remaining_time()))
                ),
                "max_links_checked": max_links,
            },
        ),
    ]

    for skill_id, fn, kwargs in site_checks:

        if remaining_time() <= 0:
            check_errors.append({
                "skill": skill_id,
                "error": (
                    f"{time_limit}-second time limit reached; "
                    "site check skipped."
                ),
            })
            break

        checks_run.append(skill_id)

        findings, error = _run_safely(
            fn,
            url,
            **kwargs,
        )

        if error:
            check_errors.append({
                "skill": skill_id,
                "error": error,
            })

            all_findings.append(
                _error_finding(
                    skill_id,
                    error,
                )
            )

        elif isinstance(findings, list):
            all_findings.extend(findings)

    # ---------------------------------------------------------
    # Page discovery
    # ---------------------------------------------------------

    pages = [url]

    if remaining_time() > 0:

        try:

            homepage_timeout = max(
                1,
                min(
                    timeout,
                    int(remaining_time())
                )
            )

            homepage_resp, used_fallback_ua = (
                disc_mod._get_with_fallback(
                    url,
                    homepage_timeout,
                    min_bytes=500,
                )
            )

            if homepage_resp is None:
                raise requests.RequestException(
                    "Unable to fetch homepage."
                )

            homepage_html = homepage_resp.text or ""

            pages = disc_mod.discover_pages(
                url,
                homepage_html,
                max_pages=max_pages,
                timeout=homepage_timeout,
                deadline=deadline,
            )

            if not pages:
                pages = [url]

            if len(pages) == 1:

                fallback_message = ""

                if used_fallback_ua:
                    fallback_message = (
                        " even after retrying with a browser User-Agent"
                    )

                check_errors.append({
                    "skill": "page-discovery",
                    "error": (
                        "Only the homepage was audited — no additional "
                        "same-domain pages were discovered through "
                        "robots.txt/sitemap.xml/sitemap indexes or "
                        f"homepage links{fallback_message}. "
                        "This audit does not execute JavaScript."
                    ),
                })

        except requests.RequestException as exc:

            check_errors.append({
                "skill": "page-discovery",
                "error": str(exc),
            })

        except Exception as exc:

            check_errors.append({
                "skill": "page-discovery",
                "error": (
                    f"Unexpected page-discovery error: {exc}"
                ),
            })

    # ---------------------------------------------------------
    # Page-level checks
    # ---------------------------------------------------------

    page_level_checks = [
        (
            "structured-data-audit",
            sd_mod.run_check,
        ),
        (
            "fact-extractability-audit",
            fe_mod.run_check,
        ),
    ]

    # Tracks every page that completed at least one serial check.
    # The homepage always counts since site-level checks ran on it.
    pages_audited = {url}

    for skill_id, fn in page_level_checks:

        if remaining_time() <= 0:
            check_errors.append({
                "skill": skill_id,
                "error": (
                    f"{time_limit}-second time limit reached; "
                    "page-level check skipped."
                ),
            })
            break

        checks_run.append(skill_id)

        grouped = {}
        pages_checked = 0

        # -------------------------------------------------
        # Serial page checks — one page at a time so that
        # the time limit produces a natural, variable count.
        # -------------------------------------------------

        for page_url in pages:

            if remaining_time() <= 0:
                check_errors.append({
                    "skill": skill_id,
                    "error": (
                        f"{time_limit}-second time limit reached; "
                        "remaining pages were skipped."
                    ),
                })
                break

            page_timeout = max(
                1,
                min(
                    timeout,
                    int(remaining_time())
                )
            )

            findings, error = _run_safely(
                fn,
                page_url,
                timeout=page_timeout,
            )

            if error:
                check_errors.append({
                    "skill": skill_id,
                    "page": page_url,
                    "error": error,
                })
                continue

            pages_checked += 1

            # Record this page as successfully audited.
            pages_audited.add(page_url)

            if not isinstance(findings, list):
                continue

            for finding in findings:

                if not isinstance(
                    finding,
                    dict
                ):
                    continue

                title = finding.get(
                    "title",
                    "Unnamed finding",
                )

                bucket = grouped.setdefault(
                    title,
                    {
                        "finding": finding,
                        "pages": [],
                    },
                )

                bucket["pages"].append(
                    page_url
                )

        # -----------------------------------------------------
        # Aggregate findings
        # -----------------------------------------------------

        finding_number = 0

        for title, bucket in grouped.items():

            finding_number += 1

            finding = dict(
                bucket["finding"]
            )

            hit_pages = bucket["pages"]

            original_id = finding.get(
                "id",
                skill_id[:2].upper(),
            )

            original_id = original_id.split("-")[0]

            finding["id"] = (
                f"{original_id}-AGG-{finding_number:03d}"
            )

            finding["evidence"] = (
                f"{len(hit_pages)}/{pages_checked} pages checked "
                f"show this issue "
                f"(examples: {hit_pages[:3]}). "
                f"{finding.get('evidence', '')}"
            )

            severity = finding.get(
                "severity",
                "low",
            )

            if (
                severity != "info"
                and pages_checked >= 3
                and len(hit_pages) / pages_checked >= 0.8
            ):

                current_rank = SEVERITY_ORDER.get(
                    severity,
                    3,
                )

                bumped_rank = max(
                    current_rank - 1,
                    0,
                )

                reverse_severity = {
                    value: key
                    for key, value
                    in SEVERITY_ORDER.items()
                }

                bumped_severity = reverse_severity[
                    bumped_rank
                ]

                finding["severity"] = bumped_severity

                suggested_action = finding.get(
                    "suggested_action"
                )

                if isinstance(
                    suggested_action,
                    dict,
                ):
                    suggested_action[
                        "priority"
                    ] = bumped_severity

            all_findings.append(
                finding
            )

    # ---------------------------------------------------------
    # Sort findings
    # ---------------------------------------------------------

    all_findings.sort(
        key=lambda finding: SEVERITY_ORDER.get(
            finding.get(
                "severity",
                "low",
            ),
            3,
        )
    )

    # ---------------------------------------------------------
    # Count severities
    # ---------------------------------------------------------

    counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for finding in all_findings:

        severity = finding.get(
            "severity",
            "low",
        )

        if severity in counts:
            counts[severity] += 1

    # ---------------------------------------------------------
    # Proactive suggestions
    # ---------------------------------------------------------

    proactive_suggestions = []

    for finding in all_findings:

        if not finding.get("proactive"):
            continue

        suggested_action = finding.get(
            "suggested_action",
            {},
        )

        proactive_suggestions.append({
            "id": finding.get("id"),
            "title": finding.get("title"),
            "suggested_action": (
                suggested_action.get(
                    "summary",
                    "",
                )
                if isinstance(
                    suggested_action,
                    dict,
                )
                else ""
            ),
        })

    # ---------------------------------------------------------
    # Final report
    # ---------------------------------------------------------

    parsed_url = up.urlparse(url)

    site = (
        parsed_url.netloc
        or url
    )

    # Build the final ordered list of pages that were actually audited
    # within the time limit (serial crawling = natural variable count).
    pages_actually_sampled = [
        p for p in pages if p in pages_audited
    ] or [url]

    elapsed = time.monotonic() - start_time

    report = {
        "site": site,

        "audited_at": (
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),

        "summary": {
            "pages_crawled": len(pages_actually_sampled),
            "total_findings": len(all_findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "proactive_suggestions": len(
                proactive_suggestions
            ),
            "time_limit_seconds": time_limit,
            "execution_time_seconds": round(
                elapsed,
                2
            ),
        },

        "findings": all_findings,

        "proactive_suggestions": (
            proactive_suggestions
        ),

        "checks_run": checks_run,

        "pages_sampled": pages_actually_sampled,
    }

    if check_errors:
        report["check_errors"] = check_errors

    if output_path:

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as report_file:

            json.dump(
                report,
                report_file,
                indent=2,
                ensure_ascii=False,
            )

    return report


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run the full Brand AI Readiness audit "
            "against a website."
        )
    )

    parser.add_argument(
        "url",
        help=(
            "Website URL to audit, "
            "e.g. https://example.com"
        ),
    )

    parser.add_argument(
        "--output",
        default="audit_report.json",
        help=(
            "Path to write the JSON report "
            "(default: audit_report.json)"
        ),
    )

    parser.add_argument(
        "--search-results",
        default=None,
        help=(
            "Optional JSON file containing "
            "agent-gathered search corroboration."
        ),
    )

    parser.add_argument(
        "--max-links",
        type=int,
        default=8,
        help=(
            "Maximum internal links sampled "
            "by the engagement check."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help=(
            "HTTP request timeout in seconds "
            "(default: 5)."
        ),
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=400,
        help=(
            "Maximum pages sampled "
            "(default: 400)."
        ),
    )

    parser.add_argument(
        "--time-limit",
        type=int,
        default=120,
        help=(
            "Maximum audit time in seconds "
            "(default: 120)."
        ),
    )

    args = parser.parse_args()

    if not args.url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        args.url = (
            "https://"
            + args.url
        )

    if args.max_links < 1:
        parser.error(
            "--max-links must be at least 1"
        )

    if args.max_pages < 1:
        parser.error(
            "--max-pages must be at least 1"
        )

    if args.timeout < 1:
        parser.error(
            "--timeout must be at least 1"
        )

    if args.time_limit < 1:
        parser.error(
            "--time-limit must be at least 1"
        )

    search_results = None

    if args.search_results:

        with open(
            args.search_results,
            "r",
            encoding="utf-8",
        ) as search_file:

            search_results = json.load(
                search_file
            )

    report = run_full_audit(
        args.url,
        timeout=args.timeout,
        max_links=args.max_links,
        max_pages=args.max_pages,
        time_limit=args.time_limit,
        search_results=search_results,
        output_path=args.output,
    )

    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        f"\nAudit report written to: {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

