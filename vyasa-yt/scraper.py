#!/usr/bin/env python3
"""
Phase 1 — Scraper.

Scrapes chapter translation text and Sanskrit shlokas from vyas-mahabharat.com.
Uses confirmed selectors: p.trans (translation), p.sans (Sanskrit), div.verse.

Saves each chapter to data/chapters/{parvan_key}_{chapter_num:04d}.json
Idempotent: skips chapters already saved with status != "error".
3-second delay between requests.  Use --limit N to batch.
"""

import time
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    PARVANS, CHAPTER_URL_TEMPLATE, USER_AGENT, REQUEST_DELAY,
    CHAPTERS_DIR,
)
from utils import (
    chapter_id, chapter_filename, chapter_url, now_iso,
    load_json, save_json, RateLimiter, print_status_table,
)


def parse_chapter(html: str) -> dict:
    """
    Parse a chapter page and extract translation + Sanskrit text.

    Returns dict with keys:
        title, translation_text, shlokas_raw, word_count, verse_count, status
    """
    soup = BeautifulSoup(html, "html.parser")

    # Chapter heading
    heading = ""
    ch_el = soup.find(class_="chapter-heading")
    if ch_el:
        heading = ch_el.get_text(strip=True)

    book_title = ""
    bt_el = soup.find(class_="book-title")
    if bt_el:
        book_title = bt_el.get_text(strip=True)

    title = f"{book_title} - {heading}" if book_title and heading else heading or book_title

    # Extract translation paragraphs (p.trans)
    trans_els = soup.find_all("p", class_="trans")
    trans_texts = []
    for t in trans_els:
        txt = t.get_text(strip=True)
        if txt:
            trans_texts.append(txt)

    translation_text = "\n\n".join(trans_texts)
    word_count = len(translation_text.split()) if translation_text else 0

    # Extract Sanskrit shlokas (p.sans)
    sans_els = soup.find_all("p", class_="sans")
    shloka_texts = []
    for s in sans_els:
        txt = s.get_text(strip=True)
        if txt:
            shloka_texts.append(txt)

    shlokas_raw = "\n\n".join(shloka_texts)

    # Verse count
    verses = soup.find_all(class_="verse")
    verse_count = len(verses)

    # Determine status
    if word_count == 0 and len(shloka_texts) > 0:
        status = "untranslated"
    elif word_count == 0:
        status = "untranslated"
    else:
        status = "ok"

    return {
        "title": title,
        "translation_text": translation_text,
        "shlokas_raw": shlokas_raw,
        "word_count": word_count,
        "verse_count": verse_count,
        "status": status,
    }


def scrape_chapter(parvan_name: str, parvan_key: str, book_num: int,
                   ch_num: int, rate_limiter: RateLimiter) -> dict:
    """Scrape a single chapter. Returns the chapter data dict."""
    cid = chapter_id(parvan_key, ch_num)
    url = chapter_url(parvan_name, ch_num)

    rate_limiter.wait()

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        return {
            "id": cid,
            "parvan": parvan_name,
            "parvan_key": parvan_key,
            "parvan_book_num": book_num,
            "chapter_num": ch_num,
            "title": "",
            "translation_text": "",
            "shlokas_raw": "",
            "word_count": 0,
            "source_url": url,
            "scraped_at": now_iso(),
            "status": "error",
            "error_detail": str(e),
        }

    if resp.status_code == 404:
        return {
            "id": cid,
            "parvan": parvan_name,
            "parvan_key": parvan_key,
            "parvan_book_num": book_num,
            "chapter_num": ch_num,
            "title": "",
            "translation_text": "",
            "shlokas_raw": "",
            "word_count": 0,
            "source_url": url,
            "scraped_at": now_iso(),
            "status": "error",
            "error_detail": f"HTTP 404",
        }

    if resp.status_code != 200:
        return {
            "id": cid,
            "parvan": parvan_name,
            "parvan_key": parvan_key,
            "parvan_book_num": book_num,
            "chapter_num": ch_num,
            "title": "",
            "translation_text": "",
            "shlokas_raw": "",
            "word_count": 0,
            "source_url": url,
            "scraped_at": now_iso(),
            "status": "error",
            "error_detail": f"HTTP {resp.status_code}",
        }

    parsed = parse_chapter(resp.text)

    return {
        "id": cid,
        "parvan": parvan_name,
        "parvan_key": parvan_key,
        "parvan_book_num": book_num,
        "chapter_num": ch_num,
        "title": parsed["title"],
        "translation_text": parsed["translation_text"],
        "shlokas_raw": parsed["shlokas_raw"],
        "word_count": parsed["word_count"],
        "source_url": url,
        "scraped_at": now_iso(),
        "status": parsed["status"],
    }


def run_scraper(parvan_filter: str | None = None,
                dry_run: bool = False,
                resume_errors: bool = False,
                limit: int | None = None):
    """
    Scrape all chapters (or one parvan).

    Args:
        parvan_filter: If set, only scrape this parvan (by name, e.g. "Adiparvan")
        dry_run: Print URLs without fetching
        resume_errors: Only re-scrape chapters with status="error"
        limit: Max chapters to scrape in this run (for batching)
    """
    print("=" * 64)
    print("  vyasa-yt · Phase 1 · Scraper")
    print("=" * 64)

    # Build work list
    work = []
    for parvan_name, parvan_key, book_num, total in PARVANS:
        if parvan_filter and parvan_name.lower() != parvan_filter.lower():
            continue
        for ch in range(1, total + 1):
            work.append((parvan_name, parvan_key, book_num, ch))

    if not work:
        print(f"No chapters to scrape (filter={parvan_filter})")
        return

    # Filter based on existing files
    to_scrape = []
    skipped = 0
    for parvan_name, parvan_key, book_num, ch in work:
        cid = chapter_id(parvan_key, ch)
        path = CHAPTERS_DIR / f"{cid}.json"

        if path.exists():
            if resume_errors:
                existing = load_json(path)
                if existing and existing.get("status") == "error":
                    to_scrape.append((parvan_name, parvan_key, book_num, ch))
                    continue
            skipped += 1
            continue
        to_scrape.append((parvan_name, parvan_key, book_num, ch))

    # Apply --limit
    if limit and limit > 0 and len(to_scrape) > limit:
        deferred = len(to_scrape) - limit
        to_scrape = to_scrape[:limit]
        print(f"\n  --limit {limit} applied. {deferred} chapters deferred to next run.")

    print(f"\nTotal chapters: {len(work)}")
    print(f"Already saved:  {skipped}")
    print(f"To scrape:      {len(to_scrape)}")
    if to_scrape:
        est = len(to_scrape) * REQUEST_DELAY
        print(f"Estimated time: {est // 60}m {est % 60}s  ({REQUEST_DELAY}s × {len(to_scrape)} chapters)")

    if dry_run:
        print("\n  DRY RUN — printing URLs:\n")
        for parvan_name, parvan_key, book_num, ch in to_scrape[:50]:
            print(f"  {chapter_url(parvan_name, ch)}")
        if len(to_scrape) > 50:
            print(f"  ... and {len(to_scrape) - 50} more")
        return

    if not to_scrape:
        print("\nAll chapters already scraped. Use --resume to re-scrape errors.")
        return

    rate_limiter = RateLimiter(REQUEST_DELAY)
    stats = {"ok": 0, "untranslated": 0, "error": 0}

    print()
    for parvan_name, parvan_key, book_num, ch in tqdm(to_scrape, desc="Scraping"):
        data = scrape_chapter(parvan_name, parvan_key, book_num, ch, rate_limiter)
        cid = data["id"]
        save_json(CHAPTERS_DIR / f"{cid}.json", data)
        stats[data["status"]] = stats.get(data["status"], 0) + 1

    # Print summary table
    print(f"\n  Done. ok={stats['ok']}  untranslated={stats['untranslated']}  error={stats['error']}")
    print()

    # Per-parvan summary
    rows = []
    for parvan_name, parvan_key, book_num, total in PARVANS:
        if parvan_filter and parvan_name.lower() != parvan_filter.lower():
            continue
        ok = unt = err = 0
        for ch in range(1, total + 1):
            cid = chapter_id(parvan_key, ch)
            path = CHAPTERS_DIR / f"{cid}.json"
            if path.exists():
                d = load_json(path)
                if d:
                    s = d.get("status", "")
                    if s == "ok":
                        ok += 1
                    elif s == "untranslated":
                        unt += 1
                    else:
                        err += 1
        rows.append({
            "parvan": parvan_name,
            "total": total,
            "ok": ok,
            "untranslated": unt,
            "error": err,
        })

    print_status_table(rows)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Mahabharata chapters")
    parser.add_argument("--parvan", help="Scrape only this parvan")
    parser.add_argument("--dry-run", action="store_true", help="Print URLs without fetching")
    parser.add_argument("--resume", action="store_true", help="Re-scrape error chapters only")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max chapters to scrape in this run (for batching)")
    args = parser.parse_args()
    run_scraper(parvan_filter=args.parvan, dry_run=args.dry_run,
                resume_errors=args.resume, limit=args.limit)
