"""CRAFT.market_segmentation_impl — decision a implemented (2026-06-12).

THE AUDIT'S FINDING: the bare `buy` verb (space_commands.BuyCommand's
fallthrough — originally the ship-weapon shop) resolved the ENTIRE
weapon registry by name with no stock gate, no vendor-presence gate,
and no room gate: every row, the Drop G contraband band included, was
credit-purchasable anywhere at book cost + haggle. Every Gundark drop
silently widened that store. Meanwhile the NPC channels that LOOK like
stores (commissary) were clean — faction-issue keys, fully disjoint
from the craft catalog — and player-droid shops are sanctioned by the
decision itself.

THE FIX: `vendor_stocked: bool = False` on WeaponData — DEFAULT CLOSED,
so every future row ships off-market until deliberately opened. Exactly
13 Avail-1 commons are flagged open at book cost; band 2–3 is craft /
loot / player-shop; band 4/X is Gundark-taught contraband. The `buy`
gate refuses unstocked rows; the `weapons` reference list keeps every
row but shows prices only on stocked ones ("craft" otherwise).

GRANDFATHER vs WITHDRAW (the queued call): there were no stocked
violations to withdraw — the violation was the ungated verb itself.
Items players already bought stay theirs (nothing touches inventories);
the gate only closes FUTURE purchases. Recorded as the resolution.
"""
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

OPEN_COMMONS = sorted([
    # NOTE: vibroaxe AND stun_pistol were in the first-cut open list
    # and the band test below rejected both — each is a band-40
    # schematic's output (heavy vibroblade / basic stun pistol), so
    # decision a closes them. The consistency test earned its keep
    # twice before the drop even shipped.
    "hold_out_blaster", "blaster_pistol",
    "heavy_blaster_pistol", "sporting_blaster", "sporting_blaster_rifle",
    "knife", "vibroblade", "stun_baton",
    "vibrosaw_greel", "blaster_pistol_dl22", "heavy_blaster_pistol_dl6h",
])


def _registry():
    from engine.weapons import get_weapon_registry
    return get_weapon_registry()


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


class TestStockFlag(unittest.TestCase):
    def test_exactly_the_commons_are_open(self):
        wr = _registry()
        raw = yaml.safe_load(
            (REPO / "data" / "weapons.yaml").read_text(encoding="utf-8"))
        stocked = sorted(k for k in raw
                         if wr.get(k) and wr.get(k).vendor_stocked)
        self.assertEqual(stocked, OPEN_COMMONS)

    def test_default_is_closed(self):
        # A row without the field is OFF-market — the safe default that
        # protects every future drop from silently widening the store.
        from engine.weapons import WeaponData
        self.assertFalse(WeaponData(key="x", name="x", weapon_type="t",
                                    skill="s", damage="1D").vendor_stocked)

    def test_contraband_band_closed(self):
        wr = _registry()
        for key in ("disruptor_pistol", "predator_rifle",
                    "anti_vehicle_grenade", "thermal_detonator"):
            self.assertFalse(wr.get(key).vendor_stocked, key)

    def test_band_2_plus_craftables_closed(self):
        # Every craft output whose materials band is 40+ AND lives in
        # the weapon registry must be off the open market — that is the
        # decision's core line: band 2-3 = craft/loot/player-shop only.
        wr = _registry()
        for s in _schematics():
            band = max((c.get("min_quality", 0)
                        for c in s.get("components", [])), default=0)
            if band >= 40 and s.get("output_type") == "weapon":
                w = wr.get(s["output_key"])
                if w is not None:
                    self.assertFalse(
                        w.vendor_stocked,
                        f"{s['output_key']} (band {band}) is open-market")

    def test_open_rows_have_real_prices(self):
        wr = _registry()
        for key in OPEN_COMMONS:
            self.assertGreater(wr.get(key).cost, 0, key)


class TestBuyGate(unittest.TestCase):
    def _code(self, path):
        src = (REPO / path).read_text(encoding="utf-8")
        return "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))

    def test_buy_refuses_unstocked(self):
        code = self._code("parser/space_commands.py")
        gate_idx = code.index('vendor_stocked", False)')
        # Order invariant (not a fixed char-window — the WORLDEVENT
        # hutt_auction consumer 2026-06-13 inserts a rep-gated unlock
        # branch between the gate and the refusal): the unstocked-item
        # refusal still exists AND fires AFTER the vendor_stocked check,
        # below the name-resolution gate. The segmentation gate holds;
        # only eligible (hutt_auction + rep) players bypass it.
        self.assertIn("find_by_name", code[:gate_idx])
        refusal_idx = code.index("No open vendor stocks")
        self.assertGreater(refusal_idx, gate_idx,
                           "refusal must come after the vendor_stocked check")

    def test_listing_prices_only_stocked(self):
        code = self._code("parser/builtin_commands.py")
        idx = code.index('class WeaponsListCommand')
        window = code[idx:idx + 2500]
        self.assertIn("vendor_stocked", window)
        self.assertIn('"craft"', window)


class TestAuditFindings(unittest.TestCase):
    def test_commissary_respects_the_band_line(self):
        # The audit's first-cut claim was total key-disjointness — wrong
        # premise: commissary's blaster_pistol IS a craft output, but
        # it's band-25, which decision a explicitly allows in vendor
        # channels (rank-gated requisition discount included). The REAL
        # line: no NPC channel may sell a band-40+ craft output.
        from engine.commissary import COMMISSARY_STOCK
        band = {}
        for s in _schematics():
            b = max((c.get("min_quality", 0)
                     for c in s.get("components", [])), default=0)
            k = s["output_key"]
            band[k] = max(band.get(k, 0), b)
        for faction, rows in COMMISSARY_STOCK.items():
            for row in rows:
                self.assertLess(band.get(row["key"], 0), 40,
                                f"{faction}:{row['key']}")

    def test_player_shop_channel_untouched(self):
        # Player-droid shops are SANCTIONED by decision a (band 2-3 =
        # craft/loot/player-shop). The stock/unstock surface must not
        # have grown a vendor_stocked gate.
        src = (REPO / "engine" / "vendor_droids.py").read_text(
            encoding="utf-8")
        self.assertNotIn("vendor_stocked", src)


if __name__ == "__main__":
    unittest.main()
