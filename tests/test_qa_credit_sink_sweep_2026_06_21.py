# -*- coding: utf-8 -*-
"""
tests/test_qa_credit_sink_sweep_2026_06_21.py — systematic credit-integrity
sweep (2026-06-21).

After QA sweeps kept turning up the SAME credit-integrity pattern one zone at a
time (stale session-cache affordability pre-check, then an unguarded
`adjust_credits(char, -cost)` a concurrent drain can drive negative), we audited
EVERY negative player sink (see docs/design/credit_sink_audit_2026-06-21.md) and
hardened the 22 genuinely-vulnerable fixed-cost sinks. The chokepoint contract:
`adjust_credits(..., allow_negative=False)` refuses an over-draw atomically and
returns `None` (it does NOT raise) → the caller aborts.

This suite pins the whole sweep so a regression at any one site fails loudly:
  * every hardened sink's `adjust_credits` call carries `allow_negative=False`;
  * the 6 "state created before the debit" sites are debit-FIRST (the guarded
    debit precedes the state-creation call), so a refused debit grants nothing;
  * the p2p transfer aborts BEFORE crediting the recipient / taxing (no minting);
  * the two full-demand extortions fall through to refusal/combat on a refused
    debit instead of paying a negative balance;
  * Drop A (qa-housing-credit-integrity) already carries the end-to-end
    behavioral proof of this exact fix pattern (rent_room / sell_shopfront).

Run: python -m pytest tests/test_qa_credit_sink_sweep_2026_06_21.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _src(rel):
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


# Each hardened site as (file, UNIQUE contiguous fragment of its guarded
# adjust_credits call). The fragment pins the specific sink — tags that appear
# in a docstring or a safe sibling (repair / ship_purchase / debt_payment) are
# disambiguated by the delta + allow_negative=False signature.
HARDENED = [
    ("engine/buildings.py", '"player_building_construct", allow_negative=False'),
    ("engine/commissary.py", '"commissary_purchase", allow_negative=False'),
    ("engine/dens.py", "DEN_SETUP_SOURCE, allow_negative=False"),
    ("engine/encounter_pirate.py", '"space_pirate_extortion", allow_negative=False'),
    ("engine/gear_insurance.py", "PREMIUM_SOURCE, allow_negative=False"),
    ("engine/housing.py", '"home_prestige", allow_negative=False'),
    ("engine/housing.py", '"housing_rename", allow_negative=False'),
    ("engine/titles.py", '"vanity_title", allow_negative=False'),
    ("engine/npc_space_traffic.py", '"npc_pirate_extortion", allow_negative=False'),
    ("engine/spacer_quest.py", '"spacer_quest_ship", allow_negative=False'),
    ("parser/builtin_commands.py", '"bacta_tank", allow_negative=False'),
    ("parser/builtin_commands.py", '-cost, "repair", allow_negative=False'),
    ("parser/builtin_commands.py", '-amount, "p2p_transfer", allow_negative=False'),
    ("parser/crew_commands.py", '"crew_wage", allow_negative=False'),
    ("parser/shipyard_commands.py", '-price, "ship_purchase", allow_negative=False'),
    ("parser/space_commands.py", '"ground_weapon_purchase", allow_negative=False'),
    ("parser/space_commands.py", '"trade_goods", allow_negative=False'),
    ("parser/spacer_quest_commands.py", '-principal, "debt_payment", allow_negative=False'),
]


class TestEverySinkGuarded:
    @pytest.mark.parametrize("rel,fragment", HARDENED)
    def test_sink_has_allow_negative_false(self, rel, fragment):
        src = _src(rel)
        assert fragment in src, (
            f"{rel} must contain the guarded sink call {fragment!r} — the "
            f"hardened debit is missing or regressed")

    def test_all_three_ship_refuel_sites_guarded(self):
        """space_commands has 3 ship_refuel debits (launch / misjump / jump
        success) — every one must carry the guard."""
        src = _src("parser/space_commands.py")
        idxs = [m.start() for m in re.finditer(r'"ship_refuel"', src)]
        guarded = 0
        for i in idxs:
            start = src.rfind("adjust_credits(", 0, i)
            if start == -1:
                continue
            if "allow_negative=False" in src[start:i + 40]:
                guarded += 1
        assert guarded >= 3, (
            f"all 3 ship_refuel sinks must be guarded, found {guarded}")


class TestReorderDebitFirst:
    """The 6 sites where state was created BEFORE the debit must now debit
    FIRST — the guarded debit must precede the state-creation call, and the
    state-creation must NOT also run before the debit."""

    def _assert_debit_first(self, rel, debit_fragment, state_marker):
        src = _src(rel)
        debit = src.find(debit_fragment)
        assert debit != -1, f"{rel}: guarded debit {debit_fragment!r} not found"
        # the state creation appears shortly AFTER the debit...
        after = src.find(state_marker, debit)
        assert after != -1 and (after - debit) < 2500, (
            f"{rel}: state creation {state_marker!r} must follow the debit "
            f"{debit_fragment!r} (debit-first)")
        # ...and NOT in the lines immediately before it (it was moved after).
        before = src[max(0, debit - 1200):debit]
        assert state_marker not in before, (
            f"{rel}: state creation {state_marker!r} still runs BEFORE the "
            f"debit — refused debit would grant it for free")

    def test_repair_debits_before_save(self):
        self._assert_debit_first("parser/builtin_commands.py",
                                 '-cost, "repair", allow_negative=False',
                                 "item.repair()")

    def test_crew_wage_debits_before_hire(self):
        self._assert_debit_first("parser/crew_commands.py",
                                 '"crew_wage", allow_negative=False', "hire_npc(")

    def test_ground_weapon_debits_before_equip(self):
        self._assert_debit_first("parser/space_commands.py",
                                 '"ground_weapon_purchase", allow_negative=False',
                                 "write_equipment(weapon=item")

    def test_trade_goods_debits_before_update_ship(self):
        self._assert_debit_first("parser/space_commands.py",
                                 '"trade_goods", allow_negative=False',
                                 "update_ship(ship")

    def test_debt_payoff_debits_before_save(self):
        self._assert_debit_first("parser/spacer_quest_commands.py",
                                 '-principal, "debt_payment", allow_negative=False',
                                 'debt["principal"] = 0')

    def test_spacer_quest_ship_debits_before_transfer(self):
        self._assert_debit_first("engine/spacer_quest.py",
                                 '"spacer_quest_ship", allow_negative=False',
                                 "_transfer_ship_ownership")


class TestP2PNoMint:
    """The p2p transfer must abort (return) on a refused offerer debit BEFORE
    the recipient is credited or the tax sink fires — otherwise a stale-cache
    offerer mints credits into the recipient's account from nothing."""

    def test_offerer_debit_aborts_before_recipient_credit(self):
        src = _src("parser/builtin_commands.py")
        debit = src.find('-amount, "p2p_transfer", allow_negative=False')
        none_abort = src.find("if offerer_new_bal is None:", debit)
        recipient_credit = src.find('received, "p2p_transfer"', debit)
        tax_sink = src.find('"p2p_tax"', debit)
        assert debit != -1, "offerer debit must use allow_negative=False"
        assert none_abort != -1, "missing the None-abort guard"
        assert recipient_credit != -1 and tax_sink != -1
        assert debit < none_abort < recipient_credit < tax_sink, (
            "ordering: guarded offerer debit -> None-abort -> recipient "
            "credit -> tax")
        between = src[none_abort:recipient_credit]
        assert "return" in between, (
            "the p2p transfer must RETURN on a refused offerer debit before "
            "crediting the recipient (no minting)")


class TestExtortionFallthrough:
    """The two full-demand extortion debits must, on a refused (None) debit,
    take the same can't-pay path (combat / refusal) — not pay a negative."""

    def test_pirate_pay_falls_through_to_combat_on_none(self):
        src = _src("engine/encounter_pirate.py")
        debit = src.find('"space_pirate_extortion", allow_negative=False')
        none_check = src.find("is None:", debit)
        combat = src.find("_start_pirate_combat", none_check)
        assert debit != -1 and none_check != -1 and combat != -1
        assert none_check < combat, (
            "a refused extortion debit must fall through to combat")

    def test_npc_pirate_extortion_returns_false_on_none(self):
        src = _src("engine/npc_space_traffic.py")
        debit = src.find('"npc_pirate_extortion", allow_negative=False')
        assert debit != -1, "npc_pirate_extortion must be guarded"
        after = src[debit:debit + 400]
        assert "is None:" in after and "return" in after, (
            "npc_pirate_extortion must return on a refused debit, not pay "
            "a negative balance")
