# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/chain_bounty_track.py — tutorial bounty target
binding (drop 26, 2026-06-13).

Verifies that the bounty_hunter chain's tutorial contract
(`tutorial_bhg_tarko_vinn`) binds its target NPC + room when spawned,
so `bountytrack` works instead of hard-erroring "Contract data error —
target NPC not found".

Root cause (drop 26): `engine/chain_missions._materialize_bounty` left
`target_npc_id` / `target_room_id` = None; the tutorial_bounties.yaml
entry carries `target_room_slug` which the materializer ignored.
`_spawn_bounty` now resolves the slug → room id and binds the anchor
NPC (Tarko Vinn, placed in the warrens safehouse by the world build).
This also surfaced + fixed a latent crash in BountyTrackCommand
(`Character.from_db_dict(char_row, skill_reg)` — extra positional arg).
"""
from __future__ import annotations

import json


async def cbt_1_bountytrack_works_on_tutorial_contract(h):
    """CBT-1 — Spawn the bounty_hunter step-2 tutorial contract, claim
    it, and run `bountytrack`. It must investigate the bound target
    (Tarko Vinn) rather than hit the unbound-target data error."""
    from engine.tutorial_chains import load_tutorial_chains
    from engine.chain_missions import maybe_spawn_for_step

    corpus = load_tutorial_chains(h.era)
    if corpus is None:
        return  # era without chains — nothing to verify
    chain = corpus.by_id().get("bounty_hunter")
    if chain is None:
        return

    s = await h.start_chain("CBTHunter", "bounty_hunter",
                            skills={"search": "8D"})
    char_id = s.character["id"]

    # Advance the seeded chain state to step 2 (the bounty_accepted step)
    # WITHOUT walking — this scenario is about the contract binding, not
    # the walk (the walkthrough smoke covers the walk). Then drive the
    # spawn the way the engine does on step entry.
    char = await h.get_char(char_id)
    attrs = json.loads(char.get("attributes") or "{}")
    attrs["tutorial_chain"]["step"] = 2
    attrs["tutorial_chain"]["completed_steps"] = [1]
    await h.db.save_character(char_id, attributes=json.dumps(attrs))
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()

    spawned = await maybe_spawn_for_step(
        h.db, await h.get_char(char_id), "bounty_hunter", 2)
    assert spawned == "tutorial_bhg_tarko_vinn", (
        f"expected tutorial bounty to spawn; got {spawned!r}"
    )

    # Claim then track.
    await h.cmd(s, "+bounties")
    claim = await h.cmd(s, "bountyclaim chain_tutorial_bhg_tarko_vinn")
    assert "traceback" not in claim.lower(), (
        f"bountyclaim raised: {claim[:300]!r}"
    )
    track = await h.cmd(s, "bountytrack")
    track_lc = track.lower()
    assert "traceback" not in track_lc, (
        f"bountytrack raised: {track[:400]!r}"
    )
    assert "contract data error" not in track_lc, (
        f"bountytrack still hits the unbound-target data error — the "
        f"tutorial contract's target NPC was not bound. Output: "
        f"{track[:300]!r}"
    )
    assert "from_db_dict" not in track_lc and "positional argument" \
        not in track_lc, (
        f"bountytrack hit the from_db_dict signature crash. Output: "
        f"{track[:300]!r}"
    )
    # A working track names the target and shows a roll.
    assert "tarko vinn" in track_lc, (
        f"bountytrack did not investigate the bound target Tarko Vinn. "
        f"Output: {track[:300]!r}"
    )
