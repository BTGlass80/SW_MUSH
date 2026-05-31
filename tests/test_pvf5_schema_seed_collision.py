# -*- coding: utf-8 -*-
"""
tests/test_pvf5_schema_seed_collision.py — Regression guard for the
YAML-id-vs-DB-id miscalibration bug surfaced by PVF-5 on May 18 2026.

Background
==========

The schema in ``db/database.py`` pre-inserts three legacy Mos Eisley
rooms via raw INSERT statements at DB ids 1, 2, 3:

  * id 1: "Landing Pad - Mos Eisley Spaceport"
  * id 2: "Mos Eisley Street"
  * id 3: "Chalmun's Cantina"

These predate the YAML-driven world build and are pinned at low DB
ids because the schema runs BEFORE ``write_world_bundle()``. The
YAML-write path uses ``db.create_room()`` which delegates to
SQLite's ``AUTOINCREMENT``, so the first YAML room (yaml_id 0,
``docking_bay_94_entrance``) lands at DB id 4, not DB id 1.

The semantic impact: any smoke scenario that hardcodes ``room_id=1``
expecting a specific CW spaceport room actually gets the legacy
seed instead — which has ``zone_id=None``, ``properties={}``, and
resolves CONTESTED by default. PVF-5 surfaced this because its
assertion is tight: "an attack in this room MUST NOT produce a
combat_state event because the room is SECURED." DB id 1 is
CONTESTED, so the attack engages, and the assertion fails.

What this file guards
=====================

1. The legacy seed at DB id 1 exists and matches its known shape
   (name, zone_id=None, properties={}). This is a deliberate
   schema feature that the GCW auto-build and the
   ``tests/smoke/scenarios/movement.py`` scenarios depend on. If
   somebody removes or changes the seed, this test fails loudly so
   the change is intentional rather than accidental.

2. The CW YAML world write writes its rooms at DB ids 4+ (not 1+),
   because the seed claimed 1-3 first. This is the invariant smoke
   scenarios must reason about. If somebody changes the seed scope
   or insert order, this test catches it.

3. ``h.room_id_by_slug("docking_bay_94_pit")`` resolves to a DB id
   != 1 in the CW era. This is the slug-lookup pattern smoke
   scenarios should use. If somebody reorganizes the YAML world so
   that ``docking_bay_94_pit`` lands at DB id 1, the slug-lookup
   pattern still works — but this test will fail, prompting a
   review of whether the seed should still be there.

4. Recoverable: even with the offset, ``get_room_by_slug`` finds the
   intended room and ``get_effective_security`` resolves SECURED.
   This is the end-to-end PVF-5 invariant.
"""
from __future__ import annotations

import json

import pytest


pytestmark = pytest.mark.smoke


class TestSchemaSeedRoomCollision:
    """The schema seeds DB ids 1-3 before the YAML world writer
    runs. CW YAML rooms land at DB ids 4+. Smoke scenarios that
    need a specific CW room must resolve by slug, never by hardcoded
    integer id.
    """

    async def test_db_id_1_is_legacy_landing_pad_not_yaml_room(
            self, harness):
        """DB id 1 is the schema-seed "Landing Pad - Mos Eisley
        Spaceport", not the YAML id-0 room (which is
        ``docking_bay_94_entrance``).
        """
        rows = await harness.db.fetchall(
            "SELECT id, name, zone_id, properties FROM rooms WHERE id = 1"
        )
        assert rows, "DB id 1 should exist (schema seed inserts it)"
        row = dict(rows[0])
        assert row["name"] == "Landing Pad - Mos Eisley Spaceport", (
            f"DB id 1's name changed from the schema-seed value. "
            f"Got: {row['name']!r}. If this is intentional (e.g., the "
            f"seed was removed), update or delete this test and "
            f"audit smoke scenarios that login_as(room_id=1)."
        )
        assert row["zone_id"] is None, (
            f"Legacy seed at DB id 1 should have zone_id=None; got "
            f"{row['zone_id']!r}. If this is intentional (e.g., a "
            f"migration linked it to a zone), audit PVF-5 and W-CMB-1."
        )

    async def test_db_id_1_resolves_contested_not_secured(
            self, harness):
        """The legacy seed at DB id 1 has no zone link and no
        ``properties.security``, so the resolver falls through to
        CONTESTED. This is the failure mode that made PVF-5 break
        when it logged in at room_id=1 expecting SECURED.
        """
        from engine.security import (
            get_effective_security, SecurityLevel)
        eff = await get_effective_security(1, harness.db, character=None)
        assert eff == SecurityLevel.CONTESTED, (
            f"DB id 1 resolves to {eff!r}, not CONTESTED. If this is "
            f"intentional, this is now a public security room and "
            f"PVF-5's room sourcing should be updated."
        )

    async def test_cw_yaml_rooms_start_at_db_id_4_or_higher(
            self, harness):
        """The first YAML room (yaml_id 0, ``docking_bay_94_entrance``)
        writes after the schema seeds claim DB ids 1-3, so it lands
        at DB id 4 or higher.
        """
        row = await harness.db.get_room_by_slug("docking_bay_94_entrance")
        assert row is not None, (
            "CW world write should have created "
            "docking_bay_94_entrance, but get_room_by_slug returned "
            "None. World loader broken or wrong era pinned."
        )
        db_id = int(row["id"])
        assert db_id >= 4, (
            f"docking_bay_94_entrance is at DB id {db_id}, but the "
            f"schema seeds claim DB ids 1-3 first, so YAML rooms "
            f"should start at id 4. If this changed, audit the "
            f"smoke scenarios that hardcode room_id=1 (PVF-5, W-CMB-1)."
        )

    async def test_docking_bay_94_pit_resolves_secured_by_slug(
            self, harness):
        """End-to-end PVF-5 invariant: looked up by slug,
        ``docking_bay_94_pit`` resolves SECURED via the
        ``tatooine_spaceport`` zone-level security default added
        by S-RES.2. This is the room PVF-5 actually wants.
        """
        from engine.security import (
            get_effective_security, SecurityLevel)

        db_id = await harness.room_id_by_slug("docking_bay_94_pit")
        assert db_id != 1, (
            f"Slug lookup returned db_id=1 — but DB id 1 is the "
            f"legacy seed. If docking_bay_94_pit actually wrote to "
            f"DB id 1, the schema seeds are gone or the YAML id "
            f"collision is exposing a deeper bug."
        )

        eff = await get_effective_security(
            db_id, harness.db, character=None)
        assert eff == SecurityLevel.SECURED, (
            f"docking_bay_94_pit (DB id {db_id}) resolves to {eff!r}, "
            f"not SECURED. The tatooine_spaceport zone-level "
            f"security default from S-RES.2 may have been removed "
            f"from zones.yaml. PVF-5 will fail if this regresses."
        )

    async def test_room_id_by_slug_raises_lookuperror_for_unknown(
            self, harness):
        """The harness helper raises ``LookupError`` for unknown
        slugs, so a scenario typo fails loudly instead of silently
        defaulting to a wrong room.
        """
        with pytest.raises(LookupError):
            await harness.room_id_by_slug(
                "this_slug_definitely_does_not_exist_anywhere"
            )

    async def test_room_id_by_slug_raises_for_empty_string(
            self, harness):
        """Empty slug is a programmer error; the helper raises."""
        with pytest.raises(LookupError):
            await harness.room_id_by_slug("")
