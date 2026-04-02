#!/usr/bin/env python3
"""
Phase 4 — Video assembly.

Combines background image + audio + subtitles into a portrait-format
(1080×1920) video for each chapter.

Layout:
  - Top 12%:    Parvan name + Chapter number (saffron/gold text on dark strip)
  - Center 76%: Background image
  - Bottom 12%: Subtitle chunks (white text with drop shadow)

Uses moviepy==1.0.3 and Pillow for text rendering.
Saves to data/videos/{script_id}.mp4. Idempotent: skips if exists.
"""

import json
import sys
import textwrap
from pathlib import Path

from tqdm import tqdm

from config import (
    PARVANS, SCRIPTS_DIR, AUDIO_DIR, VIDEOS_DIR, ASSETS_DIR,
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, SUBTITLE_WORD_CHUNK,
)
from utils import chapter_id, load_text, load_json


def ensure_moviepy():
    try:
        import moviepy.editor as mpe
        return mpe
    except ImportError:
        print("ERROR: 'moviepy' not installed. pip install moviepy==1.0.3")
        sys.exit(1)


def ensure_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        print("ERROR: 'Pillow' not installed. pip install Pillow")
        sys.exit(1)


def get_background(parvan_key: str) -> Path:
    """Return background image path, with fallback to default."""
    specific = ASSETS_DIR / f"bg_{parvan_key}.jpg"
    if specific.exists():
        return specific
    default = ASSETS_DIR / "bg_default.jpg"
    if default.exists():
        return default
    # Generate a simple dark background if no image exists
    Image, ImageDraw, _ = ensure_pillow()
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color=(20, 15, 10))
    default.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(default))
    return default


def split_subtitles(text: str, words_per_chunk: int = SUBTITLE_WORD_CHUNK) -> list[str]:
    """Split script text into subtitle chunks of ~N words each."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i:i + words_per_chunk])
        chunks.append(chunk)
    return chunks


def create_frame_with_text(bg_path: Path, top_text: str, subtitle_text: str,
                           width: int, height: int) -> str:
    """
    Render a single frame as a temp image with overlaid text.
    Returns path to the rendered frame image.
    """
    Image, ImageDraw, ImageFont = ensure_pillow()

    # Load and resize background
    bg = Image.open(str(bg_path)).convert("RGB")
    bg = bg.resize((width, height), Image.LANCZOS)

    draw = ImageDraw.Draw(bg)

    # ── Top strip (12% height) ──
    top_h = int(height * 0.12)
    # Dark overlay
    overlay = Image.new("RGBA", (width, top_h), (0, 0, 0, 180))
    bg.paste(Image.alpha_composite(
        Image.new("RGBA", (width, top_h), (0, 0, 0, 0)), overlay
    ).convert("RGB"), (0, 0))

    # Top text (saffron/gold)
    try:
        font_top = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
    except (IOError, OSError):
        font_top = ImageFont.load_default()

    # Center the top text
    bbox = draw.textbbox((0, 0), top_text, font=font_top)
    tw = bbox[2] - bbox[0]
    tx = (width - tw) // 2
    ty = (top_h - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), top_text, fill=(255, 165, 0), font=font_top)

    # ── Bottom strip (12% height) ──
    bot_h = int(height * 0.12)
    bot_y = height - bot_h
    # Dark overlay
    overlay_bot = Image.new("RGBA", (width, bot_h), (0, 0, 0, 200))
    bg_rgba = bg.convert("RGBA")
    bot_section = Image.new("RGBA", (width, bot_h), (0, 0, 0, 0))
    bot_section = Image.alpha_composite(bot_section, overlay_bot)
    bg.paste(bot_section.convert("RGB"), (0, bot_y))

    draw = ImageDraw.Draw(bg)  # re-acquire after paste

    if subtitle_text:
        try:
            font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        except (IOError, OSError):
            font_sub = ImageFont.load_default()

        # Wrap text to fit width
        wrapped = textwrap.fill(subtitle_text, width=40)
        # Drop shadow
        bbox_s = draw.textbbox((0, 0), wrapped, font=font_sub)
        sw = bbox_s[2] - bbox_s[0]
        sh = bbox_s[3] - bbox_s[1]
        sx = (width - sw) // 2
        sy = bot_y + (bot_h - sh) // 2
        draw.text((sx + 2, sy + 2), wrapped, fill=(0, 0, 0), font=font_sub)
        draw.text((sx, sy), wrapped, fill=(255, 255, 255), font=font_sub)

    return bg


def build_video(script_id: str, parvan_name: str, parvan_key: str,
                chapter_label: str):
    """
    Assemble one video from audio + background + subtitles.
    """
    mpe = ensure_moviepy()

    audio_path = AUDIO_DIR / f"{script_id}.mp3"
    if not audio_path.exists():
        return False, f"Audio not found: {audio_path}"

    script_path = SCRIPTS_DIR / f"{script_id}_script.txt"
    script_text = load_text(script_path)
    if not script_text:
        return False, f"Script not found: {script_path}"

    output_path = VIDEOS_DIR / f"{script_id}.mp4"
    if output_path.exists():
        return True, "already exists"

    bg_path = get_background(parvan_key)

    # Load audio to get duration
    audio_clip = mpe.AudioFileClip(str(audio_path))
    duration = audio_clip.duration

    # Split script into subtitle chunks
    chunks = split_subtitles(script_text)
    if not chunks:
        chunks = [""]

    chunk_duration = duration / len(chunks)
    top_text = f"{parvan_name}  ·  {chapter_label}"

    # Build video as sequence of image clips with different subtitles
    clips = []
    for i, chunk in enumerate(chunks):
        frame_img = create_frame_with_text(
            bg_path, top_text, chunk,
            VIDEO_WIDTH, VIDEO_HEIGHT
        )
        # Convert PIL Image to moviepy ImageClip
        import numpy as np
        frame_array = np.array(frame_img)
        clip = mpe.ImageClip(frame_array).set_duration(chunk_duration)
        clips.append(clip)

    video = mpe.concatenate_videoclips(clips, method="compose")
    video = video.set_audio(audio_clip)

    video.write_videofile(
        str(output_path),
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        logger=None,  # suppress moviepy's verbose output
    )

    audio_clip.close()
    video.close()

    return True, "ok"


def list_audio_files() -> list[Path]:
    """Return all audio MP3 files."""
    return sorted(AUDIO_DIR.glob("*.mp3"))


def run_video_builder(parvan_filter: str | None = None, dry_run: bool = False):
    """
    Build videos for all chapters with audio.

    Args:
        parvan_filter: Only process this parvan
        dry_run: Print plan without building
    """
    print("=" * 64)
    print("  vyasa-yt · Phase 4 · Video Assembly")
    print("=" * 64)

    audio_files = list_audio_files()
    if not audio_files:
        print("\n  No audio files found. Run --audio first.")
        return

    # Filter
    if parvan_filter:
        pkey = parvan_filter.lower()
        audio_files = [a for a in audio_files if a.stem.startswith(pkey)]

    to_build = []
    skipped = 0

    for audio_path in audio_files:
        script_id = audio_path.stem  # e.g. "adiparvan_0001"
        video_path = VIDEOS_DIR / f"{script_id}.mp4"

        if video_path.exists():
            skipped += 1
            continue

        # Determine parvan info from script_id
        # Format: {parvan_key}_{chapter_num:04d} or {parvan_key}_{chapter_num:04d}_p{1|2}
        parts = script_id.split("_")
        parvan_key = parts[0]
        chapter_part = parts[1] if len(parts) >= 2 else "0001"

        # Look up parvan name
        parvan_name = parvan_key.capitalize()
        for pn, pk, bn, tc in PARVANS:
            if pk == parvan_key:
                parvan_name = pn
                break

        # Chapter label
        if "_p1" in script_id or "_p2" in script_id:
            part_num = script_id[-1]
            ch_num = chapter_part.lstrip("0") or "1"
            chapter_label = f"Chapter {ch_num} (Part {part_num})"
        else:
            ch_num = chapter_part.lstrip("0") or "1"
            chapter_label = f"Chapter {ch_num}"

        to_build.append((script_id, parvan_name, parvan_key, chapter_label))

    print(f"\n  Audio files:   {len(audio_files)}")
    print(f"  Already built: {skipped}")
    print(f"  To build:      {len(to_build)}")

    if dry_run:
        for sid, pn, pk, cl in to_build[:20]:
            print(f"    {sid} → {pn} {cl}")
        if len(to_build) > 20:
            print(f"    ... and {len(to_build) - 20} more")
        return

    if not to_build:
        print("\n  All videos already built.")
        return

    print()
    errors = 0
    for script_id, parvan_name, parvan_key, chapter_label in tqdm(to_build, desc="Video"):
        try:
            ok, msg = build_video(script_id, parvan_name, parvan_key, chapter_label)
            if not ok:
                print(f"\n  ✗ {script_id}: {msg}")
                errors += 1
        except Exception as e:
            print(f"\n  ✗ {script_id}: {e}")
            errors += 1

    print(f"\n  Done. Built: {len(to_build) - errors}  Errors: {errors}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build videos from audio + scripts")
    parser.add_argument("--parvan", help="Only this parvan")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_video_builder(parvan_filter=args.parvan, dry_run=args.dry_run)
