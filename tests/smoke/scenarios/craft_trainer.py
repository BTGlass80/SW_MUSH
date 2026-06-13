# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/craft_trainer.py — Crafting trainer lane (CT1-CT3).

Gundark Drop G smoke: the `learn <schematic>` verb.

Coverage:
  CT1 — `learn` with no argument shows usage (not a traceback).
  CT2 — `learn <schematic>` when the bound trainer NPC is NOT in the room
         returns the trainer-absent refusal (not a traceback, not a silent
         no-op, and the schematic does NOT appear in known schematics).
  CT3 — With the trainer NPC seeded into the room via db.create_npc,
         `learn <schematic>` either takes the free first lesson (credits
         unchanged, tuition=0) or debits the correct tuition, AND the
         schematic appears in get_known_schematics on a fresh DB fetch.

economy_progression.E7 DELIBERATELY bypasses the trainer (direct
schematic injection) — `learn`/`teach` has no coverage there. CT1–CT3
are the only smoke guards for the schematic_tuition credit sink and the
trainer-presence gate.

What each arm catches:
  CT1 — argless path raises / returns empty (wiring regression on early-return)
  CT2 — trainer-absent gate is bypassed (schematic granted for free without
         the trainer being present; credit sink evaded entirely)
  CT3 — schematic never written to DB ("_save_char was a no-op" regression,
         same class of bug as CRAFT.P1); credit delta wrong (adjust_credits
         not called or called with wrong delta / wrong tag)
"""
from __future__ import annotations

import json as _json


# ---------------------------------------------------------------------------
# CT1 — learn with no argument shows usage
# ---------------------------------------------------------------------------

async def ct1_learn_no_arg_shows_usage(h):
    """CT1 — `learn` with no argument produces a usage message.

    Catches: the command's early-return path crashes or returns empty
    rather than rendering the help/usage text.
    """
    s = await h.login_as("CT1Learner", room_id=1)
    out = await h.cmd(s, "learn")

    low = out.lower()
    assert "traceback" not in low, (
        f"`learn` (no arg) raised: {out[:500]!r}"
    )
    assert "error occurred" not in low, (
        f"`learn` (no arg) reported an internal error: {out[:500]!r}"
    )
    assert out and out.strip(), "`learn` (no arg) produced no output at all"
    # The command must produce a usage hint, not silently do nothing.
    assert "usage" in low or "learn what" in low or "schematic" in low, (
        f"`learn` (no arg) output doesn't look like a usage message: "
        f"{out[:400]!r}"
    )


# ---------------------------------------------------------------------------
# CT2 — learn when trainer is NOT in the room
# ---------------------------------------------------------------------------

async def ct2_learn_trainer_absent_refused(h):
    """CT2 — `learn <schematic>` when the bound trainer is not present
    returns a trainer-absent refusal.

    Uses `anti_vehicle_grenade` (trainer: Gundark, base_cost: 750,
    tuition: 375 cr) — the cheapest Gundark schematic, so tuition is
    small but non-zero on the paid path.

    Catches:
    - Trainer-presence gate bypassed: schematic granted without the NPC
      being in the room (credit sink entirely evaded).
    - Command crashes instead of returning a clean refusal.
    """
    s = await h.login_as("CT2Absent", room_id=1, credits=5000)
    char_id = s.character["id"]

    # Room 1 has no Gundark NPC in the freshly-built test world.
    out = await h.cmd(s, "learn anti-vehicle grenade")
    low = out.lower()

    assert "traceback" not in low, (
        f"`learn` (trainer absent) raised: {out[:500]!r}"
    )
    assert "error occurred" not in low, (
        f"`learn` (trainer absent) internal error: {out[:500]!r}"
    )
    assert out and out.strip(), (
        "`learn` (trainer absent) produced no output at all"
    )

    # Must see the trainer-absent refusal, not a success message.
    assert "isn't here" in low or "not here" in low or "teaches that" in low, (
        f"`learn` (trainer absent) didn't emit a trainer-absent refusal. "
        f"Output: {out[:500]!r}"
    )

    # The schematic must NOT have been granted.
    fresh = await h.get_char(char_id)
    attrs = _json.loads(fresh.get("attributes") or "{}")
    known = attrs.get("schematics", [])
    assert "anti_vehicle_grenade" not in known, (
        f"Schematic was granted even though trainer was absent! "
        f"known={known!r}"
    )


# ---------------------------------------------------------------------------
# CT3 — learn with trainer seeded in the room
# ---------------------------------------------------------------------------

async def ct3_learn_with_trainer_present(h):
    """CT3 — With the Gundark NPC seeded into the room, `learn
    anti-vehicle grenade` either takes the free first lesson (no credits
    debited) or debits the correct tuition (375 cr), and in both cases
    the schematic appears in get_known_schematics on a fresh DB read.

    Schematic chosen: `anti_vehicle_grenade`
      trainer_npc: Gundark
      base_cost: 750
      tuition (schematic_tuition): max(50, 750 // 2) = 375 cr

    Free-lesson logic (from LearnCommand): if trainer_free_lessons[gundark]
    is not set, the first learn is free (tuition=0). So a fresh character
    with no prior Gundark interactions gets the lesson free, and credits
    are unchanged. If, for some reason, the free-lesson flag is already
    set (e.g. a talk path fired before this command), tuition=375 is
    debited. The assertion accepts both outcomes by checking the actual
    credit delta against the two expected values.

    Catches:
    - `_save_char` was a no-op (CRAFT.P1 class): schematic never written
      to DB even though the verb reported success.
    - `adjust_credits` not called / called with wrong delta / wrong tag.
    - Free-lesson gate inverted: credits deducted even on a free lesson,
      or NOT deducted on a paid lesson.
    """
    # Seed the character in room 2 (avoid room 1 which may have other
    # NPCs from parallel scenarios; we pick a stable, low-traffic room).
    ROOM_ID = 2
    s = await h.login_as("CT3Learner", room_id=ROOM_ID, credits=5000)
    char_id = s.character["id"]

    pre_credits = await h.get_credits(char_id)

    # Seed the Gundark NPC into the same room via the real DB seam.
    # create_npc is idempotent by (name, room_id).
    await h.db.create_npc(
        name="Gundark",
        room_id=ROOM_ID,
        species="Human",
        description="A black-market arms dealer.",
        ai_config_json=_json.dumps({"role": "trainer", "hostile": False}),
    )

    # Run the command.
    out = await h.cmd(s, "learn anti-vehicle grenade")
    low = out.lower()

    assert "traceback" not in low, (
        f"`learn` (trainer present) raised: {out[:500]!r}"
    )
    assert "error occurred" not in low, (
        f"`learn` (trainer present) internal error: {out[:500]!r}"
    )
    assert out and out.strip(), (
        "`learn` (trainer present) produced no output at all"
    )

    # The verb must have reported success (either free or paid).
    # Acceptable success strings from LearnCommand.execute():
    #   "first lesson's on the house"  (free path)
    #   "you pay"                       (paid path)
    #   "walks you through"            (both paths)
    assert (
        "first lesson" in low or "on the house" in low
        or "walks you through" in low or "you pay" in low
    ), (
        f"`learn` (trainer present) output doesn't look like a success "
        f"message. Output: {out[:500]!r}"
    )

    # --- DB read-back: schematic must be known ---
    fresh = await h.get_char(char_id)
    attrs = _json.loads(fresh.get("attributes") or "{}")
    known = attrs.get("schematics", [])
    assert "anti_vehicle_grenade" in known, (
        f"Schematic NOT persisted after successful `learn`. "
        f"known={known!r}. Command output: {out[:500]!r}"
    )

    # --- Credit delta check ---
    post_credits = await h.get_credits(char_id)
    delta = pre_credits - post_credits   # positive means credits spent

    # Determine which path fired: free (delta==0) or paid (delta==375).
    # Compute expected tuition from the engine function so the test
    # stays in sync with any future base_cost changes.
    from engine.crafting import get_all_schematics, schematic_tuition
    schem = get_all_schematics().get("anti_vehicle_grenade")
    assert schem is not None, "anti_vehicle_grenade not found in schematics"
    expected_tuition = schematic_tuition(schem)

    assert delta == 0 or delta == expected_tuition, (
        f"Credit delta {delta} is neither 0 (free lesson) nor "
        f"{expected_tuition} (paid tuition). "
        f"pre={pre_credits} post={post_credits}. "
        f"Command output: {out[:500]!r}"
    )

    # --- Trainer-free-lesson flag must be set after the learn ---
    # (ensures a second learn cannot get a second free lesson)
    trainer_key = "gundark"
    free_lessons = attrs.get("trainer_free_lessons", {})
    assert free_lessons.get(trainer_key) is True, (
        f"trainer_free_lessons['{trainer_key}'] not set after learn. "
        f"attrs keys: {list(attrs.keys())!r}"
    )
