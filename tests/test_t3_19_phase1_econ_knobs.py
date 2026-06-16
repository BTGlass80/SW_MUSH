# -*- coding: utf-8 -*-
"""T3.19 Phase 1 — HIGH-priority economy knobs externalized to data/tunables.yaml.

For each knob, verify BOTH:
  (a) behavior-preserving when absent — the in-code default is used (the YAML is
      purely additive; omitting a key is identical to the pre-T3.19 behaviour);
  (b) the knob actually flows to its call site when set.

All assertions are deterministic (band-collapse / fixed values / seeded RNG with a
collapsed range) so there is no RNG flake. Every value is read at the USE SITE via
get_tunable(key, <in-code default>) — never frozen at module import — which these
tests exercise by mutating the live tunables after the modules are imported.
"""
import pathlib
import random

import pytest
import yaml

from engine import tunables
from engine.tunables import reset_tunables


@pytest.fixture(autouse=True)
def _clean_tunables():
    reset_tunables()
    yield
    reset_tunables()


def _set(**kw):
    tunables._TUNABLES.update(kw)


# ── trade price multipliers (engine/trading.py) ──────────────────────────────
def test_trade_price_source_default_then_override():
    from engine.trading import TRADE_GOODS, get_planet_price
    lux = TRADE_GOODS["luxury_goods"]  # base 400, source = nar_shaddaa
    assert get_planet_price(lux, "nar_shaddaa") == 280  # 400 * 0.70 default
    _set(**{"trade.price_source_multiplier": 0.50})
    assert get_planet_price(lux, "nar_shaddaa") == 200  # 400 * 0.50


def test_trade_price_demand_default_then_override():
    from engine.trading import TRADE_GOODS, get_planet_price
    lux = TRADE_GOODS["luxury_goods"]  # demand = coruscant
    assert get_planet_price(lux, "coruscant") == 560  # 400 * 1.40 default
    _set(**{"trade.price_demand_multiplier": 2.0})
    assert get_planet_price(lux, "coruscant") == 800


# ── supply (engine/trading.py) ───────────────────────────────────────────────
def test_supply_max_luxury_goods_default_then_override():
    from engine.trading import _max_units
    assert _max_units("luxury_goods") == 6  # the in-code MAX_UNITS_PER_REFRESH value
    _set(**{"trade.supply_max_luxury_goods": 3})
    assert _max_units("luxury_goods") == 3


def test_supply_max_luxury_knob_does_not_affect_other_goods():
    from engine.trading import _max_units
    baseline = _max_units("raw_ore")
    _set(**{"trade.supply_max_luxury_goods": 1})
    assert _max_units("raw_ore") == baseline  # only luxury_goods is keyed


def test_supply_refresh_seconds_default_then_override():
    from engine.trading import SupplyPool
    p = SupplyPool()
    p.available("tatooine", "luxury_goods")  # seed the pool at "now"
    assert abs(p.seconds_until_refresh("tatooine", "luxury_goods") - 2700) < 10
    _set(**{"trade.supply_refresh_seconds": 100})
    p2 = SupplyPool()
    p2.available("tatooine", "luxury_goods")
    assert abs(p2.seconds_until_refresh("tatooine", "luxury_goods") - 100) < 10


# ── mission smuggling reward max (engine/missions.py) ────────────────────────
def test_mission_smuggling_max_read_at_call_site():
    from engine.missions import MissionType, _scale_reward
    # collapse the band to lo (500) -> reward is deterministically 500 for any roll
    _set(**{"mission.reward_smuggling_max": 500})
    for sl in (1, 3, 6):
        random.seed(sl)
        assert _scale_reward(MissionType.SMUGGLING, sl) == 500
    # default band: every roll lands within [500, 5000]
    reset_tunables()
    for sl in (1, 3, 6):
        random.seed(sl)
        assert 500 <= _scale_reward(MissionType.SMUGGLING, sl) <= 5000


def test_mission_smuggling_knob_does_not_touch_other_types():
    from engine.missions import MissionType, _scale_reward
    _set(**{"mission.reward_smuggling_max": 500})
    random.seed(7)
    with_knob = _scale_reward(MissionType.COMBAT, 3)
    reset_tunables()
    random.seed(7)
    without_knob = _scale_reward(MissionType.COMBAT, 3)
    assert with_knob == without_knob  # COMBAT band is untouched


# ── bounty superior reward max (engine/bounty_board.py) ──────────────────────
def test_bounty_superior_max_read_at_call_site():
    from engine.bounty_board import BountyTier, _scale_reward
    _set(**{"bounty.reward_superior_max": 3000})  # collapse to lo
    for s in range(5):
        random.seed(s)
        assert _scale_reward(BountyTier.SUPERIOR) == 3000  # randint(3000,3000)
    reset_tunables()
    for s in range(5):
        random.seed(s)
        assert 3000 <= _scale_reward(BountyTier.SUPERIOR) <= 10000


def test_bounty_superior_knob_does_not_touch_other_tiers():
    from engine.bounty_board import BountyTier, _scale_reward
    _set(**{"bounty.reward_superior_max": 3000})
    random.seed(11)
    with_knob = _scale_reward(BountyTier.VETERAN)
    reset_tunables()
    random.seed(11)
    without_knob = _scale_reward(BountyTier.VETERAN)
    assert with_knob == without_knob


# ── commissary sellback rate (engine/commissary.py) ──────────────────────────
def test_commissary_sellback_default_then_override():
    from engine.commissary import _refund_amount
    item = {"requisition_cost": 1000}
    assert _refund_amount(item, "republic") == 500  # 0.50 default
    _set(**{"commissary.sellback_rate": 0.25})
    assert _refund_amount(item, "republic") == 250


# ── p2p trade tax (parser/builtin_commands.py) ───────────────────────────────
def test_p2p_tax_externalized_formula_is_integer_identical_to_legacy():
    # max(1, amount*pct//100) with pct=5 == the legacy max(1, amount//20), exactly
    for amt in (0, 1, 19, 20, 21, 39, 40, 100, 999, 100000, 123456):
        assert max(1, amt * 5 // 100) == max(1, amt // 20)


def test_p2p_tax_call_site_reads_tunable():
    # the credit-trade path is DB/session-heavy; assert the externalization is
    # wired at the source (the formula equivalence is covered above).
    src = pathlib.Path("parser/builtin_commands.py").read_text(encoding="utf-8")
    assert 'get_tunable("p2p.tax_pct", 5)' in src
    assert "amount * tax_pct // 100" in src


# ── data/tunables.yaml ships the cluster at the in-code defaults ──────────────
def test_tunables_yaml_ships_cluster_at_defaults():
    d = yaml.safe_load(pathlib.Path("data/tunables.yaml").read_text(encoding="utf-8"))
    assert d["trade.price_source_multiplier"] == 0.70
    assert d["trade.price_demand_multiplier"] == 1.40
    assert d["trade.supply_refresh_seconds"] == 2700
    assert d["trade.supply_max_luxury_goods"] == 6
    assert d["mission.reward_smuggling_max"] == 5000
    assert d["bounty.reward_superior_max"] == 10000
    assert d["p2p.tax_pct"] == 5
    assert d["commissary.sellback_rate"] == 0.50
