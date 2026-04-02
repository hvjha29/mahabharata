#!/usr/bin/env python3
"""
Phase 3 — Text-to-Speech.

Converts narration scripts to MP3 audio using gTTS.
Saves to data/audio/{script_id}.mp3. Idempotent: skips if exists.

NOTE: gTTS produces functional but robotic audio. For channel quality,
upgrade to ElevenLabs with voice "Adam" or "Daniel":
  pip install elevenlabs
  set ELEVENLABS_API_KEY
"""

import sys
from pathlib import Path

from tqdm import tqdm

from config import PARVANS, SCRIPTS_DIR, AUDIO_DIR, TTS_LANG, TTS_SLOW
from utils import chapter_id, load_text


def synthesize_gtts(text: str, output_path: Path):
    """Generate MP3 from text using gTTS."""
    try:
        from gtts import gTTS
    except ImportError:
        print("ERROR: 'gTTS' not installed. pip install gTTS")
        sys.exit(1)

    tts = gTTS(text=text, lang=TTS_LANG, slow=TTS_SLOW)
    tts.save(str(output_path))


def list_scripts() -> list[Path]:
    """Return all script text files, sorted."""
    return sorted(SCRIPTS_DIR.glob("*_script.txt"))


def run_tts(parvan_filter: str | None = None, dry_run: bool = False):
    """
    Convert all scripts to audio.

    Args:
        parvan_filter: Only process scripts for this parvan
        dry_run: Print files without synthesizing
    """
    print("=" * 64)
    print("  vyasa-yt · Phase 3 · Text-to-Speech")
    print("=" * 64)

    scripts = list_scripts()
    if not scripts:
        print("\n  No scripts found. Run --scripts first.")
        return

    # Filter by parvan if requested
    if parvan_filter:
        pkey = parvan_filter.lower()
        scripts = [s for s in scripts if s.stem.startswith(pkey)]

    to_process = []
    skipped = 0

    for script_path in scripts:
        # Script filename: {script_id}_script.txt → audio: {script_id}.mp3
        script_id = script_path.stem.replace("_script", "")
        audio_path = AUDIO_DIR / f"{script_id}.mp3"

        if audio_path.exists():
            skipped += 1
            continue

        to_process.append((script_path, script_id, audio_path))

    print(f"\n  Total scripts: {len(scripts)}")
    print(f"  Already done:  {skipped}")
    print(f"  To synthesize: {len(to_process)}")

    if dry_run:
        for sp, sid, ap in to_process[:20]:
            print(f"    {sid} → {ap.name}")
        if len(to_process) > 20:
            print(f"    ... and {len(to_process) - 20} more")
        return

    if not to_process:
        print("\n  All audio files already generated.")
        return

    print()
    errors = 0
    for script_path, script_id, audio_path in tqdm(to_process, desc="TTS"):
        text = load_text(script_path)
        if not text or not text.strip():
            print(f"\n  ⚠ Empty script: {script_id}")
            errors += 1
            continue

        try:
            synthesize_gtts(text, audio_path)
        except Exception as e:
            print(f"\n  ✗ Error for {script_id}: {e}")
            errors += 1

    print(f"\n  Done. Synthesized: {len(to_process) - errors}  Errors: {errors}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate TTS audio from scripts")
    parser.add_argument("--parvan", help="Only this parvan")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_tts(parvan_filter=args.parvan, dry_run=args.dry_run)
