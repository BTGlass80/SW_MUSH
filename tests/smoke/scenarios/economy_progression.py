# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/economy_progression.py — Economy & progression (E1-E6).

Per design §6.7.

Coverage:
  E1: +shop (or shop list) renders without crashing
  E2: market list (commodities)
  E3: +cpstatus displays CP balance
  E4: +kudos awards CP
  E5: +scenebonus path
  E6: survey runs (already covered indirectly by test_economy_validation;
      added here for end-to-end smoke pairing)

E7 (full crafting roll loop) and E8 (experiment success/fail paths)
were deferred at first (rich state, resource-node/cooldown harness
gaps) and are now LIVE (CRAFT.P0, 2026-06-10): direct DB state
seeding (schematic grant + component stacks + canonical equipment
write) sidesteps both gaps — no cooldown ticking, no node seeding.
"""
from __future__ import annotations

import asyncio


async def e1_shop_lists(h):
    """E1 — `+shop list` (or `shop`) shows shop-related output.

    The shop command's exact behavior depends on the player's
    location: in a shop room, lists wares; outside, lists nearby
    shops or shows an error. We assert non-error output.
    """
    s = await h.login_as("E1Shopper", room_id=1)
    # Try the most common forms — first one that produces output wins.
    for cmd in ("+shop list", "+shop", "shop"):
        out = await h.cmd(s, cmd)
        if out and out.strip():
            assert "traceback" not in out.lower(), (
                f"`{cmd}` raised: {out[:500]!r}"
            )
            return
    assert False, "No form of shop command produced output"


async def e2_market_lists(h):
    """E2 — `market` (or `market list`) shows commodity data.

    The market command lists available commodities at the current
    location's market or a default. Lightweight: just exercises the
    read path.
    """
    s = await h.login_as("E2Trader", room_id=1)
    out = await h.cmd(s, "market")
    assert out and out.strip(), "market produced no output"
    assert "traceback" not in out.lower(), (
        f"market raised: {out[:500]!r}"
    )


async def e3_cpstatus(h):
    """E3 — `+cpstatus` shows the character's CP balance.

    Validates the CP status display pipeline. Test characters have
    character_points=5 from the harness defaults.
    """
    s = await h.login_as("E3CPSee", room_id=1)
    out = await h.cmd(s, "+cpstatus")
    assert out and out.strip(), "+cpstatus produced no output"
    assert "traceback" not in out.lower(), (
        f"+cpstatus raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The display should mention CP or character points.
    assert "cp" in out_lc or "character point" in out_lc, (
        f"+cpstatus output doesn't reference CP: {out[:400]!r}"
    )


async def e4_kudos_awards_cp(h):
    """E4 — `+kudos <player>` awards CP to another PC.

    Two PCs in the same room — Alice gives Bob a kudos. We don't
    assert exact CP delta because the kudos amount may vary by
    config; we assert the command runs and produces some output.
    """
    s_alice = await h.login_as("E4Giver", room_id=1)
    s_bob = await h.login_as("E4Receiver", room_id=1)
    out = await h.cmd(s_alice, "+kudos E4Receiver thank you for the great roleplay")
    assert "traceback" not in out.lower(), (
        f"+kudos raised: {out[:500]!r}"
    )
    # Some output should be present (success or rate-limit message).
    assert out and out.strip(), "+kudos produced no output"


async def e5_scenebonus_runs(h):
    """E5 — `+scenebonus` (admin/director command) runs without crash.

    For non-admin characters this typically refuses with a permissions
    message. We give an admin character so the path can run, but only
    assert that no traceback occurs — actual award semantics depend
    on scene-tracker state.
    """
    s = await h.login_as("E5Admin", room_id=1, is_admin=True)
    out = await h.cmd(s, "+scenebonus")
    assert "traceback" not in out.lower(), (
        f"+scenebonus raised: {out[:500]!r}"
    )
    assert out and out.strip(), "+scenebonus produced no output"


async def e6_survey_runs_with_skill(h):
    """E6 — `survey` runs without raising for a character with the
    search skill set.

    The harness's economy_validation.py already exercises survey for
    cooldown semantics (and surfaced the soft warning). This scenario
    just smokes the read path on a fresh character.

    Survey requires being in a wilderness/resource room; in spawn
    (Landing Pad) it may refuse with a "no resources here" message.
    Both refusal and success are acceptable — we just assert no
    traceback.
    """
    s = await h.login_as(
        "E6Surveyor", room_id=1,
        skills={"search": "3D"},
    )
    out = await h.cmd(s, "survey")
    assert "traceback" not in out.lower(), (
        f"survey raised: {out[:500]!r}"
    )
    # Some output: success, refusal, or "no resources here" — all fine.
    assert out and out.strip(), "survey produced no output"


async def e7_full_craft_loop(h):
    """E7 — the full craft loop: learn → check → craft → item lands.

    Previously deferred for harness reasons (survey cooldowns, resource
    nodes); un-deferred by CRAFT.P0 via DIRECT STATE SEEDING — the
    schematic is granted and the components written straight to the DB,
    so no cooldown ticking or node seeding is needed. This is the
    scenario that would have caught the F1.D float→resolve_craft crash
    (every `craft` invocation raised for at least 8 days) and the F2
    evaporation (crafted weapons never landed anywhere).

    Asserts the strongest invariant the verb owns: after a `craft` that
    reports success, the item EXISTS in db.get_inventory. RNG note: the
    skill check can fail/fumble — components are seeded generously and
    the assertion branches on the reported outcome, so a legitimate
    failed roll doesn't flake the smoke; a crash or a success-without-
    item always fails it.
    """
    import json as _json

    s = await h.login_as(
        "E7Crafter", room_id=1,
        skills={"first_aid": "6D"},   # medpac_basic rolls first_aid vs 10
    )
    char_id = s.character["id"]

    # Seed: known schematic (attributes) + components (inventory).
    attrs = _json.loads(s.character.get("attributes") or "{}")
    attrs.setdefault("schematics", [])
    if "medpac_basic" not in attrs["schematics"]:
        attrs["schematics"].append("medpac_basic")
    inv = {"items": [], "resources": [
        {"type": "chemical", "quantity": 6, "quality": 60.0},
        {"type": "organic",  "quantity": 4, "quality": 60.0},
    ]}
    await h.db.save_character(
        char_id,
        attributes=_json.dumps(attrs),
        inventory=_json.dumps(inv),
    )
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()

    # The listing must render (F1.B1/B2 both crashed or lied here).
    out = await h.cmd(s, "schematics")
    assert "traceback" not in out.lower(), f"schematics raised: {out[:400]!r}"
    assert "medpac" in out.lower(), f"known schematic missing: {out[:400]!r}"
    out = await h.cmd(s, "resources")
    assert "traceback" not in out.lower(), f"resources raised: {out[:400]!r}"
    assert "chemical" in out.lower(), f"seeded stack missing: {out[:400]!r}"

    # The craft itself (F1.C/D + landing F2).
    out = await h.cmd(s, "craft medpac")
    low = out.lower()
    assert "error occurred" not in low and "traceback" not in low, (
        f"craft raised: {out[:500]!r}")

    if "added to your consumables" in low:
        # Success path: the consumable token must actually exist.
        fresh = await h.get_char(char_id)
        fattrs = _json.loads(fresh.get("attributes") or "{}")
        count = (fattrs.get("consumables") or {}).get("medpac", 0)
        assert count >= 1, (
            f"craft reported success but consumables.medpac={count}")
    else:
        # Legit failed/fumbled roll: output must say so, not be empty.
        assert any(k in low for k in
                   ("fail", "fumble", "can't quite", "ruined",
                    "struggle")), (
            f"craft neither succeeded nor reported failure: {out[:500]!r}")


async def e8_experiment_paths(h):
    """E8 — `experiment` runs against an equipped craftable weapon.

    Previously deferred; un-deferred by direct equipment-column seeding
    (canonical per-slot write). This is the scenario class that would
    have caught the pre-untangle parse_equipment_json regression
    ("no weapon equipped" forever). One experiment only — the cooldown
    never gates the first attempt. Outcome (success/failure/fumble) is
    RNG; the assertions accept any resolved outcome and reject crashes,
    "no weapon equipped", and silent no-ops.
    """
    import json as _json
    from engine.items import ItemInstance, write_equipment

    s = await h.login_as(
        "E8Tinkerer", room_id=1,
        skills={"blaster_repair": "5D"},
    )
    char_id = s.character["id"]

    equipment = write_equipment(
        weapon=ItemInstance(key="blaster_pistol", condition=100,
                            quality=70, crafter="E8Tinkerer"))
    await h.db.save_character(char_id, equipment=equipment)
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()

    # Status listing must see the equipped weapon.
    out = await h.cmd(s, "experiment list")
    low = out.lower()
    assert "traceback" not in low, f"experiment list raised: {out[:400]!r}"
    assert "no weapon equipped" not in low, (
        f"equipped weapon not seen (reader regression): {out[:400]!r}")
    assert "experimentation" in low, f"status panel missing: {out[:400]!r}"

    # One real experiment on the damage axis.
    out = await h.cmd(s, "experiment damage")
    low = out.lower()
    assert "error occurred" not in low and "traceback" not in low, (
        f"experiment raised: {out[:500]!r}")
    assert any(k in low for k in
               ("experiment success", "experiment fails",
                "experiment doesn't work", "boom", "crack", "clunk",
                "close call")), (
        f"experiment produced no resolved outcome: {out[:500]!r}")
