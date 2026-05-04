# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/pvp.py — PvP positive-path scenarios (PV1–PV3).
Drop 5.

CX2 (Drop 2) covered the refusal path — A attacks B without consent
in CONTESTED, gets "Imperial law prohibits". The success path —
challenge → accept → mutual attack starts combat — was deferred
until the dispatch ambiguity could be sorted out.

This drop landed the dispatch fix (parser/mission_commands.py
::AcceptMissionCommand smart-routes to AcceptCommand when the arg
names a PC with a pending challenge) so PvP consent is finally
reachable from `accept`. PV1/PV2/PV3 verify the round-trip.

  PV1 — `challenge <PC>` records a pending consent
  PV2 — `accept <challenger>` activates consent (regression guard
        for the dispatch fix — pre-fix this was routing to
        AcceptMissionCommand and saying "No mission 'alice' on
        the board")
  PV3 — Post-consent, attacker can `attack <target>` and combat
        starts with both PCs as combatants
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# PV1 — challenge records pending consent
# ──────────────────────────────────────────────────────────────────────────

async def pv1_challenge_records_pending_consent(h):
    """PV1 — `challenge <PC>` in a CONTESTED room records the
    challenge in the pvp_consent dict.

    Default CW spawn (room 1) is CONTESTED, so no security
    override needed.
    """
    a = await h.login_as("PV1Alice", room_id=1)
    b = await h.login_as("PV1Bob", room_id=1)

    out = await h.cmd(a, "challenge PV1Bob")
    assert "traceback" not in out.lower(), (
        f"`challenge` raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    assert "challenge" in out_lc, (
        f"challenge response missing 'challenge' confirmation. "
        f"Output: {out[:300]!r}"
    )
    assert "accept" in out_lc, (
        f"challenge response should tell target how to accept. "
        f"Output: {out[:300]!r}"
    )

    # Module-global state should now have the pending entry
    from parser.combat_commands import _pvp_consent
    a_id = a.character["id"]
    b_id = b.character["id"]
    assert (a_id, b_id) in _pvp_consent, (
        f"_pvp_consent missing ({a_id}, {b_id}) after challenge. "
        f"Current: {dict(_pvp_consent)!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PV2 — accept activates consent (regression guard for dispatch fix)
# ──────────────────────────────────────────────────────────────────────────

async def pv2_accept_activates_consent(h):
    """PV2 — After `challenge <target>`, the target running
    `accept <challenger>` activates mutual combat consent.

    REGRESSION GUARD for the Drop-5 dispatch fix in
    parser/mission_commands.py::AcceptMissionCommand. Pre-fix
    `accept Alice` (a PC name) routed to mission accept and
    surfaced "No mission 'alice' on the board" while the combat
    consent stayed pending. The combat AcceptCommand was
    unreachable.
    """
    a = await h.login_as("PV2Alice", room_id=1)
    b = await h.login_as("PV2Bob", room_id=1)

    await h.cmd(a, "challenge PV2Bob")
    out = await h.cmd(b, "accept PV2Alice")
    assert "traceback" not in out.lower(), (
        f"`accept` raised: {out[:500]!r}"
    )
    # Specific catch for the pre-fix routing bug.
    assert "no mission" not in out.lower(), (
        f"`accept <PC>` routed to mission accept instead of combat. "
        f"Pre-Drop-5 dispatch bug regressed. Output: {out[:300]!r}"
    )
    out_lc = out.lower()
    assert (
        "accept" in out_lc and
        ("consent" in out_lc or "challenge" in out_lc)
    ), (
        f"accept response doesn't surface combat consent activation. "
        f"Output: {out[:300]!r}"
    )

    # Verify the mutual-active dict reflects the consent
    from parser.combat_commands import _pvp_active, _pvp_consent
    a_id = a.character["id"]
    b_id = b.character["id"]
    assert (a_id, b_id) in _pvp_active, (
        f"_pvp_active missing ({a_id}, {b_id}) after accept. "
        f"Current: {dict(_pvp_active)!r}"
    )
    # Pending entry should be cleared
    assert (a_id, b_id) not in _pvp_consent, (
        f"_pvp_consent still has ({a_id}, {b_id}) — should have "
        f"been popped on accept. Current: {dict(_pvp_consent)!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PV3 — Post-consent attack starts combat with both PCs
# ──────────────────────────────────────────────────────────────────────────

async def pv3_post_consent_attack_starts_combat(h):
    """PV3 — After mutual consent, A's attack on B starts combat
    with both PCs registered as combatants.

    Closes the asymmetry where Drop 2's CX2 covered the refusal
    path (no consent → "Imperial law prohibits") but the success
    path was untested.
    """
    a = await h.login_as("PV3Alice", room_id=1)
    b = await h.login_as("PV3Bob", room_id=1)

    # Challenge + accept
    await h.cmd(a, "challenge PV3Bob")
    await h.cmd(b, "accept PV3Alice")

    # Attack — should start combat (not refuse)
    out = await h.cmd(a, "attack PV3Bob")
    assert "traceback" not in out.lower(), (
        f"`attack` raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Refusal indicators that would mean the consent flow didn't
    # take effect:
    assert "imperial law" not in out_lc, (
        f"Attack still refused with 'Imperial law' after consent "
        f"was activated. Output: {out[:400]!r}"
    )
    # Combat-init indicators
    assert (
        "round" in out_lc or "combat" in out_lc or
        "declare" in out_lc or "turn order" in out_lc
    ), (
        f"Post-consent attack didn't surface combat init. "
        f"Output: {out[:400]!r}"
    )

    # Verify combat instance via the engine helper
    from parser.combat_commands import _ensure_in_combat
    char_a = await h.get_char(a.character["id"])
    combat, _combatant = _ensure_in_combat(
        char_a, char_a["room_id"]
    )
    assert combat is not None, (
        f"No combat instance registered for room {char_a['room_id']} "
        f"after PvP attack."
    )
    assert len(combat.combatants) >= 2, (
        f"Combat should have ≥2 combatants (Alice + Bob); got "
        f"{len(combat.combatants)}"
    )
    combatant_names = sorted(c.name for c in combat.combatants.values())
    assert "PV3Alice" in combatant_names, (
        f"Alice missing from combat. Combatants: {combatant_names!r}"
    )
    assert "PV3Bob" in combatant_names, (
        f"Bob missing from combat. Combatants: {combatant_names!r}"
    )
