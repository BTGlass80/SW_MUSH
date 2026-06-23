"""tests/test_guide_22_espionage_authoritative.py

Authoritative Opus quality-pass guard for Guide_22_Espionage.md.
Complements the Sonnet-draft guard ``test_guide_22_espionage_rework.py``;
this file pins the corrections the authoritative pass made against HEAD and
cross-checks the guide's quoted facts against the live command keys + engine
constants, so a future rename or balance change forces the guide to move
with it.

Drift this pass corrected (verified against parser/espionage_commands.py,
engine/espionage.py, engine/intel_handlers.py and engine/world_events.py at
HEAD):
  - The room-search command is ``search`` (alias ``inspect``), NOT
    ``investigate`` — command-syntax rework Drop 7 moved the bare
    ``investigate`` key to the wilderness-anomaly verb. The guide said
    "investigate (aliases: search, inspect)".
  - Assess has exactly THREE reveal tiers (margin 0+, +5, +10) — the guide
    invented a phantom "15+" tier. The +5 tier reveals a credits/wealth
    band, which the guide omitted.
  - Eavesdrop initiation is a flat Moderate (15), not a "distance-scaled"
    difficulty; its muffling is a flat ~⅓ word survival (quoted speech
    leaks), not margin-scaled clarity. The guide claimed both.
  - Espionage awards NO reputation. The guide claimed "+2 to +5 rep per
    report" and faction-rep penalties on discovery; neither exists. The
    real reward is credits + territory influence.
  - The ``listen`` (eavesdrop) alias was undocumented.
  - INTELLIGENCE_THAW doubles the CREDIT payout (intel_pay_mult == 2.0);
    influence is unscaled.
"""

import pathlib
import re

GUIDE_PATH = pathlib.Path("data/guides/Guide_22_Espionage.md")
PARSER_SRC = pathlib.Path("parser/espionage_commands.py")
ENGINE_SRC = pathlib.Path("engine/espionage.py")
HANDLERS_SRC = pathlib.Path("engine/intel_handlers.py")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


# ── Command surface cross-checks ─────────────────────────────────────────

def test_room_search_command_is_search_not_investigate():
    from parser.espionage_commands import InvestigateCommand
    # The espionage room-search command was canonicalized to 'search' in
    # command-syntax rework Drop 7; bare 'investigate' is the anomaly verb.
    assert InvestigateCommand.key == "search"
    assert "inspect" in InvestigateCommand.aliases
    assert "investigate" not in InvestigateCommand.aliases


def test_bare_investigate_is_the_anomaly_command():
    from parser.anomaly_commands import InvestigateCommand as AnomalyInvestigate
    assert AnomalyInvestigate.key == "investigate"


def test_guide_documents_search_not_investigate_as_the_room_verb():
    text = read_guide()
    # The guide must NOT present the room search as bare `investigate
    # (aliases: search, inspect)` — that's the corrected drift.
    assert "investigate\n(aliases: search, inspect)" not in text
    # The §4 command block uses `search` with the inspect alias.
    assert "(aliases: inspect; umbrella: +spy investigate)" in text
    # The Quick Reference row uses `search`, never a bare `| `investigate` |`.
    assert "| `search` |" in text
    assert "| `investigate` |" not in text


def test_assess_command_keys_match():
    from parser.espionage_commands import ScanCommand
    assert ScanCommand.key == "assess"
    assert ScanCommand.aliases == ["size"]


def test_eavesdrop_listen_alias_documented():
    from parser.espionage_commands import EavesdropCommand
    assert "listen" in EavesdropCommand.aliases
    assert "(alias: listen)" in read_guide()


def test_intercept_keys_match():
    from parser.espionage_commands import InterceptCommand
    assert InterceptCommand.key == "intercept"
    assert set(InterceptCommand.aliases) == {"wiretap", "comtap"}


# ── Assess reveal tiers ──────────────────────────────────────────────────

def test_assess_has_exactly_three_reveal_tiers():
    src = ENGINE_SRC.read_text(encoding="utf-8")
    # generate_scan_result branches at margin >= 5 and >= 10 only.
    assert "margin >= 5" in src
    assert "margin >= 10" in src
    assert "margin >= 15" not in src, (
        "Assess has no 15+ tier; the guide must not invent one."
    )
    text = read_guide()
    assert "15+" not in text, "Phantom assess tier '15+' must be gone."


def test_assess_documents_the_credit_wealth_read():
    # The +5 tier reveals a credits/wealth band (generate_scan_result).
    src = ENGINE_SRC.read_text(encoding="utf-8")
    assert "credit_desc" in src
    text = read_guide().lower()
    assert "wealth band" in text or "wealth read" in text, (
        "The +5 assess tier reveals a credits/wealth band — the guide must "
        "document it."
    )


# ── Eavesdrop difficulty + muffling ──────────────────────────────────────

def test_eavesdrop_difficulty_is_flat_moderate_15():
    src = PARSER_SRC.read_text(encoding="utf-8")
    assert "difficulty = 15  # Moderate for adjacent room" in src
    text = read_guide()
    assert "distance-scaled" not in text, (
        "Eavesdrop difficulty is a flat Moderate (15), not distance-scaled."
    )
    assert "Perception vs. Moderate (15)" in text


def test_eavesdrop_muffling_is_flat_not_margin_scaled():
    text = read_guide()
    # The relay muffles at a flat rate (muffle_for_eavesdrop default margin
    # 0 → 30% survival); the guide must not promise margin-scaled clarity.
    assert "High-margin success: you hear most of the words" not in text
    assert "quoted" in text.lower(), (
        "Quoted speech leaks through eavesdrop muffling — document it."
    )


# ── Intel handover economy ───────────────────────────────────────────────

def test_intel_quality_tiers_match_engine():
    from engine.intel_handlers import (
        INTEL_QUALITY_LOW, INTEL_QUALITY_MEDIUM, INTEL_QUALITY_HIGH,
    )
    # (min_inf, max_inf, min_cr, max_cr)
    assert INTEL_QUALITY_LOW == (1, 3, 200, 500)
    assert INTEL_QUALITY_MEDIUM == (4, 8, 600, 1500)
    assert INTEL_QUALITY_HIGH == (10, 20, 2000, 5000)
    text = read_guide()
    assert "200–500 cr, 1–3 influence" in text
    assert "600–1,500 cr, 4–8 influence" in text
    assert "2,000–5,000 cr, 10–20 influence" in text


def test_intelligence_thaw_doubles_credits_only():
    from engine.world_events import EVENT_DEFS, EventType
    eff = EVENT_DEFS[EventType.INTELLIGENCE_THAW].mechanical_effects
    assert eff.get("intel_pay_mult") == 2.0
    text = read_guide().lower()
    assert "double" in text and "influence" in text


def test_freshness_window_is_24h_with_3day_penalty():
    from engine.intel_handlers import _FRESHNESS_WINDOW_SECS
    assert _FRESHNESS_WINDOW_SECS == 24 * 3600
    text = read_guide()
    assert "24 hours" in text
    assert "3 days" in text


def test_report_caps_match_engine():
    src = ENGINE_SRC.read_text(encoding="utf-8")
    assert "if len(reports) >= 10:" in src       # create cap
    assert 'if len(draft["lines"]) >= 20:' in src  # add-line cap
    text = read_guide()
    assert "10 reports" in text
    assert "20 lines" in text


# ── No reputation award (phantom-killer) ─────────────────────────────────

def test_espionage_awards_no_reputation():
    # The handover path credits + influence only — it never calls a
    # reputation mutator (set_standing / faction_rep). Guard the source so a
    # future change that DOES add rep forces the guide to re-document it.
    for src_path in (PARSER_SRC, HANDLERS_SRC):
        src = src_path.read_text(encoding="utf-8")
        assert "set_standing" not in src, (
            f"{src_path} now touches reputation — re-document Guide_22 §9."
        )


def test_guide_does_not_claim_phantom_reputation():
    text = read_guide()
    assert "+2 to +5 per significant report" not in text, (
        "Phantom rep claim: espionage awards no reputation points."
    )
    assert "rep gain" not in text.lower()
    # §9 must state the reward is credits + influence, not rep.
    assert "not rep" in text.lower() or "no rep" in text.lower()


# ── Era cleanness ────────────────────────────────────────────────────────

_ERA_RE = [re.compile(p) for p in (
    r"\bImperial(?! Sourcebook)\b",
    r"\bGalactic Empire\b",
    r"\bRebel Alliance\b",
    r"\bGalactic Civil War\b",
    r"\bGCW\b",
    r"\bTIE fighter\b",
)]


def test_era_clean():
    viols = []
    for i, line in enumerate(read_guide().split("\n"), start=1):
        for pat in _ERA_RE:
            if pat.search(line):
                viols.append((i, line.strip()))
    assert not viols, "Guide_22 era violations:\n" + "\n".join(
        f"  line {n}: {t!r}" for n, t in viols
    )
