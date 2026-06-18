"""Guard: the comms guide (#21) + the Guide_05 cross-ref teach POST-rework
canonical commands, verified against the SAME live registry game_server builds.

The command-syntax rework (Drops 0-7) deleted the bare query/meta forms and
made the ``+``-prefixed variant canonical.  ``who`` was one of them: DROP 1
merged the channel ``who`` into the builtin ``+who`` and left ``+who`` as the
*sole* key (no bare ``who`` key or alias).  Bare ``who`` now resolves to
nothing — a "command not found" for any new player following the guide.

``Guide_21_Channels_Mail_News.md`` still documented bare ``who`` in five places
(a section header, a code block, two quick-reference tables, and the closing
"Try ``who``" nudge), and ``Guide_05_Space_Systems.md`` referenced "the ``who``
list".  The unit suite never caught it — the convention-invariant test guards
the registry, not free-text guide prose.

This test resolves every command form Guide_21 teaches against the live
registry, asserts the deleted bare ``who`` is gone (registry AND guide text),
and pins the §1/§10 communication-layer count so a future edit can't silently
re-break the new-player guidance.
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
        "_commsreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every comms command Guide_21 teaches must resolve against HEAD ────────────
# Standalone keys + the bare aliases the guide presents as "(alias: x)".
_COMMS_FORMS = [
    "+who",                              # canonical online-players (DROP 1)
    "say", "'", '"',                     # same-room IC speech
    "tt",                                # place-only table-talk
    "page", "p",                         # private whisper
    "comlink", "cl",                     # planet-wide IC
    "fcomm", "fc",                       # faction-wide IC
    "commfreq", "cf",                    # custom frequency
    "ooc", "newbie", "oocsay",           # server-wide OOC
    "tune", "untune",                    # frequency tuning
    "+freqs", "freqs",                   # tuned-frequency list
    "+channels", "channels",             # channel overview
    "+news", "news",                     # galactic news bulletin
    "@mail",                             # persistent mail
    "+scene",                            # Scenario 1 cross-ref (+scene/start)
]


class TestGuideCommandsResolve:
    def test_every_comms_form_resolves(self, reg):
        for form in _COMMS_FORMS:
            assert reg.get(form) is not None, (
                f"Guide_21 teaches {form!r} but it no longer resolves "
                f"against the live registry"
            )

    def test_who_is_plus_prefixed_only(self, reg):
        """Bare ``who`` was deleted in DROP 1 — ``+who`` is the sole canonical.

        This is exactly why the guide had to change; if bare ``who`` ever
        resolves again the guide guidance and this guard both need revisiting.
        """
        plus = reg.get("+who")
        assert plus is not None and plus.key == "+who"
        bare = reg.get("who")
        assert bare is None or bare.key != "+who", (
            "bare 'who' resolves again — re-evaluate the +who canonicalization"
        )

    def test_mail_switches_are_valid(self, reg):
        cmd = reg.get("@mail")
        valid = set(getattr(cmd, "valid_switches", []) or [])
        for sw in ("read", "reply", "forward", "delete", "purge",
                   "send", "unread", "sent", "quick"):
            assert sw in valid, (
                f"Guide_21 documents @mail/{sw} but it is not in "
                f"@mail valid_switches={sorted(valid)}"
            )

    def test_scene_start_switch_valid(self, reg):
        cmd = reg.get("+scene")
        subs = set(getattr(cmd, "valid_switches", []) or [])
        # +scene uses a module _SUBS tuple rather than valid_switches; fall back
        # to confirming the help/usage advertises start if the attr is absent.
        if subs:
            assert "start" in subs
        else:
            assert "start" in (getattr(cmd, "help_text", "") or "").lower()


# ── The deleted bare ``who`` must NOT reappear as a command in the guides ─────
# `+who` is written `` `+who` ``; a backtick immediately followed by `who`
# only matches the broken bare form.
_BARE_WHO = re.compile(r"`who\b")


@pytest.mark.parametrize(
    "guide", ["Guide_21_Channels_Mail_News.md", "Guide_05_Space_Systems.md"]
)
def test_no_bare_who_command_in_guide(guide):
    text = _read(os.path.join(GUIDE_DIR, guide))
    m = _BARE_WHO.search(text)
    assert m is None, (
        f"{guide} still teaches bare `who` (deleted in DROP 1 → `+who`) "
        f"near: ...{text[max(0, m.start() - 30):m.start() + 20]}..."
    )


def test_guide21_teaches_plus_who():
    text = _read(os.path.join(GUIDE_DIR, "Guide_21_Channels_Mail_News.md"))
    assert "`+who`" in text, "Guide_21 must teach the canonical `+who`"


# ── §1 intro layer count must match the §10 numbers table ─────────────────────
def test_communication_layer_count_consistent():
    text = _read(os.path.join(GUIDE_DIR, "Guide_21_Channels_Mail_News.md"))
    assert "Nine communication layers" in text, (
        "§1 intro must say 'Nine communication layers' (matches the 9-row "
        "table and the §10 'Communication layers | 9' figure)"
    )
    assert "Five communication layers" not in text, (
        "stale 'Five communication layers' miscount still present in §1"
    )
    assert "| Communication layers | 9 " in text, (
        "§10 numbers table should record 9 communication layers"
    )
