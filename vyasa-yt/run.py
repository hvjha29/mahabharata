#!/usr/bin/env python3
"""
vyasa-yt — Mahābhārata chapter-to-YouTube pipeline orchestrator.

Usage:
  python run.py --probe                          Phase 0: test site structure
  python run.py --scrape [--parvan Adiparvan]    Phase 1: scrape chapters
  python run.py --scripts [--parvan Adiparvan]   Phase 2: generate narration scripts
  python run.py --audio [--parvan Adiparvan]     Phase 3: text-to-speech
  python run.py --video [--parvan Adiparvan]     Phase 4: video assembly
  python run.py --metadata [--parvan Adiparvan]  Phase 5: YouTube metadata
  python run.py --all [--parvan Adiparvan]       All phases (1–5)
  python run.py --status                         Pipeline status table
  python run.py --resume                         Re-run error items only
  python run.py --dry-run --scrape               Print URLs/plans without executing
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="vyasa-yt: Mahābhārata → YouTube narration pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Phase flags
    parser.add_argument("--probe", action="store_true",
                        help="Phase 0: probe site structure")
    parser.add_argument("--scrape", action="store_true",
                        help="Phase 1: scrape chapters")
    parser.add_argument("--scripts", action="store_true",
                        help="Phase 2: generate narration scripts (HuggingFace)")
    parser.add_argument("--audio", action="store_true",
                        help="Phase 3: text-to-speech (gTTS)")
    parser.add_argument("--video", action="store_true",
                        help="Phase 4: video assembly (moviepy)")
    parser.add_argument("--metadata", action="store_true",
                        help="Phase 5: YouTube metadata generation (HuggingFace)")
    parser.add_argument("--all", action="store_true",
                        help="Run phases 1–5 sequentially")
    parser.add_argument("--status", action="store_true",
                        help="Print pipeline status table")

    # Modifiers
    parser.add_argument("--parvan", type=str, default=None,
                        help="Filter to a single parvan (e.g. 'Adiparvan')")
    parser.add_argument("--resume", action="store_true",
                        help="Re-process only error/failed items")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max items to process per phase (for batching)")

    args = parser.parse_args()

    # No flags → show help
    if not any([args.probe, args.scrape, args.scripts, args.audio,
                args.video, args.metadata, args.all, args.status]):
        parser.print_help()
        sys.exit(0)

    # ── Phase 0: Probe ──
    if args.probe:
        from probe import run_probe
        run_probe()
        return

    # ── Status ──
    if args.status:
        from utils import collect_pipeline_status, print_status_table
        rows = collect_pipeline_status()
        print("\n  vyasa-yt Pipeline Status\n")
        print_status_table(rows)
        # Totals
        print()
        totals = {}
        for key in rows[0]:
            if key == "parvan":
                continue
            totals[key] = sum(r[key] for r in rows)
        print(f"  TOTAL: {totals.get('total', 0)} chapters | "
              f"scraped={totals.get('scraped', 0)} | "
              f"ok={totals.get('ok', 0)} | "
              f"untranslated={totals.get('untranslated', 0)} | "
              f"error={totals.get('error', 0)} | "
              f"scripted={totals.get('scripted', 0)} | "
              f"audio={totals.get('audio', 0)} | "
              f"video={totals.get('video', 0)}")
        return

    # ── Determine which phases to run ──
    phases = []
    if args.all:
        phases = ["scrape", "scripts", "audio", "video", "metadata"]
    else:
        if args.scrape:
            phases.append("scrape")
        if args.scripts:
            phases.append("scripts")
        if args.audio:
            phases.append("audio")
        if args.video:
            phases.append("video")
        if args.metadata:
            phases.append("metadata")

    for phase in phases:
        print(f"\n{'━' * 64}")
        print(f"  Running phase: {phase}")
        print(f"{'━' * 64}\n")

        if phase == "scrape":
            from scraper import run_scraper
            run_scraper(
                parvan_filter=args.parvan,
                dry_run=args.dry_run,
                resume_errors=args.resume,
                limit=args.limit,
            )

        elif phase == "scripts":
            from script_gen import run_script_gen
            run_script_gen(
                parvan_filter=args.parvan,
                dry_run=args.dry_run,
                limit=args.limit,
            )

        elif phase == "audio":
            from tts import run_tts
            run_tts(
                parvan_filter=args.parvan,
                dry_run=args.dry_run,
            )

        elif phase == "video":
            from video_builder import run_video_builder
            run_video_builder(
                parvan_filter=args.parvan,
                dry_run=args.dry_run,
            )

        elif phase == "metadata":
            from metadata_gen import run_metadata_gen
            run_metadata_gen(
                parvan_filter=args.parvan,
                dry_run=args.dry_run,
                limit=args.limit,
            )

    print(f"\n{'━' * 64}")
    print(f"  All requested phases complete.")
    print(f"{'━' * 64}\n")


if __name__ == "__main__":
    main()
