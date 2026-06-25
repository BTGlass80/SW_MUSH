"""
test_named_exit_routing.py — first-session-unblock parser fix.

The web client advertises room exits by NAME (e.g. "corridor") and players
type / click that name, but the dispatcher's movement fallback only routed
compass words + enter/leave + custom edge words — a bare NAMED exit fell
through to "Huh? Unknown command", stranding the player (the fun-assessment
pass's #1 kills-it). The fix routes a bare unknown word that matches a REAL
exit of the caller's current room to MoveCommand (reusing _match_exit so a
typo still falls through to Unknown command).

In-process dispatcher test, mirroring the seed/fake-session pattern in
tests/test_cities_phase1.py.
"""
from __future__ import annotations

import asyncio


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    # Auxiliary schemas the move auto-look / room render may query.
    try:
        from engine.housing import ensure_schema as _hs
        await _hs(db)
    except Exception:
        pass
    try:
        from engine.territory import ensure_territory_schema as _ts
        await _ts(db)
    except Exception:
        pass
    try:
        from engine.player_cities import ensure_schema as _pc
        await _pc(db)
    except Exception:
        pass
    return db


async def _seed_zone(db, name="Test Zone"):
    cur = await db._db.execute(
        "INSERT INTO zones (name, properties) VALUES (?, '{}')", (name,))
    await db._db.commit()
    return cur.lastrowid


async def _seed_room(db, zone_id, name):
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
        "VALUES (?, ?, '', '')", (name, zone_id))
    await db._db.commit()
    return cur.lastrowid


async def _seed_char(db, name, room_id):
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('t', 'h', 't@e.com')")
    cur = await db._db.execute(
        "INSERT INTO characters (account_id, name, species, room_id, credits) "
        "VALUES (1, ?, 'Human', ?, 1000)", (name, room_id))
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None

    def sessions_in_room(self, room_id):
        return []

    def __getattr__(self, name):
        # Any broadcast_*/send_* the move/auto-look path calls → async no-op.
        if name.startswith("broadcast") or name.startswith("send"):
            async def _noop(*a, **k):
                return None
            return _noop
        raise AttributeError(name)


class _FakeSession:
    _counter = 0

    def __init__(self, character):
        type(self)._counter += 1
        self.id = type(self)._counter
        self.character = character
        self.is_in_game = True
        self.account = {"is_admin": 0, "is_builder": 0}
        self.sent: list[str] = []

    async def send_line(self, line: str = "") -> None:
        self.sent.append(line)

    async def send_prompt(self) -> None:
        pass

    def __getattr__(self, name):
        # Any other send_*/notify_* the engine calls during auto-look → no-op.
        if name.startswith("send") or name.startswith("notify"):
            async def _noop(*a, **k):
                return None
            return _noop
        raise AttributeError(name)


async def _build_dispatcher(db):
    from parser.commands import CommandRegistry, CommandParser
    from parser.builtin_commands import register_all
    reg = CommandRegistry()
    register_all(reg)
    return CommandParser(reg, db, _FakeSessionManager())


def test_typed_named_exit_routes_to_move():
    """Typing a bare NAMED exit ("corridor") walks the player through it."""
    async def _t():
        db = await _fresh_db()
        z = await _seed_zone(db)
        r1 = await _seed_room(db, z, "Briefing Room")
        r2 = await _seed_room(db, z, "Main Corridor")
        await db.create_exit(r1, r2, "corridor")
        char = await _seed_char(db, "Mover", r1)
        disp = await _build_dispatcher(db)
        sess = _FakeSession(char)
        await disp.parse_and_dispatch(sess, "corridor")
        moved = await db.get_character(char["id"])
        assert int(moved["room_id"]) == r2, (
            f"typed named exit 'corridor' did not move the player "
            f"(room_id={moved['room_id']}, expected {r2}). "
            f"sent={sess.sent!r}")
        # And it must NOT have produced an Unknown-command error.
        assert not any("Unknown command" in s for s in sess.sent), (
            f"named exit produced an Unknown-command error: {sess.sent!r}")
    asyncio.run(_t())


def test_typo_still_unknown_command():
    """A non-exit word still falls through to 'Huh? Unknown command' and
    does NOT move the player (routing is gated on a real exit match)."""
    async def _t():
        db = await _fresh_db()
        z = await _seed_zone(db)
        r1 = await _seed_room(db, z, "Briefing Room")
        r2 = await _seed_room(db, z, "Main Corridor")
        await db.create_exit(r1, r2, "corridor")
        char = await _seed_char(db, "Typoer", r1)
        disp = await _build_dispatcher(db)
        sess = _FakeSession(char)
        await disp.parse_and_dispatch(sess, "zzqplmnope")
        still = await db.get_character(char["id"])
        assert int(still["room_id"]) == r1, "a typo should not move the player"
        assert any("Unknown command" in s for s in sess.sent), (
            f"a non-exit word should produce 'Unknown command'; sent={sess.sent!r}")
    asyncio.run(_t())


def test_compass_direction_still_routes():
    """Regression: compass-word movement (the pre-existing path) still works."""
    async def _t():
        db = await _fresh_db()
        z = await _seed_zone(db)
        r1 = await _seed_room(db, z, "Pad")
        r2 = await _seed_room(db, z, "Street")
        await db.create_exit(r1, r2, "north")
        char = await _seed_char(db, "Walker", r1)
        disp = await _build_dispatcher(db)
        sess = _FakeSession(char)
        await disp.parse_and_dispatch(sess, "north")
        moved = await db.get_character(char["id"])
        assert int(moved["room_id"]) == r2, (
            f"compass 'north' regressed (room_id={moved['room_id']}); sent={sess.sent!r}")
    asyncio.run(_t())
