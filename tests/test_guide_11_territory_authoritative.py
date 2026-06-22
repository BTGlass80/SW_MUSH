"""tests/test_guide_11_territory_authoritative.py

Authoritative Opus quality-pass guard for Guide_11_Territory_Control.md
(Guide Version 3.0). Complements the Sonnet-draft guard
``test_guide_11_territory_rework.py``; this file pins the corrections the
authoritative pass made against HEAD and cross-checks the guide's quoted
numbers against the live engine constants so a future balance change that
moves a constant forces the guide to move with it.

Drift this pass corrected (verified against engine/territory.py,
engine/contest.py, engine/security.py, parser/faction_commands.py at HEAD):
  - Influence is earned ONLY in wilderness rooms (SYN.5 two-tier rule);
    city-map activity grants zero influence.
  - Garrison guards SCATTER across the region's landmarks (not one
    "central landmark room").
  - The Jedi Order garrison guard (Temple Sentinel) was missing.
  - ``faction guard remove`` is a retired/phantom command (the guard verb
    only prints a "retired" notice now) — removed from the guide.
  - The upkeep-lapse mechanic (garrison dismissed first, then ownership
    lost) was undocumented.
  - During an active contest, in-region influence is DOUBLED (2×) for both
    sides + a 1.5× outnumbered-defender bonus — the guide said "normal".
  - A high-influence challenger summons extra Anchor reinforcements.
  - A challenger win also puts the former owner on the 14-day cooldown.

Engine fix shipped in the same drop:
  - ``faction contest`` (bare) now dispatches to the contest view (it only
    worked as ``+faction contest`` before — a documented-but-dead form).
"""

import asyncio
import pathlib
import re
import types

GUIDE_PATH = pathlib.Path("data/guides/Guide_11_Territory_Control.md")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


# ── Authoritative-pass accuracy pins ────────────────────────────────────

def test_wilderness_only_influence_rule_documented():
    text = read_guide().lower()
    assert "wilderness rule" in text or "wilderness region" in text
    # The key correction: city-map activity earns zero influence.
    assert "zero influence" in text, (
        "Guide must state that city-map combat/missions earn ZERO influence "
        "(SYN.5 two-tier rule) — territory is built in the wilderness only."
    )


def test_garrison_scatters_not_central_room():
    text = read_guide()
    assert "central landmark room" not in text, (
        "Drift: garrison does NOT deploy to one central room; it scatters "
        "across the region's landmarks (spawn_region_garrison random.choice)."
    )
    assert "scattered across" in text.lower()


def test_jedi_garrison_guard_present():
    text = read_guide()
    assert "Temple Sentinel" in text, (
        "Jedi Order garrison guard (Temple Sentinel) missing from the guard "
        "table — _GUARD_TEMPLATES['jedi_order'] is a live CW faction."
    )


def test_no_phantom_guard_remove_command():
    text = read_guide()
    # remove_guard_npc is a retired no-op stub; faction guard remove only
    # prints a "retired" notice. It must not be presented as a real command.
    assert "guard remove" not in text, (
        "'faction guard remove' is a retired/phantom command and must not "
        "appear in the guide."
    )


def test_upkeep_lapse_mechanic_documented():
    text = read_guide().lower()
    assert "lapse" in text, (
        "The upkeep-lapse mechanic (region returns to un-owned when treasury "
        "can't cover base maintenance) must be documented."
    )
    # Garrison is dismissed first as a cost-saving stage.
    assert "garrison dismissed" in text or "dismissed first" in text


def test_contest_influence_doubling_documented():
    text = read_guide()
    lower = text.lower()
    assert "earn normal influence" not in lower, (
        "Drift: influence is NOT 'normal' during a contest — it is doubled."
    )
    assert "doubled" in lower or "2×" in text, (
        "Guide must document the 2× in-region influence doubling during a "
        "contest (apply_contest_influence_multipliers)."
    )
    assert "1.5×" in text, (
        "Guide must document the 1.5× outnumbered-defender bonus."
    )


def test_anchor_reinforcements_documented():
    text = read_guide().lower()
    assert "reinforcement" in text, (
        "Guide must document that a high-influence challenger causes the "
        "defender to field extra Anchor reinforcements "
        "(compute_anchor_reinforcements)."
    )


def test_symmetric_loss_cooldown_documented():
    text = read_guide().lower()
    # Both sides eat the 14-day cooldown on a loss; the guide previously
    # only mentioned the challenger's.
    assert "symmetric" in text, (
        "Guide must note the cooldown/penalty is symmetric (whichever side "
        "loses eats the 25-influence penalty + 14-day lockout)."
    )


# ── Engine cross-check guard — guide numbers must match HEAD ─────────────

def test_guide_numbers_match_territory_constants():
    from engine import territory as T
    text = read_guide()

    # Thresholds + cap
    assert T.THRESHOLD_PRESENCE == 25 and "25" in text
    assert T.THRESHOLD_FOOTHOLD == 50 and "50" in text
    assert T.THRESHOLD_DOMINANCE == 75 and "75" in text
    assert T.THRESHOLD_CONTROL == 100 and "100" in text
    assert T.INFLUENCE_CAP == 150 and "150" in text

    # Earn rates the guide quotes verbatim
    assert T.INFLUENCE_NPC_KILL == 2
    assert T.INFLUENCE_MISSION == 5
    assert T.INFLUENCE_PVP_WIN == 15 and "+15" in text
    assert T.INFLUENCE_INVEST_PER_1K == 10
    assert T.INFLUENCE_INVEST_MIN == 1000 and "1,000" in text
    assert T.INFLUENCE_INVEST_MAX == 10000 and "10,000" in text

    # Decay
    assert T.DECAY_NO_PRESENCE_HOURS == 48 and "48" in text
    assert T.DECAY_RATE_PER_DAY == 5

    # Region claim economy
    assert T.REGION_CLAIM_COST == 5000 and "5,000" in text
    assert T.REGION_CLAIM_MIN_RANK == 3
    assert T.REGION_WEEKLY_MAINT == 2000 and "2,000" in text
    assert T.REGION_GARRISON_WEEKLY == 1000 and "1,000" in text
    assert T.REGION_GARRISON_COUNT == 5 and "5 garrison guards" in text

    # Passive yield bands
    assert T.REGION_PASSIVE_CONTESTED_MIN == 50
    assert T.REGION_PASSIVE_CONTESTED_MAX == 150
    assert T.REGION_PASSIVE_LAWLESS_MIN == 100
    assert T.REGION_PASSIVE_LAWLESS_MAX == 250


def test_guide_numbers_match_contest_constants():
    from engine import contest as C
    text = read_guide()

    assert C.REGION_CONTEST_DURATION_SECS == 7 * 24 * 3600 and "7 day" in text.lower()
    assert C.REGION_CONTEST_CULMINATING_SECS == 4 * 3600 and "4 hour" in text.lower()
    assert C.REGION_CONTEST_TRIGGER_RATIO == 0.75 and "75%" in text
    assert C.REGION_CONTEST_MIN_CHALLENGER_INFLUENCE == 50
    assert C.REGION_CONTEST_FAILURE_PENALTY == 25 and "25" in text
    assert C.REGION_CONTEST_COOLDOWN_SECS == 14 * 24 * 3600 and "14-day" in text
    assert C.OUTNUMBERED_DEFENDER_INFLUENCE_MULTIPLIER == 1.5


# ── Engine-fix functional guard: bare `faction contest` routes ──────────

def test_bare_faction_contest_dispatches_to_contest_view():
    """`faction contest` (bare) must route to the contest handler.

    Before this drop only `+faction contest` worked; the bare `faction`
    surface — where every other territory verb lives — was missing the
    subcommand. We drive an independent-faction character so the handler
    short-circuits before any DB access, proving the dispatch wiring
    without a live DB.
    """
    from parser.faction_commands import FactionCommand

    assert hasattr(FactionCommand, "_cmd_contest"), (
        "FactionCommand._cmd_contest method missing (bare contest view)."
    )

    sent = []

    async def _send_line(msg):
        sent.append(msg)

    char = {"id": 1, "name": "Tester", "faction_id": "independent"}
    session = types.SimpleNamespace(character=char, send_line=_send_line)
    ctx = types.SimpleNamespace(session=session, args="contest", db=None)

    asyncio.run(FactionCommand().execute(ctx))

    blob = "\n".join(sent).lower()
    assert "member of a faction" in blob, (
        "Bare `faction contest` did not route to the contest handler "
        "(expected the independent-char 'not a member' rejection)."
    )


def test_bare_faction_contest_registered_in_dispatch_source():
    """Static belt-and-suspenders: the dispatch wiring is present."""
    src = pathlib.Path("parser/faction_commands.py").read_text(encoding="utf-8")
    assert re.search(r'"contest":\s*self\._cmd_contest', src), (
        "`contest` subcommand not wired into the bare FactionCommand dispatch."
    )
