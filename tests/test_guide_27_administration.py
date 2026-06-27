"""Guard: Guide_27 Administration teaches the staff command surface that actually
RESOLVES against the live registry, at the access levels it documents, and never
promises a moderation verb that does not exist.

The Opus-owned guides quality pass.  Before this pass Guide_27 carried two real
drifts a future reader would have trusted:

* **§4 listed `@spawn` among the verbs that do NOT exist.**  It does — as a
  BUILDER ship-spawn tool (`SpawnShipCommand`, ``@spawn <template> <ship name>``).
  The intended point (no NPC/player hand-summon, no global kick) is true, but the
  blanket "no generic ``@spawn``" was a phantom *denial*.  Corrected: ``@spawn`` is
  documented in §2 as a ship hull tool, and §4 only denies the verbs that are
  genuinely absent.
* **§3 omitted `@director fidelity`** — the cadence governor sub-command — from the
  Director control table.

This test resolves every command the guide teaches against the SAME registry
``GameServer.__init__`` builds, asserts each documented access level, pins the
moderation verbs that must stay dead, and pins ``@spawn``'s real (ship/BUILDER)
nature so a future change that desyncs the guide fails loudly here.
"""
import importlib.util
import os
import re

import pytest

from parser.commands import AccessLevel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_27_Administration.md")
DIRECTOR_SRC = os.path.join(PROJECT_ROOT, "parser", "director_commands.py")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__).
    spec = importlib.util.spec_from_file_location(
        "_adminreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every @-command the guide teaches must resolve against HEAD ───────────────
# (form, documented minimum access level)
_TAUGHT = [
    # §1 access
    ("@grant", AccessLevel.ADMIN),
    # §2 world-building (BUILDER+) — a representative slice + @spawn
    ("@dig", AccessLevel.BUILDER),
    ("@tunnel", AccessLevel.BUILDER),
    ("@open", AccessLevel.BUILDER),
    ("@link", AccessLevel.BUILDER),
    ("@unlink", AccessLevel.BUILDER),
    ("@rdesc", AccessLevel.BUILDER),
    ("@rname", AccessLevel.BUILDER),
    ("@destroy", AccessLevel.BUILDER),
    ("@teleport", AccessLevel.BUILDER),
    ("@examine", AccessLevel.BUILDER),
    ("@rooms", AccessLevel.BUILDER),
    ("@find", AccessLevel.BUILDER),
    ("@entrances", AccessLevel.BUILDER),
    ("@set", AccessLevel.BUILDER),
    ("@lock", AccessLevel.BUILDER),
    ("@success", AccessLevel.BUILDER),
    ("@fail", AccessLevel.BUILDER),
    ("@zone", AccessLevel.BUILDER),
    ("@create", AccessLevel.BUILDER),
    ("@emit", AccessLevel.BUILDER),
    ("@name", AccessLevel.BUILDER),
    ("@pemit", AccessLevel.BUILDER),
    ("@spawn", AccessLevel.BUILDER),       # §2/§4 — ship hull tool, BUILDER
    # §3 Director / world (ADMIN)
    ("@director", AccessLevel.ADMIN),
    ("@economy", AccessLevel.ADMIN),
    ("@balance", AccessLevel.ADMIN),       # §3 — T3.19 telemetry read-side
    ("@lore", AccessLevel.ADMIN),
    ("@hazard", AccessLevel.ADMIN),
    ("@roomstate", AccessLevel.ADMIN),
    ("@ai", AccessLevel.ADMIN),
    # §4 moderation (ADMIN)
    ("@wall", AccessLevel.ADMIN),
    ("@force", AccessLevel.ADMIN),
    ("@newpassword", AccessLevel.ADMIN),
    ("@pcbounty", AccessLevel.ADMIN),
    ("@city", AccessLevel.ADMIN),
    ("@security", AccessLevel.ADMIN),
    ("@faction", AccessLevel.ADMIN),
    # §5 Jedi / progression overrides (ADMIN)
    ("@bond", AccessLevel.ADMIN),
    ("@trial", AccessLevel.ADMIN),
    ("@knight", AccessLevel.ADMIN),
    ("@weight", AccessLevel.ADMIN),
    # §6 debug / commerce (ADMIN)
    ("@getcharattr", AccessLevel.ADMIN),
    ("@setcharattr", AccessLevel.ADMIN),
    ("@shop", AccessLevel.ADMIN),
    ("@setbounty", AccessLevel.ADMIN),
    ("@narrative", AccessLevel.ADMIN),
    # §7 lifecycle
    ("@shutdown", AccessLevel.ADMIN),
]


class TestTaughtCommandsResolve:
    @pytest.mark.parametrize("form,_lvl", _TAUGHT)
    def test_form_resolves(self, reg, form, _lvl):
        assert reg.get(form) is not None, (
            f"Guide_27 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    @pytest.mark.parametrize("form,lvl", _TAUGHT)
    def test_access_level_matches_doc(self, reg, form, lvl):
        cmd = reg.get(form)
        assert cmd is not None and cmd.access_level == lvl, (
            f"Guide_27 documents {form!r} at {lvl} but the registry has "
            f"{getattr(cmd, 'access_level', None)} — re-check the guide's tier"
        )

    @pytest.mark.parametrize("form", [
        f for f, _ in _TAUGHT if f != "@spawn"
    ])
    def test_taught_form_appears_in_guide(self, guide_text, form):
        assert form in guide_text, (
            f"{form!r} is taught by the test roster but missing from the guide body"
        )


# ── Documented aliases must resolve to the same command ───────────────────────
class TestAliases:
    @pytest.mark.parametrize("alias,key", [
        ("@gca", "@getcharattr"),   # §6
        ("@sca", "@setcharattr"),   # §6
        ("@bounty", "@setbounty"),  # §6 (alias)
        ("@bal", "@balance"),       # §3 (alias)
    ])
    def test_alias_resolves_to_key(self, reg, alias, key):
        a, k = reg.get(alias), reg.get(key)
        assert a is not None and k is not None
        assert type(a) is type(k), (
            f"alias {alias!r} no longer maps to {key!r}"
        )


# ── @spawn is real (ship/BUILDER) and the guide treats it as such ─────────────
class TestSpawnIsShipTool:
    def test_spawn_resolves_builder(self, reg):
        cmd = reg.get("@spawn")
        assert cmd is not None and cmd.access_level == AccessLevel.BUILDER
        assert type(cmd).__name__ == "SpawnShipCommand"

    def test_guide_no_longer_denies_spawn(self, guide_text):
        # The old phantom denial must be gone.
        assert "generic `@spawn`" not in guide_text
        # And the guide must explain @spawn spawns a ship, not a creature, and
        # that there is no NPC/player summon verb.
        lowered = guide_text.lower()
        assert "@spawn" in guide_text
        assert "ship" in lowered
        assert "no npc- or player-summon verb" in lowered


# ── @director sub-command table must match the live dispatch ───────────────────
_DIRECTOR_SUBS = [
    "status", "enable", "disable", "trigger", "budget",
    "fidelity", "influence", "log", "reset", "narrative", "cult",
]


class TestDirectorSubcommands:
    @pytest.fixture(scope="class")
    def dir_src(self):
        return _read(DIRECTOR_SRC)

    @pytest.mark.parametrize("sub", _DIRECTOR_SUBS)
    def test_sub_in_dispatch(self, dir_src, sub):
        # The execute() dispatch maps each sub-command to a handler.
        assert re.search(rf'"{sub}"\s*:\s*self\._', dir_src), (
            f"@director sub-command {sub!r} is no longer dispatched"
        )

    def test_guide_documents_fidelity(self, guide_text):
        # The drift this pass fixed: fidelity was missing from §3.
        assert "@director fidelity" in guide_text

    @pytest.mark.parametrize("sub", ["budget", "influence", "fidelity", "cult"])
    def test_guide_documents_key_subs(self, guide_text, sub):
        assert sub in guide_text


# ── @balance (T3.19 telemetry read-side) — guide must match the live command ───
class TestBalanceDashboard:
    """The `t319-balance-dashboard` drop shipped `@balance` as the behavioural
    read-side companion to `@economy`; this pass added it to §3.  Pin the guide's
    claims against the live `BalanceCommand` so a future rename/removal fails here.
    """

    def test_balance_resolves_admin(self, reg):
        cmd = reg.get("@balance")
        assert cmd is not None and cmd.access_level == AccessLevel.ADMIN
        assert type(cmd).__name__ == "BalanceCommand"

    def test_guide_pairs_the_two_boards(self, guide_text):
        # The guide must teach BOTH boards and the live-vs-telemetry distinction.
        assert "@economy" in guide_text and "@balance" in guide_text
        lowered = guide_text.lower()
        assert "telemetry" in lowered
        assert "live db state" in lowered  # the @economy side of the contrast

    @pytest.mark.parametrize("sub", [
        "grind", "cp", "objectives", "chains", "encounters", "events", "raw",
    ])
    def test_guide_documents_balance_subforms(self, guide_text, sub):
        assert f"@balance {sub}" in guide_text, (
            f"Guide_27 §3 should document the @balance {sub!r} sub-board"
        )

    @pytest.mark.parametrize("sub", [
        "grind", "cp", "objectives", "chains", "encounters", "events", "raw",
    ])
    def test_subform_is_really_dispatched(self, sub):
        # Each documented sub-board must actually be handled by execute().
        src = _read(DIRECTOR_SRC)
        # Slice out the BalanceCommand class body so the match is scoped to it.
        start = src.index("class BalanceCommand")
        nxt = src.find("\nclass ", start + 1)
        body = src[start:nxt if nxt != -1 else len(src)]
        assert re.search(rf'(["\']){sub}\1', body), (
            f"@balance {sub!r} is documented but no longer handled in "
            f"BalanceCommand.execute()"
        )

    def test_every_usage_subform_is_documented(self, reg, guide_text):
        # Self-maintaining guard against the drift the `chains` board exposed:
        # the hand-maintained list above had gone stale, so a sub-board shipped
        # in the command without a matching §3 entry slipped through. Derive the
        # canonical sub-board list from the LIVE command's own `usage` string so
        # any FUTURE `@balance` sub-board MUST be documented in the guide.
        cmd = reg.get("@balance")
        assert cmd is not None
        # usage = "@balance [grind|cp|objectives|chains|encounters|events|raw [N]]"
        m = re.search(r"\[([a-z|]+)", cmd.usage)
        assert m, f"could not parse @balance usage string: {cmd.usage!r}"
        subs = m.group(1).split("|")
        assert "chains" in subs, (
            "the chains sub-board should be in the live usage string "
            f"(got {subs!r})"
        )
        for sub in subs:
            assert f"@balance {sub}" in guide_text, (
                f"@balance usage advertises the {sub!r} sub-board but Guide_27 "
                f"§3 never documents `@balance {sub}` — keep the guide in "
                f"lockstep with the command's usage line."
            )


# ── The "does not exist" denials must stay true ───────────────────────────────
class TestNoPhantomModerationVerbs:
    @pytest.mark.parametrize("phantom", [
        "@ban", "@boot", "@kick", "@mute", "@slay", "@revoke",
    ])
    def test_phantom_does_not_resolve(self, reg, phantom):
        assert reg.get(phantom) is None, (
            f"{phantom!r} now resolves — Guide_27 §4 claims it does not exist"
        )

    def test_guide_still_denies_them(self, guide_text):
        for phantom in ("@ban", "@kick", "@mute", "@slay"):
            assert phantom in guide_text, (
                f"Guide_27 §4 should still tell staff {phantom!r} is unavailable"
            )

    def test_no_npc_or_player_summon_verb(self, reg):
        # The guide promises NPCs/players are not hand-summoned.
        for form in ("@spawnnpc", "@summon", "@spawnplayer"):
            assert reg.get(form) is None
