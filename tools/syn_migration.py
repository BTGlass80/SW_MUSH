# -*- coding: utf-8 -*-
"""
tools/syn_migration.py — Contestable Wilderness pivot migration.

PER ``contestable_wilderness_design_v2.md`` §5 (SYN.0 deliverable):
   "Write migration script: dissolve city-map cities with 75% refund;
    wipe ``territory_claims``."

PER ``HANDOFF_MAY24_DESIGN_LOCK_v2.md`` (SYN.0 scope):
   "Tag deprecated surfaces in TODO.json."

This script is the SYN.0 deliverable. **It does not run yet.** SYN.0
ships the *plan* and the *script*; SYN.1 wires the schema change and
calls this migration as part of its drop. The migration was authored
in SYN.0 so SYN.1 can apply it atomically with the schema rename.

──────────────────────────────────────────────────────────────────────
Migration sequence (when SYN.1 invokes this)
──────────────────────────────────────────────────────────────────────

1. **Audit phase** — count rows that will be dissolved/wiped. Report
   to stdout. Always runs (whether --dry-run or not).

2. **Dissolve city-map cities** (§2.9 + §6 of v2 design). For every
   row in ``player_cities`` whose anchor HQ entry room lies in a
   regular city-map zone (i.e. not a wilderness region):

   - Refund 75% of the founding cost to the city's org treasury,
     using ``db.adjust_org_treasury`` so the audit log records the
     refund.
   - Mark ``player_cities.state = 'dissolved'`` (does NOT delete the
     row — preserves the audit trail). Append a `dissolved_reason`
     note: ``"SYN pivot 2026 — city-map cities retired in favor of
     wilderness anchors"``.
   - Cascade-clear ``player_city_rooms`` for that city.
   - Emit one news entry per dissolved city via the standard news
     surface so players see what happened on first login post-pivot.

3. **Wipe territory_claims** (§5 design.SYN.1; §6 design.deprecation
   — pure cold start, zero seeded influence). Two ways this can run:

   - ``--cold-start`` (default for SYN.1 invocation): unconditionally
     deletes every row in ``territory_claims``. Per design §1.4
     ("Why cold start with zero seeded influence") this is the
     correct behavior for launch.
   - ``--preserve-room-claims`` (debugging only): leaves the table
     alone. Not used in production.

4. **Tag deprecated surfaces** in ``TODO.json::tech_debt`` from
   ``deprecated_after_design_pivot_2026_05_24`` to
   ``retired_in_SYN.N_<date>``. SYN.0 does NOT do this transition —
   each SYN.N drop transitions its own surfaces. The function lives
   here so all SYN drops use the same helper.

──────────────────────────────────────────────────────────────────────
Why this lives in tools/ rather than engine/
──────────────────────────────────────────────────────────────────────

This is a one-shot migration. It runs once per environment, on the
SYN.1 deployment. Putting it in ``engine/`` would imply it's part of
runtime; ``tools/`` is the right home for sketches, build scripts,
and migrations.

──────────────────────────────────────────────────────────────────────
Pre-flight findings (logged during SYN.0 audit)
──────────────────────────────────────────────────────────────────────

The pre-flight audit conducted during SYN.0 surfaced three findings
that adjust the SYN.1+ scope:

* **Finding 1.** The TODO.json deprecation list names
  ``MAX_CLAIMS_PER_ZONE`` and ``MAX_CLAIMS_PER_ORG``. These constants
  do not exist in ``engine/territory.py``. The actual constants are
  ``CLAIM_MAX_PER_ZONE = 3`` and ``CLAIM_MAX_TOTAL = 10`` (territory.py
  lines 66–67). SYN.1 retires these by their real names. The TODO.json
  surface list is corrected in this drop.

* **Finding 2.** ``is_room_claimed_by`` is consumed in five callers
  beyond ``engine/security.py::_apply_claim_upgrade``:
  ``parser/faction_commands.py`` (armory access), three internal
  ``engine/territory.py`` callers (armory storage/withdraw),
  ``engine/sleeping.py`` (sleeping bonus in claimed territory),
  and ``engine/security.py`` itself. The design doc §3.1 only names
  ``_apply_claim_upgrade``. SYN.1 retargets all six call sites or
  retires the function entirely — to be decided in SYN.1's own pre-
  flight.

* **Finding 3.** ``engine/player_cities.py::found_city`` is NOT
  anchor-agnostic at HEAD. The full validation chain (steps 7–10 of
  the function) anchors to the org's tier-5 HQ entry room, then to
  that room's zone, then to that zone's declared_security and to
  the org's influence in that zone. SYN.4 will rewrite all four
  steps to anchor on a wilderness region instead. The ~2 sess
  estimate in the design doc is consistent with this scope.

──────────────────────────────────────────────────────────────────────
Usage (when SYN.1 invokes this)
──────────────────────────────────────────────────────────────────────

    python tools/syn_migration.py --audit-only      # SYN.0 dry run
    python tools/syn_migration.py --dry-run         # full plan, no writes
    python tools/syn_migration.py --cold-start      # do it (SYN.1 production)

──────────────────────────────────────────────────────────────────────
Reversibility
──────────────────────────────────────────────────────────────────────

This migration is NOT cleanly reversible. The 75% refund is one-way
(once credits enter the treasury they can be spent), and ``player_
cities.state = 'dissolved'`` is a marker, not a reversible operation.
Brian's design call (May 24): cold start is desired, no reversibility
needed.

If a rollback IS needed mid-flight, SYN.1's transaction wrapper
covers atomicity within the drop — see ``apply_syn1_migration``
which wraps schema + this migration in one ``BEGIN``/``COMMIT``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import aiosqlite


# ──────────────────────────────────────────────────────────────────────
# Audit phase
# ──────────────────────────────────────────────────────────────────────

async def audit(conn) -> dict:
    """Count rows that would be touched by a full migration run.

    Returns a dict with the audit results, suitable for printing.
    """
    result: dict[str, int | list] = {}

    # 1. Active player_cities count
    cur = await conn.execute(
        "SELECT COUNT(*) FROM player_cities WHERE state = 'active'"
    )
    row = await cur.fetchone()
    result["active_cities"] = int(row[0]) if row else 0

    # 2. territory_claims count (will be wiped on cold start)
    try:
        cur = await conn.execute("SELECT COUNT(*) FROM territory_claims")
        row = await cur.fetchone()
        result["territory_claims_rows"] = int(row[0]) if row else 0
    except aiosqlite.OperationalError:
        # Schema doesn't have the table yet — pre-Drop-6 environment.
        result["territory_claims_rows"] = 0

    # 3. territory_influence row count (NOT wiped — design §1.4 names
    # only territory_claims; influence carries forward but everything
    # is zero at cold start so this is effectively a no-op).
    try:
        cur = await conn.execute("SELECT COUNT(*) FROM territory_influence")
        row = await cur.fetchone()
        result["territory_influence_rows"] = int(row[0]) if row else 0
    except aiosqlite.OperationalError:
        result["territory_influence_rows"] = 0

    # 4. player_city_rooms count (cascade-cleared per dissolved city)
    try:
        cur = await conn.execute("SELECT COUNT(*) FROM player_city_rooms")
        row = await cur.fetchone()
        result["player_city_rooms_rows"] = int(row[0]) if row else 0
    except aiosqlite.OperationalError:
        result["player_city_rooms_rows"] = 0

    return result


def print_audit(label: str, results: dict) -> None:
    print(f"\n── {label} ──")
    for k, v in results.items():
        print(f"  {k:>30s} : {v}")
    print()


# ──────────────────────────────────────────────────────────────────────
# Phase 1 — Dissolve city-map cities (SYN.4 invokes; placeholder here)
# ──────────────────────────────────────────────────────────────────────

async def dissolve_city_map_cities(
    conn, *, dry_run: bool = True,
) -> dict:
    """Dissolve city-map cities with 75% founding-cost refund.

    Placeholder — full impl ships in SYN.4 alongside the wilderness-
    anchor retarget of ``engine/player_cities.py::found_city``. The
    rationale for deferring to SYN.4: dissolution + wilderness
    anchor + migration test in one atomic drop is cleaner than
    splitting across SYN.1 (schema) and SYN.4 (player_cities).

    Returns a dict describing what *would have* happened. This is
    SYN.0's pre-flight contract for SYN.4.
    """
    # Each candidate city: read founding_cost from founding metadata
    # (player_cities.founding_cost_credits column), apply 75% refund.
    # Real implementation pseudocode:
    #
    #   cursor = await conn.execute(
    #       "SELECT id, org_id, founding_cost_credits, name "
    #       "FROM player_cities WHERE state = 'active'"
    #   )
    #   rows = await cursor.fetchall()
    #   for r in rows:
    #       refund = int(r["founding_cost_credits"] * 0.75)
    #       if not dry_run:
    #           await db.adjust_org_treasury(r["org_id"], refund)
    #           await conn.execute(
    #               "UPDATE player_cities SET state = 'dissolved', "
    #               "dissolved_reason = ?, dissolved_at = ? "
    #               "WHERE id = ?",
    #               ("SYN pivot 2026 — city-map retired", time.time(),
    #                r["id"]),
    #           )
    #           await conn.execute(
    #               "DELETE FROM player_city_rooms WHERE city_id = ?",
    #               (r["id"],),
    #           )
    #           # ... news entry, citizen notification ...
    return {
        "candidates": "SYN.4 will populate",
        "would_refund_total": "SYN.4 will compute",
        "would_dissolve": "SYN.4 will list",
    }


# ──────────────────────────────────────────────────────────────────────
# Phase 2 — Wipe territory_claims (SYN.1 invokes)
# ──────────────────────────────────────────────────────────────────────

async def wipe_territory_claims(
    conn, *, dry_run: bool = True,
) -> int:
    """Wipe all rows in ``territory_claims``.

    Returns the number of rows that were/would be deleted.

    Cold start per design §1.4. SYN.1 invokes this as part of its
    schema migration (which renames the table's room_id column to
    wilderness_region_slug after wiping).
    """
    cur = await conn.execute("SELECT COUNT(*) FROM territory_claims")
    row = await cur.fetchone()
    n = int(row[0]) if row else 0
    if not dry_run and n > 0:
        await conn.execute("DELETE FROM territory_claims")
        await conn.commit()
    return n


# ──────────────────────────────────────────────────────────────────────
# Phase 3 — Tag retired surfaces (helper for SYN.N transitions)
# ──────────────────────────────────────────────────────────────────────

def tag_surface_retired(
    todo_json_path: Path,
    surface_name: str,
    syn_drop_id: str,
    retired_date: str,
) -> bool:
    """Transition a tech_debt surface from `deprecated_after_design_pivot`
    to `retired_in_SYN.N_<date>`.

    Returns True if the transition was applied, False if the surface
    wasn't found in tech_debt or was already retired.

    Each SYN.N drop calls this for every surface it retires, in the
    same drop. Per Pattern-2 hygiene: deprecation tags are forward
    promises; retirement transitions are the receipts.
    """
    with open(todo_json_path, "r", encoding="utf-8") as f:
        todo = json.load(f)

    matched = False
    tech_debt = todo.get("tech_debt", []) or []
    for entry in tech_debt:
        if entry.get("name") != "shipped_surfaces_retiring_in_SYN_sequence":
            continue
        for surface in entry.get("surfaces", []):
            if surface.get("surface") == surface_name:
                if "retired_in_SYN" in (surface.get("status") or ""):
                    return False  # already retired
                surface["status"] = (
                    f"retired_in_{syn_drop_id}_{retired_date}"
                )
                matched = True

    if matched:
        with open(todo_json_path, "w", encoding="utf-8") as f:
            json.dump(todo, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return matched


# ──────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────

async def _main_async(args) -> int:
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row

        # Always run the audit
        before = await audit(conn)
        print_audit("BEFORE migration", before)

        if args.audit_only:
            print("(--audit-only specified; no further action)")
            return 0

        dry_run = args.dry_run or not args.cold_start

        # Phase 1 — dissolve city-map cities (SYN.4 will impl)
        diss = await dissolve_city_map_cities(conn, dry_run=dry_run)
        print(f"\n── Phase 1 (city dissolution) ──")
        print(f"  status: SYN.4 deliverable — placeholder result:")
        for k, v in diss.items():
            print(f"    {k}: {v}")

        # Phase 2 — wipe territory_claims (SYN.1 will impl invocation)
        wiped = await wipe_territory_claims(conn, dry_run=dry_run)
        print(f"\n── Phase 2 (territory_claims wipe) ──")
        action = "would delete" if dry_run else "deleted"
        print(f"  {action}: {wiped} rows")

        after = await audit(conn)
        print_audit("AFTER migration", after)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contestable Wilderness pivot migration (SYN.0 plan + "
            "SYN.1/SYN.4 invocation)."
        ),
    )
    parser.add_argument(
        "--db", default="sw_mush.db",
        help="Path to SQLite database (default: sw_mush.db)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--audit-only", action="store_true",
        help="Print audit results only; do not plan or execute.",
    )
    mode.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen; do not write.",
    )
    mode.add_argument(
        "--cold-start", action="store_true",
        help="Execute the full migration (SYN.1 production invocation).",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
