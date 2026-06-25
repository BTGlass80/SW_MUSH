# -*- coding: utf-8 -*-
"""Throwaway ground-truth audit for the GRIND-realignment lane (2026-06-24).

Boots the real clone_wars world into a temp DB and resolves the EFFECTIVE
security tier of every npcs_drop_mob_grind_*.yaml placement via the live
engine resolver. A SECURED tier => combat is hard-blocked
(engine.security.is_combat_allowed -> False) => the mob is literally
unkillable => dead content.

Output: per-file + aggregate classification + a JSON sidecar the strip step
consumes. NOT a committed test — delete after the strip lands.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Room/zone name fragments that mark a CONTESTED room as a "civilized civic
# hub" (immersion-breaking to grind in) vs a contested-DANGEROUS frontier
# room (legit grind venue). Used only to TAG contested rooms for the Opus
# adjudication step — never to auto-delete.
CIVIC_HINTS = (
    "police", "security office", "weapon shop", "clinic", "cantina",
    "medical", "hospital", "bank", "market", "bazaar", "shop", "store",
    "embassy", "senate", "government", "administration", "admin",
    "spaceport", "docking", "hotel", "hostel", "diner", "restaurant",
    "academy", "temple", "hall", "office", "plaza", "promenade",
    "concourse", "terminal", "court", "council", "chamber",
)


async def main() -> None:
    from tests.harness import _LiveHarness
    from engine.security import SecurityLevel, get_effective_security

    h = await _LiveHarness.boot(era="clone_wars")
    db = h.db

    cache: dict[str, dict] = {}

    async def resolve(room_name: str) -> dict:
        if room_name in cache:
            return cache[room_name]
        rows = await db.fetchall(
            "SELECT id FROM rooms WHERE name = ?", (room_name,)
        )
        if not rows:
            res = {
                "found": False, "structural": None, "effective": None,
                "zone": None,
            }
        else:
            rid = rows[0]["id"]
            raw = await db.get_room_property(rid, "security")
            structural = (raw or "contested").lower()
            try:
                eff = (await get_effective_security(rid, db, None)).value
            except Exception as e:  # noqa: BLE001
                eff = f"ERR:{e}"
            room = await db.get_room(rid)
            zone_name = None
            zid = (room or {}).get("zone_id")
            if zid:
                try:
                    zrows = await db.fetchall(
                        "SELECT slug FROM zones WHERE id = ?", (zid,)
                    )
                    if zrows:
                        zone_name = zrows[0]["slug"]
                except Exception:
                    zone_name = None  # best-effort; leave zone unresolved on read error
            res = {
                "found": True, "room_id": rid, "structural": structural,
                "effective": eff, "zone": zone_name,
            }
        cache[room_name] = res
        return res

    try:
        files = sorted(
            glob.glob(str(ROOT / "data/worlds/clone_wars/"
                          "npcs_drop_mob_grind_*.yaml"))
        )
        report: dict[str, dict] = {}
        grand = Counter()
        for f in files:
            data = yaml.safe_load(Path(f).read_text(encoding="utf-8")) or {}
            npcs = data.get("npcs", []) or []
            entries = []
            tier_counts = Counter()
            for n in npcs:
                rn = (n.get("room") or "").strip()
                info = await resolve(rn)
                if not info["found"]:
                    tier = "NOT_FOUND"
                else:
                    tier = info["effective"].upper()
                tier_counts[tier] += 1
                grand[tier] += 1
                civic = (
                    info["found"]
                    and info["effective"] == "contested"
                    and any(k in rn.lower() for k in CIVIC_HINTS)
                )
                entries.append({
                    "npc": n.get("name"),
                    "room": rn,
                    "zone": info.get("zone"),
                    "structural": info.get("structural"),
                    "effective": info.get("effective"),
                    "found": info["found"],
                    "tier": tier,
                    "civic_contested": civic,
                })
            # File-level verdict
            n_total = len(entries)
            n_secured = tier_counts.get("SECURED", 0)
            n_notfound = tier_counts.get("NOT_FOUND", 0)
            n_civic = sum(1 for e in entries if e["civic_contested"])
            n_keep = sum(
                1 for e in entries
                if e["tier"] in ("CONTESTED", "LAWLESS")
                and not e["civic_contested"]
            )
            dead = n_secured + n_notfound  # tone-independent dead content
            if n_total == 0:
                verdict = "EMPTY"
            elif n_keep == 0 and (dead + n_civic) == n_total:
                verdict = "STRIP_WHOLE"   # nothing defensible
            elif dead + n_civic == 0:
                verdict = "KEEP_WHOLE"
            else:
                verdict = "SURGICAL"
            report[os.path.basename(f)] = {
                "verdict": verdict,
                "total": n_total,
                "secured_dead": n_secured,
                "not_found": n_notfound,
                "civic_contested": n_civic,
                "keep": n_keep,
                "tiers": dict(tier_counts),
                "entries": entries,
            }

        out = ROOT / "tools" / "_audit_mob_grind_security.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        # ── Console summary ──
        print("\n================ MOB-GRIND SECURITY AUDIT ================")
        print(f"files: {len(files)}   total NPCs: {sum(grand.values())}")
        print(f"GRAND TIER TOTALS: {dict(grand)}")
        print("\nPER-FILE VERDICTS:")
        for name, r in sorted(
            report.items(), key=lambda kv: (kv[1]["verdict"], kv[0])
        ):
            print(
                f"  [{r['verdict']:11}] {name:58} "
                f"tot={r['total']:2} secured={r['secured_dead']:2} "
                f"nf={r['not_found']:2} civic={r['civic_contested']:2} "
                f"keep={r['keep']:2}  {r['tiers']}"
            )
        print(f"\nJSON written: {out}")
    finally:
        await h.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
