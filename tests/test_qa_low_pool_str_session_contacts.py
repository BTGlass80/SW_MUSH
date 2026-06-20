"""
QA LOW: two small phantom-import / concurrent-dict fixes (2026-06-20).

1. _pool_to_str added to engine.skill_checks (phantom import in medical_commands).
2. _build_area_contacts uses session_mgr.all() snapshot (not live ._sessions dict).
"""
import importlib
import sys
import types
import pytest


# ── _pool_to_str importable from skill_checks ──────────────────────────────

def test_pool_to_str_importable():
    from engine.skill_checks import _pool_to_str
    assert callable(_pool_to_str)


def test_pool_to_str_no_pips():
    from engine.skill_checks import _pool_to_str
    assert _pool_to_str(4, 0) == "4D"


def test_pool_to_str_with_pips():
    from engine.skill_checks import _pool_to_str
    assert _pool_to_str(4, 2) == "4D+2"


def test_pool_to_str_one_pip():
    from engine.skill_checks import _pool_to_str
    assert _pool_to_str(3, 1) == "3D+1"


def test_pool_to_str_two_dice():
    from engine.skill_checks import _pool_to_str
    assert _pool_to_str(2, 0) == "2D"


def test_pool_to_str_roundtrip():
    from engine.skill_checks import _parse_dice_str, _pool_to_str
    for s in ("2D", "3D+1", "4D+2", "5D"):
        d, p = _parse_dice_str(s)
        assert _pool_to_str(d, p) == s


# ── medical_commands._get_pool_str returns dice string not "?" ──────────────

def test_get_pool_str_import_resolves():
    """After adding _pool_to_str to skill_checks, the import in medical_commands
    must not raise ImportError — previously this phantom import returned '?'."""
    import importlib
    import engine.skill_checks as sc
    # The function must now exist on the module
    assert hasattr(sc, "_pool_to_str"), "_pool_to_str still missing from skill_checks"
    # And medical_commands must be importable without error
    import parser.medical_commands  # noqa: F401


# ── session._build_area_contacts uses .all() not ._sessions.values() ────────

def test_build_area_contacts_uses_all_snapshot(monkeypatch):
    """Confirm _build_area_contacts iterates session_mgr.all() (snapshot),
    not _sessions.values() directly (unsafe under concurrent disconnect)."""
    import ast
    import inspect
    from server.session import Session

    src = inspect.getsource(Session._build_area_contacts)
    # Should NOT reference ._sessions
    assert "._sessions" not in src, (
        "_build_area_contacts still references ._sessions directly — "
        "should use session_mgr.all() to avoid RuntimeError on concurrent disconnect"
    )
    # Should call the .all property (no parentheses — it's a @property)
    assert "session_mgr.all" in src, (
        "_build_area_contacts should use session_mgr.all for a snapshot"
    )


def test_session_manager_all_is_property_returning_list():
    """SessionManager.all is a @property returning a snapshot list."""
    from server.session import SessionManager
    mgr = SessionManager()
    result = mgr.all  # property, not method
    assert isinstance(result, list)
    assert result == []
