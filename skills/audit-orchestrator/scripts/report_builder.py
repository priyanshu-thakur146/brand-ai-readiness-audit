#!/usr/bin/env python3
"""
report_builder.py
==================

Used by the `audit-orchestrator` skill (the marketplace's single entrypoint).

Takes the RAW findings emitted by the five specialist skills
(crawl-render-audit, structured-data-audit, content-extractability-audit,
freshness-corroboration-audit, engagement-audit) and merges them into the
ONE fixed-schema audit report required by the contest brief:

    {
      "site": "example.com",
      "audited_at": "2026-09-20T14:32:00Z",
      "summary": {"total_findings": 6, "critical": 1, "high": 2, "medium": 3},
      "findings": [
        {
          "id": "F-001",
          "title": "...",
          "severity": "high",
          "evidence": "...",
          "suggested_action": {"summary": "...", "priority": "high"}
        }
      ]
    }

Design goals (map directly to the rubric):
  - Deterministic  -> stable sort, stable id assignment, no randomness.
  - Evidence-first  -> a finding without evidence is rejected, not silently
                        dropped-and-forgotten (it's logged as a builder error).
  - No false-positive inflation -> near-duplicate findings from different
                        skills are merged into one, with evidence combined,
                        rather than reported twice.
  - Extensible but never below the floor -> we always emit at least the
    required fields; extra fields are additive only.

This file has NO third-party dependencies (stdlib only) so it never adds to
the marketplace's dependency footprint or its 50MB submission budget.

-------------------------------------------------------------------------
Contract each specialist skill is expected to produce (a "raw finding"):
-------------------------------------------------------------------------
{
  "title": str,                      # required
  "severity": str,                   # required: critical|high|medium|low
                                      # (case-insensitive; common synonyms
                                      #  are normalized, see SEVERITY_MAP)
  "evidence": str,                   # required: a concrete, observable fact
  "suggested_action": {
      "summary": str,                # required
      "priority": str                # optional, defaults to `severity`
  },
  "source_skill": str,                # required: which specialist produced it
  "category": str,                    # optional: free-text grouping used
                                       # only for de-duplication, e.g.
                                       # "structured-data", "crawlability"
  "dedupe_key": str,                  # optional: an explicit, exact-match
                                       # key that specialist skills can share
                                       # when they know in advance they might
                                       # both flag the same root cause (e.g.
                                       # both crawl-render-audit and
                                       # content-extractability-audit can
                                       # emit dedupe_key="js-only-content"
                                       # for a JS-rendering-only gap). When
                                       # present, this is authoritative and
                                       # skips the fuzzy title match below --
                                       # deterministic and skill-author-
                                       # controlled beats guessing from text.
  "proactive": bool                   # optional, default False.
                                       # True = a suggestion made even though
                                       # no defect was detected (still needs
                                       # `evidence` explaining the basis,
                                       # e.g. "no sameAs links found; adding
                                       # them would reduce entity ambiguity")
}

Each specialist skill writes its raw findings to a JSON file (a list of the
objects above) under a shared `raw_findings/` directory. audit-orchestrator
calls this script once, after all five specialists have run, pointing it at
that directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Canonical severity order, worst first. Anything not in SEVERITY_MAP's
# values is rejected rather than guessed at.
SEVERITY_ORDER = ["critical", "high", "medium", "low"]

# Normalizes common synonyms a specialist skill might emit, so the
# orchestrator never has to trust free-text severity from five different
# skill authors.
SEVERITY_MAP = {
    "critical": "critical",
    "blocker": "critical",
    "severe": "critical",
    "high": "high",
    "major": "high",
    "medium": "medium",
    "moderate": "medium",
    "low": "low",
    "minor": "low",
    "info": "low",
    "informational": "low",
}

REQUIRED_RAW_FIELDS = ("title", "severity", "evidence", "source_skill")

# Used only to decide whether two findings are "the same underlying problem"
# reported by two different skills (e.g. crawl-render-audit and
# content-extractability-audit both flagging the same JS-only content gap).
# Deliberately simple and dependency-free: lowercase, strip punctuation,
# collapse whitespace, compare token overlap. Good enough to catch near-dupes
# without a fuzzy-matching library, and fully deterministic.
_WORD_RE = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class ReportBuilderError(Exception):
    """Raised when a raw finding is malformed enough that silently coercing
    it would hide a bug in a specialist skill rather than surface it."""


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Finding:
    title: str
    severity: str
    evidence: list[str]
    suggested_action_summary: str
    suggested_action_priority: str
    source_skills: list[str]
    proactive: bool = False
    category: str | None = None
    id: str = field(default="")  # assigned later, after sort

    def to_report_dict(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            # Multiple specialists corroborating the same problem is itself
            # evidence of severity -> we join, we don't pick just one.
            "evidence": " | ".join(self.evidence),
            "suggested_action": {
                "summary": self.suggested_action_summary,
                "priority": self.suggested_action_priority,
            },
        }
        # Extension fields (additive, never replace required ones).
        if self.proactive:
            out["proactive"] = True
        if len(self.source_skills) > 1:
            out["source_skills"] = sorted(self.source_skills)
        return out


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def _normalize_severity(raw: str, *, context: str) -> str:
    key = str(raw).strip().lower()
    if key not in SEVERITY_MAP:
        raise ReportBuilderError(
            f"Unrecognized severity '{raw}' in finding from {context}. "
            f"Expected one of: {sorted(set(SEVERITY_MAP.values()))} "
            f"(or a known synonym)."
        )
    return SEVERITY_MAP[key]


def _dedupe_key(title: str, category: str | None) -> str:
    """Cheap, deterministic signature used to merge near-duplicate findings
    across skills. Two findings collapse together only if they share the
    same category AND a majority of significant title tokens overlap -- this
    is intentionally conservative to avoid merging two genuinely distinct
    problems just because they use similar words."""
    tokens = frozenset(_WORD_RE.findall(title.lower()))
    cat = (category or "").strip().lower()
    # Sort tokens so token order in the title doesn't affect the key.
    return f"{cat}::{'-'.join(sorted(tokens))}"


def _token_overlap(a: str, b: str) -> float:
    ta, tb = frozenset(_WORD_RE.findall(a.lower())), frozenset(_WORD_RE.findall(b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --------------------------------------------------------------------------
# Core pipeline
# --------------------------------------------------------------------------

def _validate_raw(raw: dict[str, Any], *, index: int, source_file: str) -> None:
    missing = [f for f in REQUIRED_RAW_FIELDS if not raw.get(f)]
    if missing:
        raise ReportBuilderError(
            f"Finding #{index} in {source_file} is missing required "
            f"field(s): {missing}. Every finding must be evidence-backed; "
            f"an incomplete finding is a bug in the producing skill, not "
            f"something the orchestrator should paper over."
        )
    sa = raw.get("suggested_action")
    if not isinstance(sa, dict) or not sa.get("summary"):
        raise ReportBuilderError(
            f"Finding #{index} in {source_file} ('{raw.get('title')}') is "
            f"missing suggested_action.summary."
        )


def load_raw_findings(raw_dir: Path) -> list[dict[str, Any]]:
    """Reads every *.json file in raw_dir (one per specialist skill, each
    containing a JSON list of raw findings) and returns the flattened,
    validated list."""
    if not raw_dir.is_dir():
        raise ReportBuilderError(f"raw findings directory not found: {raw_dir}")

    all_raw: list[dict[str, Any]] = []
    files = sorted(raw_dir.glob("*.json"))  # sorted -> deterministic order
    if not files:
        raise ReportBuilderError(f"no raw finding files found in {raw_dir}")

    for fp in files:
        try:
            content = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ReportBuilderError(f"{fp.name} is not valid JSON: {e}") from e

        if not isinstance(content, list):
            raise ReportBuilderError(
                f"{fp.name} must contain a JSON list of findings, "
                f"got {type(content).__name__}"
            )

        for i, raw in enumerate(content):
            _validate_raw(raw, index=i, source_file=fp.name)
            all_raw.append(raw)

    return all_raw


def merge_findings(raw_findings: Iterable[dict[str, Any]]) -> list[Finding]:
    """Normalizes severities, merges near-duplicates across skills (combining
    their evidence rather than reporting the same root cause twice), and
    returns a de-duplicated list of Finding objects (unordered)."""
    merged: dict[str, Finding] = {}

    for raw in raw_findings:
        title = str(raw["title"]).strip()
        severity = _normalize_severity(raw["severity"], context=raw["source_skill"])
        evidence = str(raw["evidence"]).strip()
        sa = raw["suggested_action"]
        priority = str(sa.get("priority") or severity).strip().lower()
        if priority not in SEVERITY_ORDER:
            priority = severity  # fall back rather than fail the whole run
        category = raw.get("category")
        source_skill = str(raw["source_skill"])
        proactive = bool(raw.get("proactive", False))
        explicit_key = raw.get("dedupe_key")

        key = f"explicit::{explicit_key}" if explicit_key else _dedupe_key(title, category)

        # 1. An explicit, skill-author-supplied dedupe_key is authoritative:
        #    exact match only, no fuzziness, fully deterministic.
        # 2. Otherwise fall back to fuzzy title overlap within the same
        #    category, as a safety net for skills that didn't coordinate a
        #    shared key in advance. This is intentionally a fallback, not
        #    the primary mechanism -- fuzzy text matching alone is not
        #    reliable enough to be the sole de-dup strategy.
        match_key = key if key in merged else None
        if match_key is None and not explicit_key and category:
            for existing_key, existing in merged.items():
                if existing.category != category:
                    continue
                if _token_overlap(existing.title, title) >= 0.6:
                    match_key = existing_key
                    break

        if match_key is not None:
            existing = merged[match_key]
            # Worse severity wins; corroboration across skills is a signal,
            # never a reason to downgrade.
            if SEVERITY_ORDER.index(severity) < SEVERITY_ORDER.index(existing.severity):
                existing.severity = severity
            if evidence not in existing.evidence:
                existing.evidence.append(evidence)
            if source_skill not in existing.source_skills:
                existing.source_skills.append(source_skill)
            # A defect finding always outranks a proactive one on merge.
            existing.proactive = existing.proactive and proactive
        else:
            merged[key] = Finding(
                title=title,
                severity=severity,
                evidence=[evidence],
                suggested_action_summary=str(sa["summary"]).strip(),
                suggested_action_priority=priority,
                source_skills=[source_skill],
                proactive=proactive,
                category=category,
            )

    return list(merged.values())


def sort_and_assign_ids(findings: list[Finding]) -> list[Finding]:
    """Deterministic ordering: worst severity first; within a severity,
    defects before proactive suggestions; within that, alphabetical by
    title (stable and reproducible run-to-run, which matters for judges
    re-running the audit and comparing output)."""
    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER.index(f.severity),
            f.proactive,  # False (0) sorts before True (1)
            f.title.lower(),
        )
    )
    for i, f in enumerate(findings, start=1):
        f.id = f"F-{i:03d}"
    return findings


def build_summary(findings: list[Finding]) -> dict[str, int]:
    counts = {level: 0 for level in SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    # Only emit severity buckets that are actually non-empty PLUS the three
    # the brief's schema always shows (critical/high/medium), so the report
    # never looks like it's missing required summary fields.
    summary = {"total_findings": len(findings)}
    for level in ("critical", "high", "medium"):
        summary[level] = counts[level]
    if counts["low"]:
        summary["low"] = counts["low"]
    return summary


def build_report(site: str, raw_findings: Iterable[dict[str, Any]],
                  audited_at: str | None = None) -> dict[str, Any]:
    findings = merge_findings(raw_findings)
    findings = sort_and_assign_ids(findings)
    return {
        "site": site,
        "audited_at": audited_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": build_summary(findings),
        "findings": [f.to_report_dict() for f in findings],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge raw findings from the 5 specialist skills into "
                    "the final fixed-schema audit report."
    )
    parser.add_argument("--site", required=True,
                         help="The audited site, e.g. example.com")
    parser.add_argument("--raw-dir", required=True, type=Path,
                         help="Directory containing one *.json file per "
                              "specialist skill, each a JSON list of raw findings.")
    parser.add_argument("--out", type=Path, default=None,
                         help="Where to write the final report JSON. "
                              "Defaults to stdout.")
    parser.add_argument("--audited-at", default=None,
                         help="ISO-8601 UTC timestamp override, mainly for "
                              "reproducible testing. Defaults to now().")
    args = parser.parse_args(argv)

    try:
        raw = load_raw_findings(args.raw_dir)
        report = build_report(args.site, raw, audited_at=args.audited_at)
    except ReportBuilderError as e:
        print(f"report_builder error: {e}", file=sys.stderr)
        return 1

    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())