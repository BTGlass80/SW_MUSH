# -*- coding: utf-8 -*-
"""tests/test_mob_grind_no_secured_placements.py

GRIND-REALIGNMENT regression guard (drop grind-realignment, 2026-06-24).

Brian's call (2026-06-24): grinding belongs in the WILDERNESS and in
lawless / contested-DANGEROUS zones, NOT the civilized core. The teardown
removed 158 misplaced mob-grind placements. The single most objective slice
of that — and the one a future content drop is most likely to silently
re-introduce — is a huntable mob seeded in a **SECURED** room, where the
engine HARD-BLOCKS combat (engine.security.is_combat_allowed -> False).
Such a mob is literally unkillable: dead content the player can see but
never fight.

This guard boots the real clone_wars world and resolves every
``npcs_drop_mob_grind_*.yaml`` placement (the civic-mob ``npcs:`` key)
through the live ``get_effective_security`` resolver. If any lands in a
SECURED room, the test fails with the offender list.

Scope note: the three ``wilderness_npcs:``-keyed mob-grind files
(coruscant_underworld[_deep], geonosis_ey_akh) are the GOOD wilderness
grind content; their rooms resolve via the wilderness-region branch
(lawless by design) and are intentionally out of scope here.

Marked ``slow`` (full world-build); runs in the full gate, opt-in via
``-m slow`` in the dev loop.
"""
from __future__ import annotations

import glob
import os

import pytest
import yaml

from engine.security import SecurityLevel, get_effective_security

HERE = os.path.dirname(os.path.abspath(__file__))
CW_DIR = os.path.abspath(os.path.join(HERE, "..", "data", "worlds", "clone_wars"))


class TestMobGrindNoSecuredPlacements:
    @pytest.mark.slow
    async def test_no_mob_grind_npc_in_secured_room(self, harness):
        db = harness.db
        files = sorted(glob.glob(
            os.path.join(CW_DIR, "npcs_drop_mob_grind_*.yaml")))
        assert files, "no mob-grind files found — glob path broke"

        offenders: list[tuple[str, str, str]] = []
        not_found: list[tuple[str, str]] = []
        checked = 0
        for f in files:
            data = yaml.safe_load(open(f, encoding="utf-8")) or {}
            for npc in (data.get("npcs") or []):   # civic-mob key only
                room = (npc.get("room") or "").strip()
                rows = await db.fetchall(
                    "SELECT id FROM rooms WHERE name = ?", (room,))
                if not rows:
                    not_found.append((os.path.basename(f), room))
                    continue
                sec = await get_effective_security(rows[0]["id"], db, None)
                checked += 1
                if sec == SecurityLevel.SECURED:
                    offenders.append(
                        (os.path.basename(f), npc.get("name", "?"), room))

        assert checked > 0, "no mob-grind placements were checked"
        # Security violation is the PRIMARY guard — assert it first so a
        # combined failure surfaces the SECURED placement, not the room typo.
        assert not offenders, (
            "Mob-grind NPCs found in SECURED (combat-blocked) rooms — these are "
            "unkillable dead content. Grinding belongs in the wilderness / "
            "lawless-contested zones, not the civilized core. "
            f"Offenders: {offenders}")
        assert not not_found, (
            "mob-grind NPCs reference rooms that do not resolve in the world "
            f"(misplaced / typo'd): {not_found}")
