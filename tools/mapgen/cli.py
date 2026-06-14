"""tools/mapgen/cli.py — entry point for the map-automation framework.

  python -m tools.mapgen.cli paint  --area tatooine.mos_eisley --n 6 [--style ref.png]
  python -m tools.mapgen.cli select --area tatooine.mos_eisley --batch <ts> --candidate cand_03

Auto-selects REAL clients when GOOGLE_API_KEY / ANTHROPIC_API_KEY are present;
otherwise runs in OFFLINE MOCK mode (clearly bannered). Coordinate scoring is
the NoOp stub until coord exports are frozen.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import paths
from .batch import BatchOrchestrator, BatchResult, CandidateArtifact, select_painting


def _make_clients():
    """Return (nano_client, screener_provider, mode_banner). Real when keys
    present, else Mock/None (offline)."""
    nano = None
    provider = None
    live = []
    if paths.has_google_key():
        from .nano_client import NanoClient
        import os
        key = (os.environ.get("GOOGLE_API_KEY", "").strip()
               or os.environ.get("GEMINI_API_KEY", "").strip())
        nano = NanoClient(api_key=key)
        live.append("Nano=LIVE")
    else:
        live.append("Nano=MOCK")
    if paths.has_anthropic_key():
        try:
            from ai.claude_provider import make_claude_provider
            provider = make_claude_provider()
            live.append("Screen=LIVE" if provider else "Screen=MOCK(no provider)")
        except Exception:
            live.append("Screen=MOCK(import failed)")
    else:
        live.append("Screen=MOCK")
    live.append("Coord=NoOp(frozen)")
    return nano, provider, " | ".join(live)


def _paint(args) -> int:
    nano, provider, banner = _make_clients()
    print(f"[mapgen] mode: {banner}")
    if not paths.has_google_key():
        print("[mapgen] OFFLINE MOCK mode — no GOOGLE_API_KEY; generating "
              "placeholder candidates to exercise the pipeline.")
    orch = BatchOrchestrator(args.area, era=args.era,
                             nano_client=nano, screener_provider=provider)
    style = Path(args.style) if args.style else None
    result = asyncio.run(orch.run_batch(
        n_candidates=args.n, timestamp=args.timestamp,
        style_reference_image=style, verified_stamp=args.timestamp))
    _print_ranking(result)
    print(f"[mapgen] batch manifest: {result.manifest_path}")
    return 0


def _print_ranking(result: BatchResult) -> None:
    print(f"\n[mapgen] {result.area_key} — {len(result.candidates)} candidate(s), "
          f"ranked:")
    by_id = {c.id: c for c in result.candidates}
    for rank, cid in enumerate(result.top_k, 1):
        c: CandidateArtifact = by_id[cid]
        flags = ",".join(c.verdict.get("flags", [])) or "-"
        print(f"  {rank}. {cid}  composite={c.composite_rank:5.1f}  "
              f"screen={c.ai_screen_score:5.1f}  coord={c.coord_fit_score:5.1f}  "
              f"flags=[{flags}]  {c.notes}")
    if not result.candidates:
        print("  (none — check the seed/brief exist for this area)")
    if result.escalated:
        print(f"\n[mapgen] {len(result.escalated)} candidate(s) flagged ESCALATE "
              f"(borderline — give these a human/Opus look): "
              f"{', '.join(result.escalated)}")


def _select(args) -> int:
    # Reload the batch manifest into a BatchResult to select from.
    mpath = paths.batch_dir(args.area, args.batch) / "manifest.json"
    if not mpath.exists():
        print(f"[mapgen] no batch manifest at {mpath}", file=sys.stderr)
        return 1
    data = json.loads(mpath.read_text(encoding="utf-8"))
    result = BatchResult(
        area_key=data["area_key"], timestamp=data["timestamp"],
        seed_path=data["seed_path"], brief_path=data["brief_path"],
        top_k=data["top_k"], escalated=data.get("escalated", []),
        manifest_path=str(mpath),
        candidates=[CandidateArtifact(**c) for c in data["candidates"]],
    )
    line = select_painting(result, args.candidate, slug=args.slug)
    if line is None:
        print(f"[mapgen] candidate {args.candidate} not in batch", file=sys.stderr)
        return 1
    print(f"[mapgen] selected {args.candidate}; copied to static/maps/.")
    print(f"[mapgen] add this to the area map YAML (MANUAL — map-safety):\n  {line}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools.mapgen.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("paint", help="generate + screen + rank a batch")
    p.add_argument("--area", required=True, help="area key, e.g. tatooine.mos_eisley")
    p.add_argument("--n", type=int, default=6, help="candidates to generate")
    p.add_argument("--style", default="", help="style-reference PNG for style-lock")
    p.add_argument("--era", default="clone_wars")
    p.add_argument("--timestamp", required=True,
                   help="batch id (caller-supplied for determinism/resume)")
    p.set_defaults(func=_paint)

    s = sub.add_parser("select", help="pick a candidate as the substrate")
    s.add_argument("--area", required=True)
    s.add_argument("--batch", required=True, help="batch timestamp/id")
    s.add_argument("--candidate", required=True, help="candidate id, e.g. cand_03")
    s.add_argument("--slug", default="", help="substrate slug (default: area key)")
    s.set_defaults(func=_select)

    args = ap.parse_args(argv)
    if args.cmd == "select" and not args.slug:
        args.slug = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
