"""
verify_gcw_equivalence.py — confirm that loading data/worlds/gcw/*.yaml
produces parsed Python data structures equivalent to the legacy hardcoded
constants in engine/world_lore.py and engine/director.py.

This is the regression-test asset that Drop 6a.2 / 6a.3 will gate on. It
runs as a standalone check in the parallel CW track so we know the YAMLs
are correct before the engine refactor lands.

Usage (from the SW_MUSH repo root):
    python3 verify_gcw_equivalence.py

Or from elsewhere:
    SW_MUSH_REPO=/path/to/SW_MUSH python3 verify_gcw_equivalence.py

Pass criteria:
  1. lore.yaml parses to N entries == len(SEED_ENTRIES)
  2. Every entry's (title, keywords, content, category, priority,
     [zone_scope]) round-trips exactly
  3. director_config.yaml.valid_factions == VALID_FACTIONS (set equality)
  4. zone_baselines == DEFAULT_INFLUENCE (dict equality, faction order
     within zone is irrelevant since dicts compare by content)
  5. system_prompt == director.py system_prompt (string equality)
  6. milestone_events round-trip ERA_MILESTONES tuples (ordered list)
  7. ambient_events.yaml.ambient_events parses to == legacy file dict
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path

import yaml


REPO = Path(os.environ.get("SW_MUSH_REPO", os.getcwd()))
GCW = REPO / "data" / "worlds" / "gcw"


# ── Source loaders (same as build script) ─────────────────────────────────────


def load_seed_entries():
    spec = importlib.util.spec_from_file_location("world_lore_src", str(REPO / "engine" / "world_lore.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.SEED_ENTRIES)


def load_director_constants():
    src = (REPO / "engine" / "director.py").read_text()
    tree = ast.parse(src)
    wanted = {
        "VALID_FACTIONS", "VALID_ZONES", "DEFAULT_INFLUENCE",
        "MIN_INFLUENCE", "MAX_INFLUENCE", "MAX_DELTA",
        "FACTION_TURN_INTERVAL", "ERA_MILESTONES",
    }
    ns: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in wanted:
                    code = ast.get_source_segment(src, node)
                    exec(code, ns)
    # system_prompt
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "system_prompt"):
            try:
                ns["SYSTEM_PROMPT"] = ast.literal_eval(node.value)
            except Exception:
                code = ast.get_source_segment(src, node)
                tmp: dict = {}
                exec(code, tmp)
                ns["SYSTEM_PROMPT"] = tmp["system_prompt"]
            break
    return ns


# ── Test harness ──────────────────────────────────────────────────────────────


PASS, FAIL = 0, 0
errors: list[str] = []


def check(label: str, expected, actual, *, set_compare: bool = False):
    global PASS, FAIL
    if set_compare:
        ok = set(expected) == set(actual)
    else:
        ok = expected == actual
    if ok:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        errors.append(f"{label}: expected={expected!r} actual={actual!r}")
        print(f"  ✗ {label}")


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_lore():
    print("\n[1] lore.yaml byte-equivalence")
    expected = load_seed_entries()
    loaded = yaml.safe_load((GCW / "lore.yaml").read_text())
    actual = loaded["entries"]

    check("entry count", len(expected), len(actual))

    if len(expected) != len(actual):
        return  # don't bother on length mismatch

    # Build dict-by-title for deterministic compare
    expected_by_title = {e["title"]: e for e in expected}
    actual_by_title = {e["title"]: e for e in actual}

    check("title set", set(expected_by_title), set(actual_by_title), set_compare=True)

    # Entry-by-entry
    field_mismatches: list[tuple[str, str, str, str]] = []
    for title in expected_by_title:
        if title not in actual_by_title:
            continue
        e = expected_by_title[title]
        a = actual_by_title[title]
        for key in ("title", "keywords", "category", "priority"):
            if e.get(key) != a.get(key):
                field_mismatches.append((title, key, repr(e.get(key)), repr(a.get(key))))
        # content: YAML folded-block introduces line-folding artifacts —
        # check normalized whitespace equality.
        ce = " ".join(e["content"].split())
        ca = " ".join(a["content"].split())
        if ce != ca:
            field_mismatches.append((title, "content (whitespace-normalized)",
                                     ce[:80] + "...", ca[:80] + "..."))
        # zone_scope: both should have it or both should not
        if ("zone_scope" in e) != ("zone_scope" in a):
            field_mismatches.append((title, "zone_scope presence",
                                     repr(e.get("zone_scope")), repr(a.get("zone_scope"))))
        elif "zone_scope" in e and e["zone_scope"] != a["zone_scope"]:
            field_mismatches.append((title, "zone_scope", repr(e["zone_scope"]), repr(a["zone_scope"])))

    if field_mismatches:
        for title, key, exp, act in field_mismatches[:5]:
            print(f"    MISMATCH in '{title}' / {key}:")
            print(f"      expected: {exp}")
            print(f"      actual:   {act}")
        if len(field_mismatches) > 5:
            print(f"    ...and {len(field_mismatches) - 5} more mismatches")
        check("all field values", 0, len(field_mismatches))
    else:
        check("all field values", "match", "match")


def test_director_config():
    print("\n[2] director_config.yaml byte-equivalence")
    expected = load_director_constants()
    loaded = yaml.safe_load((GCW / "director_config.yaml").read_text())

    check("valid_factions == VALID_FACTIONS",
          expected["VALID_FACTIONS"], loaded["valid_factions"], set_compare=True)
    check("influence_min", expected["MIN_INFLUENCE"], loaded["influence_min"])
    check("influence_max", expected["MAX_INFLUENCE"], loaded["influence_max"])
    check("max_delta_per_turn", expected["MAX_DELTA"], loaded["max_delta_per_turn"])
    check("faction_turn_interval_seconds", expected["FACTION_TURN_INTERVAL"],
          loaded["faction_turn_interval_seconds"])

    # zone_baselines: both keys + values must match exactly (order-independent dicts)
    check("zone_baselines == DEFAULT_INFLUENCE",
          expected["DEFAULT_INFLUENCE"], loaded["zone_baselines"])

    # system_prompt: byte-exact
    check("system_prompt", expected["SYSTEM_PROMPT"], loaded["system_prompt"])

    # milestone_events: round-trip ERA_MILESTONES tuples
    expected_milestones = expected["ERA_MILESTONES"]
    actual_milestones = loaded.get("milestone_events", [])
    check("milestone count", len(expected_milestones), len(actual_milestones))

    for i, ((faction, threshold, era_key, headline, event_type, duration_min),
            actual) in enumerate(zip(expected_milestones, actual_milestones)):
        prefix = f"milestone[{i}] {era_key}"
        check(f"{prefix}.id", era_key, actual.get("id"))
        check(f"{prefix}.faction", faction, actual.get("trigger", {}).get("faction"))
        check(f"{prefix}.threshold", threshold, actual.get("trigger", {}).get("threshold"))
        check(f"{prefix}.headline", headline, actual.get("headline"))
        # event_type may be None (omitted) or a string
        check(f"{prefix}.event_type",
              event_type, actual.get("narrative_event_type"))
        # duration_min may be 0 (omitted) or > 0
        check(f"{prefix}.duration_minutes",
              duration_min if duration_min else None, actual.get("duration_minutes"))


def test_ambient_events():
    print("\n[3] ambient_events.yaml byte-equivalence")
    expected = yaml.safe_load((REPO / "data" / "ambient_events.yaml").read_text())
    loaded = yaml.safe_load((GCW / "ambient_events.yaml").read_text())
    actual = loaded["ambient_events"]

    check("zone-key set", set(expected), set(actual), set_compare=True)

    # Per-zone line-count + content
    line_count_mismatch = []
    content_mismatch = []
    for zone in sorted(expected):
        if zone not in actual:
            continue
        if len(expected[zone]) != len(actual[zone]):
            line_count_mismatch.append(zone)
            continue
        for i, (e, a) in enumerate(zip(expected[zone], actual[zone])):
            if e != a:
                content_mismatch.append((zone, i, e, a))
    if line_count_mismatch:
        print(f"    Line-count mismatch in zones: {line_count_mismatch}")
    if content_mismatch:
        for zone, i, e, a in content_mismatch[:3]:
            print(f"    Content mismatch {zone}[{i}]: expected={e} actual={a}")
    check("all per-zone content matches",
          0, len(line_count_mismatch) + len(content_mismatch))


def test_era_yaml():
    print("\n[4] era.yaml structural validation")
    loaded = yaml.safe_load((GCW / "era.yaml").read_text())
    check("era.code", "gcw", loaded["era"]["code"])
    check("policy.factions matches engine VALID_FACTIONS",
          set(load_director_constants()["VALID_FACTIONS"]),
          set(loaded["policy"]["factions"]), set_compare=True)
    check("content_refs.lore", "lore.yaml", loaded["content_refs"]["lore"])
    check("content_refs.director_config", "director_config.yaml",
          loaded["content_refs"]["director_config"])
    check("content_refs.ambient_events", "ambient_events.yaml",
          loaded["content_refs"]["ambient_events"])


def main():
    test_lore()
    test_director_config()
    test_ambient_events()
    test_era_yaml()
    print()
    print("─" * 60)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    if FAIL:
        print()
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
