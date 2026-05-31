"""
test_map_cardinals_reverse.py — Drop 3 (B): geometry-true direction words.

The old check_map_cardinals only validated the FORWARD word and assumed the
reverse was its opposite, so geometrically wrong REVERSE words shipped (an exit
drawn due-north shown as "east"; a stale "...to Bay 86" pointing at a different
room). This pins the rewritten tool:

  · check_map now classifies BOTH forward and reverse against their own bearing.
  · derive_fixes proposes geometry-consistent words and is COLLISION-AWARE:
    when a room's ideal octant is taken (a hub fans several exits into one
    octant), it nudges to the nearest FREE octant rather than duplicating a word.
  · a " to <label>" suffix is KEPT when it names the destination room and
    DROPPED when it names a different room (stale copy-paste); labels are never
    invented.
  · the four real reverse mismatches (tatooine x2, nar_shaddaa x2) are corrected
    in the planet YAMLs, and every shipped map is now gate-green.

Runs the ACTUAL tool functions (imported from tools/check_map_cardinals.py).
"""
from __future__ import annotations

import glob
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
import check_map_cardinals as cmc  # noqa: E402


# ── synthetic fixture: a hub with two neighbours competing for "north" ──

def _write_world(tmp_path: Path) -> Path:
    base = tmp_path / "data" / "worlds" / "clone_wars"
    (base / "maps").mkdir(parents=True)
    (base / "planets").mkdir(parents=True)
    # Geometry: hub at origin; A due north; B north-NE; C north-NW; all three
    # neighbours sit ~north of the hub, so their reverse words (shown AT the hub)
    # can't all be "north" — the tool must spread them.
    (base / "maps" / "synthplace.yaml").write_text(textwrap.dedent("""\
        area_key: synth.synthplace
        rooms:
          - {slug: hub,    x: 0.0,  y: 0.0}
          - {slug: alpha,  x: 0.0,  y: 1.0}
          - {slug: beta,   x: 0.1,  y: 1.0}
          - {slug: gamma,  x: -0.1, y: 1.0}
    """), encoding="utf-8")
    (base / "planets" / "synth.yaml").write_text(textwrap.dedent("""\
        rooms:
          - {id: 0, slug: hub,   name: "Central Hub"}
          - {id: 1, slug: alpha, name: "Alpha Plaza"}
          - {id: 2, slug: beta,  name: "Beta Beacon"}
          - {id: 3, slug: gamma, name: "Gamma Gate"}
        exits:
          - {from: 1, to: 0, forward: "south", reverse: "north"}
          - {from: 2, to: 0, forward: "south", reverse: "south to Beacon"}
          - {from: 3, to: 0, forward: "south", reverse: "south to Wrongplace"}
    """), encoding="utf-8")
    return base / "maps" / "synthplace.yaml"


def test_reverse_mismatch_is_detected():
    """A reverse word pointing the wrong way is flagged (the old tool ignored
    the reverse entirely)."""
    # beta/gamma reverses say 'south' but the rooms are NORTH of the hub.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp = _write_world(Path(td))
        res = cmc.check_map(mp)
    rev_mm = [r for r in res["rows"] if r["side"] == "reverse" and r["status"] == "mismatch"]
    pairs = {(r["frm"], r["to"]) for r in rev_mm}
    assert ("beta", "hub") in pairs and ("gamma", "hub") in pairs, pairs
    # the correct forward 'north' on alpha's reverse is fine
    assert not any(r["frm"] == "alpha" and r["status"] == "mismatch" for r in res["rows"])


def test_derive_is_collision_aware_and_unique():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp = _write_world(Path(td))
        res = cmc.check_map(mp)
        props = cmc.derive_fixes(res)
    by_pair = {(p["frm"], p["to"]): p for p in props}
    # alpha already holds 'north' at the hub; beta + gamma must NOT also be 'north'
    beta = by_pair[("beta", "hub")]["new"]
    gamma = by_pair[("gamma", "hub")]["new"]
    assert cmc.base_word(beta) != "north", beta
    assert cmc.base_word(gamma) != "north", gamma
    # and they must differ from each other (unique words at the hub)
    assert cmc.base_word(beta) != cmc.base_word(gamma), (beta, gamma)
    # both are adjacent octants of north → within the 'minor' band, not wild
    assert cmc.base_word(beta) in {"northeast", "northwest"}
    assert cmc.base_word(gamma) in {"northeast", "northwest"}


def test_label_kept_when_correct_dropped_when_stale():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp = _write_world(Path(td))
        res = cmc.check_map(mp)
        props = {(p["frm"], p["to"]): p for p in cmc.derive_fixes(res)}
    # 'south to Beacon' -> dest is Beta Beacon → label kept
    assert props[("beta", "hub")]["new"].endswith("to Beacon"), props[("beta", "hub")]["new"]
    # 'south to Wrongplace' -> dest is Gamma Gate → label dropped (bare word)
    assert " to " not in props[("gamma", "hub")]["new"], props[("gamma", "hub")]["new"]


# ── regression lock: the real maps are all gate-green after the data fix ──

def test_all_shipped_maps_have_zero_mismatches():
    maps = sorted(glob.glob(str(REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps" / "*.yaml")))
    assert maps, "no maps found"
    total_mm = 0
    offenders = []
    for mp in maps:
        res = cmc.check_map(Path(mp))
        if res.get("error"):
            continue
        c = cmc.summarize(res)
        total_mm += c["mismatch"]
        if c["mismatch"]:
            offenders.append((res["area_key"], c["mismatch"]))
    assert total_mm == 0, f"forward+reverse cardinal mismatches remain: {offenders}"


def test_four_reverse_corrections_are_present_in_planet_yaml():
    """Pin the exact collision-aware corrections written back to the data."""
    tat = (REPO_ROOT / "data/worlds/clone_wars/planets/tatooine.yaml").read_text(encoding="utf-8")
    nar = (REPO_ROOT / "data/worlds/clone_wars/planets/nar_shaddaa.yaml").read_text(encoding="utf-8")
    # the broken originals are gone
    assert "east to Bay 86" not in tat
    assert "east to Stables" not in tat
    assert "west to Floating Market" not in nar
    assert "north to Warrens" not in nar
    # the corrected reverses are present
    assert '{from: 2, to: 0, forward: "south", reverse: "northwest"}' in tat
    assert '{from: 23, to: 22, forward: "north", reverse: "southwest to Stables"}' in tat
    assert '{from: 75, to: 64, forward: "up", reverse: "northeast to Floating Market"}' in nar
    assert '{from: 79, to: 65, forward: "down", reverse: "southeast to Warrens"}' in nar
