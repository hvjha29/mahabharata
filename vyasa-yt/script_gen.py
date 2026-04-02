#!/usr/bin/env python3
"""
Phase 2 — Script generation using HuggingFace Inference API.

Uses Qwen2.5-72B-Instruct to write ORIGINAL narration scripts from scraped
chapter reference material.  The scraped Debroy translation is used ONLY as
reference — the generated scripts are original creative works.

Sub-cases by word count:
  - word_count < 250:  combine with adjacent chapter(s) into one video
  - 250–1500:          one chapter = one video
  - > 1500:            split into two scripts

Saves to data/scripts/{id}_script.txt.  Idempotent: skips if exists.
"""

import json
import os
import sys
import time
from pathlib import Path

from tqdm import tqdm

from config import (
    PARVANS, CHAPTERS_DIR, SCRIPTS_DIR,
    MIN_WORDS_STANDALONE, MAX_WORDS_SINGLE, MAX_INPUT_CHARS,
    HF_MODEL, SYSTEM_PROMPT,
)
from utils import (
    chapter_id, load_json, save_json, save_text, load_text, now_iso,
)


# ── HuggingFace client ────────────────────────────────────────

def _get_hf_client():
    """Return a HuggingFace InferenceClient.  Requires HF_TOKEN env var."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("ERROR: Set HF_TOKEN environment variable.")
        print("  export HF_TOKEN='hf_...'")
        sys.exit(1)

    from huggingface_hub import InferenceClient
    return InferenceClient(token=token)


# ── Script generation ──────────────────────────────────────────

def generate_script(client, parvan: str, chapter_num: int,
                    translation_text: str,
                    combined_label: str | None = None) -> str:
    """
    Call Qwen2.5-72B to generate an original narration script.

    The reference text is capped at MAX_INPUT_CHARS (5,500) to leave headroom
    for the model's output.
    """
    ch_label = combined_label or f"Chapter {chapter_num}"

    # Cap reference text
    ref = translation_text[:MAX_INPUT_CHARS]
    if len(translation_text) > MAX_INPUT_CHARS:
        ref += "\n\n[Reference text truncated for length]"

    user_prompt = (
        f"Reference material for {parvan} {ch_label}:\n\n"
        f"{ref}\n\n"
        f"Write an original narration script. Do not quote or closely "
        f"paraphrase the reference text above."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat_completion(
                model=HF_MODEL,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            wait = 10 * (attempt + 1)
            print(f"\n  ⚠ API error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


# ── Planning ───────────────────────────────────────────────────

def load_all_chapters(parvan_key: str, total: int) -> list[dict]:
    """Load all scraped chapter data for a parvan, in order."""
    chapters = []
    for ch in range(1, total + 1):
        cid = chapter_id(parvan_key, ch)
        path = CHAPTERS_DIR / f"{cid}.json"
        data = load_json(path)
        if data:
            chapters.append(data)
    return chapters


def plan_scripts(chapters: list[dict]) -> list[dict]:
    """
    Plan which chapters become which scripts, handling combining/splitting.
    """
    plans = []
    i = 0

    while i < len(chapters):
        ch = chapters[i]
        if ch["status"] != "ok":
            i += 1
            continue

        wc = ch["word_count"]

        if wc < MIN_WORDS_STANDALONE:
            # Combine with subsequent short chapters
            combined_ids = [ch["id"]]
            combined_nums = [ch["chapter_num"]]
            combined_text = ch["translation_text"]
            total_wc = wc
            j = i + 1
            while j < len(chapters) and total_wc < MIN_WORDS_STANDALONE:
                next_ch = chapters[j]
                if next_ch["status"] != "ok":
                    j += 1
                    continue
                combined_ids.append(next_ch["id"])
                combined_nums.append(next_ch["chapter_num"])
                combined_text += "\n\n" + next_ch["translation_text"]
                total_wc += next_ch["word_count"]
                j += 1

            label = (f"Chapters {combined_nums[0]}–{combined_nums[-1]}"
                     if len(combined_nums) > 1 else None)
            plans.append({
                "script_id": combined_ids[0],
                "chapter_ids": combined_ids,
                "chapters": combined_nums,
                "combined_label": label,
                "translation_text": combined_text,
                "parvan": ch["parvan"],
                "split_part": None,
                "action": "combine" if len(combined_ids) > 1 else "single",
            })
            i = j

        elif wc > MAX_WORDS_SINGLE:
            # Split at a paragraph break near the middle
            text = ch["translation_text"]
            paras = text.split("\n\n")
            half_wc, split_idx = 0, 0
            for pi, para in enumerate(paras):
                half_wc += len(para.split())
                if half_wc >= wc // 2:
                    split_idx = pi + 1
                    break
            part1 = "\n\n".join(paras[:split_idx])
            part2 = "\n\n".join(paras[split_idx:])

            for part_num, part_text in [(1, part1), (2, part2)]:
                plans.append({
                    "script_id": f"{ch['id']}_p{part_num}",
                    "chapter_ids": [ch["id"]],
                    "chapters": [ch["chapter_num"]],
                    "combined_label": f"Chapter {ch['chapter_num']} (Part {part_num})",
                    "translation_text": part_text,
                    "parvan": ch["parvan"],
                    "split_part": part_num,
                    "action": "split",
                })
            i += 1

        else:
            plans.append({
                "script_id": ch["id"],
                "chapter_ids": [ch["id"]],
                "chapters": [ch["chapter_num"]],
                "combined_label": None,
                "translation_text": ch["translation_text"],
                "parvan": ch["parvan"],
                "split_part": None,
                "action": "single",
            })
            i += 1

    return plans


# ── Runner ─────────────────────────────────────────────────────

def run_script_gen(parvan_filter: str | None = None,
                   dry_run: bool = False,
                   limit: int | None = None):
    """
    Generate narration scripts for all scraped chapters.

    Args:
        parvan_filter: Only process this parvan (by name)
        dry_run: Print plan without calling the model
        limit: Max scripts to generate in this run (for batching)
    """
    print("=" * 64)
    print(f"  vyasa-yt · Phase 2 · Script Generation")
    print(f"  Model: {HF_MODEL}")
    print("=" * 64)

    if not dry_run:
        client = _get_hf_client()
    else:
        client = None

    total_generated = 0
    total_skipped = 0

    for parvan_name, parvan_key, book_num, total in PARVANS:
        if parvan_filter and parvan_name.lower() != parvan_filter.lower():
            continue

        print(f"\n  {parvan_name} ({total} chapters)")
        chapters = load_all_chapters(parvan_key, total)
        if not chapters:
            print("    No scraped chapters found. Run --scrape first.")
            continue

        plans = plan_scripts(chapters)
        singles   = sum(1 for p in plans if p["action"] == "single")
        combines  = sum(1 for p in plans if p["action"] == "combine")
        splits    = sum(1 for p in plans if p["action"] == "split")
        print(f"    Plans: {len(plans)} scripts "
              f"({singles} single, {combines} combined, {splits} split parts)")

        if dry_run:
            for p in plans[:15]:
                print(f"    {p['script_id']:30s} [{p['action']:7s}] ch{p['chapters']}")
            if len(plans) > 15:
                print(f"    ... and {len(plans) - 15} more")
            continue

        for plan in tqdm(plans, desc=f"  {parvan_name}", leave=False):
            # Respect --limit
            if limit is not None and total_generated >= limit:
                break

            script_path = SCRIPTS_DIR / f"{plan['script_id']}_script.txt"
            if script_path.exists():
                total_skipped += 1
                continue

            try:
                script = generate_script(
                    client,
                    parvan=plan["parvan"],
                    chapter_num=plan["chapters"][0],
                    translation_text=plan["translation_text"],
                    combined_label=plan["combined_label"],
                )
                save_text(script_path, script)

                # Save metadata sidecar
                meta = {
                    "script_id": plan["script_id"],
                    "chapter_ids": plan["chapter_ids"],
                    "chapters": plan["chapters"],
                    "combined_label": plan["combined_label"],
                    "parvan": plan["parvan"],
                    "split_part": plan["split_part"],
                    "action": plan["action"],
                    "generated_at": now_iso(),
                    "model": HF_MODEL,
                }
                save_json(SCRIPTS_DIR / f"{plan['script_id']}_meta.json", meta)
                total_generated += 1

                # Small inter-request pause
                time.sleep(2)

            except Exception as e:
                print(f"\n    ✗ Error generating {plan['script_id']}: {e}")

    print(f"\n  Generated: {total_generated}  Skipped: {total_skipped}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate narration scripts")
    parser.add_argument("--parvan", help="Only this parvan")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max scripts to generate (for batching)")
    args = parser.parse_args()
    run_script_gen(parvan_filter=args.parvan, dry_run=args.dry_run,
                   limit=args.limit)
