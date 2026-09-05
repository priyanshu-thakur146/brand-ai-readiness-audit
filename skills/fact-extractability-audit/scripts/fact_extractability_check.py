#!/usr/bin/env python3
"""fact-extractability-audit: heading structure, lead clarity, non-text facts, boilerplate ratio."""
import sys
import json
import re

import requests
from bs4 import BeautifulSoup

UA = "BrandAIReadinessAuditBot/1.0 (+https://agentskills.io)"
FILLER_PATTERNS = [
    r"\bwelcome to\b", r"\bwe are passionate about\b", r"\blearn more\b",
    r"\bwe believe\b", r"\bour mission is to\b", r"\bcutting[- ]edge\b",
    r"\bworld[- ]class\b", r"\bat the forefront\b",
]
CONCRETE_PATTERNS = [r"\d", r"\$", r"%", r"\b(is|are|was|were|founded|based in|located|offers?|provides?)\b"]
BOILERPLATE_CLASSES = re.compile(r"nav|footer|cookie|banner|menu|sidebar", re.I)


def _finding(fid, title, severity, evidence, action_summary, priority):
    return {
        "id": fid,
        "category": "engagement" if "boilerplate" in fid.lower() else "discoverability",
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": priority},
    }


def run_check(url, timeout=15):
    findings = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"FE-{n:03d}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException as e:
        return [_finding(nid(), "Page unreachable for fact-extractability check", "critical",
                          f"Request error: {e}", "Fix connectivity/availability before auditing content.",
                          "critical")]

    soup = BeautifulSoup(r.text, "lxml")

    # 1. heading structure
    h1s = soup.find_all("h1")
    if len(h1s) == 0:
        findings.append(_finding(nid(), "No H1 heading", "medium",
                                  "Page has zero <h1> elements.",
                                  "Add exactly one clear <h1> stating the page's core topic — it's "
                                  "the strongest single outline signal an extractor uses.", "medium"))
    elif len(h1s) > 1:
        findings.append(_finding(nid(), "Multiple H1 headings", "low",
                                  f"Page has {len(h1s)} <h1> elements.",
                                  "Use a single <h1> per page and demote the rest to <h2>/<h3> to "
                                  "keep the outline unambiguous.", "low"))

    levels = []
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        levels.append(int(tag.name[1]))
    skipped = any(b - a > 1 for a, b in zip(levels, levels[1:]) if b > a)
    if skipped:
        findings.append(_finding(nid(), "Heading levels skip a level", "low",
                                  "Heading sequence jumps by more than one level at least once "
                                  f"(sequence found: {levels[:15]}{'...' if len(levels) > 15 else ''}).",
                                  "Keep heading levels sequential (h1 > h2 > h3, no skips) so tools "
                                  "that build an outline from headings don't misjudge structure.",
                                  "low"))

    # 2. lead clarity
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.extract()
    full_text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    lead = full_text[:400]
    filler_hits = sum(1 for p in FILLER_PATTERNS if re.search(p, lead, re.I))
    concrete_hits = sum(1 for p in CONCRETE_PATTERNS if re.search(p, lead, re.I))
    if filler_hits >= 1 and concrete_hits == 0:
        findings.append(_finding(
            nid(), "Opening content is generic marketing copy with no concrete claim", "medium",
            f"First ~150 words match filler phrasing ({filler_hits} pattern hit(s)) with no "
            "concrete noun/number/fact detected.",
            "Lead with one or two plain-text sentences stating specifically what the brand/product "
            "is or does (what, for whom, key differentiator) before any tagline-style copy — that's "
            "the text most likely to be lifted verbatim into a summary or citation.", "medium"))

    # 3. non-text facts
    imgs = soup.find_all("img")
    imgs_no_alt = [i for i in imgs if not (i.get("alt") or "").strip()]
    if imgs and len(imgs_no_alt) / len(imgs) > 0.5 and len(imgs) >= 4:
        findings.append(_finding(
            nid(), "Majority of images have no alt text", "medium",
            f"{len(imgs_no_alt)}/{len(imgs)} <img> elements have empty or missing alt attributes.",
            "Add descriptive alt text to informational images (not decorative ones) so any facts "
            "conveyed visually (diagrams, infographics, screenshots with data) have a text "
            "equivalent a machine can read.", "medium"))

    canvases = soup.find_all("canvas")
    if canvases:
        findings.append(_finding(
            nid(), "Content rendered via <canvas> has no text equivalent", "medium",
            f"{len(canvases)} <canvas> element(s) found; canvas content is not machine-readable text.",
            "If canvas is used for charts/infographics carrying facts, add an adjacent text summary "
            "or a data table with the same information.", "medium"))

    videos_iframes = soup.find_all(["video", "iframe"])
    if videos_iframes and len(full_text.split()) < 200:
        findings.append(_finding(
            nid(), "Page leans on embedded video/iframe with little surrounding text", "medium",
            f"{len(videos_iframes)} video/iframe embed(s) found alongside only "
            f"~{len(full_text.split())} words of plain text.",
            "Add a text transcript or a written summary of the embedded video's key points/claims "
            "near the embed — assistants generally cannot watch video to extract facts.", "medium"))

    pdf_links = [a for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]
    if pdf_links and len(full_text.split()) < 150:
        findings.append(_finding(
            nid(), "Key content appears to live only in a linked PDF", "low",
            f"{len(pdf_links)} PDF link(s) found on a page with only ~{len(full_text.split())} "
            "words of on-page text.",
            "Mirror the PDF's key facts as on-page HTML text (or provide an HTML version) — PDFs "
            "are crawlable but far less reliably parsed than plain HTML.", "low"))

    # 4. Table and list extractability
    tables_without_th = []
    for tbl in soup.find_all("table"):
        if not tbl.find_all("th"):
            tables_without_th.append(tbl)
    if tables_without_th:
        findings.append(_finding(
            nid(), "Data tables missing <th> header markup", "medium",
            f"{len(tables_without_th)} table(s) found without <th> header cells.",
            "Add <th> elements to data tables so AI extractors can accurately pair data values with their column/row headers.", "medium"))

    # 5. subpage extractability sampling
    import urllib.parse as up
    from concurrent.futures import ThreadPoolExecutor
    parsed = up.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    subpage_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = up.urljoin(origin, href)
        p = up.urlparse(full_url)
        if p.netloc == parsed.netloc and p.path.strip("/") and p.path.strip("/") != parsed.path.strip("/"):
            if full_url not in subpage_urls and not any(full_url.endswith(ext) for ext in [".png", ".jpg", ".pdf", ".css", ".js"]):
                subpage_urls.append(full_url)
                if len(subpage_urls) >= 4:
                    break

    if subpage_urls:
        total_sub_imgs = 0
        total_sub_no_alt = 0
        def _check_sub_extractability(u):
            try:
                resp = requests.get(u, headers={"User-Agent": UA}, timeout=min(timeout, 5))
                if resp.status_code == 200:
                    sub_soup = BeautifulSoup(resp.text, "lxml")
                    imgs = sub_soup.find_all("img")
                    no_alt = [i for i in imgs if not (i.get("alt") or "").strip()]
                    return len(imgs), len(no_alt)
            except Exception:
                pass
            return 0, 0

        with ThreadPoolExecutor(max_workers=4) as executor:
            res_list = list(executor.map(_check_sub_extractability, subpage_urls))
            for c_tot, c_no in res_list:
                total_sub_imgs += c_tot
                total_sub_no_alt += c_no

        all_imgs_tot = len(imgs) + total_sub_imgs
        all_imgs_no_alt = len(imgs_no_alt) + total_sub_no_alt
        if all_imgs_tot >= 5 and (all_imgs_no_alt / all_imgs_tot) > 0.4:
            # Multi-page evidence finding for image extractability
            findings.append(_finding(
                nid(), "High ratio of uncaptioned images across sampled pages", "medium",
                f"Crawled {1 + len(subpage_urls)} sampled pages; {all_imgs_no_alt}/{all_imgs_tot} images lack descriptive alt text.",
                "Ensure informational images across all pages have descriptive alt text so facts in visual elements are machine-extractable.", "medium"))

    # 6. boilerplate ratio (rough)
    soup2 = BeautifulSoup(r.text, "lxml")
    for s in soup2(["script", "style"]):
        s.extract()
    boiler_text_len = 0
    for el in soup2.find_all(True):
        cls = " ".join(el.get("class", [])) + " " + (el.get("id") or "")
        if BOILERPLATE_CLASSES.search(cls):
            boiler_text_len += len(el.get_text(" ", strip=True))
    total_len = len(re.sub(r"\s+", " ", soup2.get_text(" "))) or 1
    ratio = boiler_text_len / total_len
    if ratio > 0.5 and total_len > 300:
        findings.append(_finding(
            nid(), "High proportion of page text is nav/footer/boilerplate", "low",
            f"Estimated {ratio:.0%} of visible text sits in nav/footer/menu/banner-like containers.",
            "Trim repeated navigation/footer/cookie text relative to main content, or ensure the "
            "main content region is marked with <main>/semantic tags so extractors can weight it "
            "appropriately.", "low"))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fact_extractability_check.py <url>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(run_check(sys.argv[1]), indent=2))
