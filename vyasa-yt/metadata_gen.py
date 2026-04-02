#!/usr/bin/env python3
"""
Phase 5 — YouTube metadata generation using HuggingFace Inference API.

Uses Qwen2.5-72B-Instruct to generate YouTube-optimised title, description,
tags, and playlist assignment for each video.

JSON extraction strategy: direct parse → find {...} → deterministic fallback.
Never crashes on malformed model output.

Saves to data/metadata/{script_id}_meta.json.  Idempotent: skips if exists.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from tqdm import tqdm

from config import (
    PARVANS, SCRIPTS_DIR, METADATA_DIR,
    HF_MODEL, METADATA_SYSTEM_PROMPT,
)
from utils import load_text, load_json, save_json, now_iso


# ── HuggingFace client ────────────────────────────────────────

def _get_hf_client():
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("ERROR: Set HF_TOKEN environment variable.")
        print("  export HF_TOKEN='hf_...'")
        sys.exit(1)

    from huggingface_hub import InferenceClient
    return InferenceClient(token=token)


# ── Fallback template ─────────────────────────────────────────

def _fallback_metadata(script_id: str, parvan_name: str,
                       chapter_label: str, script_text: str,
                       combined: list[str]) -> dict:
    """
    Deterministic fallback metadata — guaranteed valid structure.
    Used when model output is malformed.
    """
    # Extract likely character names from the script
    common = {"The", "This", "That", "With", "From", "Into", "Upon", "What",
              "When", "Where", "Why", "How", "There", "Their", "They", "Then",
              "And", "But", "For", "Not", "Are", "Was", "Were", "Has", "Had",
              "His", "Her", "She", "Him", "Part", "Chapter", "Book", "Yet",
              "After", "Before", "While", "Every", "Each", "Some"}
    words = set(re.findall(r'\b[A-Z][a-zā-ūṁñṇṣṭḍ]{2,}\b', script_text))
    names = sorted(w for w in words if w not in common)[:6]

    tags = (["Mahabharata", parvan_name, chapter_label, "Vyasa",
             "Hindu epic", "Sanskrit epic", "BORI Critical Edition",
             "Indian mythology", "Dharma", "Education"] + names)[:15]

    first_sentence = (script_text.split(".")[0].strip() + "."
                      if script_text else "")
    desc = (
        f"{first_sentence} "
        f"Original narration of events from {parvan_name} {chapter_label} "
        f"of the Mahābhārata, based on the BORI Critical Edition. "
        f"This channel presents the complete Mahābhārata, chapter by chapter."
    )

    return {
        "video_id": script_id,
        "yt_title": f"Mahābhārata | {parvan_name} | {chapter_label}",
        "yt_description": desc[:500],
        "yt_tags": tags,
        "yt_category": "Education",
        "playlist": parvan_name,
        "combined_chapters": combined,
        "generated_by": "fallback_template",
        "generated_at": now_iso(),
    }


# ── JSON extraction ───────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """
    Try to pull a JSON object from model output.
    Strategy: direct parse → code-fence block → outermost { ... }.
    """
    # 1) Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) ```json ... ```
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Outermost braces
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass

    return None


# ── Generation ─────────────────────────────────────────────────

def generate_metadata(client, script_id: str, parvan_name: str,
                      chapter_label: str, script_text: str,
                      combined: list[str]) -> dict:
    """
    Generate YouTube metadata via Qwen2.5-72B.
    Falls back to deterministic template on any failure or malformed output.
    """
    excerpt = script_text[:3000]

    user_prompt = (
        f"Parvan: {parvan_name}\n"
        f"Chapter: {chapter_label}\n"
        f"Video ID: {script_id}\n\n"
        f"Narration script:\n{excerpt}\n\n"
        f"Generate YouTube metadata as a JSON object with keys: "
        f"yt_title, yt_description, yt_tags, yt_category, playlist.\n"
        f"Return ONLY the JSON object."
    )

    messages = [
        {"role": "system", "content": METADATA_SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        response = client.chat_completion(
            model=HF_MODEL,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        parsed = _extract_json(raw)

        if parsed and "yt_title" in parsed:
            tagline = ("This channel presents the complete Mahābhārata, "
                       "chapter by chapter.")
            desc = parsed.get("yt_description", "")
            if tagline not in desc:
                desc = desc.rstrip(". ") + ". " + tagline

            return {
                "video_id": script_id,
                "yt_title": str(parsed.get("yt_title", ""))[:100],
                "yt_description": desc[:500],
                "yt_tags": list(parsed.get("yt_tags", []))[:15],
                "yt_category": parsed.get("yt_category", "Education"),
                "playlist": parsed.get("playlist", parvan_name),
                "combined_chapters": combined,
                "generated_by": "qwen2.5-72b",
                "generated_at": now_iso(),
            }
        else:
            print(f"  ⚠ JSON parse failed for {script_id}, using fallback")
            return _fallback_metadata(script_id, parvan_name, chapter_label,
                                      script_text, combined)
    except Exception as e:
        print(f"  ⚠ API error for {script_id}: {e}, using fallback")
        return _fallback_metadata(script_id, parvan_name, chapter_label,
                                  script_text, combined)


# ── Runner ─────────────────────────────────────────────────────

def run_metadata_gen(parvan_filter: str | None = None,
                     dry_run: bool = False,
                     limit: int | None = None):
    """Generate YouTube metadata for all scripts."""
    print("=" * 64)
    print(f"  vyasa-yt · Phase 5 · Metadata Generation")
    print(f"  Model: {HF_MODEL}")
    print("=" * 64)

    if not dry_run:
        client = _get_hf_client()
    else:
        client = None

    scripts = sorted(SCRIPTS_DIR.glob("*_script.txt"))
    if not scripts:
        print("\n  No scripts found. Run --scripts first.")
        return

    if parvan_filter:
        pkey = parvan_filter.lower()
        scripts = [s for s in scripts if s.stem.startswith(pkey)]

    to_generate = []
    skipped = 0

    for script_path in scripts:
        script_id = script_path.stem.replace("_script", "")
        meta_path = METADATA_DIR / f"{script_id}_meta.json"

        if meta_path.exists():
            skipped += 1
            continue

        # Parse parvan info from script_id
        parts = script_id.split("_")
        parvan_key = parts[0]
        parvan_name = parvan_key.capitalize()
        for pn, pk, bn, tc in PARVANS:
            if pk == parvan_key:
                parvan_name = pn
                break

        chapter_part = parts[1] if len(parts) >= 2 else "0001"
        if "_p1" in script_id or "_p2" in script_id:
            part_num = script_id[-1]
            ch_num = chapter_part.lstrip("0") or "1"
            chapter_label = f"Chapter {ch_num} (Part {part_num})"
        else:
            ch_num = chapter_part.lstrip("0") or "1"
            chapter_label = f"Chapter {ch_num}"

        # Load combined-chapters list from script sidecar
        script_meta_path = SCRIPTS_DIR / f"{script_id}_meta.json"
        combined = []
        sm = load_json(script_meta_path)
        if sm:
            combined = sm.get("chapter_ids", [])

        to_generate.append((script_path, script_id, parvan_name,
                            chapter_label, combined))

    # Apply --limit
    if limit and limit > 0 and len(to_generate) > limit:
        deferred = len(to_generate) - limit
        to_generate = to_generate[:limit]
        print(f"\n  --limit {limit} applied. {deferred} items deferred.")

    print(f"\n  Total scripts: {len(scripts)}")
    print(f"  Already done:  {skipped}")
    print(f"  To generate:   {len(to_generate)}")

    if dry_run:
        for _, sid, pn, cl, _ in to_generate[:20]:
            print(f"    {sid} → {pn} {cl}")
        if len(to_generate) > 20:
            print(f"    ... and {len(to_generate) - 20} more")
        return

    if not to_generate:
        print("\n  All metadata already generated.")
        return

    print()
    generated = fallbacks = errors = 0
    for script_path, script_id, parvan_name, chapter_label, combined in tqdm(
        to_generate, desc="Metadata"
    ):
        script_text = load_text(script_path)
        if not script_text:
            errors += 1
            continue

        meta = generate_metadata(
            client, script_id, parvan_name, chapter_label,
            script_text, combined,
        )
        save_json(METADATA_DIR / f"{script_id}_meta.json", meta)

        if meta.get("generated_by") == "fallback_template":
            fallbacks += 1
        else:
            generated += 1

        time.sleep(2)

    print(f"\n  Done. model={generated}  fallback={fallbacks}  errors={errors}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate YouTube metadata")
    parser.add_argument("--parvan", help="Only this parvan")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max items to generate (for batching)")
    args = parser.parse_args()
    run_metadata_gen(parvan_filter=args.parvan, dry_run=args.dry_run,
                     limit=args.limit)
