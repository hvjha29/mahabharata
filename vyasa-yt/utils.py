"""
vyasa-yt shared utilities — chapter ID helpers, JSON I/O, logging, progress table.
"""

import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import PARVANS, CHAPTER_URL_TEMPLATE


# ── Chapter ID helpers ─────────────────────────────────────────

def chapter_id(parvan_key: str, chapter_num: int) -> str:
    """Canonical chapter identifier, e.g. 'adiparvan_0001'."""
    return f"{parvan_key}_{chapter_num:04d}"


def chapter_filename(parvan_key: str, chapter_num: int) -> str:
    """Filename for chapter JSON, e.g. 'adiparvan_0001.json'."""
    return f"{chapter_id(parvan_key, chapter_num)}.json"


def chapter_url(parvan_name: str, chapter_num: int) -> str:
    """Full URL for a chapter page."""
    return CHAPTER_URL_TEMPLATE.format(
        parvan_name=parvan_name, chapter_num=chapter_num
    )


def bk_ref(book_num: int, chapter_num: int) -> str:
    """Internal chapter reference like 'bk01ch001'."""
    return f"bk{book_num:02d}ch{chapter_num:03d}"


# ── Parvan lookup ──────────────────────────────────────────────

def get_parvan(parvan_key: str):
    """Return (name, key, book_num, total_chapters) for a parvan key."""
    for p in PARVANS:
        if p[1] == parvan_key:
            return p
    raise ValueError(f"Unknown parvan key: {parvan_key}")


def get_parvan_by_name(parvan_name: str):
    """Return parvan tuple by display name."""
    for p in PARVANS:
        if p[0].lower() == parvan_name.lower():
            return p
    raise ValueError(f"Unknown parvan name: {parvan_name}")


# ── JSON I/O ───────────────────────────────────────────────────

def load_json(path: Path) -> Optional[dict]:
    """Load a JSON file; return None if missing."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_json(path: Path, data: dict):
    """Atomically write JSON (write to tmp then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.rename(path)


def save_text(path: Path, text: str):
    """Write text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def load_text(path: Path) -> Optional[str]:
    """Read text file; return None if missing."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


# ── Timestamps ─────────────────────────────────────────────────

def now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ── Rate limiter ───────────────────────────────────────────────

class RateLimiter:
    """Simple per-call delay."""

    def __init__(self, delay: float = 3.0):
        self.delay = delay
        self._last = 0.0

    def wait(self):
        elapsed = time.time() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last = time.time()


# ── Status table printer ──────────────────────────────────────

def print_status_table(rows: list[dict]):
    """Print a formatted ASCII table of pipeline status."""
    if not rows:
        print("No data.")
        return

    headers = list(rows[0].keys())
    col_widths = {h: max(len(h), max(len(str(r.get(h, ""))) for r in rows)) for h in headers}

    header_line = " | ".join(h.ljust(col_widths[h]) for h in headers)
    sep_line = "-+-".join("-" * col_widths[h] for h in headers)
    print(header_line)
    print(sep_line)
    for r in rows:
        print(" | ".join(str(r.get(h, "")).ljust(col_widths[h]) for h in headers))


def collect_pipeline_status():
    """Scan data/ directories and return per-parvan status rows."""
    from config import PARVANS, CHAPTERS_DIR, SCRIPTS_DIR, AUDIO_DIR, VIDEOS_DIR

    rows = []
    for parvan_name, parvan_key, book_num, total in PARVANS:
        scraped = ok = untranslated = errors = scripted = audio = video = 0
        for ch in range(1, total + 1):
            cid = chapter_id(parvan_key, ch)
            ch_file = CHAPTERS_DIR / f"{cid}.json"
            if ch_file.exists():
                scraped += 1
                data = load_json(ch_file)
                if data:
                    st = data.get("status", "")
                    if st == "ok":
                        ok += 1
                    elif st == "untranslated":
                        untranslated += 1
                    elif st == "error":
                        errors += 1
            if (SCRIPTS_DIR / f"{cid}_script.txt").exists():
                scripted += 1
            if (AUDIO_DIR / f"{cid}.mp3").exists():
                audio += 1
            if (VIDEOS_DIR / f"{cid}.mp4").exists():
                video += 1

        rows.append({
            "parvan": parvan_name,
            "total": total,
            "scraped": scraped,
            "ok": ok,
            "untranslated": untranslated,
            "error": errors,
            "scripted": scripted,
            "audio": audio,
            "video": video,
        })
    return rows
