# -*- coding: utf-8 -*-
"""engine/contextual_hints.py — NPE-C2 first-hit contextual help nudges.

The first time a new player uses a major subsystem (combat, shopping,
crafting, inter-world travel), surface a one-line nudge pointing them at
the relevant in-game field guide. Fires at most ONCE per system per
character.

Design:
  * Producer seam — parser/commands.py CommandParser._execute, alongside
    the CW-tutorial command hook, matching on the *resolved* cmd.key
    (alias-robust: kill/att/shoot all normalize to 'attack').
  * Per-character memory — a 'seen_hints' map (hint_key -> True) lives in
    the SAME character `attributes` JSON blob as 'tutorial_chain', read /
    written through chain_events._load_attrs / _persist_attrs (the
    canonical attribute-persistence path; never a save_character
    force_sensitive kwarg). seen_hints is a NEW top-level key, a sibling
    of tutorial_chain — never nested under it, so chain state is never
    clobbered.
  * Delivery — a sys-event pose (engine.pose_events.make_system_event)
    over session.send_json('pose_event', ...). On the web client this is
    a banner row; on Telnet send_json falls back to a plain styled line
    (server/session.py send_json sys-event branch) — graceful, web-first.
  * Best-effort — a hint failure must NEVER break or delay the command;
    every path is wrapped and the helper self-guards.

Era-clean: the nudge copy is production-visible (no Imperial/Rebel/TIE).
The guide slugs are the live /api/portal/guide/{slug} ids
(server/web_portal: Guide_NN_Title.md -> title.lower().replace('_','-')).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# New top-level attributes key — sibling of 'tutorial_chain'.
SEEN_HINTS_KEY = "seen_hints"

# Resolved cmd.key -> (hint_key, guide_slug, nudge_text).
#
# Several command keys can share a hint_key so the nudge fires once per
# *subsystem*, not once per command (e.g. shop/buy/sell -> "shop"). The
# nudge tells the player to type `help` — which on the web client opens
# the in-game field-guide browser (the bare-`help` sendCmd intercept) and
# on Telnet runs the server help system, so the copy is universal.
HINTS: dict[str, tuple[str, str, str]] = {
    # ── Combat ──────────────────────────────────────────────────────
    "attack": (
        "combat", "ground-combat",
        "New to a fight? Type 'help' to open the field guides and read "
        "Ground Combat -- how attacks, defense, and stun damage work.",
    ),
    # ── Player shops / economy ──────────────────────────────────────
    "shop": (
        "shop", "player-shops",
        "Shopping for the first time? Type 'help' and read Player Shops "
        "-- browsing, buying, selling, and haggling with vendor droids.",
    ),
    "buy": (
        "shop", "player-shops",
        "Buying something? Type 'help' and read Player Shops -- how "
        "purchases, prices, and haggling work.",
    ),
    "sell": (
        "shop", "player-shops",
        "Selling something? Type 'help' and read Player Shops -- how "
        "selling and vendor pricing work.",
    ),
    # ── Crafting ────────────────────────────────────────────────────
    "craft": (
        "craft", "crafting",
        "Starting to craft? Type 'help' and read Crafting -- gathering "
        "resources, using schematics, and build quality.",
    ),
    # ── Inter-world travel (space landing) ──────────────────────────
    "land": (
        "travel", "space-systems",
        "Traveling between worlds? Type 'help' and read Space & Systems "
        "-- landing, takeoff, and finding your way around the galaxy.",
    ),
}


def _seen_map(attrs: dict) -> dict:
    """The per-character seen_hints sub-dict (tolerant of legacy shapes)."""
    seen = attrs.get(SEEN_HINTS_KEY)
    return seen if isinstance(seen, dict) else {}


async def maybe_emit_first_hit_hint(session, db, char, cmd_key: str) -> bool:
    """Emit a one-line contextual guide nudge the FIRST time `char` uses a
    tracked subsystem (keyed by resolved cmd_key). Returns True iff a hint
    was emitted this call. Idempotent per (character, subsystem). Fully
    best-effort: any failure is swallowed and returns False.
    """
    try:
        entry = HINTS.get(cmd_key)
        if not entry:
            return False
        hint_key, _slug, text = entry

        # Lazy imports keep this module import-cheap and avoid any cycle
        # through parser/commands at module load.
        from engine.chain_events import _load_attrs, _persist_attrs
        from engine.pose_events import make_system_event

        attrs = _load_attrs(char)
        seen = _seen_map(attrs)
        if seen.get(hint_key):
            return False  # already shown for this subsystem

        # Emit FIRST, then mark seen + persist. If delivery throws (e.g. a
        # disconnecting client), the flag stays UNset and the nudge
        # re-fires next time — re-showing is a better failure mode than
        # marking the player "seen" for a hint they never received. The
        # persist round-trips the whole attrs blob (additive key, so
        # tutorial_chain and everything else stays intact).
        await session.send_json("pose_event", make_system_event(text))
        seen[hint_key] = True
        attrs[SEEN_HINTS_KEY] = seen
        await _persist_attrs(db, char, attrs)
        return True
    except Exception:
        log.debug("contextual hint emit failed (cmd_key=%s)", cmd_key,
                  exc_info=True)
        return False
