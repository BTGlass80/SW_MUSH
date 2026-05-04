"""
verify_tutorial_chains.py — schema + cross-reference validation for
data/worlds/clone_wars/tutorials/chains.yaml.

Verifies:
  1. File parses as YAML.
  2. Top-level shape: {schema_version: 1, chains: [...]}.
  3. Each chain has the required schema fields.
  4. All `faction_alignment` values resolve to organizations.yaml codes.
  5. All `starting_zone` values resolve to zones.yaml keys.
  6. All `prerequisites` flags use known flag names.
  7. Every step has the required schema fields.
  8. Every `completion.type` is from the allowed set.
  9. Step IDs are 1-indexed and contiguous.
 10. The Jedi Path chain is correctly marked locked + has prerequisite flag.

Usage:
    python3 verify_tutorial_chains.py
or:
    SW_MUSH_REPO=/path/to/SW_MUSH python3 verify_tutorial_chains.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


REPO = Path(os.environ.get("SW_MUSH_REPO", os.getcwd()))
CHAINS = REPO / "data" / "worlds" / "clone_wars" / "tutorials" / "chains.yaml"
ZONES = REPO / "data" / "worlds" / "clone_wars" / "zones.yaml"
ORGS = REPO / "data" / "worlds" / "clone_wars" / "organizations.yaml"


# ── Allowed values ───────────────────────────────────────────────────────────

ALLOWED_COMPLETION_TYPES = {
    "command_executed",
    "talk_to_npc",
    "combat_won",
    "skill_check_passed",
    "mission_accepted",
    "mission_completed",
    "bounty_accepted",
    "item_acquired",
    "item_used",
    "room_entered",
    "prerequisite",
}

ALLOWED_NPC_ROLES = {"instructor", "contact", "antagonist"}

ALLOWED_PREREQUISITE_FLAGS = {
    "chargen_complete",
    "force_sensitive",
    "jedi_path_unlocked",
    "tutorial_core_complete",
}

# `faction_intent` is a key:value, not a flat flag. Validate that
# the value is a known faction code; the key itself is always allowed.

ALLOWED_FACTION_INTENT_VALUES_PLACEHOLDER = None  # filled at runtime


# ── Test harness ──────────────────────────────────────────────────────────────

PASS, FAIL = 0, 0
errors: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        msg = label + (f": {detail}" if detail else "")
        errors.append(msg)
        print(f"  ✗ {msg}")


# ── Load reference data ──────────────────────────────────────────────────────


def load_zone_keys() -> set[str]:
    data = yaml.safe_load(ZONES.read_text())
    return set(data["zones"].keys())


def load_faction_codes() -> set[str]:
    """Load both faction codes and guild codes from organizations.yaml.

    The schema separates `factions:` (capital-F factions like republic/cis/
    jedi_order) from `guilds:` (the trade/profession guilds like
    shipwrights_guild). Tutorial chains reference both — Shipwright/Trader
    aligns to shipwrights_guild — so we treat them as a single ID-space
    for cross-reference purposes.
    """
    data = yaml.safe_load(ORGS.read_text())
    codes = {f["code"] for f in data.get("factions", [])}
    codes |= {g["code"] for g in data.get("guilds", [])}
    return codes


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_top_level(data):
    print("\n[1] Top-level shape")
    check("schema_version present", "schema_version" in data)
    check("schema_version == 1", data.get("schema_version") == 1)
    check("'chains' key present", "chains" in data)
    chains = data.get("chains", [])
    check("chains is a list", isinstance(chains, list))
    check("expected 9 chains", len(chains) == 9,
          f"got {len(chains)}")
    # F.7.j (May 4 2026) — chain count grew 8 → 9 with the split of
    # the formerly-monolithic `jedi_path` chain into Path-A
    # (`jedi_path`) and Path-B (`jedi_path_independent`) flavors.


def test_chain_shape(chain, idx, zone_keys, faction_codes):
    cid = chain.get("chain_id", f"<unknown #{idx}>")
    label = f"chain[{idx}] ({cid})"
    print(f"\n[2.{idx}] {label}")

    required = {
        "chain_id", "chain_name", "description", "archetype_label",
        "faction_alignment", "starting_zone", "prerequisites",
        "duration_minutes", "locked", "graduation", "steps",
    }
    keys = set(chain.keys())
    missing = required - keys
    check(f"all required fields present", not missing,
          f"missing: {sorted(missing)}" if missing else "")

    # faction_alignment
    fa = chain.get("faction_alignment")
    if fa is None:
        check(f"faction_alignment is null (allowed for unaligned)", True)
    else:
        check(f"faction_alignment '{fa}' resolves to organizations.yaml",
              fa in faction_codes,
              f"not in {sorted(faction_codes)[:10]}...")

    # starting_zone
    sz = chain.get("starting_zone")
    check(f"starting_zone '{sz}' resolves to zones.yaml",
          sz in zone_keys,
          f"not in known zones")

    # prerequisites — list of strings or {key: value} maps
    prereqs = chain.get("prerequisites", [])
    for pr in prereqs:
        if isinstance(pr, str):
            check(f"prerequisite flag '{pr}' known",
                  pr in ALLOWED_PREREQUISITE_FLAGS,
                  f"not in {sorted(ALLOWED_PREREQUISITE_FLAGS)}")
        elif isinstance(pr, dict):
            for k, v in pr.items():
                if k == "faction_intent":
                    check(f"faction_intent '{v}' resolves",
                          v in faction_codes,
                          f"not a valid faction code")
                elif k == "village_chosen_path":
                    # F.7.j (May 4 2026) — second mapped-key prereq.
                    # Valid values: 'a' (Path A — Order), 'b'
                    # (Path B — Independent), 'c' (Path C — Dark
                    # Whispers, currently unused for chain gating
                    # but reserved). See engine.tutorial_chains.
                    check(f"village_chosen_path '{v}' valid",
                          str(v).strip().lower() in {"a", "b", "c"},
                          f"must be 'a', 'b', or 'c'")
                else:
                    check(f"prerequisite '{k}' is a known mapped key",
                          k in {"faction_intent", "village_chosen_path"},
                          f"unknown mapped prerequisite key: {k}")

    # duration_minutes type
    dm = chain.get("duration_minutes")
    check(f"duration_minutes is int", isinstance(dm, int))

    # locked / locked_message
    if chain.get("locked"):
        check(f"locked chain has locked_message",
              "locked_message" in chain and chain["locked_message"])

    # graduation
    grad = chain.get("graduation", {})
    check(f"graduation has drop_room",
          "drop_room" in grad,
          "missing drop_room")
    if grad.get("faction_rep"):
        for fac, delta in grad["faction_rep"].items():
            check(f"graduation.faction_rep faction '{fac}' resolves",
                  fac in faction_codes,
                  f"unknown faction: {fac}")
            check(f"graduation.faction_rep '{fac}' is int",
                  isinstance(delta, int))

    # steps
    steps = chain.get("steps", [])
    check(f"chain has at least 1 step", len(steps) >= 1,
          f"got {len(steps)}")
    if not chain.get("locked"):
        check(f"unlocked chain has 4-6 steps",
              4 <= len(steps) <= 6,
              f"got {len(steps)}")

    # 1-indexed contiguous step numbers
    if steps:
        step_nums = [s.get("step") for s in steps]
        expected = list(range(1, len(steps) + 1))
        check(f"step numbers are 1..{len(steps)}",
              step_nums == expected,
              f"got {step_nums}")

    # per-step validation
    for sidx, step in enumerate(steps):
        prefix = f"  step[{step.get('step', '?')}] {step.get('title', '?')}"
        # required step fields
        required_step = {
            "step", "title", "location", "npc", "npc_role",
            "teaches", "objective", "npc_intro", "completion",
            "npc_complete", "reward", "next_hint",
        }
        missing_step = required_step - set(step.keys())
        if missing_step:
            check(f"{prefix} required fields",
                  False,
                  f"missing: {sorted(missing_step)}")
            continue

        # npc_role
        check(f"{prefix} npc_role allowed",
              step["npc_role"] in ALLOWED_NPC_ROLES,
              f"got '{step['npc_role']}', allowed {ALLOWED_NPC_ROLES}")

        # completion type
        comp = step["completion"]
        ct = comp.get("type")
        check(f"{prefix} completion.type allowed",
              ct in ALLOWED_COMPLETION_TYPES,
              f"got '{ct}'")

        # teaches must be a list
        check(f"{prefix} teaches is a list",
              isinstance(step["teaches"], list))


def test_jedi_path_locked(data):
    print("\n[3] Jedi Path locked-stub validation")
    chains_by_id = {c["chain_id"]: c for c in data.get("chains", [])}
    jedi = chains_by_id.get("jedi_path")
    check("jedi_path chain present", jedi is not None)
    if not jedi:
        return
    check("jedi_path is locked", jedi.get("locked") is True)
    check("jedi_path has locked_message",
          bool(jedi.get("locked_message")))
    check("jedi_path requires jedi_path_unlocked flag",
          "jedi_path_unlocked" in jedi.get("prerequisites", []))
    check("jedi_path requires force_sensitive flag",
          "force_sensitive" in jedi.get("prerequisites", []))
    check("jedi_path duration is 0 (unrunnable as locked)",
          jedi.get("duration_minutes") == 0)


def test_chain_uniqueness(data):
    print("\n[4] Chain uniqueness")
    chains = data.get("chains", [])
    ids = [c.get("chain_id") for c in chains]
    check("all chain_ids unique", len(ids) == len(set(ids)),
          f"duplicates: {[i for i in set(ids) if ids.count(i) > 1]}")
    names = [c.get("chain_name") for c in chains]
    check("all chain_names unique", len(names) == len(set(names)),
          f"duplicates: {[n for n in set(names) if names.count(n) > 1]}")


def main():
    if not CHAINS.is_file():
        print(f"ERROR: {CHAINS} not found")
        sys.exit(2)

    data = yaml.safe_load(CHAINS.read_text())
    zone_keys = load_zone_keys()
    faction_codes = load_faction_codes()

    print(f"Loaded chains.yaml with {len(data.get('chains', []))} chains")
    print(f"Loaded zones.yaml with {len(zone_keys)} zone keys")
    print(f"Loaded organizations.yaml with {len(faction_codes)} faction codes")

    test_top_level(data)
    for idx, chain in enumerate(data.get("chains", [])):
        test_chain_shape(chain, idx, zone_keys, faction_codes)
    test_jedi_path_locked(data)
    test_chain_uniqueness(data)

    print()
    print("─" * 60)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    if FAIL:
        print()
        print("Failures:")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ...and {len(errors) - 20} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
