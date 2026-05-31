# -*- coding: utf-8 -*-
"""
tests/test_q1_3_falleen_syndicate.py — Drop Q1.3 (May 18 2026).

Pins the Xizor's Castle District → Falleen Syndicate Tower scrub.
Companion to test_q1_2_extended_sweep.py::test_coruscant_xizor_district_scrubbed
(which pins the negative — no Xizor in room 230). This file pins
the positive: the replacement content is present and policy-
compliant.

Coverage:
  * Room 230 has the new slug `falleen_syndicate_tower`.
  * Room 230's description names Vigo Sethel Vask (an original
    character; no canonical Black Sun figure on-stage).
  * The Falleen Syndicate Tower is reachable from at least one
    other room (the reverse-exit fix from upper_city_promenade).
  * The new NPC drop file (`npcs_drop_i_falleen_syndicate.yaml`)
    is registered in era.yaml's NPCs list.
  * The NPC drop file contains Vask, and Vask's room field matches
    the rewritten room name.
  * The NPC drop file is itself Q1-compliant — no unframed canonical
    Black Sun names (Xizor, Garyn, Veers, Sprax, etc.) in its
    player-facing strings.

Why a separate test file: this is the positive backstop for the
Xizor scrub. The xfail-promoted test in test_q1_2_extended_sweep.py
pins absence; this file pins presence-of-replacement. Both must
pass for the design call to be considered closed.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CW_ERA = PROJECT_ROOT / "data" / "worlds" / "clone_wars"
COR_YAML = CW_ERA / "planets" / "coruscant.yaml"
ERA_YAML = CW_ERA / "era.yaml"
NPC_YAML = CW_ERA / "npcs_drop_i_falleen_syndicate.yaml"

# Canonical Black Sun figures that must not appear on-stage in the
# new content. Xizor is the famous one; the others are off-stage
# names that may be referenced in lore.yaml but not in this NPC
# drop or the rewritten room.
BLACK_SUN_CANONICAL = (
    "Xizor",
    "Alexi Garyn",   # the GCW-era Black Sun Underlord — off-stage only
    "Sprax",         # GCW Vigo (Shadows of the Empire) — off-stage only
    "Perit",         # GCW Vigo — off-stage only
)


def _yaml_load(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _has_word(text: str, word: str) -> bool:
    """Whole-word match, case-insensitive, on word boundaries.
    Mirrors the helper in test_q1_2_extended_sweep.py."""
    return bool(re.search(
        r"\b" + re.escape(word) + r"\b",
        text or "",
        re.IGNORECASE,
    ))


class TestFalleenSyndicateReplacement(unittest.TestCase):
    """Pin Q1.3: room 230 is now the Falleen Syndicate Tower, backed
    by an original Falleen Vigo (Sethel Vask)."""

    def setUp(self):
        self.coruscant = _yaml_load(COR_YAML)
        self.era = _yaml_load(ERA_YAML)
        self.npc_drop = _yaml_load(NPC_YAML)

    def _room_230(self):
        for r in self.coruscant.get("rooms") or []:
            if isinstance(r, dict) and r.get("id") == 230:
                return r
        return None

    # ─────────────────────────────────────────────────────────────────
    # Room rewrite
    # ─────────────────────────────────────────────────────────────────

    def test_room_230_has_new_slug(self):
        room = self._room_230()
        self.assertIsNotNone(
            room, "coruscant.yaml is missing room id=230."
        )
        self.assertEqual(
            room.get("slug"), "falleen_syndicate_tower",
            f"Room 230 slug should be 'falleen_syndicate_tower'; "
            f"got {room.get('slug')!r}. Q1.3 rewrote this room and "
            f"the slug is the durable identity contract."
        )

    def test_room_230_names_vask(self):
        room = self._room_230()
        combined = " ".join(filter(None, [
            room.get("name", ""),
            room.get("short_desc", ""),
            room.get("description", ""),
        ]))
        self.assertTrue(
            _has_word(combined, "Vask"),
            "Room 230 should reference Vigo Sethel Vask (the "
            "original Falleen Black Sun character replacing Xizor). "
            "Without a named backed character the room loses its "
            "Q1.3 design intent — a generic 'a Falleen syndicate "
            "tower' is acceptable for hallway-scenery rooms but not "
            "here, because the original room had emotional weight "
            "and the design call (option C) was 'replace with an "
            "original Falleen NPC'."
        )

    def test_room_230_no_canonical_black_sun(self):
        room = self._room_230()
        combined = " ".join(filter(None, [
            room.get("name", ""),
            room.get("short_desc", ""),
            room.get("description", ""),
        ]))
        for canonical in BLACK_SUN_CANONICAL:
            self.assertFalse(
                _has_word(combined, canonical),
                f"Room 230 references canonical Black Sun figure "
                f"{canonical!r}. The Q1.3 design call was to put an "
                f"ORIGINAL character on-stage; canonical figures "
                f"belong only in lore.yaml as off-stage referents."
            )

    # ─────────────────────────────────────────────────────────────────
    # Connectivity: the room is reachable
    # ─────────────────────────────────────────────────────────────────

    def test_room_230_has_inbound_exit(self):
        """The pre-Q1.3 room had NO inbound exits — it was a
        one-way dead end. Q1.3 added a reverse exit from
        upper_city_promenade so the new NPC is actually reachable
        by players (otherwise we've created backed content that's
        invisible at runtime)."""
        rooms_by_slug = {}
        for r in self.coruscant.get("rooms") or []:
            if isinstance(r, dict) and r.get("slug"):
                rooms_by_slug[r["slug"]] = r

        target = "falleen_syndicate_tower"
        inbound = []
        for slug, r in rooms_by_slug.items():
            for direction, dest in (r.get("exits") or {}).items():
                if dest == target:
                    inbound.append((slug, direction))
        # Also check top-level exits (older planet-YAML style)
        for e in self.coruscant.get("exits") or []:
            if not isinstance(e, dict):
                continue
            to_id = e.get("to")
            # Resolve to slug
            for r in self.coruscant.get("rooms") or []:
                if (isinstance(r, dict)
                        and r.get("id") == to_id
                        and r.get("slug") == target):
                    src_id = e.get("from")
                    for r2 in self.coruscant.get("rooms") or []:
                        if (isinstance(r2, dict)
                                and r2.get("id") == src_id):
                            inbound.append(
                                (r2.get("slug"), e.get("forward"))
                            )
                    break

        self.assertTrue(
            inbound,
            "falleen_syndicate_tower has no inbound exits. The "
            "pre-Q1.3 room (Xizor's Castle District) was a dead-end "
            "with one outbound exit and no way in; Q1.3 added a "
            "reverse-pair exit from upper_city_promenade. If this "
            "test fails, the reverse exit was removed."
        )

    # ─────────────────────────────────────────────────────────────────
    # NPC registration and placement
    # ─────────────────────────────────────────────────────────────────

    def test_npc_drop_registered_in_era(self):
        # Walk era.yaml for the NPCs list (its exact path varies by
        # era manifest version)
        found = False
        def walk(obj):
            nonlocal found
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if (k == "npcs" and isinstance(v, list)
                            and any("drop" in str(x) for x in v)):
                        if "npcs_drop_i_falleen_syndicate.yaml" in v:
                            found = True
                    walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    walk(x)
        walk(self.era)
        self.assertTrue(
            found,
            "npcs_drop_i_falleen_syndicate.yaml is not registered "
            "in era.yaml's NPCs list. The drop file exists but the "
            "engine's npc_loader will not pick it up without the "
            "registration, so Vask would never spawn."
        )

    def test_vask_npc_exists_in_drop(self):
        npcs = self.npc_drop.get("npcs") or []
        vask = next(
            (n for n in npcs
             if isinstance(n, dict) and "Vask" in (n.get("name") or "")),
            None,
        )
        self.assertIsNotNone(
            vask,
            "npcs_drop_i_falleen_syndicate.yaml does not contain a "
            "Vask NPC. Q1.3 requires the on-stage character to be "
            "backed; a room reference without a backing NPC means "
            "the player never actually meets him."
        )
        self.assertEqual(vask.get("species"), "Falleen")
        # Room field must match the rewritten room's display name
        room230 = self._room_230()
        self.assertEqual(
            vask.get("room"), room230.get("name"),
            f"Vask's NPC.room ({vask.get('room')!r}) does not match "
            f"room 230's display name ({room230.get('name')!r}). "
            f"npc_loader matches by display name, so a mismatch "
            f"means Vask spawns nowhere."
        )

    # ─────────────────────────────────────────────────────────────────
    # NPC content is Q1-compliant
    # ─────────────────────────────────────────────────────────────────

    def test_npc_drop_no_unframed_canonical_black_sun(self):
        """Vask's NPC entry can reference canonical Black Sun
        figures only with absence framing (e.g., 'the Underlord is
        offworld'). Direct on-stage references are violations.

        This test walks every player-facing string in the NPC drop
        and checks for unframed canonical names.
        """
        # Absence-framing markers — mirrors test_q1_2_extended_sweep.py
        absence_markers = (
            "off-world", "offworld", "off world", "elsewhere",
            "not here", "not present", "remains at", "historical",
            "the late", "presumed", "vanished", "rumored to",
            "in absentia", "off-stage",
        )
        npcs = self.npc_drop.get("npcs") or []

        def collect_strings(obj):
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from collect_strings(v)
            elif isinstance(obj, list):
                for x in obj:
                    yield from collect_strings(x)

        violations = []
        for npc in npcs:
            for s in collect_strings(npc):
                low = s.lower()
                framed = any(m in low for m in absence_markers)
                for canonical in BLACK_SUN_CANONICAL:
                    if _has_word(s, canonical) and not framed:
                        violations.append((canonical, s[:120]))
                        break
        self.assertEqual(
            violations, [],
            f"NPC drop has unframed canonical Black Sun references: "
            f"{violations}. Wrap each reference with an absence-"
            f"framing phrase or remove the canonical name."
        )


if __name__ == "__main__":
    unittest.main()
