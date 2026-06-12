"""Webify UI-8 — crafting_state producer tests (2026-06-10).

engine/crafting.py::build_crafting_state + component_availability.
ABI: web_client_vision_and_protocol_v1_4.md §1.9. The panel renders only
what the engine computes — these tests pin that the structural payload
matches the CRAFT.P0.1 check_resources semantics exactly.
"""
import json
import unittest


def _char(known=None, resources=None):
    return {
        "attributes": json.dumps({"schematics": known or []}),
        "inventory": json.dumps({"items": [],
                                 "resources": resources or []}),
    }


class TestComponentAvailability(unittest.TestCase):
    def test_have_vs_have_at_quality_split(self):
        from engine.crafting import component_availability
        char = _char(resources=[
            {"type": "metal", "quantity": 3, "quality": 30.0},
            {"type": "metal", "quantity": 2, "quality": 70.0},
        ])
        c = component_availability(
            char, {"type": "metal", "quantity": 4, "min_quality": 50})
        self.assertEqual(c["have"], 5)
        self.assertEqual(c["have_at_quality"], 2)
        self.assertEqual(c["quantity"], 4)
        self.assertEqual(c["min_quality"], 50)

    def test_absent_type_is_zeroes(self):
        from engine.crafting import component_availability
        c = component_availability(
            _char(), {"type": "rare", "quantity": 1, "min_quality": 1})
        self.assertEqual((c["have"], c["have_at_quality"]), (0, 0))


class TestBuildCraftingState(unittest.TestCase):
    def test_known_schematic_shape_and_craftable_flag(self):
        from engine.crafting import build_crafting_state
        # medpac_basic: 2x chemical q25+, 1x organic q20+
        char = _char(known=["medpac_basic"], resources=[
            {"type": "chemical", "quantity": 2, "quality": 60.0},
            {"type": "organic", "quantity": 1, "quality": 60.0},
        ])
        out = build_crafting_state(char)
        self.assertEqual(len(out["schematics"]), 1)
        s = out["schematics"][0]
        self.assertEqual(s["key"], "medpac_basic")
        self.assertEqual(s["skill"], "first_aid")
        self.assertTrue(s["craftable"])
        self.assertFalse(s["t5"])
        self.assertEqual(s["output_type"], "consumable")
        comp_types = {c["type"] for c in s["components"]}
        self.assertEqual(comp_types, {"chemical", "organic"})
        for c in s["components"]:
            for field in ("quantity", "min_quality", "have",
                          "have_at_quality"):
                self.assertIn(field, c)

    def test_quality_blocked_is_not_craftable(self):
        from engine.crafting import build_crafting_state
        # Plenty of material, all below min_quality.
        char = _char(known=["medpac_basic"], resources=[
            {"type": "chemical", "quantity": 9, "quality": 10.0},
            {"type": "organic", "quantity": 9, "quality": 10.0},
        ])
        s = build_crafting_state(char)["schematics"][0]
        self.assertFalse(s["craftable"])
        chem = next(c for c in s["components"] if c["type"] == "chemical")
        self.assertEqual(chem["have"], 9)
        self.assertEqual(chem["have_at_quality"], 0)

    def test_craftable_matches_check_resources(self):
        # The flag and the verb gate must never disagree.
        from engine.crafting import (build_crafting_state, check_resources,
                                     get_all_schematics)
        for resources in (
            [],
            [{"type": "chemical", "quantity": 2, "quality": 60.0},
             {"type": "organic", "quantity": 1, "quality": 60.0}],
            [{"type": "chemical", "quantity": 2, "quality": 10.0},
             {"type": "organic", "quantity": 1, "quality": 60.0}],
        ):
            char = _char(known=["medpac_basic"], resources=resources)
            flag = build_crafting_state(char)["schematics"][0]["craftable"]
            ok, _ = check_resources(
                char, get_all_schematics()["medpac_basic"]["components"])
            self.assertEqual(flag, ok, f"disagree on {resources!r}")

    def test_t5_flag_and_resources_section(self):
        from engine.crafting import build_crafting_state
        char = _char(known=["t5_master_crafted_lightsaber"], resources=[
            {"type": "kyber_shard_minor", "quantity": 1, "quality": 76.0},
        ])
        out = build_crafting_state(char)
        self.assertTrue(out["schematics"][0]["t5"])
        self.assertEqual(out["resources"], [
            {"type": "kyber_shard_minor", "quantity": 1, "quality": 76.0}])

    def test_last_result_passthrough_and_default(self):
        from engine.crafting import build_crafting_state
        char = _char()
        self.assertIsNone(build_crafting_state(char)["last_result"])
        out = build_crafting_state(char, last_result={
            "success": True, "partial": False, "fumble": False,
            "quality": 71.4, "name": "Medpac (Basic)"})
        lr = out["last_result"]
        self.assertTrue(lr["success"])
        self.assertEqual(lr["name"], "Medpac (Basic)")
        self.assertAlmostEqual(lr["quality"], 71.4)

    def test_unknown_keys_and_malformed_attrs_tolerated(self):
        from engine.crafting import build_crafting_state
        char = _char(known=["no_such_schematic", "medpac_basic"])
        out = build_crafting_state(char)
        self.assertEqual([s["key"] for s in out["schematics"]],
                         ["medpac_basic"])
        broken = {"attributes": "{not json", "inventory": "{nor this"}
        out2 = build_crafting_state(broken)   # never raises
        self.assertEqual(out2["schematics"], [])
        self.assertEqual(out2["resources"], [])


if __name__ == "__main__":
    unittest.main()
