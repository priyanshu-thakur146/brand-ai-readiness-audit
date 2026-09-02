---
name: entity-disambiguation-audit
description: Checks whether the brand can be told apart from other entities that share its name — schema.org sameAs links tying the site to canonical external profiles (Wikipedia, Wikidata, LinkedIn, Crunchbase), and consistency of name/address/phone (NAP) across the page. Use this for any brand whose name is a common word, is short, or is shared with other companies/products, per Appendix D of the brief.
license: MIT
allowed-tools: [bash, python, web_search]
---

# Entity Disambiguation Audit

## When to use
Use for any brand audit — ambiguity risk is worth checking even when not obviously a problem,
since a false negative here (assuming the name is unique when it isn't) is easy to make. Appendix D:
when several different things share a name, a system can mix them up unless there's something that
clearly distinguishes one from the others.

## Inputs
- `url` (required)
- `timeout` (optional, default 15s)
- `--search-results <file>` (optional): if the calling agent has searched the brand name and found
  multiple unrelated entities sharing it, pass that here to raise ambiguity-risk severity. Format:
  `{"name_collision_count": 3, "examples": ["Acme Corp (security)", "Acme Inc (dance studio)"]}`

## Procedure
1. Extract the brand/organization name from JSON-LD (`Organization.name`) or `og:site_name`/`<title>`.
2. Check for a `sameAs` array on the Organization entity linking to canonical external profiles
   (Wikipedia, Wikidata, LinkedIn, Crunchbase, official social accounts). These are the strongest,
   cheapest disambiguation signal — they tell an assistant "this site and that Wikidata entity are
   the same thing."
3. Heuristically flag names that are common dictionary words or very short (<=4 characters) as
   higher ambiguity risk if no sameAs/disambiguating entity markup is present.
4. Check basic NAP (name/address/phone) consistency between the header/footer and any Organization
   or LocalBusiness JSON-LD — mismatches create a second, subtler ambiguity problem.
5. If `--search-results` indicates real name collisions on the web, escalate severity.
6. Emit findings via `scripts/entity_check.py`.

## Output
Findings with `id` prefixed `ED-`, following the shared schema.
