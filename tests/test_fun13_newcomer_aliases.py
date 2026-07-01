# -*- coding: utf-8 -*-
"""
tests/test_fun13_newcomer_aliases.py — FUN13 newcomer inventory-reflex aliases.

Fun-assessment finding (8th re-run, Brian's call): new players reflexively type
`inventory` (e.g. right after being handed a rifle + armor at graduation) and
hit a dead-end, because command_syntax_rework_design_v2 made `+inv` the sole
canonical and DELETED the bare reflexes. Brian re-opened the reflexes as
back-compat aliases (canonical `+inv` unchanged). This guards that.
"""
from __future__ import annotations

from parser.commands import CommandRegistry
from parser.builtin_commands import register_all


def _registry():
    reg = CommandRegistry()
    register_all(reg)
    return reg


def test_inventory_reflexes_resolve_to_plus_inv():
    reg = _registry()
    inv = reg.get("+inv")
    assert inv is not None and inv.key == "+inv", "canonical +inv missing"
    for reflex in ("inventory", "inv", "i"):
        assert reg.get(reflex) is inv, (
            f"{reflex!r} should resolve to the +inv inventory command")


def test_plus_inv_stays_canonical():
    """The re-add is additive: +inv is still the primary key + help form."""
    reg = _registry()
    inv = reg.get("+inv")
    assert inv.key == "+inv"
    assert "inventory" in inv.aliases and "inv" in inv.aliases and "i" in inv.aliases
