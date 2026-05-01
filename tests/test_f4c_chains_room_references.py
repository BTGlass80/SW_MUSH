# -*- coding: utf-8 -*-
"""
tests/test_f4c_chains_room_references.py — F.4c chain reconciliation tests

F.4c (Apr 30 2026) reconciled `data/worlds/clone_wars/tutorials/chains.yaml`
against the live CW room set. The 27 missing slugs identified in F.4
were resolved via 3 renames (typos / drift) and 24 redirects (chain
references rewritten to point at existing rooms with the closest
narrative function). Two of the renames were genuine typos
(`dexs_diner` → `dexters_diner`, `tipoca_briefing_chamber` →
`tipoca_briefing_room`); one was naming-drift (`jedi_temple_gates` →
`jedi_temple_main_gate`).

This test file is a regression guard. If a future content drop adds
a new chain step pointing at a slug that doesn't exist, this test
fires before it reaches the runtime tutorial executor.

Tests covered:

  - Every `starting_room` resolves to a live CW room
  - Every `graduation.drop_room` resolves to a live CW room
  - Every `step.location` resolves to a live CW room
  - Every `step.completion.room` (when present) resolves to a live CW room
  - The `jedi_path` chain's `starting_room: null` is permitted because
    the chain is `locked: true` (intentional design — the Jedi Order
    is not selectable as a starting archetype)

This test ALWAYS asserts the strict invariant: zero unresolved chain
slugs against the loaded CW world.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestChainsRoomReferences(unittest.TestCase):
    """All `chains.yaml` room references must resolve to live CW rooms."""

    @classmethod
    def setUpClass(cls):
        import yaml
        from engine.world_loader import load_world_dry_run

        chains_path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
                       "tutorials" / "chains.yaml")
        if not chains_path.is_file():
            raise unittest.SkipTest(
                f"chains.yaml not present at {chains_path}"
            )
        with open(chains_path, encoding="utf-8") as f:
            cls.chains_data = yaml.safe_load(f)

        b = load_world_dry_run("clone_wars")
        cls.live_slugs = {r.slug for r in b.rooms.values()}
        cls.cw_world = b

    def _walk_room_refs(self):
        """Yield (chain_id, field_path, slug) for every room reference."""
        for c in self.chains_data["chains"]:
            cid = c.get("chain_id", "?")
            sr = c.get("starting_room")
            if sr:
                yield (cid, "starting_room", sr)
            grad = c.get("graduation", {}) or {}
            dr = grad.get("drop_room")
            if dr:
                yield (cid, "graduation.drop_room", dr)
            for i, step in enumerate(c.get("steps", []) or []):
                loc = step.get("location")
                if loc:
                    yield (cid, f"step[{i}].location", loc)
                comp = step.get("completion", {}) or {}
                if isinstance(comp, dict) and "room" in comp:
                    yield (cid, f"step[{i}].completion.room", comp["room"])

    def test_all_chain_rooms_resolve(self):
        """Every chain room reference resolves to a live CW slug."""
        unresolved = []
        for cid, field, slug in self._walk_room_refs():
            if slug not in self.live_slugs:
                unresolved.append((cid, field, slug))
        if unresolved:
            lines = [
                f"  {cid:<24}  {field:<32}  -> {slug}"
                for cid, field, slug in unresolved
            ]
            self.fail(
                f"{len(unresolved)} chain room references do not resolve "
                f"to live CW slugs. Either rename the chain reference, "
                f"redirect it to an existing room, or author the missing "
                f"room. Per the F.4c approach, prefer rename/redirect "
                f"over authoring new rooms.\n" + "\n".join(lines)
            )

    def test_chains_yaml_parses(self):
        """The chains file must parse as YAML and have a `chains` list."""
        self.assertIn("chains", self.chains_data)
        self.assertIsInstance(self.chains_data["chains"], list)
        self.assertGreater(len(self.chains_data["chains"]), 0)

    def test_locked_chains_may_omit_starting_room(self):
        """Locked chains (e.g., jedi_path) are permitted to have no
        starting_room — they're not selectable as archetypes via the
        normal flow. The graduation.drop_room must still resolve."""
        for c in self.chains_data["chains"]:
            cid = c.get("chain_id", "?")
            if c.get("locked", False):
                # Locked chains may have starting_room: null
                continue
            sr = c.get("starting_room")
            self.assertTrue(
                sr,
                f"Unlocked chain {cid!r} must have a starting_room "
                f"(got {sr!r})"
            )

    def test_no_known_dead_slugs(self):
        """Regression guard: enumerate the slugs F.4c retired and assert
        none remain as ROOM REFERENCES anywhere in chains.yaml. F.8.b
        update: the check now parses the YAML and inspects only
        room-reference fields (`location`, `starting_room`,
        `graduation.drop_room`, `completion.room`). The
        `starting_zone` field is allowed to reference any zone slug
        from zones.yaml, including slugs like `tatooine_dune_sea` that
        are zones AND F.4c-retired room references — the retirement
        applied only to using them as room slugs, not zones.

        If a future drop re-introduces a retired slug as a room
        reference (typo / copy-paste from old design notes), this
        test fires.
        """
        chains_path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
                       "tutorials" / "chains.yaml")
        with open(chains_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # F.8.b update (Apr 30 2026): Most of F.4c's original 28-entry
        # retired-slug list has been re-authored as legitimate
        # tutorial-zone rooms in data/worlds/clone_wars/tutorials/rooms.yaml.
        # The retained list below is just the slugs that remain TRULY
        # retired:
        #   1. F.4c rename-map entries where chain content should use the
        #      F.4c-corrected form: tipoca_briefing_chamber (renamed to
        #      tipoca_briefing_room), dexs_diner (renamed to dexters_diner),
        #      jedi_temple_gates (renamed to jedi_temple_main_gate).
        #   2. Zone-as-room misuses: tatooine_dune_sea, nar_shaddaa_warrens,
        #      space_nar_shaddaa, space_tatooine. These are valid zones
        #      but were never legitimate `location:` values; F.8.b
        #      replaced them with real tutorial-zone room slugs
        #      (jedi_temple_main_gate, nar_shaddaa_warrens_safehouse,
        #      smuggler_ship_cockpit, tatooine_smuggler_holdout).
        retired_slugs = {
            # F.4c genuine-typo renames
            "tipoca_briefing_chamber",  # F.4c → tipoca_briefing_room
            "dexs_diner",                # F.4c → dexters_diner
            "jedi_temple_gates",         # F.4c → jedi_temple_main_gate
            # F.4c zone-as-room misuses (zones, never room slugs)
            "tatooine_dune_sea",
            "nar_shaddaa_warrens",
            "space_nar_shaddaa",
            "space_tatooine",
        }

        # Collect all room-reference slugs from chains.yaml. Allowed
        # room-reference fields are: starting_room, graduation.drop_room,
        # step.location, step.completion.room. (NOT starting_zone, which
        # references zones.yaml.)
        room_refs = []
        for c in data.get("chains", []):
            cid = c.get("chain_id", "?")
            if c.get("starting_room"):
                room_refs.append((c["starting_room"], f"{cid}.starting_room"))
            grad = c.get("graduation", {}) or {}
            if grad.get("drop_room"):
                room_refs.append((grad["drop_room"], f"{cid}.graduation.drop_room"))
            for step in c.get("steps") or []:
                if step.get("location"):
                    room_refs.append(
                        (step["location"],
                         f"{cid}.step{step.get('step', '?')}.location"),
                    )
                comp = step.get("completion") or {}
                if comp.get("room"):
                    room_refs.append(
                        (comp["room"],
                         f"{cid}.step{step.get('step', '?')}.completion.room"),
                    )

        offenders = [
            (slug, where) for slug, where in room_refs
            if slug in retired_slugs
        ]
        self.assertEqual(
            offenders, [],
            f"Retired slug(s) reappeared as room references in chains.yaml: "
            f"{offenders}. Use the F.4c map to replace with the correct "
            f"live slug (or author a real tutorial-zone room).",
        )


if __name__ == "__main__":
    unittest.main()
