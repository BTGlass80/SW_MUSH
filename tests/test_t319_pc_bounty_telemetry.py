# -*- coding: utf-8 -*-
"""tests/test_t319_pc_bounty_telemetry.py — T3.19 telemetry for the PvP
player-bounty economy (parser/pc_bounty_commands.py).

The PvP player-bounty system (PG.2) is a closed credit loop DISTINCT from the
NPC ``bounty_board`` faucet (already telemetered): a poster STAKES escrow +
burns a 10% posting fee (sink); a BH Guild hunter is PAID 80% on fulfilment with
20% sunk to the Guild treasury (faucet); cancel/void/expire leak escrow back to
contributors minus the already-sunk fee. Every credit leg already lands in
``credit_log`` per-tag, but nothing rejoins offline into the *contract
lifecycle* — the post→fulfil vs post→cancel/expire funnel, the escrow-amount
distribution against ``MAX_BOUNTY``, and the posting/cancel fee-burn volume.
This drop adds ONE fail-open, sample-tunable ``pc_bounty`` event at each
lifecycle transition: post / stack / cancel / fulfill / void / expire.

The behavioral suite drives the REAL ``BountyCommand`` / ``AdminBountyCommand``
handlers + ``run_pc_bounty_expiry_tick`` against an in-memory ``Database``
(mirroring tests/test_pg2_pc_bounty_session{1,2}.py) and proves: exactly one
event per successful transition with the right action + signed amount + the
fee/sunk/escrow/target/bounty fields; every refusal (insufficient credits,
self-target, …) emits nothing — never a phantom post/fulfil signal; the
``telemetry.pc_bounty_sample`` tunable is honoured; and — the load-bearing
contract — a broken sink NEVER disturbs the post/cancel/fulfil it observes. The
helper schema + the seam wiring are pinned directly.

Run: python -m pytest tests/test_t319_pc_bounty_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import pc_bounty_commands as pcb  # noqa: E402
from parser.pc_bounty_commands import (  # noqa: E402
    BountyCommand, AdminBountyCommand, run_pc_bounty_expiry_tick,
    _emit_pc_bounty, POSTING_FEE_PCT, CANCEL_FEE_PCT,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts with a fresh sink + tunables, and cleans up after."""
    telemetry.reset()
    tunables.reset_tunables()
    yield
    telemetry.reset()
    tunables.reset_tunables()


def _events(ev_type="pc_bounty"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


# ── DB harness (mirrors tests/test_pg2_pc_bounty_session{1,2}.py) ─────────────
async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names, *, faction="", credits=100000):
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('test', 'hash', 't@e.com')"
    )
    out = {}
    for n in names:
        cur = await db._db.execute(
            "INSERT INTO characters "
            "(account_id, name, species, room_id, credits, faction_id) "
            "VALUES (1, ?, 'Human', 1, ?, ?)",
            (n, credits, faction),
        )
        out[n] = cur.lastrowid
    await db._db.commit()
    return {n: await db.get_character(cid) for n, cid in out.items()}


class _FakeSession:
    def __init__(self, character=None, *, admin=False):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 1 if admin else 0, "is_builder": 0}
        self.sent: list = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None


def _ctx_for(session, db, command, args):
    from parser.commands import CommandContext
    return CommandContext(
        session=session, raw_input=f"{command} {args}".strip(),
        command=command, args=args,
        args_list=args.split() if args else [],
        db=db, session_mgr=_FakeSessionManager(),
    )


async def _post(db, poster, target_name, amount, reason="r"):
    sess = _FakeSession(poster)
    await BountyCommand().execute(
        _ctx_for(sess, db, "+pcbounty", f"post {target_name} {amount} {reason}")
    )
    return sess


# ═══════════════════════════════════════════════════════════════════════════
# 1. Helper schema (direct unit tests)
# ═══════════════════════════════════════════════════════════════════════════
class TestEmitHelperSchema:
    def test_emits_one_event_with_envelope_and_fields(self):
        _emit_pc_bounty("post", 5, -11000, escrow=10000, fee=1000,
                        bounty_id=3, target_id=7)
        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["ev"] == "pc_bounty"
        assert e["action"] == "post"
        assert e["char_id"] == 5
        assert e["amount"] == -11000
        assert e["escrow"] == 10000
        assert e["fee"] == 1000
        assert e["bounty_id"] == 3
        assert e["target_id"] == 7
        # Envelope fields always present.
        assert "ts" in e and "seq" in e

    def test_none_extras_dropped(self):
        _emit_pc_bounty("void", 0, 5000, target_id=None, sunk=None,
                        n_contributors=2)
        e = _events()[0]
        assert "target_id" not in e
        assert "sunk" not in e
        assert e["n_contributors"] == 2

    def test_char_id_coerced_to_int_when_parseable(self):
        _emit_pc_bounty("fulfill", "42", 8000)
        assert _events()[0]["char_id"] == 42

    def test_char_id_non_numeric_preserved(self):
        _emit_pc_bounty("fulfill", "abc", 8000)
        assert _events()[0]["char_id"] == "abc"

    def test_amount_coerced_to_int(self):
        _emit_pc_bounty("cancel", 1, 7500.0)
        amt = _events()[0]["amount"]
        assert amt == 7500
        assert isinstance(amt, int)

    def test_caller_cannot_clobber_envelope(self):
        # ev/ts/seq are reserved — the sink drops collisions.
        _emit_pc_bounty("post", 1, -100, ev="HACK", ts="x", seq="y")
        e = _events()[0]
        assert e["ev"] == "pc_bounty"
        assert e["action"] == "post"

    def test_sampling_zero_drops_event(self):
        tunables._TUNABLES["telemetry.pc_bounty_sample"] = 0.0
        _emit_pc_bounty("post", 1, -100)
        assert _events() == []

    def test_sampling_one_keeps_event(self):
        tunables._TUNABLES["telemetry.pc_bounty_sample"] = 1.0
        _emit_pc_bounty("post", 1, -100)
        assert len(_events()) == 1

    def test_fail_open_never_raises(self):
        # A broken emit() underneath must be swallowed.
        with mock.patch("engine.telemetry.emit",
                        side_effect=RuntimeError("boom")):
            _emit_pc_bounty("post", 1, -100)  # must not raise

    def test_tunable_default_is_one_when_unregistered(self):
        # No knob loaded → default 1.0 → event kept.
        tunables.reset_tunables()
        _emit_pc_bounty("post", 1, -100)
        assert len(_events()) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. Behavioral wiring — one event per successful transition
# ═══════════════════════════════════════════════════════════════════════════
class TestPostEmits:
    def test_post_emits_sink_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo", "Greedo"])
            telemetry.reset()  # ignore any boot/setup events
            sess = await _post(db, chars["Solo"], "Greedo", 10000)
            assert "Bounty posted" in "\n".join(sess.sent)
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "post"
            assert e["char_id"] == chars["Solo"]["id"]
            # escrow + 10% fee leaves the poster: -(10000 + 1000)
            assert e["amount"] == -11000
            assert e["escrow"] == 10000
            assert e["fee"] == 10000 * POSTING_FEE_PCT // 100
            assert e["target_id"] == chars["Greedo"]["id"]
            assert e["bounty_id"] > 0
        _run(_check())

    def test_insufficient_credits_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Broke", "T"], credits=500)
            telemetry.reset()
            sess = await _post(db, chars["Broke"], "T", 10000)
            assert "don't have enough" in "\n".join(sess.sent).lower()
            assert _events() == []  # no phantom post
        _run(_check())

    def test_self_target_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Me"])
            telemetry.reset()
            await _post(db, chars["Me"], "Me", 10000)
            assert _events() == []
        _run(_check())

    def test_below_min_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            telemetry.reset()
            await _post(db, chars["P"], "T", 100)  # < MIN_BOUNTY
            assert _events() == []
        _run(_check())


class TestStackEmits:
    def test_stack_emits_sink_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P1", "P2", "T"])
            await _post(db, chars["P1"], "T", 10000)
            telemetry.reset()  # isolate the stack event
            sess = await _post(db, chars["P2"], "T", 5000)
            assert "stacked" in "\n".join(sess.sent).lower()
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "stack"
            assert e["char_id"] == chars["P2"]["id"]
            assert e["amount"] == -(5000 + 500)
            assert e["escrow"] == 5000
            assert e["total_escrow"] == 15000
            assert e["target_id"] == chars["T"]["id"]
        _run(_check())


class TestCancelEmits:
    def test_cancel_emits_faucet_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            await _post(db, chars["P"], "T", 10000)
            telemetry.reset()
            sess = _FakeSession(chars["P"])
            await BountyCommand().execute(
                _ctx_for(sess, db, "+pcbounty", "cancel"))
            assert "canceled" in "\n".join(sess.sent).lower()
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "cancel"
            assert e["char_id"] == chars["P"]["id"]
            # 25% cancel fee burned on 10000 escrow → 7500 refunded.
            cancel_fee = (10000 * CANCEL_FEE_PCT + 99) // 100
            assert e["amount"] == 10000 - cancel_fee
            assert e["fee"] == cancel_fee
            assert e["total_escrow"] == 10000
            assert e["n_contributors"] == 1
        _run(_check())

    def test_no_active_outgoing_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P"])
            telemetry.reset()
            sess = _FakeSession(chars["P"])
            await BountyCommand().execute(
                _ctx_for(sess, db, "+pcbounty", "cancel"))
            assert _events() == []
        _run(_check())


class TestFulfillEmits:
    def test_fulfill_emits_payout_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            bh = await _make_chars(db, ["BH"], faction="bh_guild")
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=86400)
            telemetry.reset()
            sess = _FakeSession(chars["Staff"], admin=True)
            await AdminBountyCommand().execute(
                _ctx_for(sess, db, "@pcbounty", f"fulfill {bid} BH"))
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "fulfill"
            assert e["char_id"] == bh["BH"]["id"]
            # 80% payout, 20% sunk to Guild treasury.
            assert e["amount"] == 8000
            assert e["sunk"] == 2000
            assert e["total_escrow"] == 10000
            assert e["bounty_id"] == bid
            assert e["target_id"] == chars["T"]["id"]
        _run(_check())

    def test_fulfill_unknown_bh_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=86400)
            telemetry.reset()
            sess = _FakeSession(chars["Staff"], admin=True)
            await AdminBountyCommand().execute(
                _ctx_for(sess, db, "@pcbounty", f"fulfill {bid} Nobody"))
            assert _events() == []
        _run(_check())


class TestVoidEmits:
    def test_void_emits_full_refund_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=86400)
            telemetry.reset()
            sess = _FakeSession(chars["Staff"], admin=True)
            await AdminBountyCommand().execute(
                _ctx_for(sess, db, "@pcbounty", f"void {bid} cheating"))
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "void"
            assert e["char_id"] == 0  # staff action, no single actor
            # Void refunds escrow + the otherwise-sunk fee in full.
            assert e["amount"] == 11000
            assert e["bounty_id"] == bid
            assert e["n_contributors"] == 1
        _run(_check())


class TestExpireEmits:
    def test_expire_tick_emits_per_bounty_event(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=-100)
            telemetry.reset()
            summary = await run_pc_bounty_expiry_tick(db)
            assert summary["expired"] == 1
            evs = _events()
            assert len(evs) == 1
            e = evs[0]
            assert e["action"] == "expire"
            assert e["char_id"] == 0  # tick, no actor
            assert e["amount"] == 10000  # stake refunded (fee was sunk)
            assert e["bounty_id"] == bid
            assert e["target_id"] == chars["T"]["id"]
            assert e["n_contributors"] == 1
        _run(_check())

    def test_no_expiry_emits_nothing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=86400)
            telemetry.reset()
            await run_pc_bounty_expiry_tick(db)
            assert _events() == []  # nothing past its window
        _run(_check())


# ═══════════════════════════════════════════════════════════════════════════
# 3. Load-bearing contract — telemetry NEVER disturbs gameplay
# ═══════════════════════════════════════════════════════════════════════════
class TestTelemetryNeverDisturbsGameplay:
    def test_broken_sink_does_not_block_post(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo", "Greedo"])
            with mock.patch("engine.telemetry.emit",
                            side_effect=RuntimeError("sink down")):
                sess = await _post(db, chars["Solo"], "Greedo", 10000)
            # The post still succeeded despite the broken sink.
            assert "Bounty posted" in "\n".join(sess.sent)
            reloaded = await db.get_character(chars["Solo"]["id"])
            assert int(reloaded["credits"]) == 100000 - 11000
            row = await db.get_active_incoming_for_target(chars["Greedo"]["id"])
            assert row is not None and row["amount"] == 10000
        _run(_check())

    def test_broken_sink_does_not_block_fulfill(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            bh = await _make_chars(db, ["BH"], faction="bh_guild")
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"], target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000, duration_seconds=86400)
            sess = _FakeSession(chars["Staff"], admin=True)
            with mock.patch("engine.telemetry.emit",
                            side_effect=RuntimeError("sink down")):
                await AdminBountyCommand().execute(
                    _ctx_for(sess, db, "@pcbounty", f"fulfill {bid} BH"))
            # BH still got paid.
            bh_reloaded = await db.get_character(bh["BH"]["id"])
            assert int(bh_reloaded["credits"]) == 100000 + 8000
        _run(_check())


# ═══════════════════════════════════════════════════════════════════════════
# 4. Source-level wiring pins (drift guards)
# ═══════════════════════════════════════════════════════════════════════════
class TestSourceWiring:
    def test_helper_defined(self):
        assert callable(pcb._emit_pc_bounty)

    def test_all_six_actions_wired(self):
        import re
        src = Path(pcb.__file__).read_text(encoding="utf-8")
        # Each lifecycle action must appear as the first arg of an
        # _emit_pc_bounty(...) call (allow whitespace/newline before it).
        for action in ("post", "stack", "cancel", "fulfill", "void",
                       "expire"):
            pat = r'_emit_pc_bounty\(\s*"' + re.escape(action) + r'"'
            assert re.search(pat, src), f"action {action!r} not wired"

    def test_tunable_registered(self):
        text = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8")
        assert "telemetry.pc_bounty_sample" in text
