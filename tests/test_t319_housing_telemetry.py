# -*- coding: utf-8 -*-
"""tests/test_t319_housing_telemetry.py — T3.19 telemetry for the player-housing
economy (engine/housing.py).

The credit legs already ride ``credit_flow`` (adjust_credits tags
``housing_purchase`` / ``housing_rent`` / ``housing_deposit_refund`` /
``home_prestige``), but those isolated ledger rows can't be rejoined offline
into the housing *lifecycle* — the acquire → weekly-rent → overdue → forfeit
funnel, the voluntary-checkout churn, or the deposit-forfeit rate. This drop
adds ONE fail-open, sample-tunable ``housing`` event at each credit-moving
transition: acquire (``rent_room``), rent_paid + rent_overdue
(``tick_housing_rent``), checkout (``checkout_room``), and prestige
(``purchase_home_prestige``).

The behavioral suite drives the REAL engine functions against the in-memory
harness DB and proves: exactly one event per transition with the right action +
signed amount + the lifecycle fields; the refused-overdraw acquire emits
nothing; the ``telemetry.housing_sample`` tunable is honoured; and — the
load-bearing contract — a broken sink NEVER disturbs the rent/acquire/checkout
it observes. The helper schema + the seam wiring are pinned directly.

Run: python -m pytest tests/test_t319_housing_telemetry.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

ACQUIRE_COST = housing.TIER1_DEPOSIT + housing.TIER1_WEEKLY_RENT  # 550


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts with a fresh sink + tunables, and cleans up after."""
    telemetry.reset()
    tunables.reset_tunables()
    yield
    telemetry.reset()
    tunables.reset_tunables()


def _events(ev_type="housing"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _NoSessions:
    """Minimal session_mgr for tick_housing_rent — no live sessions, so the
    player-notify send_line path is skipped."""

    def find_by_character(self, char_id):
        return None


async def _make_lot(harness, *, planet="tatooine", label="Tele Lot",
                    security="contested", max_homes=5):
    """Create a lobby room + a housing_lots row, return (lot_id, room_id)."""
    room_id = await harness.db.create_room(
        name=label, desc_short="A test housing lobby.",
        desc_long="A test housing lobby.", zone_id=None,
        properties=json.dumps({"security": security}),
    )
    cur = await harness.db.execute(
        """INSERT INTO housing_lots
           (room_id, planet, label, security, max_homes, current_homes)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (room_id, planet, label, security, max_homes),
    )
    await harness.db.commit()
    return cur.lastrowid, room_id


async def _force_rent_due(harness, housing_id):
    """Drive the policy's rent clock into the past so the next tick collects."""
    await harness.db.execute(
        "UPDATE player_housing SET rent_paid_until = 0 WHERE id = ?",
        (housing_id,),
    )
    await harness.db.commit()


# ── acquire: rent_room emits one event, the deposit+first-week sink ───────────
class TestAcquireEmit:
    async def test_rent_room_emits_acquire(self, harness):
        lot_id, _ = await _make_lot(harness, label="Acquire Lot")
        s = await harness.login_as("HouseAcquire", credits=5000)
        char = dict(s.character)

        res = await housing.rent_room(harness.db, char, lot_id)
        assert res["ok"] is True, res.get("msg")

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "acquire"
        assert e["char_id"] == s.character["id"]
        assert e["amount"] == -ACQUIRE_COST          # the sink delta
        assert e["deposit"] == housing.TIER1_DEPOSIT
        assert e["weekly_rent"] == housing.TIER1_WEEKLY_RENT
        assert e["lot_id"] == lot_id
        assert e["housing_type"] == "rented_room"

    async def test_refused_overdraw_emits_nothing(self, harness):
        """A refused acquire (live DB can't cover the cached balance) leaves no
        room AND no telemetry — never a phantom acquire signal."""
        lot_id, _ = await _make_lot(harness, label="Refuse Lot")
        s = await harness.login_as("HouseRefuse", credits=5000)
        cid = s.character["id"]
        await harness.db.execute(
            "UPDATE characters SET credits = 1 WHERE id = ?", (cid,))
        await harness.db.commit()

        char = dict(s.character)   # carries the stale cached 5000
        res = await housing.rent_room(harness.db, char, lot_id)
        assert res["ok"] is False
        assert _events() == []

    async def test_acquire_amount_matches_ledger_leg(self, harness):
        lot_id, _ = await _make_lot(harness, label="Ledger Lot")
        s = await harness.login_as("HouseLedger", credits=5000)
        cid = s.character["id"]
        await housing.rent_room(harness.db, dict(s.character), lot_id)

        e = _events()[0]
        led = await harness.db.fetchall(
            "SELECT delta FROM credit_log "
            "WHERE char_id = ? AND source = 'housing_purchase'", (cid,))
        assert len(led) == 1
        assert e["amount"] == led[0]["delta"] == -ACQUIRE_COST


# ── checkout: the deposit-refund faucet ───────────────────────────────────────
class TestCheckoutEmit:
    async def test_voluntary_checkout_emits_refund_faucet(self, harness):
        lot_id, _ = await _make_lot(harness, label="Checkout Lot")
        s = await harness.login_as("HouseCheckout", credits=5000)
        await housing.rent_room(harness.db, dict(s.character), lot_id)
        telemetry.get_sink().drain()   # discard the acquire event

        char = dict(s.character)
        res = await housing.checkout_room(harness.db, char)
        assert res["ok"] is True, res.get("msg")

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "checkout"
        assert e["char_id"] == s.character["id"]
        assert e["amount"] == housing.TIER1_DEPOSIT     # refund faucet
        assert e["refund"] == housing.TIER1_DEPOSIT
        assert e["forfeited"] is False
        assert e["housing_type"] == "rented_room"
        # The refund credit landed.
        after = await harness.get_credits(s.character["id"])
        assert after == 5000 - ACQUIRE_COST + housing.TIER1_DEPOSIT
        # The teardown fully completed: the housing record is gone (the pre-fix
        # FK-ordering bug crashed before reaching this).
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?",
            (s.character["id"],))
        assert rows == []


# ── checkout teardown is FK-safe (regression: characters.home_room_id FK) ─────
class TestCheckoutTeardownFKSafe:
    async def test_full_teardown_no_crash_rooms_deleted(self, harness):
        """checkout_room must clear home_room_id before deleting the room, so
        the rooms/player_housing teardown never FK-crashes under
        PRAGMA foreign_keys=ON (production posture)."""
        lot_id, _ = await _make_lot(harness, label="Teardown Lot")
        s = await harness.login_as("HouseTeardown", credits=5000)
        cid = s.character["id"]
        res = await housing.rent_room(harness.db, dict(s.character), lot_id)
        room_id = res["room_id"]

        out = await housing.checkout_room(harness.db, dict(s.character))
        assert out["ok"] is True

        # The private room is gone, the housing record is gone, and the
        # character no longer points at a deleted room.
        assert await harness.db.get_room(room_id) is None
        hrows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (cid,))
        assert hrows == []
        crows = await harness.db.fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (cid,))
        assert crows[0]["home_room_id"] in (None, 0)


# ── rent tick: the recurring sink + the overdue (no-collect) tick ─────────────
class TestRentTickEmit:
    async def test_rent_paid_emits_sink(self, harness):
        lot_id, _ = await _make_lot(harness, label="RentPaid Lot")
        s = await harness.login_as("HouseRentPaid", credits=5000)
        res = await housing.rent_room(harness.db, dict(s.character), lot_id)
        telemetry.get_sink().drain()   # discard acquire
        await _force_rent_due(harness, res["housing_id"])

        await housing.tick_housing_rent(harness.db, _NoSessions())

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "rent_paid"
        assert e["char_id"] == s.character["id"]
        assert e["amount"] == -housing.TIER1_WEEKLY_RENT
        assert e["weekly_rent"] == housing.TIER1_WEEKLY_RENT

    async def test_overdue_emits_zero_amount_with_week_count(self, harness):
        lot_id, _ = await _make_lot(harness, label="Overdue Lot")
        s = await harness.login_as("HouseOverdue", credits=5000)
        cid = s.character["id"]
        res = await housing.rent_room(harness.db, dict(s.character), lot_id)
        telemetry.get_sink().drain()   # discard acquire
        # Drain the player below the weekly rent so the tick can't collect.
        await harness.db.execute(
            "UPDATE characters SET credits = 0 WHERE id = ?", (cid,))
        await _force_rent_due(harness, res["housing_id"])

        await housing.tick_housing_rent(harness.db, _NoSessions())

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "rent_overdue"
        assert e["char_id"] == cid
        assert e["amount"] == 0           # nothing collected
        assert e["weeks_overdue"] == 1
        assert e["weekly_rent"] == housing.TIER1_WEEKLY_RENT


# ── prestige: the cosmetic-tier sink (driven with a synthetic policy row) ─────
class TestPrestigeEmit:
    async def test_prestige_emits_sink(self, harness):
        nxt = housing.next_prestige_tier(0)
        if nxt is None:
            pytest.skip("no prestige tiers configured")
        cost = int(nxt["cost"])
        s = await harness.login_as("HousePrestige", credits=cost + 1000)
        char = dict(s.character)
        # purchase_home_prestige UPDATEs player_housing by id; a synthetic id is
        # fine — the no-op UPDATE commits, the debit + emit fire on success.
        res = await housing.purchase_home_prestige(
            harness.db, char, {"id": 999_999, "prestige_level": 0})
        assert res["ok"] is True, res.get("reason")

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "prestige"
        assert e["char_id"] == s.character["id"]
        assert e["amount"] == -cost
        assert e["level"] == 1
        assert e["cost"] == cost


# ── sampling honours the tunable; the transaction still lands ─────────────────
class TestSampling:
    async def test_sample_zero_suppresses_event_not_the_rent(self, harness):
        tunables._TUNABLES["telemetry.housing_sample"] = 0.0
        lot_id, _ = await _make_lot(harness, label="Sample Lot")
        s = await harness.login_as("HouseSample", credits=5000)
        cid = s.character["id"]
        res = await housing.rent_room(harness.db, dict(s.character), lot_id)

        assert res["ok"] is True
        assert _events() == []
        # The rent still debited despite no telemetry.
        after = await harness.get_credits(cid)
        assert after == 5000 - ACQUIRE_COST


# ── load-bearing: a broken sink never disturbs the housing transaction ────────
class TestFailOpen:
    async def test_emit_raises_rent_still_succeeds(self, harness):
        lot_id, _ = await _make_lot(harness, label="FailOpen Lot")
        s = await harness.login_as("HouseFailOpen", credits=5000)
        cid = s.character["id"]

        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        char = dict(s.character)
        with mock.patch.object(telemetry, "emit", _boom):
            res = await housing.rent_room(harness.db, char, lot_id)

        assert res["ok"] is True           # no crash
        after = await harness.get_credits(cid)
        assert after == 5000 - ACQUIRE_COST   # the debit + room creation landed
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (cid,))
        assert len(rows) == 1


# ── helper unit: per-action field schema + coercion ───────────────────────────
class TestHelperSchema:
    def test_acquire_schema(self):
        housing._emit_housing("acquire", 7, -550, deposit=500, weekly_rent=50,
                              lot_id=3, housing_type="rented_room")
        e = _events()[0]
        assert e["action"] == "acquire"
        assert e["char_id"] == 7
        assert e["amount"] == -550
        assert e["deposit"] == 500
        assert e["lot_id"] == 3

    def test_checkout_forfeited_flag_preserved(self):
        housing._emit_housing("checkout", 7, 0, refund=0, forfeited=True,
                              housing_type="rented_room")
        e = _events()[0]
        assert e["action"] == "checkout"
        assert e["amount"] == 0
        assert e["forfeited"] is True
        assert e["refund"] == 0

    def test_none_extra_fields_dropped(self):
        housing._emit_housing("rent_paid", 7, -50, weekly_rent=50,
                              housing_type=None)
        e = _events()[0]
        assert "housing_type" not in e   # None dropped
        assert e["weekly_rent"] == 50

    def test_none_id_coerced_safely(self):
        # Fail-open coercion: a None id never raises (lands unchanged).
        housing._emit_housing("acquire", None, -550)
        e = _events()[0]
        assert "char_id" in e

    def test_str_id_coerced_to_int(self):
        housing._emit_housing("acquire", "42", -550)
        assert _events()[0]["char_id"] == 42


# ── source pins: every credit seam routes through the helper ──────────────────
class TestSeamWiring:
    @classmethod
    def setup_class(cls):
        cls.src = (PROJECT_ROOT / "engine" / "housing.py").read_text(
            encoding="utf-8")

    @pytest.mark.parametrize("action", [
        '"acquire"', '"rent_paid"', '"rent_overdue"', '"checkout"',
        '"prestige"',
    ])
    def test_action_wired(self, action):
        assert f"_emit_housing({action}" in self.src, (
            f"housing.py must emit the {action} transition")

    def test_tunable_documented_in_yaml(self):
        ty = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8")
        assert "telemetry.housing_sample:" in ty
