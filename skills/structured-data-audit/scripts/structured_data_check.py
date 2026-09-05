#!/usr/bin/env python3
"""structured-data-audit: JSON-LD / meta / plain-text-fact checks."""
import sys
import json
import re

import requests
from bs4 import BeautifulSoup

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
KNOWN_TYPES = {
    "organization", "product", "article", "newsarticle", "blogposting", "faqpage",
    "localbusiness", "breadcrumblist", "website", "webpage", "person", "review",
    "aggregaterating", "offer", "event", "howto", "recipe", "video", "itemlist",
}
GENERIC_TITLES = {"home", "homepage", "welcome", "untitled", "index", "new page", "document"}

PHONE_RE = re.compile(r"(\+?\d[\d\-\.\s\(\)]{7,}\d)")
PRICE_RE = re.compile(r"[$€£₹]\s?\d[\d,]*(\.\d{2})?")
HOURS_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b.{0,20}\d{1,2}(:\d{2})?\s?(am|pm)", re.I)


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


def run_check(url, timeout=15):
    findings = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"SD-{n:03d}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException as e:
        return [_finding(nid(), "Page unreachable for structured-data check", "critical",
                          f"Request error: {e}", "Fix connectivity/availability before auditing markup.",
                          "critical")]

    soup = BeautifulSoup(r.text, "lxml")

    # 1+2. JSON-LD
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    valid_blocks = []
    invalid_count = 0
    types_found = set()
    for s in scripts:
        try:
            data = json.loads(s.string or s.get_text() or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                    items = item["@graph"]
            for item in items:
                if isinstance(item, dict):
                    valid_blocks.append(item)
        except (json.JSONDecodeError, TypeError):
            invalid_count += 1

    if not scripts:
        findings.append(_finding(
            nid(), "No JSON-LD structured data on the page", "high",
            "Zero <script type=\"application/ld+json\"> blocks found.",
            "Add schema.org JSON-LD (Organization on every page at minimum; Product/Article/"
            "LocalBusiness/FAQPage where relevant) so assistants can extract facts with certainty "
            "instead of inferring them from prose.", "high"))
    else:
        if invalid_count:
            findings.append(_finding(
                nid(), "Malformed JSON-LD block(s)", "high",
                f"{invalid_count} of {len(scripts)} ld+json block(s) failed to parse as valid JSON.",
                "Fix JSON syntax errors (trailing commas, unescaped quotes) — a parser that fails "
                "silently drops the entire block, which is equivalent to having none.", "high"))
        types_found = set()
        for item in valid_blocks:
            t = item.get("@type")
            if isinstance(t, list):
                types_found.update(x.lower() for x in t if isinstance(x, str))
            elif isinstance(t, str):
                types_found.add(t.lower())
            ctx = item.get("@context", "")
            if isinstance(ctx, str) and "schema.org" not in ctx:
                findings.append(_finding(
                    nid(), "JSON-LD block missing schema.org context", "medium",
                    f"@context = {ctx!r} does not reference schema.org.",
                    "Set \"@context\": \"https://schema.org\" so parsers recognize the vocabulary.",
                    "medium"))
        if types_found and not (types_found & KNOWN_TYPES):
            findings.append(_finding(
                nid(), "JSON-LD present but uses no recognized schema.org type", "medium",
                f"@type values found: {sorted(types_found)} — none match common schema.org types.",
                "Use a standard, well-supported @type (Organization, Product, Article, FAQPage, "
                "LocalBusiness, etc.) rather than a custom or misspelled type.", "medium"))
        if "organization" not in types_found and "localbusiness" not in types_found:
            findings.append(_finding(
                nid(), "No Organization/LocalBusiness entity markup", "medium",
                f"JSON-LD types present: {sorted(types_found) if types_found else 'none parsed'}.",
                "Add an Organization (or LocalBusiness) JSON-LD block with name, url, logo, and "
                "sameAs links — this is the anchor entity assistants use to identify the brand "
                "unambiguously (see entity-disambiguation-audit).", "medium"))

    # 3. title / meta description
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    if not title_text:
        findings.append(_finding(nid(), "Missing <title> tag", "high",
                                  "No non-empty <title> element found.",
                                  "Add a descriptive, unique <title> to every page.", "high"))
    elif title_text.strip().lower() in GENERIC_TITLES:
        findings.append(_finding(nid(), "Generic/boilerplate page title", "medium",
                                  f"<title> = {title_text!r}",
                                  "Replace with a specific, descriptive title including the brand "
                                  "and page topic.", "medium"))

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    desc_content = (meta_desc.get("content") if meta_desc else "") or ""
    if not desc_content.strip():
        findings.append(_finding(nid(), "Missing meta description", "medium",
                                  "No <meta name=\"description\"> content found.",
                                  "Add a concise (~150-160 char) meta description stating what the "
                                  "page/brand offers — assistants and search snippets draw on this.",
                                  "medium"))

    # 4. Open Graph / Twitter card
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    if not og_title or not og_desc:
        findings.append(_finding(nid(), "Incomplete Open Graph tags", "low",
                                  f"og:title present={bool(og_title)}, og:description present={bool(og_desc)}.",
                                  "Add og:title, og:description, and og:image so link previews and "
                                  "summarization tools have a clean, authoritative source to quote.",
                                  "low"))

    # 5. plain-text presence of core facts
    for tag in soup(["script", "style"]):
        tag.extract()
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    has_price_text = bool(PRICE_RE.search(text))
    has_price_image_only = False
    if not has_price_text:
        priceish_imgs = [img for img in soup.find_all("img")
                          if re.search(r"price|cost|\$", (img.get("alt", "") or "") + (img.get("src", "") or ""), re.I)]
        if priceish_imgs:
            has_price_image_only = True

    if has_price_image_only:
        findings.append(_finding(
            nid(), "Price appears to be image-only", "medium",
            "No price pattern found in plain text, but an image with a price-related name/alt "
            "attribute was found.",
            "State prices as plain text (optionally alongside a styled image), and include them "
            "in Product/Offer JSON-LD so they can be extracted and quoted verbatim.", "medium"))

    has_phone = bool(PHONE_RE.search(text))
    has_hours = bool(HOURS_RE.search(text))
    if not has_phone and not has_hours:
        # informational only — not every site needs these; keep severity low
        findings.append(_finding(
            nid(), "No contact phone or hours found in plain text", "low",
            "No phone-number or opening-hours pattern detected in visible text.",
            "If applicable to this business, state phone/hours as plain text and in "
            "LocalBusiness JSON-LD — assistants answering 'is X open now / what's their number' "
            "need this in extractable form.", "low"))

    # --- proactive suggestions (independent of any defect above) ---
    # FAQPage schema: only worth suggesting when the page actually reads like
    # a FAQ (several question-shaped headings) — otherwise it's noise.
    question_headings = [
        h.get_text(strip=True) for h in soup.find_all(re.compile(r"^h[2-4]$"))
        if h.get_text(strip=True).endswith("?")
    ]
    if len(question_headings) >= 3 and "faqpage" not in types_found:
        findings.append(_proactive(
            nid(), "FAQ-shaped content found without FAQPage schema",
            f"{len(question_headings)} question-style heading(s) detected "
            f"(e.g. {question_headings[:2]}) but no FAQPage JSON-LD present.",
            "Mark this content up as FAQPage schema (question + acceptedAnswer pairs). It's a "
            "low-effort addition that lets assistants extract and quote Q&A pairs directly, and "
            "is exactly the kind of content AI answer engines prefer to cite verbatim."))

    # Organization present but thin (no logo) — cheap, high-value addition.
    org_block = next((i for i in valid_blocks
                       if isinstance(i.get("@type"), str) and i.get("@type", "").lower() == "organization"
                       or isinstance(i.get("@type"), list) and "organization" in [x.lower() for x in i["@type"] if isinstance(x, str)]),
                      None)
    if org_block and not org_block.get("logo"):
        findings.append(_proactive(
            nid(), "Organization schema present but missing logo",
            "An Organization JSON-LD block was found without a 'logo' property.",
            "Add a 'logo' field (absolute URL to a square image) to the Organization block — "
            "several assistants and rich-result surfaces use it to visually attribute the brand "
            "in answers."))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: structured_data_check.py <url>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(run_check(sys.argv[1]), indent=2))
