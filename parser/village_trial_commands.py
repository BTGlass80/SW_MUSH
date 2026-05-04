# -*- coding: utf-8 -*-
"""
parser/village_trial_commands.py — Player commands for Village Trials
                                    + Step 10 Path choice.

F.7.c.1 shipped:
  - `trial skill` — initiate / continue Trial 1 (Skill) at the Forge
    with Smith Daro.
  - `examine fragment_<N>` — listen to a holocron fragment in the
    Trial of Insight (Council Hut). Player-facing; coexists with the
    builder `@examine`.
  - `accuse fragment_<N>` — commit the answer in the Trial of Insight.

F.7.c.2 added:
  - `trial courage` — initiate Trial 2 (Courage) with Elder Mira
    Delen at the Common Square. Mira recites a buried memory; the
    player commits with `trial courage 1|2|3`.
  - `trial courage 1` — "I won't deny it." (pass)
  - `trial courage 2` — "How did you know?" (pass + nod)
  - `trial courage 3` — walk away (fail; 24h cooldown)

F.7.c.3 added:
  - `trial flesh` — show progress on Trial 3 (Flesh). The trial
    starts automatically when the player enters the Meditation Caves
    with Courage done. `trial flesh` reports elapsed/remaining time
    and triggers the completion check if 6 hours have passed.

F.7.c.4 added:
  - `trial spirit` — initiate Trial 4 (Spirit) in the Sealed Sanctum
    (must be in the Sanctum room).
  - `trial spirit 1|2|3` — commit a response: 1=reject, 2=ambivalent,
    3=yield. 4 rejections = pass; 3 yields = Path C lock-in.

F.7.d (this revision) adds:
  - `path` — show the Step 10 menu (which roads are open). Available
    after the Trial of Insight is complete; presented in Master
    Yarael's Master's Chamber.
  - `path a` — commit Path A (Jedi Order; convoy to Coruscant Temple)
  - `path b` — commit Path B (Independent; stay with the Village)
  - `path c` — commit Path C (Dark whispers; only if Spirit locked
    Path C)

F.7.i (this revision) adds:
  - `+village` — show your current Village standing, courage choice,
    and chosen path. Available at any time. Non-Village players
    (no audience) see a brief "you have not been to the Village"
    message rather than a 0-everywhere status panel.

Note on `trial insight`: the Trial of Insight begins via talk-to-Saro,
which presents the fragments. The `examine` and `accuse` commands
then drive the trial. There is no `trial insight` command — talking
to Saro is the entry. (`trial skill`, `trial courage`, `trial flesh`,
and `trial spirit` exist because their NPC hooks only *brief*; the
player has to actively engage.)
"""
from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


class TrialCommand(BaseCommand):
    """Initiate a Village Trial attempt.

    F.7.c.3 supports:
      `trial skill`           — Trial 1 (Skill) at the Forge with Smith Daro.
      `trial courage`         — Trial 2 (Courage) at Common Square; presents
                                Mira's recital and the three response options.
      `trial courage 1|2|3`   — commits a response to the Courage trial.
      `trial flesh`           — Trial 3 (Flesh) progress report. The trial
                                starts automatically when entering the
                                Meditation Caves; `trial flesh` shows
                                elapsed/remaining time and completes the
                                trial when 6 hours have passed.

    Future drops will add:
      `trial spirit`  — with Master Yarael in Sealed Sanctum
      (No `trial insight` — Insight is driven by examine/accuse.)
    """
    key = "trial"
    aliases = []
    help_text = (
        "Initiate or continue a Village Trial.\n\n"
        "AVAILABLE TRIALS (F.7.c.4 — all five live):\n"
        "  trial skill           -- Smith Daro at the Forge (Trial 1)\n"
        "  trial courage         -- Elder Mira at the Common Square (Trial 2);\n"
        "                           presents the recital + 3 response options\n"
        "  trial courage 1       -- \"I won't deny it.\"  (pass)\n"
        "  trial courage 2       -- \"How did you know?\" (pass)\n"
        "  trial courage 3       -- Walk away.            (fail; 24h cooldown)\n"
        "  trial flesh           -- Trial 3 progress report. (Trial starts\n"
        "                           automatically when entering the Meditation\n"
        "                           Caves; 6 hours wall-clock to complete.)\n"
        "  trial spirit          -- Trial 4: Master Yarael in the Sealed\n"
        "                           Sanctum. Initiate or re-show the current\n"
        "                           turn's prompt.\n"
        "  trial spirit 1        -- Reject the dark-future-self.\n"
        "  trial spirit 2        -- Stay silent in the heart.\n"
        "  trial spirit 3        -- Yield (3 yields = Path C lock).\n\n"
        "(Trial of Insight is driven by 'examine fragment_<N>' and\n"
        "'accuse fragment_<N>' — talk to Saro at the Council Hut.)"
    )
    usage = "trial <skill|courage|flesh|spirit> [1|2|3]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        raw = (ctx.args or "").strip()
        if not raw:
            await ctx.session.send_line(
                "  Usage: trial <skill|courage> [1|2|3]. "
                "(Type 'help trial' for available trials.)"
            )
            return

        parts = raw.split(None, 1)
        which = parts[0].lower()
        sub = parts[1].strip() if len(parts) > 1 else ""

        if which == "skill":
            try:
                from engine.village_trials import attempt_skill_trial
                await attempt_skill_trial(ctx.session, ctx.db, char)
            except Exception:
                log.warning("attempt_skill_trial failed", exc_info=True)
                await ctx.session.send_line(
                    "  Something went wrong with the trial. Try again in a moment."
                )
            return

        if which == "courage":
            # Optional choice arg: parse 1|2|3 or accept None (which
            # initiates the recital).
            choice = None
            if sub:
                if sub.isdigit():
                    choice = int(sub)
                else:
                    await ctx.session.send_line(
                        "  Usage: trial courage [1|2|3]. The number is your "
                        "response. Without a number, Mira reads the recital."
                    )
                    return
            try:
                from engine.village_trials import attempt_courage_trial
                await attempt_courage_trial(ctx.session, ctx.db, char, choice=choice)
            except Exception:
                log.warning("attempt_courage_trial failed", exc_info=True)
                await ctx.session.send_line(
                    "  Something went wrong with the trial. Try again in a moment."
                )
            return

        if which == "flesh":
            try:
                from engine.village_trials import attempt_flesh_trial
                await attempt_flesh_trial(ctx.session, ctx.db, char)
            except Exception:
                log.warning("attempt_flesh_trial failed", exc_info=True)
                await ctx.session.send_line(
                    "  Something went wrong with the trial. Try again in a moment."
                )
            return

        if which == "spirit":
            # Optional choice arg: 1 (reject), 2 (ambivalent), 3 (yield).
            # No arg = initiate or re-emit current turn prompt.
            choice = None
            if sub:
                if sub.isdigit():
                    choice = int(sub)
                else:
                    await ctx.session.send_line(
                        "  Usage: trial spirit [1|2|3]. The number is your "
                        "response (1=reject / 2=silent / 3=yield). Without "
                        "a number, the figure speaks the current turn."
                    )
                    return
            try:
                from engine.village_trials import attempt_spirit_trial
                await attempt_spirit_trial(ctx.session, ctx.db, char, choice=choice)
            except Exception:
                log.warning("attempt_spirit_trial failed", exc_info=True)
                await ctx.session.send_line(
                    "  Something went wrong with the trial. Try again in a moment."
                )
            return

        if which == "insight":
            await ctx.session.send_line(
                "  The Trial of Insight is driven by 'examine fragment_<N>' "
                "and 'accuse fragment_<N>'. Speak to Elder Saro Veck at the "
                "Council Hut to begin."
            )
            return

        await ctx.session.send_line(
            f"  '{which}' is not a recognized trial. "
            f"Available: skill, courage, flesh, spirit."
        )


class ExamineCommand(BaseCommand):
    """Examine a holocron fragment (Trial of Insight).

    NOTE: this is the player-facing `examine`, distinct from the
    builder `@examine` (in parser/building_commands.py). For F.7.c.1
    its only effect is to play holocron fragments; future drops may
    extend it for other look-at-thing semantics.

    Falls through silently for non-fragment args, so it doesn't
    interfere with future extensions.
    """
    key = "examine"
    aliases = ["listen"]
    help_text = (
        "Examine an object in detail.\n\n"
        "TRIAL OF INSIGHT (F.7.c.1):\n"
        "  examine fragment_1   -- listen to holocron fragment 1\n"
        "  examine fragment_2\n"
        "  examine fragment_3\n"
        "(Council Hut, after speaking with Elder Saro Veck.)"
    )
    usage = "examine <fragment_N | thing>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        arg = (ctx.args or "").strip()
        if not arg:
            await ctx.session.send_line(
                "  Examine what? Try 'examine fragment_1' for example."
            )
            return

        # Try the fragment runtime
        try:
            from engine.village_trials import examine_insight_fragment
            handled = await examine_insight_fragment(ctx.session, ctx.db, char, arg)
            if handled:
                return
        except Exception:
            log.debug("examine_insight_fragment failed", exc_info=True)

        # Fall-through: nothing else handles `examine` yet
        await ctx.session.send_line(
            f"  You see nothing special about '{arg}'."
        )


class AccuseCommand(BaseCommand):
    """Accuse a fragment in the Trial of Insight."""
    key = "accuse"
    aliases = []
    help_text = (
        "Commit your answer in the Trial of Insight.\n\n"
        "USAGE:\n"
        "  accuse fragment_1   -- accuse fragment 1 of being the Sith\n"
        "  accuse fragment_2\n"
        "  accuse fragment_3\n"
        "(Council Hut. Wrong answers permit retries.)"
    )
    usage = "accuse <fragment_N>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        arg = (ctx.args or "").strip()
        if not arg:
            await ctx.session.send_line(
                "  Usage: accuse fragment_1 (or 2 / 3)."
            )
            return

        try:
            from engine.village_trials import accuse_insight_fragment
            await accuse_insight_fragment(ctx.session, ctx.db, char, arg)
        except Exception:
            log.warning("accuse_insight_fragment failed", exc_info=True)
            await ctx.session.send_line(
                "  Something went wrong with the accusation. Try again."
            )


def register_village_trial_commands(registry):
    """Register Village trial + Path + Standing commands."""
    cmds = [
        TrialCommand(),
        ExamineCommand(),
        AccuseCommand(),
        PathCommand(),
        VillageStandingCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)


class PathCommand(BaseCommand):
    """Path A/B/C commit (Village quest Step 10).

    `path` shows the menu. `path a|b|c` commits the path. The choice
    is irreversible. Only available after the Trial of Insight is
    complete.
    """
    key = "path"
    aliases = []
    help_text = (
        "Commit to one of the Village quest paths (Step 10).\n\n"
        "  path           -- show the Path menu (which roads are open).\n"
        "                    Available after all five trials are done.\n"
        "  path a         -- Report to the Jedi Order. Convoy to Coruscant\n"
        "                    Temple; Master Mace Windu receives you.\n"
        "  path b         -- Stay with the Village. Independent path; the\n"
        "                    Force is yours, the Order has no claim.\n"
        "  path c         -- Dark whispers. (Only available if the Spirit\n"
        "                    trial locked Path C.)\n\n"
        "The choice is final. Once committed, the road is set."
    )
    usage = "path [a|b|c]"

    async def execute(self, ctx):
        char = ctx.session.character
        if not char:
            return

        sub = (ctx.args or "").strip().lower()
        # Accept either 'path a' or just the letter as an arg shape.
        if sub in ("a", "b", "c"):
            chosen = sub
        elif not sub:
            chosen = None
        else:
            await ctx.session.send_line(
                "  Usage: path [a|b|c]. Use 'path' (no argument) to see "
                "the menu."
            )
            return

        try:
            from engine.village_choice import attempt_choose_path
            await attempt_choose_path(ctx.session, ctx.db, char, path=chosen)
        except Exception:
            log.warning("attempt_choose_path failed", exc_info=True)
            await ctx.session.send_line(
                "  Something went wrong with the Path choice. Try again."
            )


# ═══════════════════════════════════════════════════════════════════════════
# F.7.i — `+village` standing lookup
# ═══════════════════════════════════════════════════════════════════════════


# Tier thresholds for Village standing. Match the dialogue thresholds
# used by F.7.h consumers so the player-visible label corresponds to
# what NPCs actually do:
#
#   0       Stranger    — pre-Village
#   1-3     Welcomed    — entered, post-audience
#   4-7     Recognized  — through Skill/Courage/Flesh
#   8-11    Trusted     — Mira's high-standing ack threshold (F.7.h)
#   12+     Honored     — Yarael's Path A/B addendum threshold (F.7.h);
#                         max-from-quest is 12
#
# Tuple of (lower_inclusive, label). Sorted ascending; the highest
# matching tier wins.
_VILLAGE_STANDING_TIERS = (
    (0,  "Stranger"),
    (1,  "Welcomed"),
    (4,  "Recognized"),
    (8,  "Trusted"),
    (12, "Honored"),
)


def _tier_for_standing(value: int) -> str:
    """Return the descriptive tier label for a numeric standing."""
    label = _VILLAGE_STANDING_TIERS[0][1]
    for threshold, name in _VILLAGE_STANDING_TIERS:
        if value >= threshold:
            label = name
        else:
            break
    return label


def _format_courage_choice(flag_value) -> str:
    """Render the village_courage_choice flag as a player-readable line."""
    if flag_value == "deny":
        return "I won't deny it."
    if flag_value == "ask":
        return "How did you know? (Mira: 'still listening')"
    return ""


def _format_chosen_path(path_value: str) -> str:
    """Render the village_chosen_path code as a player-readable line."""
    if path_value == "a":
        return "A — Reported to the Jedi Order."
    if path_value == "b":
        return "B — Stayed with the Village (Independent)."
    if path_value == "c":
        return "C — Dark whispers."
    return ""


class VillageStandingCommand(BaseCommand):
    """`+village` — show Village quest standing and progress.

    Reads `village_standing` (F.7.f), the courage choice flag (F.7.h),
    and the chosen path (F.7.d) and renders a one-screen summary.

    Players who have not yet had the audience with Master Yarael see
    a brief "you have not yet been to the Village" message rather
    than a 0-everywhere status panel — the command is a Village
    progress report, not a chargen sheet.
    """
    key = "+village"
    aliases = ["+vil"]
    help_text = (
        "Show your Village quest standing and progress.\n"
        "\n"
        "Displays:\n"
        "  - Current village_standing value (0-12+) and tier label\n"
        "  - Trial completion status (each of the 5 trials)\n"
        "  - Courage choice (if you've taken the trial)\n"
        "  - Chosen path (if you've committed at Step 10)\n"
        "\n"
        "Players who have not yet visited the Village see a brief\n"
        "placeholder line — there is no Village progress to show."
    )
    usage = "+village"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        # Has-audience gate: don't render the panel for chars who
        # haven't been to the Village yet (cleaner than showing all
        # zeroes / "not done" for every line).
        try:
            from engine.village_trials import has_completed_audience
            in_village = has_completed_audience(char)
        except Exception:
            in_village = False

        if not in_village:
            await ctx.session.send_line(
                "  You have not yet been to the Village. Find the "
                "Hermit; he will give you the invitation."
            )
            return

        # Pull numeric standing
        try:
            from engine.village_standing import (
                get_village_standing, STANDING_MAX_FROM_QUEST,
            )
            standing = get_village_standing(char)
            max_from_quest = STANDING_MAX_FROM_QUEST
        except Exception:
            log.warning("+village: standing read failed", exc_info=True)
            standing = 0
            max_from_quest = 12  # reasonable fallback

        tier = _tier_for_standing(standing)

        # Trial-done flags read directly off the columns
        skill = bool(int(char.get("village_trial_skill_done") or 0))
        courage = bool(int(char.get("village_trial_courage_done") or 0))
        flesh = bool(int(char.get("village_trial_flesh_done") or 0))
        spirit = bool(int(char.get("village_trial_spirit_done") or 0))
        path_c_locked = bool(int(
            char.get("village_trial_spirit_path_c_locked") or 0
        ))
        insight = bool(int(char.get("village_trial_insight_done") or 0))

        # Courage choice + chosen path read out of chargen_notes
        courage_flag = ""
        path_code = (char.get("village_chosen_path") or "").strip().lower()
        try:
            import json as _j
            raw = char.get("chargen_notes") or "{}"
            if isinstance(raw, str):
                notes = _j.loads(raw)
            elif isinstance(raw, dict):
                notes = dict(raw)
            else:
                notes = {}
            if isinstance(notes, dict):
                courage_flag = notes.get("village_courage_choice") or ""
        except Exception:
            # Malformed chargen_notes JSON — fail soft (no courage
            # flag, panel renders without the choice annotation).
            # Logged at debug because this is expected for chars
            # who haven't reached the Courage trial yet (notes may
            # not have the key) and is non-fatal in any case. F.7.j
            # follow-up: bare `pass` violated the project-wide
            # `test_no_silent_except_pass_in_production` invariant
            # (test_session38.py).
            log.debug(
                "+village: chargen_notes parse failed (non-fatal)",
                exc_info=True,
            )

        # ── Render ──────────────────────────────────────────────────
        out = []
        out.append("")
        out.append(
            "  \033[1;33m─── The Village ───\033[0m"
        )
        out.append("")
        out.append(
            f"  \033[1m  Standing: {standing}/{max_from_quest}\033[0m  "
            f"\033[2m({tier})\033[0m"
        )
        out.append("")
        out.append("  \033[1m  Trials:\033[0m")
        out.append(
            f"    {self._tick(skill)}  Skill (Smith Daro at the Forge)"
        )

        # Courage line — show the choice flag inline if present.
        if courage:
            choice_str = _format_courage_choice(courage_flag)
            if choice_str:
                out.append(
                    f"    {self._tick(True)}  Courage (Elder Mira): "
                    f"\033[2m{choice_str}\033[0m"
                )
            else:
                out.append(
                    f"    {self._tick(True)}  Courage (Elder Mira)"
                )
        else:
            out.append(
                f"    {self._tick(False)}  Courage (Elder Mira)"
            )

        out.append(
            f"    {self._tick(flesh)}  Flesh (Elder Korvas)"
        )

        # Spirit line — flag Path C lock-in if it happened.
        if spirit:
            if path_c_locked:
                out.append(
                    f"    {self._tick(True)}  Spirit (Yarael): "
                    f"\033[1;31mPath C lock-in\033[0m"
                )
            else:
                out.append(
                    f"    {self._tick(True)}  Spirit (Yarael)"
                )
        else:
            out.append(
                f"    {self._tick(False)}  Spirit (Yarael)"
            )

        out.append(
            f"    {self._tick(insight)}  Insight (Elder Saro)"
        )

        # Path line — present only if committed.
        if path_code:
            path_str = _format_chosen_path(path_code)
            out.append("")
            out.append(
                f"  \033[1m  Path: {path_str}\033[0m"
            )

        out.append("")
        for line in out:
            await ctx.session.send_line(line)

    @staticmethod
    def _tick(done: bool) -> str:
        """Render a one-character status indicator."""
        if done:
            return "\033[1;32m✓\033[0m"
        return "\033[2m·\033[0m"
