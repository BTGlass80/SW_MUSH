"""tools/mapgen/overnight_runner.py — unattended, gap-surviving STYLE-REFERENCE
map-candidate sweep across every city, bounded by a hard Gemini $ budget.

WHY THIS LANE EXISTS (Brian, 2026-06-18)
----------------------------------------
The style-reference lever WORKS (a warm, painterly, water-free, text-free
mos_eisley plate that rivals the hand-made one — see HANDOFF §3 + the smoke
batch). Brian: "keep all development pushing overnight unattended … you with
Nano … do at least another planet, or $5 in Gemini, whatever you hit first."

This lane is PURE GEMINI — it makes NO Anthropic/Claude call (screening is the
mock pass-through; the human/Opus does visual QA when attended). So it keeps
generating through a Claude compute-limit gap that throttles the Opus/Sonnet
loops, because image generation only touches the Gemini API (the $10 maps
budget), not the Max subscription.

WHAT IT DOES, per fire (one ROUND = every city once):
  for each city: feed its existing tight seed + its existing brief WRAPPED with
  a terrain-agnostic STYLE-REF preamble (image1=layout, image2=style) + the
  city's own hand-made plate as the style anchor -> N candidates into the
  gitignored static/tools/batches/<area>/<round>/ . It NEVER calls `select`
  (never overwrites a real substrate) — that stays a human decision.

SAFETY / BUDGET
---------------
  • Hard cap: BUDGET_CENTS (default $5). Each generated image is charged a
    CONSERVATIVE per-image estimate (gemini-2.5-flash-image ~3.9¢; we book 4¢)
    so we UNDER-spend. A persisted ledger survives restarts; when spend hits the
    cap (or MAX_ROUNDS) it writes a DONE marker and every later fire exits fast.
  • Resumable: run_batch is idempotent per candidate; the ledger is updated
    per-area so an interrupted fire loses at most the in-flight city.
  • Non-destructive: only the gitignored batches/ dir is written; each city's
    brief is wrapped transiently and restored in a finally.
  • Key: GEMINI_API_KEY / GOOGLE_API_KEY from ENV ONLY (never committed). For
    the scheduled fires it is read from the user-env (provisioned out-of-band).

Usage:
  GEMINI_API_KEY=... python -m tools.mapgen.overnight_runner sweep            # one round
  GEMINI_API_KEY=... python -m tools.mapgen.overnight_runner sweep --mock     # offline smoke
  python -m tools.mapgen.overnight_runner status                              # show the ledger
  python -m tools.mapgen.overnight_runner reset                               # clear DONE/ledger
  python -m tools.mapgen.overnight_runner arm --every 30                      # schedule (durable)
  python -m tools.mapgen.overnight_runner disarm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import paths
from .batch import BatchOrchestrator

# area key (seed/brief slug) -> hand-made plate filename (the style anchor).
# NOT uniform: several cities' plates are named by planet+place, not the seed
# slug (verified against static/maps/ on 2026-06-18).
AREA_PLATE: dict[str, str] = {
    "mos_eisley":          "mos_eisley_substrate.png",
    "tatooine_dune_sea":   "tatooine_dune_sea_substrate.png",
    "senate_district":     "coruscant_senate_substrate.png",
    "coruscant_underworld": "coruscant_underworld_substrate.png",
    "kuat_city":           "kuat_city_substrate.png",
    "smugglers_moon":      "nar_shaddaa_substrate.png",
    "stalgasin_hive":      "geonosis_stalgasin_substrate.png",
    "tipoca_city":         "kamino_tipoca_substrate.png",
}
# Sweep order: a NEW planet first each step so "at least another planet" is hit
# early, then breadth. (mos_eisley already done in the attended smoke.)
SWEEP_ORDER = [
    "senate_district",      # Coruscant
    "kuat_city",            # Kuat
    "stalgasin_hive",       # Geonosis
    "tipoca_city",          # Kamino
    "smugglers_moon",       # Nar Shaddaa
    "coruscant_underworld", # Coruscant (wilderness-ish)
    "tatooine_dune_sea",    # Tatooine (wilderness)
    "mos_eisley",           # Tatooine (more samples)
]

BUDGET_CENTS = 900.0          # $9 hard cap — the BINDING stop (Brian raised $5->$9;
                              # $10 funded, $1 buffer). Real spend ~per-image*images.
PER_IMAGE_CENTS = 4.0         # conservative (real ~3.9¢) -> we under-spend
MAX_ROUNDS = 8                # high backstop only; the $5 cap stops it first
N_PER_CITY = 6

LEDGER = paths.BATCHES_DIR / "_overnight" / "ledger.json"
LOCKFILE = paths.BATCHES_DIR / "_overnight" / "lock"
LOCK_STALE_SECONDS = 1800     # a lock older than this is abandoned -> takeover

# Terrain-AGNOSTIC style-ref preamble (NO "desert"/"no-water" claims — those
# would break Kamino/Coruscant). Terrain comes from each city's own brief + its
# own plate as the palette/mood anchor.
STYLE_PREAMBLE = (
    "[STYLE-REFERENCE RENDER — TWO images are attached, with different jobs.]\n"
    "The FIRST attached image is the SPATIAL LAYOUT: treat it as the exact, "
    "fixed composition — keep every road, zone, feature-block and structure "
    "where it sits; do not reflow, rescale, or rearrange.\n"
    "The SECOND attached image is the ART STYLE to emulate: copy its painterly "
    "look — palette, hand-shaded brushwork, lighting, mood and surface texture — "
    "but do NOT copy its content or layout. Paint the FIRST image's layout in "
    "the SECOND image's style.\n"
    "This is a PAINTING, not a schematic, blueprint, floor-plan, battle-map, hex "
    "grid, or virtual-tabletop token map. The image must contain absolutely NO "
    "TEXT of any kind — no labels, letters, numbers, legend, or compass.\n"
    "----- city brief follows -----\n"
)


# ── ledger ───────────────────────────────────────────────────────────────────

def _load_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"cents_spent": 0.0, "images": 0, "round": 0, "done": False,
            "budget_cents": BUDGET_CENTS, "per_image_cents": PER_IMAGE_CENTS,
            "history": []}


def _save_ledger(d: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


# ── one city ──────────────────────────────────────────────────────────────────

def _wrap_brief(area_key: str) -> tuple[Path, Optional[Path]]:
    """Transiently prepend the style preamble to the city's brief on disk;
    return (brief_path, backup_path) — caller restores from backup in finally."""
    brief = paths.brief_for(area_key)
    if not brief.exists():
        return brief, None
    bak = Path(tempfile.mkdtemp(prefix="onbrief_")) / brief.name
    shutil.copy2(brief, bak)
    brief.write_text(STYLE_PREAMBLE + brief.read_text(encoding="utf-8"),
                     encoding="utf-8")
    return brief, bak


async def _run_city(area_key: str, nano, round_id: str, n: int) -> int:
    """Generate n style-ref candidates for one city. Returns images produced."""
    seed = paths.seed_for(area_key)
    if not seed.exists():
        print(f"[overnight]   skip {area_key}: no seed {seed.name}")
        return 0
    plate_name = AREA_PLATE.get(area_key)
    plate = (paths.MAPS_DIR / plate_name) if plate_name else None
    if plate and not plate.exists():
        print(f"[overnight]   {area_key}: plate {plate_name} missing — no anchor")
        plate = None

    brief, bak = _wrap_brief(area_key)
    try:
        # Record toe-the-line boundaries into a GITIGNORED file, never the
        # committed tools/mapgen/term_boundaries.json (a test pins it empty).
        orch = BatchOrchestrator(area_key, nano_client=nano, screener_provider=None,
                                 boundaries_path=LEDGER.parent / "term_boundaries.json")
        result = await orch.run_batch(n_candidates=n, timestamp=round_id,
                                      style_reference_image=plate,
                                      verified_stamp=round_id)
        made = len(result.candidates)
        print(f"[overnight]   {area_key}: {made} candidate(s) -> "
              f"{paths.batch_dir(area_key, round_id).name}/  "
              f"(anchor={'yes' if plate else 'NONE'})")
        return made
    finally:
        if bak is not None:
            shutil.copy2(bak, brief)
            shutil.rmtree(bak.parent, ignore_errors=True)


# ── sweep ─────────────────────────────────────────────────────────────────────

def _make_nano(use_mock: bool):
    if use_mock:
        from .nano_client import MockNanoClient
        return MockNanoClient(), "Nano=MOCK"
    if paths.has_google_key():
        import os
        from .nano_client import NanoClient
        key = (os.environ.get("GOOGLE_API_KEY", "").strip()
               or os.environ.get("GEMINI_API_KEY", "").strip())
        return NanoClient(api_key=key), "Nano=LIVE"
    return None, "Nano=ABSENT"


def _acquire_lock() -> bool:
    """True if we got the lock. A fresh lock (mtime < STALE) means another sweep
    is generating -> caller exits. A stale lock is taken over (a dead run)."""
    import os
    import time
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCKFILE.exists():
        age = time.time() - LOCKFILE.stat().st_mtime
        if age < LOCK_STALE_SECONDS:
            print(f"[overnight] another sweep holds the lock (age {age:.0f}s) — "
                  f"exiting so we never double-generate / race the ledger.")
            return False
        print(f"[overnight] stale lock (age {age:.0f}s) — taking over.")
    LOCKFILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_lock() -> None:
    try:
        LOCKFILE.unlink()
    except OSError:
        pass


async def _run_round(nano, led: dict, n: int, prefix: str = "on") -> None:
    round_id = f"{prefix}_r{led['round']}"
    print(f"[overnight] === ROUND {led['round']} ({round_id}), n={n}/city ===")
    for area in SWEEP_ORDER:
        if led["cents_spent"] >= led["budget_cents"]:
            print("[overnight] budget cap reached mid-round — stopping.")
            break
        made = await _run_city(area, nano, round_id, n)
        led["images"] += made
        led["cents_spent"] += made * led["per_image_cents"]
        led["history"].append({"round": led["round"], "area": area, "images": made})
        _save_ledger(led)            # per-area persist (interrupt-safe)
        LOCKFILE.touch()             # keep the lock fresh during a long round
    led["round"] += 1
    if led["cents_spent"] >= led["budget_cents"] or led["round"] >= MAX_ROUNDS:
        led["done"] = True
    _save_ledger(led)


async def _sweep(use_mock: bool, n: int, loop: bool = False,
                 prefix: str = "on") -> int:
    led = _load_ledger()
    if led.get("done"):
        print(f"[overnight] DONE already (spent ~${led['cents_spent']/100:.2f}, "
              f"{led['images']} images, {led['round']} rounds). Nothing to do.")
        return 0

    nano, tag = _make_nano(use_mock)
    print(f"[overnight] {tag} | Screen=OFF(no-anthropic) | "
          f"budget=${led['budget_cents']/100:.2f} | "
          f"spent=${led['cents_spent']/100:.2f} | round={led['round']} | "
          f"loop={loop}")
    if nano is None:
        print("[overnight] ERROR: no GEMINI_API_KEY/GOOGLE_API_KEY in env. "
              "Set it (env only) or pass --mock.", file=sys.stderr)
        return 1

    if not _acquire_lock():
        return 0
    try:
        while True:
            await _run_round(nano, led, n, prefix=prefix)
            if led["done"]:
                print(f"[overnight] *** SWEEP COMPLETE *** spent "
                      f"~${led['cents_spent']/100:.2f} over {led['images']} images "
                      f"/ {led['round']} rounds. DONE marker set.")
                break
            if not loop:
                print(f"[overnight] round done; spent ~${led['cents_spent']/100:.2f}."
                      f" Next fire runs round {led['round']}.")
                break
    finally:
        _release_lock()
    return 0


# ── status / scheduling ────────────────────────────────────────────────────────

def _status() -> int:
    led = _load_ledger()
    print(json.dumps(led, indent=2))
    print(f"\n[overnight] spent ~${led['cents_spent']/100:.2f} of "
          f"${led['budget_cents']/100:.2f}; {led['images']} images; "
          f"round {led['round']}; done={led['done']}")
    return 0


def _reset() -> int:
    if LEDGER.exists():
        LEDGER.unlink()
    print("[overnight] ledger cleared (DONE marker removed).")
    return 0


def _arm(every: int, name: str, prefix: str = "on") -> int:
    """Register a durable, gap-surviving scheduled fire using the hardened task
    XML from durable_loop (IgnoreNew so fires never overlap; StartWhenAvailable
    so a fire missed during sleep runs on wake). Reuses those PURE builders
    without editing that module."""
    import datetime as _dt
    import os
    import tools.durable_loop as DL
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    tdir = home / ".claude" / "durable_loop" / name
    log_dir = tdir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    workdir = str(paths.PROJECT_ROOT)
    py = sys.executable or "python"
    # --loop: one fire drives rounds until the $5 cap; the lock serialises with
    # any in-session run, and the recurring trigger + ledger resume after a kill.
    raw = f'"{py}" -m tools.mapgen.overnight_runner sweep --loop --prefix {prefix}'
    launcher = DL.build_launcher(workdir, "", "", str(log_dir), "opus", "bypass",
                                 raw_action=raw)
    (tdir / "launcher.cmd").write_text(launcher, encoding="utf-8", newline="")
    start = _dt.datetime.now() + _dt.timedelta(seconds=30)
    xml = DL.build_task_xml(str(tdir / "launcher.cmd"), start_dt=start,
                            every_minutes=every,
                            description="SW_MUSH overnight Nano style-ref sweep "
                                        "(pure Gemini; survives Claude compute gap)",
                            exec_time_limit="PT2H")
    xml_file = tdir / "task.xml"
    xml_file.write_text(xml, encoding="utf-16")
    if os.name != "nt":
        print(f"[overnight] (non-Windows) wrote launcher + XML to {tdir}; "
              f"register manually.")
        return 0
    import subprocess
    res = subprocess.run(["schtasks", "/create", "/tn", name, "/xml",
                          str(xml_file), "/f"], capture_output=True, text=True)
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    if res.returncode == 0:
        print(f"[overnight] armed {name}: every {every}m, workdir {workdir}\n"
              f"  logs: {log_dir}\n  disarm: python -m tools.mapgen.overnight_runner "
              f"disarm --name {name}")
    return res.returncode


def _disarm(name: str) -> int:
    import subprocess
    res = subprocess.run(["schtasks", "/delete", "/tn", name, "/f"],
                         capture_output=True, text=True)
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    return res.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools.mapgen.overnight_runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sw = sub.add_parser("sweep", help="run a round (every city once); --loop -> until $5")
    sw.add_argument("--mock", action="store_true", help="offline smoke (no key/cost)")
    sw.add_argument("--n", type=int, default=N_PER_CITY)
    sw.add_argument("--loop", action="store_true",
                    help="keep running rounds in THIS process until the $5 cap "
                         "(in-session run); scheduled fires omit it for resumability")
    sw.add_argument("--prefix", default="on", help="round-id namespace (default 'on')")
    sub.add_parser("status", help="print the budget ledger")
    sub.add_parser("reset", help="clear the ledger + DONE marker")
    ar = sub.add_parser("arm", help="schedule durable recurring fires")
    ar.add_argument("--every", type=int, default=30, help="minutes between fires")
    ar.add_argument("--name", default="SWMUSH-NanoLoop")
    ar.add_argument("--prefix", default="on", help="round-id namespace (match in-session)")
    di = sub.add_parser("disarm", help="remove the scheduled task")
    di.add_argument("--name", default="SWMUSH-NanoLoop")
    args = ap.parse_args(argv)

    if args.cmd == "sweep":
        return asyncio.run(_sweep(args.mock, args.n, loop=args.loop,
                                  prefix=args.prefix))
    if args.cmd == "status":
        return _status()
    if args.cmd == "reset":
        return _reset()
    if args.cmd == "arm":
        return _arm(args.every, args.name, prefix=args.prefix)
    if args.cmd == "disarm":
        return _disarm(args.name)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
