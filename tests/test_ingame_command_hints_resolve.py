"""Guard: every in-game ``Type 'X'`` command hint resolves against the live
registry that ``server/game_server`` builds.

The command-syntax rework (Drops 0-7) deleted the bare query/meta forms and
made the ``+``-prefixed variant canonical.  Player-facing *guide prose* was
swept by the guide-syntax tests, but the dozens of imperative
``Type 'X'`` hints emitted from *engine/parser code* in live play are a
separate surface the convention-invariant test never covered — a hint that
tells a new player to ``Type 'missions'`` when the bare form was deleted is a
"command not found" the unit suite can't see.

This guard scans ``engine/`` ``parser/`` ``server/`` for ``Type 'X'`` hints and
asserts the command word resolves (exact key OR sanctioned alias OR a
``+cmd/<switch>`` base).  It catches the whole regression class: if a future
rework deletes/renames a command, any stale hint pointing at it fails loudly.

Known, *documented* exceptions are explicit below — anything else that stops
resolving is a real break.

Drop ``ingame-hint-resolve`` (Opus loop) also fixed the two hits that were
genuinely broken at authoring time:
  * ``engine/spacer_quest.py`` step-8 hint ``'factions'`` -> ``'+factions'``
    (bare ``factions`` was deleted by the rework; new spacers hit this hint).
  * ``parser/space_commands.py`` ``@spawn`` unknown-template error pointed at a
    nonexistent ``'ships'`` command -> now lists the real available template
    keys from the in-process registry (``reg.all_templates()``).
"""
import os
import re
import importlib.util

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Files whose ``Type 'X'`` hints are NOT global-registry commands ───────────
# (paths are POSIX-relative to the project root)
_EXCLUDED_FILES = {
    # The chargen input loop runs its own command vocabulary (name/species/
    # set/skill/sheet/review/done/...) handled by engine.creation /
    # creation_wizard, NOT the global command registry.  Guide_02's chargen
    # commands are guarded separately against those handlers.
    "engine/creation.py",
    "engine/creation_wizard.py",
}

# ── Hint tokens that are legitimately NOT command-registry entries ────────────
# Movement EXITS created by the boarding system (engine/boarding.py
# BOARDING_EXIT_DIR_TO / BOARDING_EXIT_DIR_FROM).  A player crosses a boarding
# link by typing the exit name, the same way they type ``north``; exits are
# resolved by the movement system, not the command registry.
_ALLOWED_NON_COMMANDS = {
    "boarding_link",
    "boarding_link_back",
}

# Match the imperative "type 'X'" command hint, but NOT the noun "type 'X'"
# used as a data-type label in schema docstrings (e.g. an ``objects`` row
# ``of type 'breachable'``): exclude a preceding ``of `` and a closing quote
# immediately followed by ``)`` or ``:`` (only the schema docstrings do that;
# every real command hint is followed by whitespace / ``.`` / ``,`` / EOL).
_HINT_RE = re.compile(r"(?<!of )[Tt]ype '([a-zA-Z+@][a-zA-Z0-9 _+/-]*)'(?![):])")


def _base_word(token: str) -> str:
    """The command word a hint points at: first space-delimited token, minus
    any ``/switch`` suffix (``+bounty/track`` -> ``+bounty``)."""
    return token.strip().split()[0].split("/")[0].lower()


def _iter_hints():
    for sub in ("engine", "parser", "server"):
        base = os.path.join(PROJECT_ROOT, sub)
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, PROJECT_ROOT).replace(os.sep, "/")
                if rel in _EXCLUDED_FILES:
                    continue
                with open(full, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for m in _HINT_RE.finditer(line):
                            yield rel, lineno, m.group(1)


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__),
    # the same one the guide-syntax guards resolve against.
    spec = importlib.util.spec_from_file_location(
        "_hintreg_full_registry",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


def test_every_ingame_type_hint_resolves(reg):
    """No live ``Type 'X'`` hint may point at a command that doesn't resolve."""
    broken = []
    seen = 0
    for rel, lineno, token in _iter_hints():
        seen += 1
        word = _base_word(token)
        if word in _ALLOWED_NON_COMMANDS:
            continue
        if reg.get(word) is None:
            broken.append(f"{rel}:{lineno}  Type '{token}'  (base {word!r} unresolved)")
    assert seen > 30, (
        f"only scanned {seen} hints — the scanner regex or walk is broken"
    )
    assert not broken, (
        "in-game command hints point at commands that no longer resolve "
        "against the live registry (post-rework breakage):\n  "
        + "\n  ".join(broken)
    )


def test_allowlisted_tokens_are_genuinely_not_commands(reg):
    """If an allowlisted exit name becomes a real command, drop it from the
    allowlist so the resolve-guard covers it again."""
    for tok in _ALLOWED_NON_COMMANDS:
        assert reg.get(tok) is None, (
            f"{tok!r} now resolves as a command — remove it from "
            "_ALLOWED_NON_COMMANDS so the hint guard covers it"
        )


def test_spacer_quest_factions_hint_is_canonical():
    """Regression pin: the step-8 spacer hint teaches the canonical +factions."""
    path = os.path.join(PROJECT_ROOT, "engine", "spacer_quest.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "Type '+factions'" in text
    assert "Type 'factions'" not in text, (
        "bare 'factions' hint resurfaced — it was deleted by the command rework"
    )


def test_spawn_unknown_template_lists_real_templates():
    """Regression pin: the @spawn error lists real template keys instead of
    pointing at the nonexistent 'ships' command."""
    path = os.path.join(PROJECT_ROOT, "parser", "space_commands.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "Type 'ships'" not in text, (
        "@spawn error still points at the nonexistent 'ships' command"
    )
    assert "Available templates:" in text
    assert "reg.all_templates()" in text
