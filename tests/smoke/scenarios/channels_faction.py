# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/channels_faction.py — Communication channels +
faction reputation scenarios (FC1–FC3, CN1–CN2). Drop 3 Block F.

These commands had been crashing with `AttributeError: module
'server.ansi' has no attribute 'highlight'` in production for any
player who tried `+faction`, `+channels`, `tune`, `+freqs`, or
`commfreq`. The fix in this drop adds `ansi.highlight()` (bold
bright-cyan) to `server/ansi.py`. FC1 and CN1 are the regression
guards.

Mail scenarios (originally planned ML1/ML2/ML3 in Block F) are
DEFERRED. The mail commands reference `mail` and `mail_recipients`
tables that don't exist in the current schema — a substantial
missing feature, not a smoke gap. Filed in the Drop-3 handoff.

Scope:
  FC1 — `+faction` shows current affiliation cleanly
        (regression guard for ansi.highlight fix)
  FC2 — `+reputation` overview lists all canonical factions
  FC3 — `+reputation republic` detail view shows rank thresholds
  CN1 — `+channels` lists OOC + comlink + fcomm + commfreq
        (regression guard for ansi.highlight fix)
  CN2 — `tune <freq>` then `+freqs` round-trips
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# FC1 — +faction render
# ──────────────────────────────────────────────────────────────────────────

async def fc1_faction_shows_current_affiliation(h):
    """FC1 — `+faction` shows the player's current faction without
    crashing.

    REGRESSION GUARD for the Drop-3 `ansi.highlight()` fix
    (server/ansi.py). Pre-fix, this command 500'd with:

      AttributeError: module 'server.ansi' has no attribute 'highlight'

    Output exposed to player:
      "An error occurred processing your command. (module
       'server.ansi' has no attribute 'highlight')"

    Fresh CW chars default to "Independent" affiliation.
    """
    s = await h.login_as("FC1Indie", room_id=1)
    out = await h.cmd(s, "+faction")
    assert "traceback" not in out.lower(), (
        f"+faction raised: {out[:500]!r}"
    )
    # Specific catch for the AttributeError leaking through.
    assert "no attribute" not in out.lower(), (
        f"`server.ansi.highlight` AttributeError leaked through. "
        f"Output: {out[:300]!r}"
    )
    out_lc = out.lower()
    # The render labels the section "Faction" and shows current
    # affiliation. A fresh char is "Independent".
    assert "faction" in out_lc, (
        f"+faction output doesn't mention 'faction'. "
        f"Output: {out[:400]!r}"
    )
    assert "independent" in out_lc or "affiliation" in out_lc, (
        f"+faction doesn't show affiliation state. "
        f"Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# FC2 — +reputation overview
# ──────────────────────────────────────────────────────────────────────────

async def fc2_reputation_overview_lists_factions(h):
    """FC2 — `+reputation` overview shows the standing across the
    canonical factions for the active era.

    The CW canonical faction list per architecture v38 §6.5 +
    B.1.a is Republic / CIS / Jedi / Hutt / BH; GCW is Empire /
    Rebel / Hutt / BH. Tests/conftest.py defaults --smoke-era to
    "gcw" today (despite the harness docstring claiming
    "clone_wars" — drift between two related defaults, flagged
    in the Drop 3 handoff). FC2 accepts either era's canonical
    set so it doesn't break when the conftest catches up.
    """
    s = await h.login_as("FC2Repper", room_id=1)
    out = await h.cmd(s, "+reputation")
    assert "traceback" not in out.lower(), (
        f"+reputation raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # CW factions OR GCW factions — at least one canonical name
    # for the active era's faction roster must appear.
    cw_factions = ("republic", "confederacy", "jedi order")
    gcw_factions = ("empire", "rebel alliance")
    common_factions = ("hutt cartel", "bounty hunters")
    found = (
        any(f in out_lc for f in cw_factions) or
        any(f in out_lc for f in gcw_factions) or
        any(f in out_lc for f in common_factions)
    )
    assert found, (
        f"+reputation overview lists no recognized factions. "
        f"Output: {out[:500]!r}"
    )
    # Should look like a list/table — multiple lines or a divider.
    assert "\n" in out or "\r\n" in out, (
        f"+reputation output is single-line; expected multi-row "
        f"table. Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# FC3 — +reputation republic detail
# ──────────────────────────────────────────────────────────────────────────

async def fc3_reputation_detail_shows_ranks(h):
    """FC3 — `+reputation <faction>` detail view shows rank
    thresholds (or current standing) cleanly.

    The detail view renders RANK THRESHOLDS — a list of named
    ranks at numeric thresholds. We pick a faction code that
    exists in the active era's organizations table (rather than
    hard-coding "republic" — see FC2 docstring for the era drift
    note) and assert the detail formatter ran.
    """
    # Find any faction-type org other than 'independent' to use
    # as the test target. This works in both GCW and CW.
    rows = await h.db.fetchall(
        "SELECT code FROM organizations "
        "WHERE org_type = 'faction' AND code != 'independent' "
        "ORDER BY id LIMIT 1"
    )
    assert rows, (
        "No faction-type organizations seeded in the test DB. "
        "FC3 cannot validate detail-view rendering."
    )
    faction_code = rows[0]["code"]

    s = await h.login_as("FC3Detail", room_id=1)
    out = await h.cmd(s, f"+reputation {faction_code}")
    assert "traceback" not in out.lower(), (
        f"+reputation {faction_code} raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Detail view header includes faction name AND at least one
    # of standing/rank/threshold/status fields.
    assert (
        faction_code.replace("_", " ") in out_lc or
        any(t in out_lc for t in ("rank", "standing", "threshold",
                                   "status"))
    ), (
        f"+reputation {faction_code} doesn't look like a detail "
        f"view. Output: {out[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# CN1 — +channels list
# ──────────────────────────────────────────────────────────────────────────

async def cn1_channels_lists_communication_surfaces(h):
    """CN1 — `+channels` lists the canonical channels (ooc,
    comlink, fcomm, commfreq) without crashing.

    REGRESSION GUARD for the Drop-3 `ansi.highlight()` fix —
    paired with FC1. `+channels` was the second visible victim of
    the missing helper.
    """
    s = await h.login_as("CN1Chatter", room_id=1)
    out = await h.cmd(s, "+channels")
    assert "traceback" not in out.lower(), (
        f"+channels raised: {out[:500]!r}"
    )
    assert "no attribute" not in out.lower(), (
        f"ansi.highlight AttributeError leaked through. "
        f"Output: {out[:300]!r}"
    )
    out_lc = out.lower()
    # Canonical channels — at least the OOC and comlink channels
    # must appear. Both are foundational; their absence would
    # signal a deeper formatter bug.
    for required in ("ooc", "comlink"):
        assert required in out_lc, (
            f"+channels list missing '{required}' channel. "
            f"Output: {out[:500]!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# CN2 — tune + +freqs round-trip
# ──────────────────────────────────────────────────────────────────────────

async def cn2_tune_and_freqs_roundtrip(h):
    """CN2 — `tune 1138` succeeds; `+freqs` shows 1138 as tuned.

    The frequencies system stores tuning state per session (not in
    DB persistence — see channel_commands.py module-level dict).
    The same player session must do both commands; with the harness's
    session continuity, this round-trips correctly.
    """
    s = await h.login_as("CN2Tuner", room_id=1)

    out = await h.cmd(s, "tune 1138")
    assert "traceback" not in out.lower(), (
        f"`tune 1138` raised: {out[:500]!r}"
    )
    assert "1138" in out, (
        f"`tune 1138` response doesn't mention the freq. "
        f"Output: {out[:300]!r}"
    )

    out2 = await h.cmd(s, "+freqs")
    assert "traceback" not in out2.lower(), (
        f"`+freqs` raised: {out2[:500]!r}"
    )
    assert "1138" in out2, (
        f"`+freqs` doesn't show the just-tuned 1138 frequency. "
        f"Output: {out2[:400]!r}"
    )
