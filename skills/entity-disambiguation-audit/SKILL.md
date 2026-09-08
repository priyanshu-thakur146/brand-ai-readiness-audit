---
name: entity-disambiguation-audit
description: Audits how well a brand's identity is anchored against name-collision risk. Checks for schema.org Organization sameAs links to authoritative external profiles (Wikidata, Wikipedia, LinkedIn, Crunchbase), flags short or dictionary-word brand names that have no such anchors, and cross-checks Name-Address-Phone (NAP) consistency across header/footer text and structured data. Use when a brand shares its name with other companies, products, or common words and risks being confused with them in an AI assistant's answer.
license: MIT
allowed-tools: [bash, python, web_search]
---

# `skills/entity-disambiguation-audit/` — Brand Entity Disambiguation Audit

## When to use
Use this skill to check the "mistaken identity" failure mode from the Round-2 background: when
several different things share a name, an AI assistant can mix them up unless something clearly
distinguishes one from the others. This matters most for short, generic, or dictionary-word brand
names, and for any brand whose contact details are inconsistent across its own pages.

## Inputs
| Argument | Required | Description |
|---|---|---|
| `url` | yes | Target page URL to evaluate. |
| `timeout` | no | Max request timeout in seconds (default `15`). |
| `search_results` | no | Agent-gathered web-search evidence describing name collisions found on search engines. |

## Procedure (numbered, deterministic steps)
1. **Brand identity extraction** — pull the canonical organization name from JSON-LD
   `Organization.name`, `og:site_name`, or `<title>` as the best available "official" name.
2. **Authority-link audit** — check for a `sameAs` array pointing to canonical external identity
   anchors (Wikidata, Wikipedia, LinkedIn, Crunchbase, verified social profiles). These are what
   let a knowledge-graph-backed assistant resolve "this specific entity," not just "a string that
   matches this name."
3. **Ambiguity heuristic scoring** — flag names that are short (≤4 characters) or common
   dictionary words when no `sameAs`/entity markup exists to disambiguate them; a generic name with
   zero anchoring is a materially higher collision risk than a distinctive name with the same gap.
4. **NAP consistency check** — cross-check Name, Address, and Phone details as they appear in
   visible header/footer text against what JSON-LD declares, catching internal mismatches that
   would make even a correctly-identified brand look unreliable to an extractor.
5. **Emit findings** via `scripts/entity_check.py` (a site-level check, run once against the
   homepage by the orchestrator).

## Output
Findings prefixed `ED-`, each with `id`, `category: "discoverability"`, `title`, `severity`
(`critical`/`high`/`medium`/`low`), `evidence` (missing `sameAs` links, NAP mismatches found), and
`suggested_action` recommending specific schema.org authority links to add.
