# Content Extractability — Heuristics Reference

Supporting detail for `content-extractability-audit/SKILL.md`. This file is
read by the skill during steps 3–5 of its procedure; it is not itself an
entrypoint or executable.

---

## §1. Standard fact categories to check

Not every category applies to every site — judgment call in step 3 of the
main procedure. These are the categories most likely to matter for AI
discoverability, drawn from what an assistant is commonly asked to
cite about a brand:

| Category | What to look for in plain text | Typical page(s) |
|---|---|---|
| **Pricing** | A specific number with a currency symbol or explicit unit ("$49/month", "starting at $12") | pricing, product, service pages |
| **Contact / business info** | Phone number, physical address, business hours, support email | contact, about, footer |
| **Core specs / capabilities** | The 3–5 facts a buyer would compare across competitors (dimensions, materials, included features, limits) | product/service pages |
| **Policies** | Return window, shipping terms, cancellation terms, privacy basics | dedicated policy pages, FAQ |
| **Differentiators / claims** | What the brand states makes it different (certifications, guarantees, awards) — check the claim is stated as fact, not only implied by marketing copy | homepage, about, product pages |

A missing category is only a finding if the business type plausibly needs
it. A B2B services company with no listed price is often intentional
(custom quoting) — don't flag "no pricing" as a defect there; a retail or
SaaS site with genuinely no price anywhere is a real finding.

## §2. Non-text lock-in — what counts as "locked"

A fact is **locked** (extractability defect) when the *only* place it
appears is:

- An image with no `alt` text, or `alt` text that doesn't restate the fact
  (e.g. `alt="pricing chart"` when the chart contains the actual numbers)
- A PDF that isn't also mirrored in HTML anywhere on the site
- A video or audio file with no transcript, captions, or a text summary
  nearby that states the same fact
- Content assembled only via client-side JavaScript that a simple text
  extraction would never see (coordinate with `crawl-render-audit` via the
  shared `js-only-content` dedupe_key per the main SKILL.md, step 6)

A fact is **not locked**, even if it also appears in an image, PDF, or
video, as long as the same fact is separately present in plain HTML text
somewhere reachable — the redundancy is fine; the plain-text version is
what makes it extractable.

**Severity guidance for locked facts:**
- `critical` — the fact is one a customer/AI would need to complete a core
  action (price to purchase, address to visit, phone to contact) and it
  exists nowhere in plain text on the entire sampled set
- `high` — the fact is locked on the primary page where a user would look
  for it, but might exist in plain text elsewhere on the site
- `medium` — a secondary or supporting fact (a specific spec, a minor
  policy detail) is locked
- `low` — a nice-to-have fact (an award, a minor certification) is locked

## §3. Buried or ambiguous prose — what counts

Distinct from "locked" — this is when a fact **is** in plain text, but
poorly surfaced:

- **Vague headings**: a heading like "More Info", "Details", or "Learn
  More" sitting above content that actually answers a specific, nameable
  question ("Shipping Policy", "Return Window", "System Requirements").
  An assistant summarizing a page leans heavily on headings; a vague one
  makes the fact underneath harder to associate with the right query.
- **Implication instead of statement**: a fact that requires the reader to
  infer it across multiple sentences rather than being stated directly.
  Example of implied: "Most orders arrive before the following weekend in
  our experience." Example of stated: "Standard shipping takes 3–5
  business days." The implied version is harder for extraction to quote
  confidently and easier to mis-summarize.
- **Self-contradiction**: the same fact stated two different ways in two
  places on the same page or site (e.g. "free shipping over $50" in one
  section, "free shipping over $75" in another) — this doesn't just hurt
  extractability, it actively risks an assistant citing the wrong number.
  Treat as at least `high` severity regardless of which fact category it's in.

**Severity guidance for buried/ambiguous prose:**
- `high` — self-contradiction anywhere on the site
- `medium` — a primary fact (pricing, core policy) is implied rather than
  stated, or sits under a vague heading
- `low` — a secondary fact has the same issue

## §4. Evidence phrasing

Evidence should name what was checked and what was found, concretely
enough that someone could re-verify it:

- Good: `"Checked 6 sampled pages (home, /pricing, /contact, /faq,
  /products/a, /products/b); pricing appears only as
  /images/pricing-table-2026.png with alt text 'pricing'."`
- Bad: `"Pricing is hard to find."` (no page count, no specifics, not
  re-verifiable)

## §5. Suggested-action phrasing

Match the fix to the specific defect, not a generic template:

- For locked content: name the format to migrate to plain text in, and
  where ("Add the shipping table as an HTML `<table>` on /shipping-policy,
  in addition to the existing PDF").
- For vague headings: name the specific replacement heading.
- For implied facts: give the direct-statement version that should replace
  the implied one.
- For self-contradictions: name both conflicting values and which page/
  section each appears on, so the fix is "reconcile these two," not just
  "fix pricing."