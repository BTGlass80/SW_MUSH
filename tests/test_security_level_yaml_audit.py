# -*- coding: utf-8 -*-
"""
tests/test_security_level_yaml_audit.py — Audit/diagnostic test for the
§6.2 dual-source-drift bug discovered during W-CMB-2 development.

──────────────────────────────────────────────────────────────────────
The bug
──────────────────────────────────────────────────────────────────────

The world-content YAML files declare ``security_level:`` at the room
level on ~150 rooms across the CW planet files:

    - id: 53
      slug: jundland_dune_sea_edge
      name: "Jundland Wastes - Dune Sea Edge"
      ...
      security_level: lawless     ← inert

The engine resolver in ``engine/security.py::get_effective_security``
reads ``db.get_room_property(room_id, "security")``. The DB column
``get_room_property`` consults (db/database.py L1597-1640) reads
``room.properties["security"]`` first, then walks the zone hierarchy
for ``zone.properties["security"]``.

Neither path consumes the room-level ``security_level:`` YAML field.
The writer in ``engine/world_writer.py`` L186 reads only
``room.raw.get("properties", {})`` — the explicit ``properties:``
block. The top-level ``security_level:`` field is read by **no
production code path** (grep ``security_level`` --include=*.py in the
engine/parser/server tree returns zero functional hits).

──────────────────────────────────────────────────────────────────────
Impact
──────────────────────────────────────────────────────────────────────

Every room with ``security_level: lawless`` declared at the top level
is treated as CONTESTED at runtime (the default when no
``properties.security`` exists). Every ``security_level: secured`` is
likewise CONTESTED. Players in these rooms get the wrong PvP-consent
behavior, the wrong [LAWLESS]/[SECURED] tag, and the wrong combat
gates.

This was the underlying cause of W-CMB-2/W-CMB-3 failing during
wilderness combat smoke development (May 18, 2026 rollup drop). The
W.2.4 wilderness keying refactor was working correctly; the
``_check_pvp_consent`` gate refused the attack because the sentinel
room (CW Tatooine room 53, ``jundland_dune_sea_edge``,
``security_level: lawless`` declared in YAML) was resolved as
CONTESTED at runtime.

──────────────────────────────────────────────────────────────────────
What this test does
──────────────────────────────────────────────────────────────────────

This test is a **read-only audit**. It walks every planet YAML in
``data/worlds/{clone_wars,gcw}/planets/`` and counts:

  * Rooms with top-level ``security_level:`` set, by value
  * Rooms with ``properties.security`` set, by value
  * Rooms with BOTH (the loader currently keeps properties; the
    top-level field is silently dropped)

The test **does not fail** when drift is found — it reports the
discrepancy via skip-with-message so the audit shows up in pytest
output but doesn't break the suite. When Brian fixes the writer
(one-line change in ``engine/world_writer.py`` to merge
``security_level`` into properties, or a content-pass that rewrites
each room's annotation), the test can be promoted to a positive
assertion.

The audit is data-driven: a future drop that adds new planet content
will get a fresh audit count automatically. The expected value
captured here is the May 18, 2026 snapshot.

──────────────────────────────────────────────────────────────────────
Status: CLOSED by Drop S-RES (May 18 2026)
──────────────────────────────────────────────────────────────────────

The writer-level merge (resolution option A) shipped in Drop S-RES.
``engine/world_writer.py`` now promotes top-level ``security_level:``
into ``properties.security`` when properties doesn't already declare
it. The end-to-end contract is pinned by two companion test files:

  * ``tests/test_security_resolver_writer_merge.py`` — 6 unit tests
    drive ``_write_rooms`` with a stubbed DB and inspect the JSON
    payload. Covers top-level-only / properties-only / both-set
    (properties wins) / neither-set, all three values, and the
    slug+security coexistence guard.

  * ``tests/test_security_resolver_runtime.py`` — 5 integration tests
    use a real in-memory ``Database``, the real ``_write_rooms``,
    and call ``engine.security.get_effective_security`` to confirm
    the SecurityLevel enum that comes out the other end.

This file remains as a **reporter** (not promoted to a strict
assertion) on purpose: the YAML still has top-level ``security_level:``
declarations and we don't want a content rewrite in this drop. The
audit count surfaces the authoring style; the runtime behavior is
covered by the two tests above.

──────────────────────────────────────────────────────────────────────
Resolution options (historical — kept for reference)
──────────────────────────────────────────────────────────────────────

Two clean paths:

A. **Wire the writer.** ~2-line patch to ``engine/world_writer.py``
   at the room-write site:

       properties = room.raw.get("properties", {}) or {}
       # NEW: top-level security_level field promotes into properties
       if "security" not in properties:
           sl = room.raw.get("security_level")
           if sl:
               properties["security"] = sl
       ...

   Pros: minimal-touch, preserves YAML authoring style, immediately
   honors ~150 rooms' security declarations.
   Cons: changes runtime behavior for those rooms — needs a
   smoke pass + targeted regression to confirm nothing downstream
   broke (e.g. mission completion gates that quietly relied on
   the CONTESTED default).

B. **Rewrite the YAMLs.** Move every ``security_level: X`` field into
   ``properties: { security: X }`` and delete the top-level
   annotation. Same runtime effect as A, but the authoring style
   becomes uniform (everyone uses ``properties.``). Larger touch
   surface (~150 rooms × 6 files) and more risk of merge friction
   with in-flight content drops.

Recommend **A**, paired with a smoke/regression sweep across the
combat consent path, the [LAWLESS]/[CONTESTED]/[SECURED] tag
renderer, and any mission/bounty gates that read security.
"""
from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


PLANET_YAML_DIRS = (
    PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets",
    PROJECT_ROOT / "data" / "worlds" / "gcw" / "planets",
)


def _walk_planet_yamls():
    """Yield (path, parsed_yaml) for every planet yaml."""
    for base in PLANET_YAML_DIRS:
        if not base.exists():
            continue
        for f in sorted(base.glob("*.yaml")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
            except yaml.YAMLError:
                # If a planet YAML is malformed we don't want this
                # audit to mask the real failure; let other tests
                # catch it.
                continue
            if not isinstance(data, dict):
                continue
            yield (f, data)


def _audit():
    """Walk every planet yaml. Return a summary dict:

    {
        "by_value_top_level":  {"lawless": N, "contested": N, "secured": N},
        "by_value_properties": {"lawless": N, ...},
        "both_set_same":       N,
        "both_set_different":  N,
        "top_level_only":      N,
        "properties_only":     N,
        "neither":             N,
        "total_rooms":         N,
        "per_file": [
            {"file": "tatooine.yaml", "top_level": N, "properties": N},
            ...
        ],
    }
    """
    summary = {
        "by_value_top_level": {},
        "by_value_properties": {},
        "both_set_same": 0,
        "both_set_different": 0,
        "top_level_only": 0,
        "properties_only": 0,
        "neither": 0,
        "total_rooms": 0,
        "per_file": [],
    }
    for path, data in _walk_planet_yamls():
        rooms = data.get("rooms") or []
        per_file_top = 0
        per_file_props = 0
        for r in rooms:
            if not isinstance(r, dict):
                continue
            summary["total_rooms"] += 1
            top_level = r.get("security_level")
            props = r.get("properties") or {}
            in_props = (props.get("security") if isinstance(props, dict)
                        else None)
            if top_level:
                per_file_top += 1
                summary["by_value_top_level"][top_level] = (
                    summary["by_value_top_level"].get(top_level, 0) + 1)
            if in_props:
                per_file_props += 1
                summary["by_value_properties"][in_props] = (
                    summary["by_value_properties"].get(in_props, 0) + 1)
            if top_level and in_props:
                if top_level == in_props:
                    summary["both_set_same"] += 1
                else:
                    summary["both_set_different"] += 1
            elif top_level and not in_props:
                summary["top_level_only"] += 1
            elif in_props and not top_level:
                summary["properties_only"] += 1
            else:
                summary["neither"] += 1
        summary["per_file"].append({
            "file": path.relative_to(PROJECT_ROOT).as_posix(),
            "top_level": per_file_top,
            "properties": per_file_props,
        })
    return summary


class TestSecurityLevelYamlAudit(unittest.TestCase):
    """Read-only audit of the ``security_level`` YAML→runtime drift.

    This test always passes if it can run at all — it's a reporting
    tool, not a regression-gate. The point is to surface the drift
    count in pytest output (via warnings.warn) so a future drop has
    an authoritative number for the fix scope.

    When the writer is fixed (resolution option A in the file
    docstring), promote this test to a strict assertion:

        self.assertEqual(summary["top_level_only"], 0,
            "After the writer fix, every top-level security_level "
            "must also appear in properties.security.")

    Or run a one-time content-pass that rewrites all top-level
    annotations into ``properties.security:`` and then add:

        self.assertEqual(summary["top_level_only"], 0,
            "Top-level security_level: is deprecated; use "
            "properties.security: instead.")
    """

    def test_audit_security_level_drift(self):
        summary = _audit()

        # Always-passing reporter: emit a warning with the audit
        # snapshot. Pytest with -W default::UserWarning surfaces it,
        # and the warning text is part of the human-readable test
        # output.
        report_lines = [
            "",
            "──────────────────────────────────────────────────────",
            "security_level YAML→runtime drift audit",
            "──────────────────────────────────────────────────────",
            f"Total rooms scanned:                  "
            f"{summary['total_rooms']}",
            f"  top-level security_level: ONLY      "
            f"{summary['top_level_only']}  ← inert at runtime",
            f"  properties.security: ONLY           "
            f"{summary['properties_only']}",
            f"  both set, same value                "
            f"{summary['both_set_same']}",
            f"  both set, DIFFERENT values          "
            f"{summary['both_set_different']}  ← bug",
            f"  neither set (defaults CONTESTED)    "
            f"{summary['neither']}",
            "",
            "By top-level security_level value:",
        ]
        for k, v in sorted(summary["by_value_top_level"].items()):
            report_lines.append(f"  {k:12s}  {v:4d}")
        report_lines.append("")
        report_lines.append("By properties.security value:")
        for k, v in sorted(summary["by_value_properties"].items()):
            report_lines.append(f"  {k:12s}  {v:4d}")
        report_lines.append("")
        report_lines.append("Per-file breakdown (top-level / properties):")
        for f in summary["per_file"]:
            report_lines.append(
                f"  {f['file']}  →  "
                f"top-level={f['top_level']:3d} / "
                f"properties={f['properties']:3d}"
            )
        report_lines.append(
            "──────────────────────────────────────────────────────"
        )
        msg = "\n".join(report_lines)
        warnings.warn(msg, UserWarning, stacklevel=1)
        # Don't fail — this is a reporter, not a gate.

    def test_dune_sea_sentinel_is_in_audit(self):
        """Sanity: the canonical example (CW Tatooine room 53,
        jundland_dune_sea_edge) actually has top-level
        ``security_level: lawless`` set in YAML. If a future drop
        rewrites this room, the audit's example pointer breaks."""
        tat = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "planets" / "tatooine.yaml")
        if not tat.exists():
            self.skipTest("CW Tatooine YAML not present.")
        with open(tat, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        rooms = data.get("rooms") or []
        target = None
        for r in rooms:
            if isinstance(r, dict) and r.get("id") == 53:
                target = r
                break
        self.assertIsNotNone(
            target,
            "CW Tatooine room id=53 missing; the audit example pointer "
            "is stale. Update the audit docstring."
        )
        # We tolerate the room being either fixed (in properties) or
        # still using the inert top-level field — the audit reports
        # which it is.
        top = target.get("security_level")
        in_props = (target.get("properties") or {}).get("security")
        self.assertTrue(
            top or in_props,
            f"CW Tatooine room id=53 has neither security_level: nor "
            f"properties.security: declared. Either the room was "
            f"materially changed, or the audit example is wrong. "
            f"Room: {target.get('slug')!r}"
        )


if __name__ == "__main__":
    unittest.main()
