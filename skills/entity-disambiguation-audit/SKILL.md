---
name: entity-disambiguation-audit
description: Audits brand identity anchors to resolve name ambiguity risks. Checks for schema.org Organization sameAs authority links (Wikidata, Wikipedia, LinkedIn, Crunchbase), evaluates name-collision risks for short/generic brand names, and verifies Name-Address-Phone (NAP) consistency across page regions.
license: MIT
allowed-tools: [bash, python, web_search]
---

# Entity Disambiguation Audit

## Overview & Purpose
When multiple companies, products, or dictionary words share a brand's name, AI assistants can easily hallucinate or mix up facts between unrelated entities. Establishing strong, unambiguous machine-readable entity anchors is critical to ensuring AI engines attribute facts to the correct organization.

The **Entity Disambiguation Audit** skill inspects structured authority links (`sameAs`) and checks for Name-Address-Phone (NAP) consistency to anchor identity across the web.

## Key Technical Features
- **Authority Profile Mapping (`sameAs`)**: Checks for `Organization.sameAs` arrays linking to canonical external authority sources (Wikidata, Wikipedia, LinkedIn, Crunchbase, official social channels) that explicitly link the site to its global Knowledge Graph entity.
- **Generic / Short Name Ambiguity Detection**: Flags brand names that are dictionary words or short abbreviations (<=4 characters) when no explicit entity markup or `sameAs` links exist.
- **NAP Consistency Audit**: Cross-checks brand Name, Address, and Phone details across header/footer text and JSON-LD markup to catch internal identity mismatches.

## Input Parameters
- `url` *(required)*: The target page URL to evaluate.
- `timeout` *(optional)*: Maximum request timeout in seconds (defaults to 15s).
- `--search-results <file>` *(optional)*: Pre-gathered web search evidence detailing name collisions on search engines.

## Diagnostic Procedure
1. **Brand Identity Extraction**: Extracts official organization name from JSON-LD `Organization.name`, `og:site_name`, or `<title>`.
2. **Authority Link Audit**: Verifies presence and validity of `sameAs` profile arrays.
3. **Ambiguity Heuristic Evaluation**: Scores ambiguity risk based on name length, dictionary word overlap, and missing schema anchors.
4. **NAP Consistency Check**: Audits contact details across page headers, footers, and structured data.
5. **Execution**: Emits findings via `scripts/entity_check.py`.

## Output Structure
Emits findings prefixed with `ED-` adhering to the marketplace findings schema:
- `id`: e.g., `ED-001`, `ED-002`
- `category`: `"discoverability"`
- `title`: Problem title (e.g., "No Organization/LocalBusiness entity markup to anchor identity")
- `severity`: `"critical"`, `"high"`, `"medium"`, or `"low"`
- `evidence`: Empirical diagnostic data regarding missing `sameAs` links or NAP mismatches
- `suggested_action`: Direct recommendations for adding canonical schema.org authority links

