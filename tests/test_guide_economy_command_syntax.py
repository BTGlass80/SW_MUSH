"""Guard: economy guides + in-game hints teach POST-rework canonical commands.

The command-syntax rework (Drops 0-7) deleted the run-on smash keys
(``bountytrack``/``smugdeliver``/``buyresources``…) and the bare query forms
(``inventory``/``score``/``ships``…), routing everything through the
``+cmd/<switch>`` umbrellas or ``+``-prefixed canonical forms.

Two player-facing surfaces still referenced the *old* vocabulary and the unit
suite never caught it (the convention-invariant test guards the registry, not
free-text prose / hint strings):

  1. ``data/guides/Guide_06_Economy.md`` + ``Guide_07_Crafting.md`` — taught
     ``mission accept <#>`` / ``bountytrack`` / ``buyresources`` etc.
  2. In-game hint strings in the engine/parser told players to ``Type 'repair'``
     (which now resolves to the SHIP damage-control command), ``Type
     'inventory'`` (resolves to nothing), ``Type 'score'`` (nothing).

This test resolves every form the corrected surfaces now teach against the SAME
live registry ``server/game_server`` builds, and asserts the deleted forms are
gone — so a future rename can't silently re-break the new-player guidance.
"""
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_DIR = os.path.join(PROJECT_ROOT, "data", "guides")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__).
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_adminreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Canonical command forms the corrected guides now teach ────────────────────
# (umbrella key, switch) pairs — switch must be in the umbrella's valid_switches.
_UMBRELLA_SWITCHES = {
    "+mission": ["board", "accept", "view", "complete", "abandon"],
    "+bounty": ["board", "claim", "view", "track", "collect"],
    "+smuggle": ["board", "accept", "view", "deliver", "dump"],
    "+craft": ["survey", "resources", "schematics", "start",
               "experiment", "teach", "buyresources"],
}

# Bare/`+`-prefixed standalone forms the guides reference that must resolve.
_STANDALONE_FORMS = [
    "+credits", "+repair", "+inv", "+sheet",
    "market", "buy", "sell", "survey", "resources", "schematics",
    "craft", "experiment", "teach", "perform", "heal", "healaccept",
    "+commissary", "missions", "bounties", "smugjobs", "buyres",
]


class TestUmbrellaSwitchesResolve:
    def test_umbrella_keys_resolve(self, reg):
        for key in _UMBRELLA_SWITCHES:
            cmd = reg.get(key)
            assert cmd is not None, f"umbrella {key!r} does not resolve"
            assert cmd.key == key, f"{key!r} resolved to {cmd.key!r}"

    def test_every_taught_switch_is_valid(self, reg):
        for key, switches in _UMBRELLA_SWITCHES.items():
            cmd = reg.get(key)
            valid = set(getattr(cmd, "valid_switches", []) or [])
            for sw in switches:
                assert sw in valid, (
                    f"{key}/{sw} taught in guide but not in "
                    f"{key} valid_switches={sorted(valid)}"
                )

    def test_standalone_forms_resolve(self, reg):
        for form in _STANDALONE_FORMS:
            assert reg.get(form) is not None, (
                f"guide teaches {form!r} but it no longer resolves"
            )


# ── The deleted/broken vocabulary must NOT reappear in the guides ─────────────
_DELETED_IN_GUIDES = [
    r"\bbountytrack\b",
    r"\bbountyclaim\b",
    r"\bbountycollect\b",
    r"\bsmugdeliver\b",
    r"(?<!/)\bbuyresources\b",       # bare buyresources (allow +craft/buyresources)
    r"\bmission accept\b",
    r"\bmission complete\b",
    r"\bmission abandon\b",
    r"\bbounty claim\b",
    r"\bbounty collect\b",
    r"\bbounty info\b",
    r"\bmission info\b",
]


@pytest.mark.parametrize("guide", ["Guide_06_Economy.md", "Guide_07_Crafting.md"])
def test_no_deleted_forms_in_guide(guide):
    text = _read(os.path.join(GUIDE_DIR, guide))
    for pat in _DELETED_IN_GUIDES:
        m = re.search(pat, text)
        assert m is None, (
            f"{guide} still teaches deleted command form {m.group(0)!r} "
            f"(matched {pat!r}) — command-syntax rework canonicalized it"
        )


def test_guides_teach_canonical_umbrella_forms():
    econ = _read(os.path.join(GUIDE_DIR, "Guide_06_Economy.md"))
    for form in ["+mission/board", "+mission/accept", "+bounty/claim",
                 "+bounty/track", "+smuggle/deliver", "+smuggle/board"]:
        assert form in econ, f"Guide_06 missing canonical form {form!r}"
    craft = _read(os.path.join(GUIDE_DIR, "Guide_07_Crafting.md"))
    assert "+craft/buyresources" in craft


# ── In-game hint strings now point at commands that actually resolve ──────────
# (file, snippet that must be PRESENT, broken snippet that must be ABSENT)
_HINT_FILES = [
    ("parser/builtin_commands.py", "Type '+repair' to fix it", "Type 'repair' to fix it"),
    ("parser/combat_commands.py", "Type '+repair' to fix it", "Type 'repair' to fix it"),
]


@pytest.mark.parametrize("path,present,absent", _HINT_FILES)
def test_ingame_hint_corrected(path, present, absent):
    text = _read(os.path.join(PROJECT_ROOT, path))
    assert present in text, f"{path}: corrected hint {present!r} missing"
    assert absent not in text, f"{path}: stale hint {absent!r} still present"


def test_no_bare_inventory_hint_remains():
    """The 6 'Type/Use 'inventory'' hints are all re-pointed at '+inv'."""
    for path in ["parser/builtin_commands.py", "parser/shop_commands.py",
                 "parser/space_commands.py"]:
        text = _read(os.path.join(PROJECT_ROOT, path))
        for bad in ("Type 'inventory'", "Use 'inventory'"):
            assert bad not in text, f"{path}: stale {bad!r} hint still present"


def test_repair_hint_target_is_weapon_repair_not_ship_damcon(reg):
    """Regression rationale: bare 'repair' resolves to the SHIP DamCon command,
    so the broken-weapon hint MUST say '+repair' (the actual weapon-repair cmd).
    """
    bare = reg.get("repair")
    plus = reg.get("+repair")
    assert plus is not None and plus.key == "+repair"
    # bare 'repair' must NOT be the weapon-repair command (it is ship DamCon) —
    # this is exactly why the hint had to change.
    assert bare is None or bare.key != "+repair"
