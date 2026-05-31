# -*- coding: utf-8 -*-
"""
tests/test_security_zone_coverage.py — Drop S-RES.2 (May 18 2026).

Companion to test_security_level_yaml_audit.py (the original reporter).
This test promotes the audit to a strict content-level assertion:

  **Every CW planet room must resolve to a non-default security level**,
  either by declaring its own (top-level ``security_level:`` or
  ``properties.security:``) OR by being in a zone whose
  ``zones.yaml`` entry declares ``properties.security:``.

The check is purely text/YAML-level — no DB build needed. It walks
each planet YAML, finds the room's zone slug, then looks up that
zone in ``zones.yaml`` and confirms the zone declares a security
default if the room doesn't.

Why this matters
────────────────
Pre-S-RES.2, 222 CW planet rooms had no security declaration at
either room or zone level, silently resolving to the CONTESTED
default at runtime. Room 1 (``docking_bay_94_pit``, the brand-new-
character spawn AND the respawn-on-death point) was among them —
new players landed in [CONTESTED] with no clear safe radius.

S-RES.2 added zone-level defaults to 13 zones in zones.yaml. After
that drop, the "neither" count should drop to ~0 for the CW era.
This test pins that contract so future authoring drops can't
silently introduce new untagged rooms.

GCW is excluded
───────────────
The GCW era's planet files don't currently declare security at any
level (audit confirms 0 in either column for all 4 GCW planet
files). GCW is on the longer-horizon roadmap and not pre-launch
critical. A future GCW content drop can add this coverage when the
era is staged for delivery.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CW_ZONES_YAML = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "zones.yaml"
CW_PLANETS_DIR = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"


def _load_zone_security_map() -> dict[str, str]:
    """Walk zones.yaml; return zone_slug → security_value for every
    zone that declares ``properties.security``. Walks the parent
    chain too: a zone with no own properties.security but a parent
    that does inherits.
    """
    raw = yaml.safe_load(CW_ZONES_YAML.read_text(encoding="utf-8"))
    zones = raw.get("zones") or {}
    direct: dict[str, str | None] = {}
    parent: dict[str, str | None] = {}
    for slug, zd in zones.items():
        if not isinstance(zd, dict):
            continue
        props = zd.get("properties") or {}
        sec = props.get("security") if isinstance(props, dict) else None
        direct[slug] = sec
        parent[slug] = zd.get("parent")

    # Walk parent chain (max depth 10, same as the engine's resolver)
    out: dict[str, str] = {}
    for slug in direct:
        cur = slug
        depth = 0
        while cur and depth < 10:
            sec = direct.get(cur)
            if sec:
                out[slug] = sec
                break
            cur = parent.get(cur)
            depth += 1
    return out


def _walk_cw_rooms():
    """Yield (planet_file_stem, room_dict) for each room in each CW
    planet YAML."""
    for path in sorted(CW_PLANETS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        for r in data.get("rooms") or []:
            if isinstance(r, dict):
                yield (path.stem, r)


class TestSecurityZoneCoverage(unittest.TestCase):
    """Every CW planet room has a deterministic security level — no
    silent fallthrough to the CONTESTED default."""

    def test_every_cw_room_has_resolved_security(self):
        """Every room declares security itself OR is in a zone that
        does. No room should fall through to the resolver's
        CONTESTED default by accident."""
        zone_security = _load_zone_security_map()
        uncovered: list[tuple[str, str, str]] = []  # (planet, slug, zone)

        for planet, room in _walk_cw_rooms():
            top = room.get("security_level")
            props = room.get("properties") or {}
            in_props = (props.get("security")
                        if isinstance(props, dict) else None)
            zone_slug = room.get("zone") or ""
            zone_sec = zone_security.get(zone_slug)

            covered = bool(top or in_props or zone_sec)
            if not covered:
                uncovered.append(
                    (planet, room.get("slug", "?"), zone_slug)
                )

        if uncovered:
            lines = [
                f"{len(uncovered)} CW rooms have no security level at "
                "any layer (room or zone). After S-RES.2 this count "
                "should be 0. Each uncovered room is silently "
                "defaulting to CONTESTED at runtime.",
                "",
                "Either add the room's `security_level:` (or "
                "`properties.security:`), or add "
                "`properties: { security: <level> }` to the zone in "
                "data/worlds/clone_wars/zones.yaml.",
                "",
                "Uncovered rooms:",
            ]
            # Group by zone for legibility
            by_zone: dict[str, list[tuple[str, str]]] = {}
            for planet, slug, zone in uncovered:
                by_zone.setdefault(zone, []).append((planet, slug))
            for zone in sorted(by_zone):
                lines.append(f"  zone={zone!r}:")
                for planet, slug in by_zone[zone][:3]:
                    lines.append(f"    {planet}: {slug}")
                if len(by_zone[zone]) > 3:
                    lines.append(
                        f"    ... and {len(by_zone[zone]) - 3} more"
                    )
            self.fail("\n".join(lines))

    def test_starter_spawn_is_secured(self):
        """The brand-new-character spawn point (room id=1,
        docking_bay_94_pit) MUST resolve as SECURED — not CONTESTED.

        This is the launch-blocker fix: new players land at room 1,
        respawn at room 1 on death, and the spawn point should be
        the safe controlled-arrival space. The fix relies on the
        tatooine_spaceport zone declaring properties.security:
        secured in zones.yaml.

        Note: this test pins only room 1. The 2-hop radius
        (notably mos_eisley_spaceport_row in tatooine_mos_eisley)
        IS allowed to be CONTESTED — that's the deliberate
        narrative gradient: stepping out of the docking precinct
        is the player's first encounter with the Mos Eisley
        "wretched hive" tone. The tutorial is expected to explain
        the [CONTESTED] tag before that moment.

        If this test fails, the starter experience has regressed —
        either the room moved, the zone changed, or the zone-level
        security default was removed.
        """
        tat = CW_PLANETS_DIR / "tatooine.yaml"
        self.assertTrue(tat.exists(), "CW Tatooine YAML missing.")
        data = yaml.safe_load(tat.read_text(encoding="utf-8"))
        room1 = None
        for r in data.get("rooms") or []:
            if isinstance(r, dict) and r.get("id") == 1:
                room1 = r
                break
        self.assertIsNotNone(
            room1,
            "CW Tatooine room id=1 missing. The default spawn is "
            "hardcoded to id=1 in server/config.py; if the room "
            "moved, the spawn config must move with it.",
        )

        # Effective security: prefer room's own declaration, fall
        # back to zone.
        top = room1.get("security_level")
        props = room1.get("properties") or {}
        in_props = (props.get("security")
                    if isinstance(props, dict) else None)
        if top or in_props:
            effective = in_props or top
        else:
            zone_security = _load_zone_security_map()
            effective = zone_security.get(room1.get("zone") or "")

        self.assertEqual(
            effective, "secured",
            f"Room 1 ({room1.get('slug')!r}, zone="
            f"{room1.get('zone')!r}) must resolve as SECURED. "
            f"Got {effective!r}. New players spawn here and "
            f"respawn here on death — must be safe.",
        )


if __name__ == "__main__":
    unittest.main()
