# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/padawan_master.py — Padawan-Master bond
end-to-end scenarios (PM-1 … PM-3).

P-M.1 (Drop 8, May 19 2026) shipped the DB foundation. P-M.2
(May 20 2026) ships the command surface and look-output bond
markers. These scenarios drive the live in-process harness end
to end through the command pipeline.

Scenarios
=========

* **PM-1** — Happy-path bond establishment via the player flow.
  Master proposes with ``+bond <padawan>``; Padawan accepts with
  ``+bond accept <master>``. Verify (a) ``+master`` from the
  Padawan and (b) ``+padawan`` from the Master both surface the
  partner's name afterward, and (c) the DB row is active.

* **PM-2** — `look` output shows the ``[Padawan]`` (bright-green)
  and ``[Master]`` (bright-cyan) markers for bonded PCs in the
  room contents block. Mirror of PVF-10 for the v45 §6.2 seventh
  phantom-pattern (byte-grep + runtime smoke). A regression that
  moves the marker into a dead branch would pass the byte-grep
  unit test but fail PM-2.

* **PM-3** — ``+release`` dissolves the bond and the Padawan-side
  narrative event (per design §8.12 #2 design call) lands in
  the Padawan's ``pc_action_log``. Confirms (a) the bond row's
  ``bond_status`` flipped to 'dissolved', (b) the Padawan saw
  the narrative line in their session, and (c) both sides have
  a ``bond_dissolved`` action log entry.

Notes
=====

* All three scenarios run in CONTESTED (default) room 1. Bond
  establishment requires Master and Padawan to be in the same
  room; ``+release`` does not.

* PM-2 follows the PVF-10 idiom for byte-string matching against
  the live `look` output. The marker literals
  (``[Padawan]`` / ``[Master]``) appear inside ANSI color sequences
  but the bracketed token is what the smoke checks.

* PM-3 reads ``pc_action_log`` via the harness's DB handle (same
  pattern PVF-* uses for char column checks). The
  ``bond_dissolved`` action_type is the cross-write seam for the
  shared-memory subsystem; the full Force-vision payload is a
  future drop, but the log entry is the foundation it builds on.
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# PM-1 — happy-path bond establishment via player flow
# ──────────────────────────────────────────────────────────────────────────


async def pm_1_bond_happy_path(h):
    """PM-1 — Master proposes, Padawan accepts, both sides see
    the partner via +master / +padawan, DB row is active.

    Exercises the full player-flow path locked in design §8.12 #1:
      Master: +bond <padawan>
      Padawan: +bond accept <master>
    """
    master = await h.login_as("PM1Master", room_id=1)
    padawan = await h.login_as("PM1Padawan", room_id=1)

    # Master proposes.
    out = await h.cmd(master, f"+bond {padawan.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`+bond` raised: {out[:500]!r}"
    )
    assert "offer to take" in out_lc or "padawan" in out_lc, (
        f"+bond did not produce a proposal-confirmation line. "
        f"Output: {out[:300]!r}"
    )

    # Brief settle so the proposal-notification reaches the
    # padawan's session before we drain.
    await asyncio.sleep(0.1)
    padawan.drain_text()

    # Padawan accepts.
    out2 = await h.cmd(
        padawan, f"+bond accept {master.character['name']}"
    )
    out2_lc = out2.lower()
    assert "traceback" not in out2_lc, (
        f"`+bond accept` raised: {out2[:500]!r}"
    )
    assert "accept" in out2_lc and master.character["name"].lower() in out2_lc, (
        f"+bond accept did not confirm bond. "
        f"Output: {out2[:400]!r}"
    )

    # +master from Padawan
    out_m = await h.cmd(padawan, "+master")
    assert "traceback" not in out_m.lower()
    assert master.character["name"] in out_m, (
        f"+master should show the Master's name. "
        f"Output: {out_m[:300]!r}"
    )

    # +padawan from Master
    out_p = await h.cmd(master, "+padawan")
    assert "traceback" not in out_p.lower()
    assert padawan.character["name"] in out_p, (
        f"+padawan should show the Padawan's name. "
        f"Output: {out_p[:300]!r}"
    )

    # DB row sanity (read via harness DB handle).
    bond = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    assert bond is not None, (
        "DB has no active bond for the Padawan after the "
        "accept handshake."
    )
    assert bond["master_char_id"] == master.character["id"], (
        f"Bond master_char_id mismatch: {bond!r}"
    )
    assert bond["bond_status"] == "active", (
        f"Bond status should be 'active'; got {bond['bond_status']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PM-2 — `look` shows [Padawan] / [Master] markers for bonded PCs
# ──────────────────────────────────────────────────────────────────────────


async def pm_2_look_shows_bond_markers(h):
    """PM-2 — When PC B looks at a room containing a bonded
    Master-Padawan pair, both PCs appear with their respective
    markers ([Padawan] in bright green, [Master] in bright cyan).

    Per v45 §6.2 seventh phantom-pattern: the marker literals
    are byte-grep-pinned in tests/test_pm2_commands.py
    (TestMarkerLiterals / TestMarkerLiteralsInLookCode) AND
    runtime-pinned here. A regression where the look code stops
    consuming the markers (e.g. an exception-swallowing import
    that always returns "") would pass the unit test but fail
    PM-2.

    Setup: bond Master+Padawan via @bond (admin path skips the
    consent dance — keeps the scenario focused on look output,
    not the bond flow), then have a third PC (the observer) look.
    """
    master = await h.login_as("PM2Master", room_id=1)
    padawan = await h.login_as("PM2Padawan", room_id=1)
    observer = await h.login_as("PM2Observer", room_id=1)

    # Use the player flow to establish the bond. The admin @bond
    # path is exercised by the unit tests
    # (test_pm2_commands.TestAdminBondHappyPath); this smoke
    # focuses on the look-output render, so we keep the bond-
    # establishment path consistent with PM-1 (player flow) for
    # simplicity. Harness accounts are non-admin by default, and
    # @bond requires ADMIN access.
    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(
        padawan, f"+bond accept {master.character['name']}"
    )

    # Confirm bond is live before checking look.
    bond = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    assert bond is not None, (
        "PM-2 precondition failed: bond was not established "
        "(neither admin nor player flow worked)."
    )

    # Observer looks.
    observer.drain_text()
    out = await h.cmd(observer, "look")
    assert "traceback" not in out.lower(), (
        f"`look` raised: {out[:500]!r}"
    )
    # Both names visible in the room contents.
    assert master.character["name"] in out, (
        f"Master name missing from look output: {out[:400]!r}"
    )
    assert padawan.character["name"] in out, (
        f"Padawan name missing from look output: {out[:400]!r}"
    )
    # Markers present. Both should be in the same look output.
    assert "[Master]" in out, (
        f"`look` did not show the [Master] marker for the bonded "
        f"Master. The byte-grep unit test confirms the literal is "
        f"in the source — possible regression where the marker is "
        f"not reaching the live render path. Output: {out[:600]!r}"
    )
    assert "[Padawan]" in out, (
        f"`look` did not show the [Padawan] marker for the bonded "
        f"Padawan. Output: {out[:600]!r}"
    )

    # Sanity inverse: the observer (no bond) should NOT appear in
    # OTHERS' looks with either marker. Have the master look —
    # the observer should be listed but unmarked.
    master.drain_text()
    out2 = await h.cmd(master, "look")
    # Find the observer's line in the output. It must NOT carry
    # either bond marker.
    observer_lines = [
        line for line in out2.split("\n")
        if observer.character["name"] in line
    ]
    assert observer_lines, (
        f"Observer name not found in master's look. "
        f"Output: {out2[:400]!r}"
    )
    for line in observer_lines:
        assert "[Padawan]" not in line and "[Master]" not in line, (
            f"Observer (unbonded) was rendered with a bond marker: "
            f"{line!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# PM-3 — +release dissolves bond + writes narrative log on both sides
# ──────────────────────────────────────────────────────────────────────────


async def pm_3_release_dissolves_and_logs(h):
    """PM-3 — +release flips the bond to 'dissolved' AND writes
    the narrative-memory cross-write entries (action_type=
    'bond_dissolved') on BOTH the Master's and the Padawan's
    pc_action_log per design §8.12 #2 design call.

    This is the seam for the future shared-memory subsystem
    (§5.4 of the full P-M design). The Director AI will fold
    these log entries into the long_record so NPC dialogue
    can reference the dissolution naturally ("I heard your
    Master let you go...").
    """
    master = await h.login_as("PM3Master", room_id=1)
    padawan = await h.login_as("PM3Padawan", room_id=1)

    # Establish via player flow.
    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(padawan, f"+bond accept {master.character['name']}")

    bond_pre = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    assert bond_pre is not None, "PM-3 setup failed: no active bond"
    bond_id = bond_pre["id"]

    # Drain Padawan's session before the release-notification arrives.
    padawan.drain_text()

    # Master releases with a reason.
    out = await h.cmd(
        master,
        f"+release {padawan.character['name']} = path diverges",
    )
    assert "traceback" not in out.lower()
    assert "release" in out.lower(), (
        f"+release output did not confirm: {out[:300]!r}"
    )

    # Bond row flipped to dissolved.
    bond_post = await h.db.get_bond(bond_id)
    assert bond_post["bond_status"] == "dissolved", (
        f"Bond status should be 'dissolved' after +release; "
        f"got {bond_post['bond_status']!r}"
    )
    assert bond_post.get("dissolved_reason"), (
        f"Bond should record dissolved_reason from the '= reason' "
        f"clause. Got: {bond_post!r}"
    )

    # Padawan-side narrative line (online notification).
    await asyncio.sleep(0.1)
    padawan_buf = padawan.drain_text()
    assert master.character["name"] in padawan_buf, (
        f"Padawan should have received the release notification "
        f"naming the Master. Buffer: {padawan_buf[:400]!r}"
    )

    # Action log cross-write on BOTH sides.
    m_actions = await h.db.get_recent_actions(
        master.character["id"], limit=20
    )
    p_actions = await h.db.get_recent_actions(
        padawan.character["id"], limit=20
    )
    assert any(
        a["action_type"] == "bond_dissolved" for a in m_actions
    ), (
        f"Master's pc_action_log missing 'bond_dissolved' entry. "
        f"Recent actions: {[a['action_type'] for a in m_actions]}"
    )
    assert any(
        a["action_type"] == "bond_dissolved" for a in p_actions
    ), (
        f"Padawan's pc_action_log missing 'bond_dissolved' entry. "
        f"Recent actions: {[a['action_type'] for a in p_actions]}"
    )
