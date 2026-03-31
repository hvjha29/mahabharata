#!/usr/bin/env python3
"""
Phase 0 — Site probe.

Tests 3 chapter URLs per parvan (first, middle, last), identifies CSS
selectors for translation text vs Sanskrit shlokas, checks if JS
rendering is required, and outputs probe_report.json.

Confirmed selectors (from manual testing):
  - div.book-content          → main content area
  - div.verse                 → each verse block (id="v000", v001, ...)
  - p.trans                   → English translation paragraph
  - p.sans                    → Sanskrit shloka paragraph
  - p.v-num > span.v-num-text → verse number (e.g. "1-1-001")
  - div.chapter-heading.chapter-start → "Canto NNN"
  - div.chapter-end           → "Canto NNN ends."
  - .book-title               → parvan name
"""

import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import PARVANS, BASE_URL, CHAPTER_URL_TEMPLATE, USER_AGENT, PROJECT_ROOT

PROBE_REPORT_PATH = PROJECT_ROOT / "probe_report.json"
REQUEST_DELAY = 2


def build_test_urls():
    """Generate 3 test URLs per parvan: first, middle, last chapter."""
    tests = []
    for parvan_name, parvan_key, book_num, total_chapters in PARVANS:
        mid = max(1, total_chapters // 2)
        for ch in [1, mid, total_chapters]:
            url = CHAPTER_URL_TEMPLATE.format(
                parvan_name=parvan_name, chapter_num=ch
            )
            tests.append({
                "parvan_name": parvan_name,
                "parvan_key": parvan_key,
                "book_num": book_num,
                "chapter_num": ch,
                "total_chapters": total_chapters,
                "url": url,
            })
    return tests


def fetch_page(url: str) -> requests.Response | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        return requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"  ✗ Request failed: {e}")
        return None


def analyze_page(html: str, url: str) -> dict:
    """Analyze a page using confirmed selectors."""
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "url": url,
        "status_code": None,
        "js_required": False,
        "page_title": (soup.title.string.strip() if soup.title and soup.title.string else ""),
        "book_title": "",
        "chapter_heading": "",
        "verse_count": 0,
        "trans_count": 0,
        "sans_count": 0,
        "translation_word_count": 0,
        "translation_preview": "",
        "empty_trans_count": 0,
        "status": "ok",
    }

    # JS detection
    body_text = soup.get_text(strip=True)
    if len(body_text) < 200 and "javascript" in body_text.lower():
        result["js_required"] = True
        result["status"] = "js_required"
        return result

    bt = soup.find(class_="book-title")
    if bt:
        result["book_title"] = bt.get_text(strip=True)

    ch = soup.find(class_="chapter-heading")
    if ch:
        result["chapter_heading"] = ch.get_text(strip=True)

    verses = soup.find_all(class_="verse")
    result["verse_count"] = len(verses)

    trans_els = soup.find_all("p", class_="trans")
    result["trans_count"] = len(trans_els)

    empty = 0
    trans_texts = []
    for t in trans_els:
        txt = t.get_text(strip=True)
        if not txt:
            empty += 1
        else:
            trans_texts.append(txt)
    result["empty_trans_count"] = empty

    combined = " ".join(trans_texts)
    result["translation_word_count"] = len(combined.split()) if combined else 0
    result["translation_preview"] = combined[:300] if combined else ""

    sans_els = soup.find_all("p", class_="sans")
    result["sans_count"] = len(sans_els)

    if result["trans_count"] == 0 and result["sans_count"] > 0:
        result["status"] = "untranslated"
    elif result["trans_count"] > 0 and result["empty_trans_count"] == result["trans_count"]:
        result["status"] = "untranslated"
    elif result["translation_word_count"] == 0:
        result["status"] = "empty"
    else:
        result["status"] = "ok"

    return result


def run_probe():
    """Execute the full probe and save report."""
    print("=" * 64)
    print("  vyasa-yt · Phase 0 · Site Probe")
    print("=" * 64)

    tests = build_test_urls()
    print(f"\nTesting {len(tests)} URLs across {len(PARVANS)} parvans...\n")

    results = []
    js_count = 0
    word_counts = []
    url_valid = True
    errors = 0

    for i, test in enumerate(tests):
        url = test["url"]
        label = f"{test['parvan_name']} ch{test['chapter_num']}"
        print(f"[{i+1:3d}/{len(tests)}] {label:40s}", end=" ", flush=True)

        resp = fetch_page(url)
        if resp is None:
            results.append({**test, "status_code": None, "status": "error"})
            errors += 1
            print("✗ request failed")
            continue

        analysis = analyze_page(resp.text, url)
        analysis["status_code"] = resp.status_code

        if resp.status_code == 404:
            analysis["status"] = "404"
            url_valid = False
            print("✗ 404")
        elif resp.status_code != 200:
            analysis["status"] = "error"
            errors += 1
            print(f"✗ HTTP {resp.status_code}")
        elif analysis["js_required"]:
            js_count += 1
            print("⚠ JS required")
        else:
            wc = analysis["translation_word_count"]
            word_counts.append(wc)
            tag = "✓" if wc > 50 else "⚠"
            print(f"{tag} {wc:5d} words, {analysis['trans_count']:3d} verses [{analysis['status']}]")

        results.append({**test, **analysis})

        if i < len(tests) - 1:
            time.sleep(REQUEST_DELAY)

    avg_wc = round(sum(word_counts) / len(word_counts)) if word_counts else 0
    min_wc = min(word_counts) if word_counts else 0
    max_wc = max(word_counts) if word_counts else 0

    report = {
        "probe_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_urls_tested": len(tests),
        "url_pattern": CHAPTER_URL_TEMPLATE,
        "url_pattern_valid": url_valid,
        "js_rendering_required": js_count > 0,
        "js_pages_count": js_count,
        "errors": errors,
        "selector_strategy": {
            "content_container": "div.book-content",
            "verse_block": "div.verse",
            "translation": "p.trans",
            "sanskrit": "p.sans",
            "verse_number": "p.v-num > span.v-num-text",
            "chapter_heading": "div.chapter-heading.chapter-start",
            "chapter_end": "div.chapter-end",
            "book_title": ".book-title",
        },
        "avg_word_count": avg_wc,
        "min_word_count": min_wc,
        "max_word_count": max_wc,
        "results": results,
    }

    with open(PROBE_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 64)
    print("  PROBE SUMMARY")
    print("=" * 64)
    print(f"  URL pattern valid:      {url_valid}")
    print(f"  JS rendering required:  {js_count > 0} ({js_count}/{len(tests)})")
    print(f"  Errors:                 {errors}")
    print(f"  Avg word count:         {avg_wc}")
    print(f"  Min / Max word count:   {min_wc} / {max_wc}")
    print(f"  Selector strategy:      p.trans for translation, p.sans for Sanskrit")
    print(f"  Report saved to:        {PROBE_REPORT_PATH}")
    print()

    if js_count > 0:
        print("  ⛔ STOP: JS rendering detected. Install playwright.")
        sys.exit(1)

    if not url_valid:
        print("  ⚠ Some 404s detected — review probe_report.json")

    return report


if __name__ == "__main__":
    run_probe()
