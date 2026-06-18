"""
Invariant guard: any item in design_calls_pending_brian that has already been
decided (RESOLVED / EXECUTED / DEFERRED in its status) must be groomed out to
design_calls_resolved_recent.  Keeps the pending queue clean and makes the
"no open design forks" assertion trustworthy.
"""
import json
import pathlib
import pytest

TODO_PATH = pathlib.Path(__file__).parent.parent / "TODO.json"

RESOLVED_MARKERS = ("RESOLVED", "EXECUTED", "DEFERRED")


@pytest.fixture(scope="module")
def todo():
    return json.loads(TODO_PATH.read_text(encoding="utf-8"))


def test_pending_has_no_resolved_entries(todo):
    """No item with a 'RESOLVED/EXECUTED/DEFERRED' status should linger in pending."""
    pending = todo.get("design_calls_pending_brian", [])
    stale = [
        item.get("id", "<no-id>")
        for item in pending
        if any(m in str(item.get("status", "")) for m in RESOLVED_MARKERS)
    ]
    assert stale == [], (
        f"Stale resolved items found in design_calls_pending_brian — "
        f"move them to design_calls_resolved_recent: {stale}"
    )


def test_resolved_recent_contains_known_ids(todo):
    """The 7 morning-report grooming items must be in resolved_recent, not pending."""
    groomed_ids = {
        "ITEM.unified_item_registry",
        "ACH.dsp_atonement_mechanic",
        "PM.approval_pending_store",
        "CITY.dissolution_refund_formula",
        "ERA.tutorial_v2_gcw_profession_chains",
        "SEC.player_online_activity_visibility",
        "H2.faction_mission_system_reconciliation",
    }
    resolved = {
        item.get("id")
        for item in todo.get("design_calls_resolved_recent", [])
    }
    missing = groomed_ids - resolved
    assert not missing, (
        f"Expected groomed IDs not found in design_calls_resolved_recent: {missing}"
    )


def test_pending_ids_absent_from_groomed(todo):
    """None of the 7 groomed IDs should remain in pending."""
    groomed_ids = {
        "ITEM.unified_item_registry",
        "ACH.dsp_atonement_mechanic",
        "PM.approval_pending_store",
        "CITY.dissolution_refund_formula",
        "ERA.tutorial_v2_gcw_profession_chains",
        "SEC.player_online_activity_visibility",
        "H2.faction_mission_system_reconciliation",
    }
    pending_ids = {
        item.get("id")
        for item in todo.get("design_calls_pending_brian", [])
    }
    still_pending = groomed_ids & pending_ids
    assert not still_pending, (
        f"Groomed IDs still present in design_calls_pending_brian: {still_pending}"
    )
