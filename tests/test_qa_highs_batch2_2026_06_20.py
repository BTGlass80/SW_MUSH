"""QA playthrough HIGH batch 2 (drop qa-highs-batch2, 2026-06-20).

Regression guards for four confirmed-still-broken HIGH / test-infra findings
from docs/design/QA_PLAYTHROUGH_FINDINGS_2026-06-19.md, each verified against
HEAD before the fix:

* H9  — vendor buy orders accepted any resource string (dead validation guard:
        ``list(RESOURCE_TYPES.keys()) if hasattr(...)`` → ``[]`` because
        RESOURCE_TYPES is a *set*) → real credits escrowed into an unfillable
        order. Fixed to ``list(RESOURCE_TYPES)``.
* H10 — BountyTrack rolled a flat 2D and bypassed the dice funnel
        (``get_skill_pool`` w/o registry → swallowed TypeError → 2D floor;
        then ``roll_d6_pool`` direct). Fixed to route through
        ``perform_skill_check`` (wound penalties / lead+tool bonuses /
        telemetry), mirroring the sister BountyCollect.
* H13 — the command dispatcher leaked raw ``str(e)`` to the player channel.
        Fixed to a generic player line; detail stays in the server log.
* H14 — the test harness ``give_item`` crashed on dict-form inventory
        (``inv.append`` on a dict), masking real defects. Fixed to mirror
        ``db.add_to_inventory`` via ``coerce_inventory``.
"""

import asyncio
import inspect
import json

import pytest


# ── H9 — buy-order resource validation is live (no escrow on garbage) ─────────

class _FakeVendorDB:
    """Minimal async DB for engine.vendor_droids.post_buy_order."""

    def __init__(self, owner_id: int):
        self._owner_id = owner_id
        self.adjust_calls = []
        self.update_calls = []

    async def get_object(self, droid_id):
        return {
            "id": droid_id,
            "owner_id": self._owner_id,
            "name": "Test Commerce Droid",
            # gn12 == Tier 3, the only tier with buy_orders enabled.
            "data": json.dumps({"tier_key": "gn12", "buy_orders": []}),
        }

    async def adjust_credits(self, char_id, delta, tag, *, allow_negative=True):
        # Mirrors the real db.adjust_credits keyword-only allow_negative (QA
        # re-run added allow_negative=False at the escrow site); this fake
        # models a funded owner, so it always succeeds.
        self.adjust_calls.append((char_id, delta, tag))
        return 1_000_000 + delta  # arbitrary post-balance

    async def update_object(self, droid_id, data=None):
        self.update_calls.append((droid_id, data))


def test_h9_buy_order_rejects_unknown_resource_no_escrow():
    from engine import vendor_droids

    char = {"id": 7, "credits": 1_000_000}
    db = _FakeVendorDB(owner_id=7)

    ok, msg = asyncio.run(vendor_droids.post_buy_order(
        char, droid_id=99, resource_type="notarealresource",
        min_quality=1, qty_wanted=5, price_per=10, db=db,
    ))

    assert ok is False, "garbage resource_type must be rejected"
    assert "unknown resource type" in msg.lower()
    # The whole point of H9: NO credits may be escrowed for a bad order.
    assert db.adjust_calls == [], "no escrow may be deducted on rejection"
    assert db.update_calls == [], "no order may be persisted on rejection"


def test_h9_buy_order_accepts_valid_resource():
    from engine import vendor_droids

    char = {"id": 7, "credits": 1_000_000}
    db = _FakeVendorDB(owner_id=7)

    ok, msg = asyncio.run(vendor_droids.post_buy_order(
        char, droid_id=99, resource_type="metal",
        min_quality=1, qty_wanted=5, price_per=10, db=db,
    ))

    assert ok is True, f"a valid resource must be accepted: {msg!r}"
    # A real order escrows credits exactly once and persists the order.
    assert len(db.adjust_calls) == 1
    assert db.adjust_calls[0][1] == -50  # 5 x 10
    assert len(db.update_calls) == 1


def test_h9_validation_guard_is_not_dead():
    """The set→[] regression: list(RESOURCE_TYPES) must be non-empty so the
    ``... and valid_types`` guard actually runs."""
    from engine.crafting import RESOURCE_TYPES
    valid = list(RESOURCE_TYPES)
    assert valid, "RESOURCE_TYPES must enumerate — a dead guard accepts anything"
    assert "metal" in valid


# ── H10 — BountyTrack routes through the dice chokepoint ──────────────────────

def test_h10_bounty_track_uses_perform_skill_check():
    from parser import bounty_commands

    src = inspect.getsource(bounty_commands.BountyTrackCommand.execute)
    assert "perform_skill_check" in src, (
        "BountyTrack must resolve through perform_skill_check (the dice funnel)"
    )
    assert "roll_d6_pool" not in src, (
        "BountyTrack must not roll dice directly (funnel-bypass regression)"
    )


# ── H13 — the dispatcher must not leak raw exception text to players ──────────

def test_h13_dispatcher_does_not_leak_exception_to_player():
    from parser import commands

    src = inspect.getsource(commands.CommandParser._execute)
    # The leak was an f-string interpolating the caught exception into the
    # player-facing send_line. The detail must only reach log.exception.
    assert "({e})" not in src, (
        "raw exception text must not be sent to the player channel"
    )
    assert "log.exception" in src, "the detail must still be logged server-side"


# ── H14 — harness give_item handles dict-form inventory ──────────────────────

class _FakeInner:
    def __init__(self):
        self.last_params = None

    async def execute(self, sql, params):
        self.last_params = params

    async def commit(self):
        pass


class _FakeDB:
    def __init__(self):
        self._db = _FakeInner()


class _FakeHarness:
    """Stub exposing just what _LiveHarness.give_item touches."""

    def __init__(self, row):
        self._row = row
        self.db = _FakeDB()

    async def get_char(self, char_id):
        return self._row


def _run_give_item(inventory_value):
    from tests.harness import _LiveHarness

    stub = _FakeHarness({"id": 1, "inventory": inventory_value})
    item = {"name": "Datapad", "key": "datapad", "slot": "carried", "qty": 1}
    asyncio.run(_LiveHarness.give_item(stub, 1, item))
    written = json.loads(stub.db._db.last_params[0])
    return written


def test_h14_give_item_on_dict_form_inventory():
    written = _run_give_item(json.dumps({"items": [], "resources": []}))
    # Canonical dict shape preserved; item landed in ``items``.
    assert isinstance(written, dict)
    keys = [it.get("key") for it in written["items"]]
    assert "datapad" in keys


def test_h14_give_item_on_bare_list_inventory():
    written = _run_give_item("[]")
    # Bare-list coerces to the canonical dict shape (mirrors add_to_inventory).
    assert isinstance(written, dict)
    keys = [it.get("key") for it in written["items"]]
    assert "datapad" in keys


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
