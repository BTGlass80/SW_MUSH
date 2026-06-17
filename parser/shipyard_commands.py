# -*- coding: utf-8 -*-
"""
parser/shipyard_commands.py — Kuat ship brokerage (Drop 3a).

The audit's load-bearing high-tier credit sink (F2/F4): turn the inert
``starships.yaml`` catalog into a *live capital sink*. A player standing in a
Kuat Drive Yards brokerage room can buy a hull outright; the price is debited
through the ledger chokepoint (``adjust_credits(..., "ship_purchase")``), and a
real, owned ship is instantiated and delivered to a Kuat landing pad.

Scope (3a): the **civilian / freelancer** catalog only — freighters, a light
fighter, a patrol craft, and the whale-tier diplomatic cruiser. Every hull is
Clone-Wars-era-clean (no Imperial/Rebel/TIE/X-wing) and resolves in the merged
ship registry. **Military procurement** (Republic ARC-170/LAAT/V-19/Eta-2, CIS
droid fighters) needs faction-membership/rank gating and is deferred to 3b.

Design notes:
- Prices are single-sourced from the ship registry (``ShipTemplate.cost``); this
  module only *curates which hulls are on the civilian market*. A hull that does
  not resolve, or has no cost, is dropped with a loud log line (never sold at a
  bogus price).
- Instantiation mirrors the proven starter-ship path in
  ``engine/spacer_quest.py`` (create a bridge room, insert the ship, wire a
  disembark exit), but boarding uses the multi-ship ``board <name>`` command
  rather than a per-ship "board" exit (which would collide when several ships
  share one landing pad).
- Room binding is slug-based (never hardcoded DB ids), per project discipline.

Commands:
    +shipyard                          — list the civilian catalog + your credits
    +shipyard buy <hull> [name]        — purchase a hull (delivered to a Kuat pad)
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

# ── Location gating (slug-based) ────────────────────────────────────────────
# Where the brokerage operates: the KDY merchant-house shipyards and the ring
# commercial zone. Resolved to room ids at command time; only present rooms are
# active, so this degrades gracefully if a world build omits one.
BROKER_ROOM_SLUGS = (
    "kuat_deporin_shipyards",
    "kuat_ileu_shipyards",
    "kuat_ring_commercial",
)

# Where a purchased ship is delivered (its ``docked_at`` room). First present
# slug wins.
DELIVERY_DOCK_SLUGS = (
    "kuat_city_landing_pad",
    "kuat_shuttle_bay",
    "kuat_arrivals",
)

# Soft cap to prevent landing-pad room-spam abuse; generous enough not to bite
# legitimate collectors. A sink wants purchases *unconstrained by design*, but
# each hull spawns a room, so an upper bound is a resource guard, not a balance
# lever.
MAX_OWNED_SHIPS = 8

# ── Curated civilian catalog ────────────────────────────────────────────────
# Ordered cheap → whale. Keys must resolve in the merged ship registry
# (data/starships.yaml ∪ data/worlds/<era>/starships.yaml). All era-clean.
_CIVILIAN_CATALOG = (
    {"key": "z_95",            "tier": "Light fighter",
     "flavor": "A rugged Incom/Subpro headhunter — cheap, fast, and everywhere."},
    {"key": "ghtroc_720",      "tier": "Light freighter",
     "flavor": "The freelancer's workhorse; forgiving and easy to crew."},
    {"key": "yt_1300",         "tier": "Light freighter",
     "flavor": "The legendary CEC hull — roomy hold, endlessly modifiable."},
    {"key": "firespray",       "tier": "Patrol craft",
     "flavor": "A rotating-cockpit patrol/pursuit craft prized by hunters."},
    {"key": "yt_2400",         "tier": "Freighter",
     "flavor": "A bigger CEC saucer with the hardpoints to back up the haul."},
    {"key": "consular_cruiser", "tier": "Diplomatic cruiser",
     "flavor": "A surplus, civilian-fit Consular hull — a capital-class statement."},
)


def _norm(s: str) -> str:
    """Lowercase, keep only alphanumerics — for fuzzy hull matching."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


def build_catalog():
    """Return the live civilian catalog as a list of dicts:
    ``{key, name, cost, tier, flavor}``, with name/cost pulled from the ship
    registry. Hulls that don't resolve or lack a cost are dropped (logged)."""
    try:
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
    except Exception as e:  # pragma: no cover - registry should always load
        log.warning("[shipyard] ship registry unavailable: %s", e)
        return []

    out = []
    for entry in _CIVILIAN_CATALOG:
        key = entry["key"]
        tmpl = reg.get(key)
        if tmpl is None:
            log.warning("[shipyard] catalog hull %r missing from registry — dropped", key)
            continue
        cost = getattr(tmpl, "cost", 0) or 0
        if cost <= 0:
            log.warning("[shipyard] catalog hull %r has no cost — dropped", key)
            continue
        out.append({
            "key": key,
            "name": getattr(tmpl, "name", key),
            "cost": int(cost),
            "tier": entry["tier"],
            "flavor": entry["flavor"],
        })
    return out


def _match_hull(token: str, catalog):
    """Resolve a player-typed hull token to a catalog entry, or None.

    Matches against the registry key and the display name (normalized), so
    'yt1300', 'yt-1300', 'YT-1300 Transport', 'ghtroc', 'consular' all work.
    """
    nt = _norm(token)
    if not nt:
        return None
    # Exact key match first.
    for c in catalog:
        if _norm(c["key"]) == nt:
            return c
    # Then name / substring (key contains token or name contains token).
    for c in catalog:
        if nt in _norm(c["key"]) or nt in _norm(c["name"]):
            return c
    return None


async def _resolve_first_room(db, slugs):
    """Return the id of the first present room among ``slugs``, or None."""
    for slug in slugs:
        try:
            room = await db.get_room_by_slug(slug)
        except Exception:
            room = None
        if room and room.get("id"):
            return room["id"]
    return None


async def purchase_ship(db, char, room_id, hull_token, ship_name=None):
    """Core brokerage purchase. Returns a result dict:
        {"ok": bool, "message": str, "ship_id"?: int, "dock_room_id"?: int,
         "hull"?: dict, "price"?: int}

    Side effects on success: credits debited via the ledger chokepoint, a bridge
    room created, a ship row inserted (owner = char), and a disembark exit wired.
    Boarding is via the ``board <name>`` command.
    """
    catalog = build_catalog()
    if not catalog:
        return {"ok": False, "message": "The brokerage has no hulls listed right now."}

    # Location gate.
    broker_ids = set()
    for slug in BROKER_ROOM_SLUGS:
        try:
            r = await db.get_room_by_slug(slug)
        except Exception:
            r = None
        if r and r.get("id"):
            broker_ids.add(r["id"])
    if room_id not in broker_ids:
        return {"ok": False,
                "message": "You need to be at a Kuat Drive Yards brokerage to buy a ship."}

    hull = _match_hull(hull_token, catalog)
    if hull is None:
        names = ", ".join(c["key"] for c in catalog)
        return {"ok": False,
                "message": f"No hull matches '{hull_token}'. Listed: {names}."}

    price = hull["cost"]

    # Affordability.
    try:
        bal = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        bal = 0
    if bal < price:
        return {"ok": False,
                "message": (f"The {hull['name']} costs {price:,} cr — "
                            f"you have {bal:,} cr ({price - bal:,} short).")}

    # Ownership cap (room-spam guard).
    try:
        owned = await db.get_ships_owned_by(char["id"])
    except Exception:
        owned = []
    if owned is not None and len(owned) >= MAX_OWNED_SHIPS:
        return {"ok": False,
                "message": (f"You already own {len(owned)} ships "
                            f"(limit {MAX_OWNED_SHIPS}). Sell or scrap one first.")}

    # Delivery dock.
    dock_id = await _resolve_first_room(db, DELIVERY_DOCK_SLUGS)
    if not dock_id:
        return {"ok": False,
                "message": "No Kuat landing pad is available for delivery — contact an admin."}

    # Name.
    name = (ship_name or "").strip()
    if not name:
        name = hull["name"]
    if len(name) > 48:
        name = name[:48]

    # ── Debit FIRST through the ledger chokepoint (the sink). ───────────────
    # If anything downstream fails we refund, so a failed delivery never eats
    # the player's credits.
    try:
        char["credits"] = await db.adjust_credits(char["id"], -price, "ship_purchase")
    except Exception as e:
        log.warning("[shipyard] debit failed for char %s: %s", char.get("id"), e)
        return {"ok": False, "message": "Payment could not be processed. Nothing was charged."}

    async def _refund(reason):
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], price, "ship_purchase_refund")
        except Exception:
            log.warning("[shipyard] REFUND FAILED for char %s after %s",
                        char.get("id"), reason, exc_info=True)
        log.warning("[shipyard] purchase aborted (%s); refunded %d to char %s",
                    reason, price, char.get("id"))

    # Build the bridge/interior room.
    try:
        bridge_id = await db.create_room(
            f"{name} - Bridge",
            f"The interior of {name}, a {hull['name']}.",
            (f"You stand inside {name}, a {hull['name']}. Status panels glow a "
             f"steady green — freshly serviced, hull pristine. Through the "
             f"viewport, the Kuat Drive Yards' orbital ring stretches away in a "
             f"lattice of scaffolding and half-finished capital hulls."),
        )
    except Exception as e:
        await _refund(f"bridge-room create failed: {e}")
        return {"ok": False, "message": "Ship interior could not be built. You were refunded."}

    # Insert the ship (owned by the buyer, docked at the Kuat pad).
    try:
        ship_id = await db.create_ship(hull["key"], name, char["id"], bridge_id, dock_id)
    except Exception as e:
        await _refund(f"ship insert failed: {e}")
        # Best-effort cleanup of the orphan bridge room.
        try:
            await db.execute("DELETE FROM rooms WHERE id = ?", (bridge_id,))
            await db.commit()
        except Exception:
            log.debug("[shipyard] orphan bridge cleanup skipped", exc_info=True)
        return {"ok": False, "message": "Ship registration failed. You were refunded."}

    # Mark fully owned (parity with the starter ship's post-transfer state).
    try:
        import json as _json
        ship = await db.get_ship(ship_id)
        systems = _json.loads((ship or {}).get("systems") or "{}")
        systems["owned"] = True
        await db.update_ship(ship_id, systems=_json.dumps(systems))
    except Exception:
        log.debug("[shipyard] owned-flag set skipped for ship %s", ship_id, exc_info=True)

    # Wire the disembark exit (bridge → pad). Boarding uses `board <name>`.
    try:
        await db.create_exit(bridge_id, dock_id, "disembark", "Disembark")
    except Exception:
        log.debug("[shipyard] disembark exit wiring skipped", exc_info=True)

    dock_name = ""
    try:
        dock_room = await db.get_room(dock_id)
        dock_name = (dock_room or {}).get("name", "") if dock_room else ""
    except Exception:
        dock_name = ""

    msg = (f"Purchase complete — {name} ({hull['name']}) is yours for "
           f"{price:,} cr. Balance: {char.get('credits', 0):,} cr.\n"
           f"  She's been delivered to "
           f"{dock_name or 'the Kuat landing pad'}; go there and "
           f"'board {name}' to step aboard. Rename her any time with '+ship/rename'.")
    return {"ok": True, "message": msg, "ship_id": ship_id,
            "dock_room_id": dock_id, "hull": hull, "price": price}


class ShipyardCommand(BaseCommand):
    key = "+shipyard"
    aliases = ["shipyard", "+broker", "+buyship"]
    access_level = AccessLevel.PLAYER
    help_text = "Buy a ship at the Kuat Drive Yards brokerage."
    usage = "+shipyard  |  +shipyard buy <hull> [name]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game to use the brokerage.")
            return

        args = (ctx.args or "").strip()
        room_id = char.get("room_id")

        # `+shipyard buy <hull> [name]`
        if args.lower().startswith("buy"):
            rest = args[3:].strip()
            if not rest:
                await ctx.session.send_line(
                    "  Usage: +shipyard buy <hull> [name]")
                return
            parts = rest.split(None, 1)
            hull_token = parts[0]
            ship_name = parts[1] if len(parts) > 1 else None
            result = await purchase_ship(ctx.db, char, room_id, hull_token, ship_name)
            if result["ok"]:
                await ctx.session.send_line(ansi.success("  " + result["message"]))
            else:
                await ctx.session.send_line(ansi.error("  " + result["message"]))
            return

        # No args → show the catalog.
        await self._show_catalog(ctx, char, room_id)

    async def _show_catalog(self, ctx, char, room_id):
        catalog = build_catalog()

        # Are we at a broker?
        at_broker = False
        for slug in BROKER_ROOM_SLUGS:
            try:
                r = await ctx.db.get_room_by_slug(slug)
            except Exception:
                r = None
            if r and r.get("id") == room_id:
                at_broker = True
                break

        bal = 0
        try:
            bal = int(char.get("credits") or 0)
        except (TypeError, ValueError):
            bal = 0

        lines = [ansi.bold("  Kuat Drive Yards — Ship Brokerage (civilian listings)")]
        if not catalog:
            lines.append("  No hulls are listed right now.")
            await ctx.session.send_line("\n".join(lines))
            return
        for c in catalog:
            afford = ansi.GREEN if bal >= c["cost"] else ansi.RED
            lines.append(
                f"  {ansi.BRIGHT_CYAN}{c['key']:<16}{ansi.RESET} "
                f"{c['name']:<26} {c['tier']:<18} "
                f"{afford}{c['cost']:>10,} cr{ansi.RESET}")
            lines.append(f"      {c['flavor']}")
        lines.append("")
        lines.append(f"  Your credits: {bal:,} cr")
        if at_broker:
            lines.append("  Buy with:  +shipyard buy <hull> [name]")
        else:
            lines.append(ansi.yellow(
                "  (Travel to a Kuat Drive Yards brokerage to purchase.)"))
        await ctx.session.send_line("\n".join(lines))


def register_shipyard_commands(registry):
    """Register the Kuat ship brokerage command (Drop 3a)."""
    registry.register(ShipyardCommand())
    log.info("[shipyard] ship brokerage command registered")
