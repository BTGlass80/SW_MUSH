"""OBS.buy_verb_followups (a) — vendor-presence gate, decision
**a + vendor flag** (2026-06-12, drop 11).

Buying open-market commons now requires an NPC with `ai_config.vendor:
true` in the room — the `trainer: true` precedent applied to commerce.
This disentangles VENDORS from mere HAGGLERS: before the gate, any
Bargain-skilled NPC satisfied the haggle scan (Lup the grocer was an
implicit arms dealer), and with nobody present a phantom "generic 3D
vendor" closed the sale — the deep desert sold blasters. The haggle now
uses THE VENDOR'S Bargain (generic 3D only when the flagged vendor
lacks the skill), which also fixes the old first-Bargain-NPC bug.

Curated vendors (every major settlement gets a buy point): Kayson +
Sela Tarn (Kayson's Weapon Shop), Lup (General Store), Jawa Trade-Elder
Ruzz-tha (Jawa Traders) — Mos Eisley; Trex Hovan (Lower City Black
Market) — Coruscant; Halen Korr (Weapons Cache) + Reska Tol (Undercity
Market) — Nar Shaddaa; Sela Dorne (Stalgasin offworlder camp) —
Geonosis. Kamino deliberately has none (faction world; the commissary
serves it). GUNDARK IS NOT A VENDOR — he teaches the contraband band,
he does not retail commons; pinned below.
"""
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CW = REPO / "data" / "worlds" / "clone_wars"

CURATED = {
    "npcs_mos_eisley_population_p1.yaml": ["Kayson"],
    "npcs_mos_eisley_population_p2.yaml": ["Lup"],
    "npcs_drop_craft_c_armorer.yaml": ["Sela Tarn"],
    "npcs_drop_b_mos_eisley.yaml": ["Jawa Trade-Elder Ruzz-tha"],
    "npcs_drop_c2_southern_underground.yaml":
        ["Lower City Black Market Vendor Trex Hovan"],
    "npcs_drop_g2_nar_shaddaa_lower.yaml":
        ["Weapons Cache Dealer Halen Korr",
         "Undercity Market Vendor Reska Tol"],
    "npcs_drop_def_civilians.yaml": ["Independent Trader Sela Dorne"],
    # fun7-reward-loop: starter outfitters placed in the CW profession-chain
    # graduate hubs so a graduate can reach a vendor (deliberate curation).
    "npcs_drop_fun7_starter_vendors.yaml":
        ["Brekka Solwynn", "Muss Farren", "Orvak Tesh"],
}


def _npcs(fname):
    return yaml.safe_load((CW / fname).read_text(encoding="utf-8"))["npcs"]


class TestVendorCuration(unittest.TestCase):
    def test_curated_vendors_flagged(self):
        for fname, names in CURATED.items():
            by_name = {n["name"]: n for n in _npcs(fname)}
            for name in names:
                self.assertIn(name, by_name, f"{fname}:{name}")
                self.assertTrue(
                    by_name[name].get("ai_config", {}).get("vendor"),
                    f"{fname}:{name} not vendor-flagged")

    def test_curated_files_are_era_loaded(self):
        era = (CW / "era.yaml").read_text(encoding="utf-8")
        for fname in CURATED:
            self.assertIn(fname, era, fname)

    def test_gundark_is_not_a_vendor(self):
        # He TEACHES the contraband band; he does not retail commons.
        # `buy` at his stall must refuse — knowledge is his only cargo.
        npc = _npcs("npcs_drop_craft_g_gundark.yaml")[0]
        self.assertEqual(npc["name"], "Gundark")
        self.assertFalse(npc.get("ai_config", {}).get("vendor", False))

    def test_no_vendor_flag_outside_curation(self):
        # The vendor set is deliberate. A new vendor is a curation
        # decision, not a side effect — extend CURATED with the drop
        # that adds one.
        curated_pairs = {(f, n) for f, names in CURATED.items()
                         for n in names}
        for path in sorted(CW.glob("npcs_*.yaml")):
            try:
                npcs = yaml.safe_load(
                    path.read_text(encoding="utf-8")).get("npcs", [])
            except Exception:
                continue
            for npc in npcs or []:
                if (npc.get("ai_config") or {}).get("vendor"):
                    self.assertIn((path.name, npc["name"]), curated_pairs,
                                  f"uncurated vendor {path.name}:{npc['name']}")


class TestBuyGate(unittest.TestCase):
    def _code(self):
        src = (REPO / "parser" / "space_commands.py").read_text(
            encoding="utf-8")
        return "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))

    def test_gate_refuses_without_vendor(self):
        code = self._code()
        idx = code.index("No merchant here sells weapons")
        window = code[idx - 900:idx + 200]
        self.assertIn('ai_cfg.get("vendor")', window)
        self.assertIn("vendor_npc is None", window)
        self.assertIn("return", window[window.index("vendor_npc is None"):])

    def test_haggle_uses_the_vendors_bargain(self):
        code = self._code()
        # the old loop ("break on first Bargain NPC") must be gone;
        # the sheet read must come from vendor_npc specifically.
        self.assertNotIn("Use first vendor NPC with Bargain skill", code)
        idx = code.index("resolve_bargain_check")
        window = code[idx - 700:idx]
        self.assertIn('vendor_npc.get("char_sheet_json"', window)


if __name__ == "__main__":
    unittest.main()
