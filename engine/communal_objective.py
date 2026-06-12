"""engine/communal_objective.py — the dark-side cult communal objective (Drop 4b, the
communal-rally villain; the *other half* of design III.3).

Counterpart to engine/dsp_hunter.py. Where the DSP hunter is a PER-PC persistent
threat that closes on one marked dark-sider, the cult is a COMMUNAL threat the whole
playerbase rallies against — a Director-posted objective with a visible menace meter
and a real win/lose state (design III.3, sw_mush_remediation_and_fun_additions_design_v1.md).

Design contract (matches III.3 + the Drop-4 locked decisions):
  * **Non-player faction.** The villain is a fictional dark-side cult, never a player
    faction and never a canon figure (Q1). All roster names are invented; no
    Galactic-Civil-War-era faction strings anywhere (B3).
  * **Opportunities, never penalties.** A win confers status/rep; a loss confers
    nothing and the cult simply entrenches as flavor. No player is penalised for a
    community loss.
  * **Prestige-domain rewards, faucet-disciplined.** Routing the cult pays faction
    reputation (Republic — putting down a dark-side cult serves the Republic/Jedi)
    and a commemorative status flag (III.2). NO credits are minted here; if a credit
    reward is ever added it must route through db.adjust_credits (§4.32).
  * **Open across playstyles.** A "strike" against the cult accepts the BEST of a
    broad skill set so a soldier, a slicer/informant, a face, or a Jedi all qualify.
  * **Deterministic + idle-Ollama flavor only (NEVER Haiku).** This pure module owns
    the deciders, the roster, and every player-facing string. The IO orchestrator
    (engine/communal_objective_runtime.py) owns DB writes, broadcasts, reward payout,
    and director-log posts; the tick (server/tick_handlers_progression.py::
    communal_objective_tick) owns posting/advancing/resolving cadence.

This module is PURE: no DB, no asyncio, no session manager. Everything here is unit
testable with plain values, mirroring engine/dsp_hunter.py and engine/creature_library.py.
"""
from __future__ import annotations

from dataclasses import dataclass


# ── ANSI (local palette; mirrors engine/dsp_hunter.py / engine/bounty_board.py) ──
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_GREEN = "\x1b[32m"
_CYAN = "\x1b[36m"


# ── States (stored lowercase in communal_objective.state) ───────────────────────
STATE_ACTIVE = "active"
STATE_WON = "won"     # community pushed menace to 0 before the deadline
STATE_LOST = "lost"   # deadline passed (or menace maxed) with the cult still rising

# Menace runs 0..MENACE_MAX. It RISES over time (the cult gathers strength) and
# players push it DOWN with strikes. Routed at <= 0; ascendant at >= MENACE_MAX.
MENACE_MAX = 100
MENACE_START = 35          # the cult is already a visible threat when posted
DEADLINE_HOURS = 48        # a 2-day "weekly rhythm" beat (design: weekly exciting rhythm)

# Escalation: menace gained per real minute while the objective is active. At
# +0.35/min the cult adds ~21 menace/hour ungcontested — a handful of coordinated
# strikes per hour keeps pace, so a small RP community can win without grinding.
MENACE_PER_MINUTE = 0.35

# Anti-spam: a single character may land one counted strike per this window, so
# wins come from the COMMUNITY accumulating contributions, not one person macroing.
STRIKE_COOLDOWN_S = 600    # 10 minutes


# ── The cult roster (invented; CW-clean; Q1-clean; one themed cult per launch world) ──
# `world_key` is informational/flavor; the runtime maps it to a zone for the banner.
@dataclass(frozen=True)
class CultDef:
    key: str
    name: str
    world_key: str          # launch world the uprising centers on
    blurb: str              # one-line "what they are"
    rally_hook: str         # what rallying against them looks like, across playstyles


CULT_ROSTER: tuple[CultDef, ...] = (
    CultDef(
        key="hollow_sun",
        name="the Cult of the Hollow Sun",
        world_key="tatooine",
        blurb="sun-maddened ascetics who preach that the twin suns must be "
              "made to set forever",
        rally_hook="break their desert shrines, cut off their water tithes, and "
                   "turn the moisture farms they prey on",
    ),
    CultDef(
        key="ember_court",
        name="the Ember Court",
        world_key="geonosis",
        blurb="a foundry-cult worshipping the dead fires of abandoned droid forges",
        rally_hook="collapse their forge-tunnels, slice their ignition relays, and "
                   "rally the hive-laborers they conscript",
    ),
    CultDef(
        key="drowned_choir",
        name="the Drowned Choir",
        world_key="nar_shaddaa",
        blurb="an undercity choir that drowns initiates to 'hear the dark below'",
        rally_hook="raid their flooded sub-levels, expose their patrons, and pull "
                   "the desperate back out of the runoff",
    ),
    CultDef(
        key="iron_veil",
        name="the Iron Veil",
        world_key="kuat",
        blurb="orbital saboteurs who veil the shipyards in engineered blackouts",
        rally_hook="restore the cut power, trace their cells through the yards, and "
                   "keep the dock crews calm in the dark",
    ),
    CultDef(
        key="ashen_hand",
        name="the Ashen Hand",
        world_key="coruscant",
        blurb="a deep-level order that recruits among the forgotten of the undercity",
        rally_hook="burn out their warrens, buy back the informants they own, and "
                   "give the level-dwellers somewhere safer to turn",
    ),
)

CULT_BY_KEY: dict[str, CultDef] = {c.key: c for c in CULT_ROSTER}

# AI-flavor key for the idle-Ollama queue (NEVER Haiku) — mirrors dsp_hunter's
# DSP_HUNTER_AI_KEY. Used by the runtime to request optional flavor; deterministic
# fallbacks below mean the objective is fully playable with the AI off.
CULT_AI_KEY = "communal_cult_for"


def cult_for_index(idx: int) -> CultDef:
    """Pick a cult deterministically from an integer (e.g., a rotation counter)."""
    if not CULT_ROSTER:
        raise RuntimeError("CULT_ROSTER is empty")
    return CULT_ROSTER[int(idx) % len(CULT_ROSTER)]


# ── Menace state machine (pure) ─────────────────────────────────────────────────
def clamp_menace(menace: float) -> float:
    """Keep menace inside [0, MENACE_MAX]."""
    return float(max(0.0, min(float(MENACE_MAX), float(menace))))


def advance_menace(menace: float, minutes_elapsed: float) -> float:
    """Escalate the cult over `minutes_elapsed`. Deterministic, clamped."""
    m = float(menace) + (MENACE_PER_MINUTE * max(0.0, float(minutes_elapsed)))
    return clamp_menace(m)


def menace_tier(menace: float) -> str:
    """A coarse threat band for difficulty + flavor selection."""
    m = clamp_menace(menace)
    if m <= 0:
        return "routed"
    if m < 34:
        return "stirring"
    if m < 67:
        return "rising"
    return "ascendant"


def resolve_state(menace: float, now_ms: int, deadline_ms: int) -> str:
    """Return the objective state for the given menace + clock.

    Won the instant menace hits 0 (community routs the cult). Lost if the cult
    reaches full strength (menace >= MENACE_MAX) OR the deadline passes while the
    cult is still active. Otherwise still active.
    """
    m = clamp_menace(menace)
    if m <= 0:
        return STATE_WON
    if m >= MENACE_MAX:
        return STATE_LOST
    if int(now_ms) >= int(deadline_ms):
        return STATE_LOST
    return STATE_ACTIVE


# ── Strikes: open across playstyles ──────────────────────────────────────────────
# Each entry is (skill_name, attribute_fallback). The strike uses the BEST single
# pool the character has among these, so any archetype can meaningfully participate:
#   - brawling / blaster        → soldiers, hunters
#   - investigation / streetwise → slicers, informants, spies
#   - persuasion / con          → faces, entertainers, diplomats
#   - lightsaber / control       → Jedi / Force-users
# Names are matched case-insensitively against the character's skills JSON; the
# attribute is the WEG fallback die-pool when the skill is untrained.
STRIKE_SKILLS: tuple[tuple[str, str], ...] = (
    ("blaster", "dexterity"),
    ("brawling", "strength"),
    ("melee combat", "strength"),
    ("investigation", "perception"),
    ("streetwise", "knowledge"),
    ("persuasion", "perception"),
    ("con", "perception"),
    ("command", "perception"),
    ("lightsaber", "dexterity"),
    ("control", "control"),
)


def best_strike_pool_pips(skills: dict, attributes: dict) -> int:
    """Return the best available strike die-pool, in PIPS (3 pips = 1D).

    `skills` and `attributes` are the character's JSON dicts (skill->code,
    attribute->code), where a code is WEG pip-notation total (e.g. 12 == 4D).
    We look up each STRIKE_SKILL; if the character has the skill we use it, else
    we fall back to the governing attribute. The maximum across all entries is the
    pool the strike rolls. A bare 2D (6 pips) floor means even an untrained civilian
    can chip in.
    """
    skills = skills or {}
    attrs = attributes or {}
    # case-insensitive skill lookup
    lower_skills = {str(k).strip().lower(): v for k, v in skills.items()}
    lower_attrs = {str(k).strip().lower(): v for k, v in attrs.items()}

    best = 6  # 2D floor — anyone can swing
    for skill_name, attr_name in STRIKE_SKILLS:
        val = lower_skills.get(skill_name)
        if val is None:
            val = lower_attrs.get(attr_name)
        try:
            pips = int(val)
        except (TypeError, ValueError):
            continue
        if pips > best:
            best = pips
    return best


def strike_difficulty(menace: float) -> int:
    """Target number for a strike, scaling with the cult's strength.

    Stirring 10 (Easy/Moderate), Rising 13 (Moderate), Ascendant 16 (Difficult).
    A routed cult needs no strikes. Tiered to WEG's standard difficulty ladder.
    """
    tier = menace_tier(menace)
    return {"stirring": 10, "rising": 13, "ascendant": 16, "routed": 0}.get(tier, 13)


def strike_menace_reduction(margin: int) -> float:
    """How much menace a successful strike removes, scaled on the WEG 5-point bands.

    Mirrors the harvest/kyber margin-band pattern. A bare success bites; a clean
    blow bites harder. Failures (margin < 0) remove nothing — caller must gate on
    success first.
    """
    if margin < 0:
        return 0.0
    base = 5.0
    bands = margin // 5          # each full 5-point band adds punch
    return base + (3.0 * bands)  # 5 / 8 / 11 / 14 ...


@dataclass(frozen=True)
class StrikeOutcome:
    success: bool
    margin: int
    menace_before: float
    menace_after: float
    reduction: float


def apply_strike(menace: float, total: int, difficulty: int) -> StrikeOutcome:
    """Resolve a single strike given a pre-rolled `total` (the runtime rolls dice).

    Pure: the caller (runtime) does the dice roll via engine.dice and passes the
    summed total here, so this stays deterministic and unit-testable.
    """
    margin = int(total) - int(difficulty)
    success = margin >= 0
    reduction = strike_menace_reduction(margin) if success else 0.0
    after = clamp_menace(float(menace) - reduction)
    return StrikeOutcome(
        success=success,
        margin=margin,
        menace_before=clamp_menace(menace),
        menace_after=after,
        reduction=reduction,
    )


# ── Rewards (win-only; prestige-domain; no credits) ──────────────────────────────
# Faction-rep paid to the Republic, scaled by each contributor's SHARE of the total
# community effort. A token floor rewards everyone who showed up; the largest
# shareholders earn the most. Capped to stay within adjust_rep's -100..+100 band.
REP_FACTION = "republic"
REP_FLOOR = 3          # everyone who landed at least one counted strike
REP_MAX = 15           # the single largest contributor
# Contributors at/above this share of total effort also earn the commemorative
# III.2 status flag (the "earned status" payoff).
TITLE_SHARE_THRESHOLD = 0.10


def reward_rep_for_share(points: int, total_points: int, won: bool) -> int:
    """Republic-rep delta for a contributor, given their points and the total.

    Win-only. Linear in share between REP_FLOOR and REP_MAX. A loss pays nothing
    (opportunities, never penalties — a loss is simply no reward).
    """
    if not won:
        return 0
    p = max(0, int(points))
    if p <= 0:
        return 0
    total = max(1, int(total_points))
    share = min(1.0, p / total)
    return int(round(REP_FLOOR + (REP_MAX - REP_FLOOR) * share))


def earns_title(points: int, total_points: int, won: bool) -> bool:
    """Whether this contributor earns the commemorative status flag (III.2)."""
    if not won or int(points) <= 0:
        return False
    total = max(1, int(total_points))
    return (int(points) / total) >= TITLE_SHARE_THRESHOLD


# ── Player-facing strings (CW-clean; Q1-clean; deterministic fallbacks) ──────────
def menace_bar(menace: float, width: int = 20) -> str:
    """A colored ASCII menace meter for the +rally board."""
    m = clamp_menace(menace)
    filled = int(round((m / MENACE_MAX) * width))
    filled = max(0, min(width, filled))
    tier = menace_tier(m)
    color = {
        "routed": _GREEN,
        "stirring": _YELLOW,
        "rising": _YELLOW,
        "ascendant": _RED,
    }.get(tier, _YELLOW)
    bar = "#" * filled + "-" * (width - filled)
    return f"{color}[{bar}]{_RESET} {int(m)}/{MENACE_MAX} {_DIM}({tier}){_RESET}"


def time_left_line(deadline_at_ms, now_ms) -> str:
    """How long until the uprising's deadline, for the rally board."""
    remaining = int(deadline_at_ms) - int(now_ms)
    if remaining <= 0:
        return f"{_DIM}The deadline has passed.{_RESET}"
    hours = remaining // 3_600_000
    mins = (remaining % 3_600_000) // 60_000
    span = f"~{hours}h {mins}m" if hours > 0 else f"~{mins}m"
    return f"{_DIM}Time left to rout them: {span}.{_RESET}"


def viewer_contribution_line(contributions, char_id, now_ms) -> str:
    """The viewer's own stake + strike-cooldown status. Empty string if the
    viewer hasn't landed a counted strike yet (so the board stays clean for
    onlookers)."""
    rec = (contributions or {}).get(str(int(char_id))) or {}
    pts = int(rec.get("points") or 0)
    last = float(rec.get("last_strike_at") or 0)
    if pts <= 0 and last <= 0:
        return ""
    ready, secs_left = True, 0
    if last > 0:
        elapsed = int(now_ms) - int(last)
        if elapsed < STRIKE_COOLDOWN_S * 1000:
            ready, secs_left = False, (STRIKE_COOLDOWN_S * 1000 - elapsed) // 1000
    cd = (f"{_GREEN}ready{_RESET}" if ready
          else f"{_DIM}~{max(1, secs_left // 60)}m{_RESET}")
    return (f"{_CYAN}Your effort:{_RESET} {pts} menace pushed back. "
            f"Next strike: {cd}.")


def posted_broadcast(cult: CultDef, zone_label: str) -> str:
    """The galaxy-wide alert when the Director posts the uprising."""
    return (
        f"{_RED}{_BOLD}A dark tide is rising.{_RESET} {_BOLD}{cult.name}{_RESET} — "
        f"{cult.blurb} — has surfaced around {_CYAN}{zone_label}{_RESET}. "
        f"The call goes out to {cult.rally_hook}. "
        f"{_DIM}Type 'rally' to join the effort.{_RESET}"
    )


def escalation_broadcast(cult: CultDef, menace: float) -> str:
    """A periodic 'it's getting worse' nudge while the cult is rising uncontested."""
    return (
        f"{_YELLOW}{cult.name} grows bolder.{_RESET} Their influence spreads "
        f"({menace_tier(menace)}). {_DIM}Type 'rally' to push back.{_RESET}"
    )


def strike_success_line(cult: CultDef, outcome: "StrikeOutcome") -> str:
    """Personal feedback after a successful strike."""
    return (
        f"{_GREEN}You strike a blow against {cult.name}.{_RESET} "
        f"Their grip weakens (-{int(round(outcome.reduction))} menace)."
    )


def strike_fail_line(cult: CultDef) -> str:
    """Personal feedback after a failed strike."""
    return (
        f"{_RED}Your move against {cult.name} falls short.{_RESET} "
        f"{_DIM}Regroup and try again.{_RESET}"
    )


def strike_cooldown_line(seconds_left: int) -> str:
    mins = max(1, int(seconds_left) // 60)
    return (
        f"{_DIM}You've just made your move — you need to regroup. "
        f"Try again in ~{mins} min.{_RESET}"
    )


def won_broadcast(cult: CultDef, zone_label: str) -> str:
    """Galaxy-wide victory announcement."""
    return (
        f"{_GREEN}{_BOLD}The tide turns.{_RESET} Through a shared effort, "
        f"{_BOLD}{cult.name}{_RESET} has been broken and scattered from "
        f"{_CYAN}{zone_label}{_RESET}. Those who answered the call are remembered."
    )


def lost_broadcast(cult: CultDef, zone_label: str) -> str:
    """Galaxy-wide loss announcement — flavor only, no penalty."""
    return (
        f"{_RED}{cult.name} entrenches around {_CYAN}{zone_label}{_RESET}.{_RESET} "
        f"The moment to rout them has passed; they fade into the shadows to "
        f"gather again another day."
    )


def fallback_flavor(cult: CultDef, menace: float) -> str:
    """Deterministic flavor when the idle-Ollama queue returns nothing (AI off)."""
    return f"{_DIM}{cult.name} stirs in the dark. ({menace_tier(menace)}){_RESET}"
