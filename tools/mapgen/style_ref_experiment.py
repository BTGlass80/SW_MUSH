"""tools/mapgen/style_ref_experiment.py — the STYLE-REFERENCE map experiment,
made reproducible (handoff §3d: "the prior temp script wasn't persisted —
rebuild it").

THE EXPERIMENT
--------------
The hand-made `static/maps/mos_eisley_substrate.png` still beats every automated
candidate (verdict: don't switch for launch). The one untried high-value lever
is STYLE-REFERENCE: feed the existing painterly plate as the art-style anchor
(the 2nd image in the Gemini call) so output is pulled toward painterly + away
from the tactical-grid / VTT look the schematic seed induces on its own.

This script wraps the three setup steps that the stock CLI does NOT do, runs the
batch, and RESTORES everything (non-destructive — the seed/brief/keymap are
git-tracked and overwritten only transiently):

  1. Regenerate the city tight-seed with a WARM-DESERT hue override (drops the
     slate-blue index-0 district that Gemini paints as WATER; mutes the bright
     gold landmark tokens). This is the proven water fix (iteration 2).
  2. Swap in the NAMELESS + dual-image style brief
     (mos_eisley_paint_brief.styleref.md) — strips proper-noun labels and tells
     Gemini that image 1 = layout, image 2 = style.
  3. Run BatchOrchestrator with `style_reference_image=` the hand-made plate.

COST / KEYS (Brian's guardrails, 2026-06-18)
--------------------------------------------
  • Nano = LIVE on the GEMINI maps budget ($10, funded for exactly this). The
    key is read from GEMINI_API_KEY / GOOGLE_API_KEY in the ENV ONLY — never
    written to disk, never committed.
  • Screening = OFF by default. The Anthropic key is reserved for timers +
    Director AI; the VISUAL QA is done by the Opus session (free on the Max
    sub), not the metered Haiku screener. `--screen` opts the Haiku screener
    back in if you want a cheap automated cross-check (one call per candidate).

Usage:
  GEMINI_API_KEY=... python -m tools.mapgen.style_ref_experiment \
      --timestamp styleref1 --n 6
  # control arm (same desert seed + nameless brief, NO style anchor):
  GEMINI_API_KEY=... python -m tools.mapgen.style_ref_experiment \
      --timestamp nostyle1 --n 4 --no-style
  # offline pipeline smoke (no key, placeholder images):
  python -m tools.mapgen.style_ref_experiment --timestamp dry1 --n 2 --mock
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import paths
from .batch import BatchOrchestrator


# Warm-desert district palette (index 0 is NOT cool/blue) — every hue reads as
# sand / ochre / rock, so no zone gets painted as water, while staying
# distinguishable so the seed still reads as SEPARATE zones.
WARM_DESERT_HUES = [
    (158, 134, 96),   # warm sand
    (138, 112, 80),   # tan
    (150, 120, 92),   # dusty ochre
    (128, 118, 88),   # khaki-olive
    (146, 116, 84),   # adobe
    (120, 100, 80),   # canyon rock
    (162, 142, 110),  # pale dune
]
# Muted, warm landmark markers (the bright gold/cool-grey defaults read as VTT
# tokens / could pull cool). Still visible enough to place features.
WARM_LM_DIST = (196, 150, 96)   # muted terracotta (default: bright gold)
WARM_LM_GEN = (150, 138, 116)   # muted warm grey (default: cool grey-blue)

DEFAULT_STYLE_PLATE = paths.MAPS_DIR / "mos_eisley_substrate.png"
STYLEREF_BRIEF_SUFFIX = "_paint_brief.styleref.md"


def _styleref_brief_for(area_key: str) -> Path:
    return paths.SEEDS_DIR / f"{area_key.replace('.', '_')}{STYLEREF_BRIEF_SUFFIX}"


def _seed_siblings(area_key: str) -> list[Path]:
    """The on-disk artifacts the desert-seed regeneration overwrites — the tight
    seed Nano reads AND the tight keymap (reference). Both restored after."""
    base = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    return [
        paths.SEEDS_DIR / f"{base}_tight_seed.png",
        paths.SEEDS_DIR / f"{base}_tight_keymap.png",
    ]


def regenerate_desert_seed(area_key: str, era: str = "clone_wars",
                           long_edge: int = 2048) -> None:
    """Overwrite the city tight-seed/keymap with the WARM-DESERT hue override by
    monkeypatching make_substrate_seed's module globals around one render() call,
    then restoring them. The seed is written to its canonical path so the
    orchestrator (which reads paths.seed_for) picks it up with no redirection."""
    import tools.make_substrate_seed as mss
    base = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    saved = (mss.DISTRICT_HUES, mss.LM_DIST, mss.LM_GEN)
    try:
        mss.DISTRICT_HUES = list(WARM_DESERT_HUES)
        mss.LM_DIST = WARM_LM_DIST
        mss.LM_GEN = WARM_LM_GEN
        mss.render(base, era=era, root="data/worlds",
                   out=str(paths.SEEDS_DIR), long_edge=long_edge, tight=True)
    finally:
        mss.DISTRICT_HUES, mss.LM_DIST, mss.LM_GEN = saved


def _backup(files: list[Path], backup_dir: Path) -> dict:
    """Copy each existing file into backup_dir; return {orig: backup}."""
    mapping = {}
    for f in files:
        if f.exists():
            b = backup_dir / f.name
            shutil.copy2(f, b)
            mapping[f] = b
    return mapping


def _restore(mapping: dict) -> None:
    for orig, bak in mapping.items():
        try:
            shutil.copy2(bak, orig)
        except OSError as e:  # best-effort; git-tracked files recover via checkout
            print(f"[styleref] WARN could not restore {orig.name}: {e}",
                  file=sys.stderr)


def _build_clients(use_mock: bool, use_screen: bool):
    """Return (nano_client, screener_provider, banner). Screening is OFF unless
    --screen (Anthropic reserved for timers/Director; visual QA is in-session)."""
    if use_mock:
        from .nano_client import MockNanoClient
        nano, n_tag = MockNanoClient(), "Nano=MOCK"
    elif paths.has_google_key():
        import os
        from .nano_client import NanoClient
        key = (os.environ.get("GOOGLE_API_KEY", "").strip()
               or os.environ.get("GEMINI_API_KEY", "").strip())
        nano, n_tag = NanoClient(api_key=key), "Nano=LIVE"
    else:
        nano, n_tag = None, "Nano=ABSENT"  # caller errors out below

    provider, s_tag = None, "Screen=OFF(visual-QA-in-session)"
    if use_screen and paths.has_anthropic_key():
        try:
            from ai.claude_provider import make_claude_provider
            provider = make_claude_provider()
            s_tag = "Screen=LIVE(haiku,minimal)" if provider else "Screen=OFF(no-provider)"
        except Exception:
            s_tag = "Screen=OFF(import-failed)"
    return nano, provider, f"{n_tag} | {s_tag} | Coord=NoOp(frozen)"


async def run_experiment(area_key: str, *, timestamp: str, n_candidates: int,
                         era: str, style_plate: Optional[Path],
                         long_edge: int, use_mock: bool, use_screen: bool):
    """Set up the desert seed + nameless style brief, run the batch with the
    style anchor, and restore the originals in a finally. Returns the
    BatchResult."""
    nano, provider, banner = _build_clients(use_mock, use_screen)
    print(f"[styleref] mode: {banner}")
    if nano is None:
        print("[styleref] ERROR: live run requested but no GEMINI_API_KEY/"
              "GOOGLE_API_KEY in env. Pass --mock for an offline pipeline smoke, "
              "or set the key (env ONLY — never commit it).", file=sys.stderr)
        return None

    styleref_brief = _styleref_brief_for(area_key)
    if not styleref_brief.exists():
        print(f"[styleref] ERROR: missing style brief {styleref_brief}",
              file=sys.stderr)
        return None
    live_brief = paths.brief_for(area_key)

    # Back up everything we transiently overwrite so the test is non-destructive.
    targets = _seed_siblings(area_key) + [live_brief]
    backup_dir = Path(tempfile.mkdtemp(prefix="styleref_bak_"))
    backups = _backup(targets, backup_dir)

    try:
        print(f"[styleref] regenerating warm-desert seed for {area_key} …")
        regenerate_desert_seed(area_key, era=era, long_edge=long_edge)
        print(f"[styleref] swapping in nameless style brief "
              f"({styleref_brief.name} -> {live_brief.name}) …")
        shutil.copy2(styleref_brief, live_brief)

        if style_plate is not None and not style_plate.exists():
            print(f"[styleref] WARN style plate {style_plate} missing — running "
                  f"WITHOUT a style anchor.", file=sys.stderr)
            style_plate = None
        print(f"[styleref] style anchor: "
              f"{style_plate if style_plate else '(none — control arm)'}")

        orch = BatchOrchestrator(area_key, era=era, nano_client=nano,
                                 screener_provider=provider)
        result = await orch.run_batch(
            n_candidates=n_candidates, timestamp=timestamp,
            style_reference_image=style_plate, verified_stamp=timestamp)
        return result
    finally:
        _restore(backups)
        shutil.rmtree(backup_dir, ignore_errors=True)
        print("[styleref] restored original seed/keymap/brief.")


def _print_result(result) -> None:
    if result is None:
        return
    print(f"\n[styleref] {result.area_key} — {len(result.candidates)} candidate(s):")
    by_id = {c.id: c for c in result.candidates}
    for rank, cid in enumerate(result.top_k, 1):
        c = by_id[cid]
        flags = ",".join(c.verdict.get("flags", [])) or "-"
        print(f"  {rank}. {cid}  screen={c.ai_screen_score:5.1f}  "
              f"flags=[{flags}]  rungs={c.rungs_used}  {c.notes}")
    print(f"\n[styleref] candidates in: "
          f"{paths.batch_dir(result.area_key, result.timestamp) / 'candidates'}")
    print(f"[styleref] manifest: {result.manifest_path}")
    print("[styleref] NEXT: visually inspect the PNGs vs the hand-made plate; "
          "DO NOT `select` (overwrite a substrate) without Brian's approval.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools.mapgen.style_ref_experiment")
    ap.add_argument("--area", default="mos_eisley",
                    help="area key (city slug), e.g. mos_eisley")
    ap.add_argument("--timestamp", required=True, help="batch id (deterministic/resume)")
    ap.add_argument("--n", type=int, default=6, help="candidates to generate")
    ap.add_argument("--era", default="clone_wars")
    ap.add_argument("--long", type=int, default=2048, help="seed long-edge px")
    ap.add_argument("--style", default="",
                    help="style-plate PNG (default: the area's hand-made substrate)")
    ap.add_argument("--no-style", action="store_true",
                    help="control arm: same desert seed + nameless brief, NO anchor")
    ap.add_argument("--mock", action="store_true",
                    help="offline pipeline smoke (placeholder images, no key/cost)")
    ap.add_argument("--screen", action="store_true",
                    help="opt the cheap Haiku screener back in (one call/candidate)")
    args = ap.parse_args(argv)

    if args.no_style:
        style_plate = None
    elif args.style:
        style_plate = Path(args.style)
    else:
        style_plate = (paths.MAPS_DIR / f"{args.area}_substrate.png")

    result = asyncio.run(run_experiment(
        args.area, timestamp=args.timestamp, n_candidates=args.n, era=args.era,
        style_plate=style_plate, long_edge=args.long,
        use_mock=args.mock, use_screen=args.screen))
    _print_result(result)
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
