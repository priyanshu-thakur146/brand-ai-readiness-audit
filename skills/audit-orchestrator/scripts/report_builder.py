#!/usr/bin/env python3
"""report_builder.py — Merge specialist findings into one consolidated report.

Usage:
    python report_builder.py <findings_json_file> [<findings_json_file> ...]
    python report_builder.py --stdin           # read JSON array from stdin
    python report_builder.py --test            # run with built-in sample data

Each input file (or stdin) must contain JSON with a "findings" array.

Outputs a single consolidated JSON report to stdout matching the schema:
{
    "site": "...",
    "audited_at": "...",
    "summary": { "total_findings": N, "critical": N, "high": N, "medium": N, "low": N, "info": N },
    "findings": [ ... ]
}
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _sev_key(finding: dict) -> tuple[int, int]:
    sev = _SEVERITY_ORDER.get(finding.get("severity", "info"), 4)
    pri = _PRIORITY_ORDER.get(
        (finding.get("suggested_action") or {}).get("priority", "low"), 2
    )
    return (sev, pri)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _fingerprint(finding: dict) -> str:
    """Create a content-based fingerprint for deduplication."""
    parts = [
        finding.get("title", "").lower().strip(),
        finding.get("category", "").lower().strip(),
        finding.get("severity", "").lower().strip(),
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def deduplicate(findings: list[dict]) -> list[dict]:
    """Remove findings with identical fingerprints, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[dict] = []
    for f in findings:
        fp = _fingerprint(f)
        if fp not in seen:
            seen.add(fp)
            unique.append(f)
    return unique


# ---------------------------------------------------------------------------
# ID assignment
# ---------------------------------------------------------------------------


def assign_ids(findings: list[dict]) -> list[dict]:
    """Assign sequential IDs (F-001, F-002, ...) to findings."""
    for i, f in enumerate(findings, start=1):
        f["id"] = f"F-{i:03d}"
    return findings


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def build_summary(findings: list[dict]) -> dict:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
    return {"total_findings": len(findings), **counts}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def build_report(
    findings: list[dict],
    *,
    site: str = "",
    audited_at: str | None = None,
    pages_sampled: list[str] | None = None,
) -> dict:
    """Build the final consolidated audit report."""
    # Normalise severity values
    for f in findings:
        f["severity"] = f.get("severity", "info").lower()
        if f["severity"] not in _SEVERITY_ORDER:
            f["severity"] = "info"

    # Deduplicate
    findings = deduplicate(findings)

    # Sort by severity (critical first) then priority
    findings.sort(key=_sev_key)

    # Assign IDs
    findings = assign_ids(findings)

    # Build
    report = {
        "site": site,
        "audited_at": audited_at or datetime.now(timezone.utc).isoformat(),
        "summary": build_summary(findings),
        "findings": findings,
    }

    if pages_sampled is not None:
        report["pages_sampled"] = pages_sampled
        report["summary"]["pages_crawled"] = len(pages_sampled)

    return report


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def load_findings_from_files(
    paths: list[str],
) -> tuple[list[dict], str, list[str]]:
    """Load findings and sampled pages from multiple JSON files."""
    all_findings: list[dict] = []
    site = ""
    pages_sampled: list[str] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            all_findings.extend(data.get("findings", []))
            if not site and data.get("url"):
                parsed = urlparse(data["url"])
                site = parsed.netloc or data["url"]
            for page in data.get("pages_sampled", []):
                if page not in pages_sampled:
                    pages_sampled.append(page)
        elif isinstance(data, list):
            all_findings.extend(data)
    return all_findings, site, pages_sampled


def load_findings_from_stdin() -> tuple[list[dict], str, list[str]]:
    """Load findings from stdin JSON."""
    raw = sys.stdin.read()
    data = json.loads(raw)
    if isinstance(data, dict):
        site = ""
        pages_sampled = data.get("pages_sampled", [])
        if data.get("url"):
            parsed = urlparse(data["url"])
            site = parsed.netloc or data["url"]
        return data.get("findings", []), site, pages_sampled
    elif isinstance(data, list):
        # Could be array of result objects or array of findings
        all_findings: list[dict] = []
        site = ""
        pages_sampled: list[str] = []
        for item in data:
            if isinstance(item, dict) and "findings" in item:
                all_findings.extend(item["findings"])
                if not site and item.get("url"):
                    parsed = urlparse(item["url"])
                    site = parsed.netloc or item["url"]
                for page in item.get("pages_sampled", []):
                    if page not in pages_sampled:
                        pages_sampled.append(page)
            elif isinstance(item, dict):
                all_findings.append(item)
        return all_findings, site, pages_sampled
    return [], "", []


# ---------------------------------------------------------------------------
# Sample / test data
# ---------------------------------------------------------------------------

_SAMPLE_FINDINGS = [
    {
        "title": "Broad crawl block for *",
        "severity": "critical",
        "category": "crawl-render",
        "evidence": "robots.txt contains 'Disallow: /' for User-agent: *.",
        "suggested_action": {
            "summary": "Remove the blanket Disallow rule to allow crawlers to access the site.",
            "priority": "high",
        },
    },
    {
        "title": "No JSON-LD structured data found",
        "severity": "high",
        "category": "structured-data",
        "evidence": "The page contains no <script type=\"application/ld+json\"> blocks.",
        "suggested_action": {
            "summary": "Add JSON-LD structured data describing the primary entity.",
            "priority": "high",
        },
    },
    {
        "title": "No sameAs identity links in structured data",
        "severity": "medium",
        "category": "freshness-corroboration",
        "evidence": "JSON-LD does not include sameAs links.",
        "suggested_action": {
            "summary": "Add sameAs URLs in JSON-LD pointing to official profiles.",
            "priority": "medium",
        },
    },
    {
        "title": "Missing viewport meta tag",
        "severity": "high",
        "category": "engagement",
        "evidence": "No <meta name=\"viewport\"> tag found.",
        "suggested_action": {
            "summary": "Add viewport meta tag for mobile compatibility.",
            "priority": "high",
        },
    },
    {
        "title": "No clear call-to-action found",
        "severity": "high",
        "category": "engagement",
        "evidence": "No buttons, submit inputs, or CTA-style links detected.",
        "suggested_action": {
            "summary": "Add clear calls-to-action so visitors know what step to take.",
            "priority": "high",
        },
    },
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python report_builder.py <file1.json> [<file2.json> ...]\n"
            "  python report_builder.py --stdin\n"
            "  python report_builder.py --test",
            file=sys.stderr,
        )
        sys.exit(1)

    if sys.argv[1] == "--test":
        report = build_report(_SAMPLE_FINDINGS, site="example.com")
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    if sys.argv[1] == "--stdin":
        findings, site, pages_sampled = load_findings_from_stdin()
    else:
        findings, site, pages_sampled = load_findings_from_files(sys.argv[1:])

    report = build_report(
        findings,
        site=site,
        pages_sampled=pages_sampled or None,
    )
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()