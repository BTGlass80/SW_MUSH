"""Guard: Guide_24 §5 documents the WILDERNESS-anomaly player loop
(`anomalies` / `investigate <id>` -> skill / combat / skill-gate phases),
and its facts match HEAD.

Guide_24 §4 "Space Anomalies" covers the *space* scan/deepscan/salvage loop.
The *wilderness* anomaly system (`engine/wilderness_anomalies.py`, the bare
`investigate <id>` verb) was documented NOWHERE — yet Guides #22 and #26 both
cross-reference "Guide #24" as its home, and the T3.23 party skill-challenge
drop (2026-06-26, `4c785fd`) wired live skill-gate phases that `investigate`
now renders. v1.0 -> v1.1 adds §5 Wilderness Anomalies.

This re-verify pins the new §5 prose + the §10/§11 table rows against the live
engine constants and the parser command surface — the tier lifetimes, the
skill-check DC, the skill-gate retry cooldown, the influence deltas, and the
two command keys — so an engine retune or a guide drift fails loudly here
instead of silently misleading players. It also keeps the §4-vs-§5
disambiguation honest (space anomalies are NOT engaged via `investigate`).
"""
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_24_Encounters_Hazards.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


# ── The new section exists and is reachable in the structure ──────────────────
class TestWildernessSectionPresent:
    def test_section_5_is_wilderness_anomalies(self, guide_text):
        assert "## 5. Wilderness Anomalies" in guide_text

    def test_space_section_was_disambiguated(self, guide_text):
        # §4 renamed so the two anomaly systems don't collide in the reader's head.
        assert "## 4. Space Anomalies" in guide_text

    def test_section_numbers_sequential_no_gaps(self, guide_text):
        nums = [int(m) for m in re.findall(r"^## (\d+)\. ", guide_text, re.M)]
        assert nums == list(range(1, len(nums) + 1)), (
            f"Section numbers not sequential: {nums}"
        )

    def test_version_bumped(self, guide_text):
        assert "Guide Version 1.1" in guide_text


# ── The bare `investigate` verb is taught as the WILDERNESS verb ───────────────
class TestInvestigateIsWildernessVerb:
    def test_documents_the_two_commands(self, guide_text):
        assert "`investigate <id>`" in guide_text
        assert "`anomalies`" in guide_text
        # the alias is taught
        assert "`anom`" in guide_text

    def test_does_not_reintroduce_the_space_phantom(self, guide_text):
        # The sibling authoritative suite forbids this string (space anomalies
        # are NOT engaged via investigate). Keep it absent in the new section too.
        assert "investigate <anomaly_id>" not in guide_text

    def test_teaches_the_three_way_investigate_disambiguation(self, guide_text):
        # search (room) vs respond investigate (encounter) vs investigate <id>
        # (wilderness) — the confusion Guide_22 also warns about.
        assert "respond investigate" in guide_text
        assert "`search`" in guide_text


# ── Numbers match the live engine constants ───────────────────────────────────
class TestNumbersMatchEngine:
    def test_skill_anomaly_dc(self, guide_text):
        from engine.wilderness_anomalies import TIER1_RESOLUTION_DC
        assert TIER1_RESOLUTION_DC == 13
        assert "13" in guide_text  # quoted in §5 + the numbers table

    def test_tier_lifetimes(self, guide_text):
        from engine.wilderness_anomalies import (
            TIER1_DURATION_SECS, TIER2_DURATION_SECS, TIER3_DURATION_SECS,
        )
        assert TIER1_DURATION_SECS == 30 * 60
        assert TIER2_DURATION_SECS == 2 * 60 * 60
        assert TIER3_DURATION_SECS == 8 * 60 * 60
        # prose: ~30 minutes / ~2 hours / ~8 hours
        assert "30 min" in guide_text
        assert "2 hr" in guide_text or "2 hours" in guide_text
        assert "8 hr" in guide_text or "8 hours" in guide_text

    def test_influence_deltas(self, guide_text):
        from engine.wilderness_anomalies import (
            TIER1_INFLUENCE_DELTA, TIER2_INFLUENCE_DELTA, TIER3_INFLUENCE_DELTA,
        )
        assert (TIER1_INFLUENCE_DELTA, TIER2_INFLUENCE_DELTA,
                TIER3_INFLUENCE_DELTA) == (5, 20, 50)
        assert "+5 / +20 / +50" in guide_text

    def test_skill_gate_retry_cooldown(self, guide_text):
        from engine.wilderness_anomalies import SKILL_GATE_RETRY_COOLDOWN_SECS
        assert SKILL_GATE_RETRY_COOLDOWN_SECS == 12
        assert "12-second" in guide_text or "12 seconds" in guide_text


# ── The party-challenge mechanics the prose promises actually exist ───────────
class TestSkillGateBackingExists:
    def test_resolver_and_constants_live(self):
        import engine.wilderness_anomalies as wa
        # T3.23 skill-gate resolver + solo-engagement helper are wired.
        assert hasattr(wa, "_resolve_skill_gate_phase")
        assert hasattr(wa, "_is_solo_engagement")

    def test_participation_union_field_exists(self):
        # The reward is split across the union of combat killers + skill-gate
        # clearers; the clearers are tracked in contribution_log.
        import dataclasses
        from engine.wilderness_anomalies import WildernessAnomaly
        names = {f.name for f in dataclasses.fields(WildernessAnomaly)}
        assert "contribution_log" in names
        assert "kill_counts" in names

    def test_solo_penalty_and_retry_referenced_in_resolver(self):
        import inspect
        import engine.wilderness_anomalies as wa
        src = inspect.getsource(wa._resolve_skill_gate_phase)
        assert "solo_penalty" in src
        assert "SKILL_GATE_RETRY_COOLDOWN_SECS" in src
        assert "contribution_log" in src

    def test_guide_teaches_skill_gate_party_loop(self, guide_text):
        assert "skill-gate" in guide_text.lower()
        assert "solo penalty" in guide_text.lower()
        # participation-scaled reward is the load-bearing promise
        assert "participation-scaled" in guide_text


# ── The two commands the guide names are really registered verbs ──────────────
class TestCommandSurfaceLive:
    def test_anomalies_and_investigate_commands_exist(self):
        from parser.anomaly_commands import (
            AnomaliesCommand, InvestigateCommand,
        )
        assert AnomaliesCommand.key == "anomalies"
        assert "anom" in AnomaliesCommand.aliases
        assert InvestigateCommand.key == "investigate"
        assert InvestigateCommand.usage == "investigate <id>"


# ── Era cleanness (mirror of the sibling authoritative suite) ─────────────────
_ERA_RE = [re.compile(p) for p in (
    r"\bImperial(?! Sourcebook)\b",
    r"\bGalactic Empire\b",
    r"\bRebel Alliance\b",
    r"\bGalactic Civil War\b",
    r"\bGCW\b",
)]


def test_era_clean(guide_text):
    viols = []
    for i, line in enumerate(guide_text.split("\n"), start=1):
        for pat in _ERA_RE:
            if pat.search(line):
                viols.append((i, line.strip()))
    assert not viols, "Guide_24 era violations:\n" + "\n".join(
        f"  line {n}: {t!r}" for n, t in viols
    )
