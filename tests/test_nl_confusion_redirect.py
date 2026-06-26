"""
test_nl_confusion_redirect.py — FUN tier-3 natural-language confusion redirect.

A non-MUSH newcomer types "what do i do" / "how do i fight?" — instead of a
bare "Huh? Unknown command", the dispatcher now replies with a help redirect
(and the active objective when on a tutorial step). Single-word typos still get
the crisp "Huh? Unknown command".

In-process dispatcher test, mirroring tests/test_named_exit_routing.py.
"""
from __future__ import annotations

import asyncio


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _seed_char(db, name="Newbie"):
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('t','h','t@e.com')")
    await db._db.execute(
        "INSERT INTO zones (name, properties) VALUES ('Z','{}')")
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
        "VALUES ('R', 1, '', '')")
    rid = cur.lastrowid
    cur = await db._db.execute(
        "INSERT INTO characters (account_id, name, species, room_id, credits) "
        "VALUES (1, ?, 'Human', ?, 100)", (name, rid))
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


class _FakeSessionMgr:
    def find_by_character(self, cid): return None
    def __getattr__(self, n):
        if n.startswith("broadcast") or n.startswith("send"):
            async def _noop(*a, **k): return None
            return _noop
        raise AttributeError(n)


class _FakeSession:
    _n = 0
    def __init__(self, character):
        type(self)._n += 1
        self.id = type(self)._n
        self.character = character
        self.is_in_game = True
        self.account = {"is_admin": 0, "is_builder": 0}
        self.sent: list[str] = []
    async def send_line(self, line=""): self.sent.append(line)
    async def send_prompt(self): pass
    def __getattr__(self, n):
        if n.startswith("send") or n.startswith("notify"):
            async def _noop(*a, **k): return None
            return _noop
        raise AttributeError(n)


async def _dispatch(db, sess, raw):
    from parser.commands import CommandRegistry, CommandParser
    from parser.builtin_commands import register_all
    reg = CommandRegistry(); register_all(reg)
    await CommandParser(reg, db, _FakeSessionMgr()).parse_and_dispatch(sess, raw)


def _run(raw):
    async def _t():
        db = await _fresh_db()
        char = await _seed_char(db)
        sess = _FakeSession(char)
        await _dispatch(db, sess, raw)
        return "\n".join(sess.sent)
    return asyncio.run(_t())


def test_question_phrase_redirects_not_huh():
    out = _run("what do i do")
    assert "Unknown command" not in out, f"NL question should not dead-end: {out!r}"
    assert "didn't catch that" in out.lower()
    assert "help" in out.lower()


def test_question_mark_redirects():
    out = _run("how?")
    assert "Unknown command" not in out
    assert "help" in out.lower()


def test_three_word_unknown_redirects():
    out = _run("punch the wall")
    assert "Unknown command" not in out
    assert "didn't catch that" in out.lower()


def test_single_word_typo_still_huh():
    out = _run("asdfgh")
    assert "Unknown command" in out, f"single-word typo should keep the crisp error: {out!r}"
    assert "didn't catch that" not in out.lower()
