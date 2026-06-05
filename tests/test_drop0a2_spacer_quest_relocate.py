"""
tests/test_drop0a2_spacer_quest_relocate.py — Drop 0a-2 (2026-06-02)

Pins the "From Dust to Stars" starter-quest era relocation that finishes
Drop 0a (un-break the dead-ends) from
sw_mush_remediation_and_fun_additions_design_v1.md.

The 06-01 era migration deleted Kessel and Corellia from the Clone Wars
graph, but the FDtS quest still routed through them:
  - step 7/13/26  Mak Torvin "at Docking Bay 94" — but he was seeded on
                  Nar Shaddaa, dead-ending step 7 in Phase 1.
  - step 20       "land on Kessel/Corellia" — dead planets.
  - step 24       Venn Kator "on Corellia" — misdirecting text (he is in
                  fact already at Docking Bay 94 via the base roster).
  - step 26/27    Lira Shan "on Corellia/Coronet" — Lira was reserved but
                  never seeded, so the ship-purchase climax was
                  uncompletable.

Resolution (from_dust_to_stars_design_v2_clone_wars.md §0/§"Step 27"):
Kessel→Kuat, Corellia→Coruscant, Lira→Kuat (KDY broker). Mak moved to
Docking Bay 94 (Tatooine). Venn stays where he already was.

These are structural pins (no DB / server harness needed): they read
QUEST_STEPS and the relevant YAML files directly.
"""

import os
import unittest
from pathlib import Path

import yaml

# Repo root = parent of tests/
ROOT = Path(__file__).resolve().parents[1]

from engine.spacer_quest import QUEST_STEPS, get_step  # noqa: E402


# Active CW roster per FDtS v2 §0 (the only planets the quest may reference).
ACTIVE_PLANETS = {"tatooine", "nar_shaddaa", "kuat", "coruscant"}
# Planets the 06-01 migration deleted — must not appear in quest geography.
DEAD_PLANETS = ("kessel", "corellia", "coronet")


def _step_strings(step: dict) -> str:
    """Concatenate the player-visible geography text of a quest step."""
    parts = [
        str(step.get("objective_desc", "")),
        str(step.get("briefing", "")),
        str(step.get("completion_text", "")),
        str(step.get("hint", "")),
    ]
    od = step.get("objective_data", {}) or {}
    parts.append(" ".join(str(p) for p in od.get("planets", [])))
    parts.append(str(od.get("room_substr", "")))
    parts.append(str(od.get("npc", "")))
    return " ".join(parts).lower()


class TestSpacerQuestGeographyMigrated(unittest.TestCase):
    """No dead-planet (Kessel/Corellia/Coronet) geography survives in any
    quest step. The Nar Shaddaa 'Corellian Sector' district is the one
    legitimate 'corellia*' token and is explicitly allowed."""

    def test_no_dead_planet_references(self):
        for step in QUEST_STEPS:
            text = _step_strings(step)
            # The only legitimate 'corellia*' token is the Nar Shaddaa
            # district "Corellian Sector"; strip it before the assertion.
            text = text.replace("corellian sector", "")
            for dead in DEAD_PLANETS:
                self.assertNotIn(
                    dead, text,
                    f"step {step.get('step_id')} still references dead "
                    f"location '{dead}': {text!r}")

    def test_corellian_sector_district_preserved(self):
        """Sanity: the legitimate district reference is still there
        (we removed the planet, not the Nar Shaddaa neighborhood)."""
        all_text = " ".join(_step_strings(s) for s in QUEST_STEPS)
        self.assertIn("corellian sector", all_text,
                      "Zekka's 'Corellian Sector' (a Nar Shaddaa district) "
                      "should be preserved")


class TestGrandTourRoster(unittest.TestCase):
    """Step 20 'The Grand Tour' visits exactly the 4 active CW planets."""

    def test_step20_planets(self):
        step = get_step(20)
        self.assertIsNotNone(step)
        planets = set(step["objective_data"]["planets"])
        self.assertEqual(
            planets, ACTIVE_PLANETS,
            f"step 20 should visit {sorted(ACTIVE_PLANETS)}, got "
            f"{sorted(planets)}")
        self.assertEqual(step["objective_data"]["target"], 4)


class TestShipPurchaseClimaxPointsToKuat(unittest.TestCase):
    """Step 27 (the ship-purchase climax) must gate on Lira in a Kuat
    Drive Yards room — the location where Lira is now seeded."""

    def test_step27_room_and_npc(self):
        step = get_step(27)
        self.assertIsNotNone(step)
        self.assertEqual(step["objective_type"], "talk_with_credits")
        od = step["objective_data"]
        self.assertEqual(od["npc"], "lira")
        self.assertEqual(od["room_substr"], "Kuat Drive Yards")
        self.assertEqual(od["cost"], 8000)


class TestLiraShanSeededOnKuat(unittest.TestCase):
    """The new Drop 0a-2 NPC file seeds Lira Shan in the exact Kuat room
    that step 27's room_substr matches."""

    LIRA_FILE = ROOT / "data/worlds/clone_wars/npcs_drop_0a2_fdts_relocate.yaml"
    LIRA_ROOM = "Kuat Drive Yards - Commercial Zone"

    def test_file_exists_and_parses(self):
        self.assertTrue(self.LIRA_FILE.exists(),
                        f"missing {self.LIRA_FILE}")
        with open(self.LIRA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("npcs", data)

    def test_lira_present_in_kuat_room(self):
        with open(self.LIRA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        lira = next((n for n in data["npcs"]
                     if n.get("name") == "Lira Shan"), None)
        self.assertIsNotNone(lira, "Lira Shan must be seeded in the 0a-2 file")
        self.assertEqual(lira["room"], self.LIRA_ROOM)

    def test_lira_room_matches_step27_substr(self):
        """The seed room must satisfy step 27's room_substr gate."""
        with open(self.LIRA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        lira = next(n for n in data["npcs"] if n.get("name") == "Lira Shan")
        substr = get_step(27)["objective_data"]["room_substr"]
        self.assertIn(substr.lower(), lira["room"].lower())

    def test_lira_no_corellia_residue(self):
        """Lira's CW re-grounding should not mention Corellia/Coronet as her
        location in her *data* (room/description/dialogue). The file's header
        comment legitimately documents the old location, so we check only the
        parsed NPC entry, not the raw text."""
        with open(self.LIRA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        lira = next(n for n in data["npcs"] if n.get("name") == "Lira Shan")
        # Flatten Lira's string-valued data fields.
        import json as _json
        text = _json.dumps(lira).lower()
        self.assertNotIn("coronet", text)
        # 'corellia' as a place; the adjective 'corellian' is not used here.
        self.assertNotIn("corellia", text.replace("corellian", ""))


class TestMakTorvinRelocatedToTatooine(unittest.TestCase):
    """Mak Torvin must live at Docking Bay 94 (Tatooine) — where the quest
    code (steps 7/13/26) and his own ship expect him — not Nar Shaddaa."""

    G1_FILE = ROOT / "data/worlds/clone_wars/npcs_drop_g1_nar_shaddaa_topside.yaml"
    MAK_ROOM = "Docking Bay 94 - Pit Floor"

    def _mak(self):
        with open(self.G1_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return next((n for n in data["npcs"]
                     if n.get("name") == "Mak Torvin"), None)

    def test_mak_present_and_on_tatooine(self):
        mak = self._mak()
        self.assertIsNotNone(mak, "Mak Torvin must still be defined")
        self.assertEqual(mak["room"], self.MAK_ROOM)

    def test_mak_not_on_nar_shaddaa(self):
        mak = self._mak()
        self.assertNotIn("nar shaddaa", mak["room"].lower(),
                         "Mak's room must no longer be on Nar Shaddaa")

    def test_steps_7_and_26_target_maks_room(self):
        """The quest's Mak steps must match Mak's actual room."""
        mak_room = self.MAK_ROOM.lower()
        for sid in (7, 26):
            substr = get_step(sid)["objective_data"]["room_substr"].lower()
            self.assertIn(substr, mak_room,
                          f"step {sid} room_substr {substr!r} must match "
                          f"Mak's room {mak_room!r}")


class TestCrewStepRetargetedToRenna(unittest.TestCase):
    """Step 24 (the crew/shipwright beat) talked to Venn Kator "on Corellia"
    in v1. Design v2 §501-507 removes Venn (a Corellia NPC absent from the CW
    manifest) and retargets the step to Renna Dox, who is already seeded on
    Nar Shaddaa. These pins lock that retarget and ensure no Venn residue."""

    def test_step24_targets_renna_dox(self):
        step = get_step(24)
        self.assertIsNotNone(step)
        self.assertEqual(step["objective_type"], "talk")
        self.assertEqual(step["objective_data"]["npc"], "renna dox")

    def test_step24_has_no_venn_or_corellia_residue(self):
        step = get_step(24)
        text = _step_strings(step)
        self.assertNotIn("venn", text,
                         "step 24 should no longer mention Venn (removed)")
        self.assertNotIn("corellia", text.replace("corellian", ""))

    def test_renna_dox_target_is_unambiguous(self):
        """'renna dox' must not collide with other 'renna' substrings
        (Threnna Coralis, Vrenna Sahl) under the hook's bidirectional
        substring match. 'renna dox' is contained in neither."""
        target = get_step(24)["objective_data"]["npc"]
        for other in ("threnna coralis", "vrenna sahl"):
            self.assertNotIn(target, other)
            self.assertNotIn(other, target)


class TestCWManifestStaysBespoke(unittest.TestCase):
    """CW must NOT load the gg7 base roster. If it ever lists npcs_gg7.yaml
    as a content_ref, 50+ GCW/Imperial NPCs would flood the Clone Wars world
    (era-fidelity regression). A comment merely mentioning gg7 is fine; an
    actual list-item content_ref is not."""

    def test_cw_manifest_does_not_load_gg7_base(self):
        era = (ROOT / "data/worlds/clone_wars/era.yaml").read_text(encoding="utf-8")
        for line in era.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            item = stripped[2:].split("#", 1)[0].strip().strip('"\'')
            if item.endswith("npcs_gg7.yaml"):
                self.fail(f"CW manifest must not load gg7 base roster: {line!r}")


class TestLiraFileRegisteredInEraManifest(unittest.TestCase):
    """The new NPC file must be wired into era.yaml's npcs list or the
    loader will never pick it up (and Lira stays unseeded)."""

    ERA_FILE = ROOT / "data/worlds/clone_wars/era.yaml"

    def test_lira_file_in_npcs_list(self):
        with open(self.ERA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # era.yaml may nest the npcs list under a content key; search the
        # raw text as a robust fallback and the parsed structure first.
        npcs = None
        if isinstance(data, dict):
            # find any 'npcs' list value anywhere one level deep
            for v in data.values():
                if isinstance(v, dict) and isinstance(v.get("npcs"), list):
                    npcs = v["npcs"]
                    break
            if npcs is None and isinstance(data.get("npcs"), list):
                npcs = data["npcs"]
        if npcs is not None:
            self.assertIn("npcs_drop_0a2_fdts_relocate.yaml", npcs)
        else:
            # fallback: the filename appears in the manifest text
            raw = self.ERA_FILE.read_text(encoding="utf-8")
            self.assertIn("npcs_drop_0a2_fdts_relocate.yaml", raw)


class TestCWWorldLoadResolvesFDtSNPCs(unittest.TestCase):
    """Integration pin (the strongest one): load the actual Clone Wars world
    + era NPC roster and assert each FDtS-quest NPC resolves to its intended
    room — NOT the fallback (Market Row). This catches the failure mode the
    structural pins can't: an NPC whose file is registered but whose room
    name doesn't match (silent Market Row fallback). It is also the check
    that caught Venn's absence during this drop (he is in the gg7 base
    roster, which CW does not load — so step 24 was retargeted to Renna).

    Skips gracefully if the dry-run loaders aren't importable in this
    environment (the full DB-backed harness is Windows ground-truth)."""

    EXPECTED = {
        "Lira Shan": "Kuat Drive Yards - Commercial Zone",   # step 27 (seeded here)
        "Mak Torvin": "Docking Bay 94 - Pit Floor",          # steps 7/13/26 (relocated)
        "Renna Dox": "Nar Shaddaa - Renna Dox's Workshop",   # step 24 target (pre-existing)
    }
    FALLBACK_IDX = 8  # Market Row — load_npcs_from_yaml's silent fallback

    @classmethod
    def setUpClass(cls):
        try:
            from engine.world_loader import load_world_dry_run
            from engine.npc_loader import load_era_npcs
        except Exception as exc:  # pragma: no cover - env-dependent
            raise unittest.SkipTest(f"CW dry-run loaders unavailable: {exc}")
        bundle = load_world_dry_run("clone_wars")
        cls.room_map = {r.name: r.id for r in bundle.rooms.values()}
        cls.idx2name = {v: k for k, v in cls.room_map.items()}
        era_dir = os.path.join(str(ROOT), "data", "worlds", "clone_wars")
        planet, _hireable = load_era_npcs(era_dir, cls.room_map)
        cls.by_name = {t[0]: t for t in planet}

    def test_fdts_npcs_resolve_to_intended_rooms(self):
        for name, want_room in self.EXPECTED.items():
            with self.subTest(npc=name):
                self.assertIn(name, self.by_name,
                              f"{name} must load in the CW planet roster")
                room_idx = self.by_name[name][1]
                self.assertNotEqual(
                    room_idx, self.FALLBACK_IDX,
                    f"{name} fell back to Market Row — room name mismatch")
                self.assertEqual(
                    self.idx2name.get(room_idx), want_room,
                    f"{name} resolved to {self.idx2name.get(room_idx)!r}, "
                    f"expected {want_room!r}")

    def test_step24_independent_of_venn(self):
        """The FDtS quest must NOT depend on Venn Kator. 0a-2 removed the old
        Corellia-Venn dependency and retargeted step 24 to Renna Dox.

        NOTE: a separate drop (npcs_mos_eisley_population_p1.yaml) later seeds a
        *different* Venn instance — the Mos Eisley shipwright at Docking Bay 94,
        the data/schematics.yaml ship-component crafting trainer — which is
        legitimate and unrelated to the quest. So we no longer assert Venn is
        globally absent; we assert the quest still routes through Renna and that
        step 24 names Renna, not Venn, regardless of whether a Venn exists."""
        step = get_step(24)
        self.assertEqual(step["objective_data"]["npc"], "renna dox",
                         "step 24 must target Renna Dox, never Venn")
        self.assertIn("Renna Dox", self.by_name,
                      "Renna Dox (the step-24 target) must load in CW")
        # If a Venn is present at all, it must be the Mos Eisley DB94 shipwright
        # (the crafting trainer), not anything the quest points at.
        if "Venn Kator" in self.by_name:
            venn_room = self.idx2name.get(self.by_name["Venn Kator"][1], "")
            self.assertIn("Docking Bay 94", venn_room,
                          "any seeded Venn must be the Mos Eisley DB94 "
                          f"shipwright, not elsewhere (got {venn_room!r})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
