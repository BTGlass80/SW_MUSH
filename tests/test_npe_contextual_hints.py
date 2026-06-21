# -*- coding: utf-8 -*-
"""
tests/test_npe_contextual_hints.py — NPE-C2 first-hit contextual help
nudges (2026-06-20).

Pins engine/contextual_hints.maybe_emit_first_hit_hint:
  * first use of a tracked subsystem emits ONE sys-event nudge + marks
    the per-character seen_hints flag;
  * a second use of the same subsystem does NOT re-emit;
  * commands sharing a hint_key (shop/buy/sell) fire the nudge once
    across the whole subsystem;
  * untracked commands are no-ops;
  * the persist path writes only `attributes` (never force_sensitive);
  * every hint's guide slug is a REAL guide (no phantom consumer);
  * the helper is best-effort (a throwing transport never raises).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import unittest

from engine.contextual_hints import (
    maybe_emit_first_hit_hint, HINTS, SEEN_HINTS_KEY,
)


class _CapSession:
    def __init__(self, raise_on_send=False):
        self.sent = []  # list[(msg_type, data)]
        self._raise = raise_on_send

    async def send_json(self, msg_type, data):
        if self._raise:
            raise RuntimeError("transport down")
        self.sent.append((msg_type, data))


class _CapDB:
    def __init__(self):
        self.saves = []  # list[(char_id, fields_dict)]

    async def save_character(self, char_id, **fields):
        self.saves.append((char_id, fields))


def _char(attrs=None):
    return {"id": 7, "name": "Newbie",
            "attributes": json.dumps(attrs or {})}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestContextualHints(unittest.TestCase):

    def test_first_attack_emits_and_marks_seen(self):
        sess, db, char = _CapSession(), _CapDB(), _char()
        out = _run(maybe_emit_first_hit_hint(sess, db, char, "attack"))
        self.assertTrue(out, "first attack should emit a hint")
        # exactly one sys-event pose
        self.assertEqual(len(sess.sent), 1)
        mtype, data = sess.sent[0]
        self.assertEqual(mtype, "pose_event")
        self.assertEqual(data.get("event_type"), "sys-event")
        self.assertIn("Ground Combat", data.get("text", ""))
        # seen flag persisted in the attributes blob
        attrs = json.loads(char["attributes"])
        self.assertTrue(attrs.get(SEEN_HINTS_KEY, {}).get("combat"))

    def test_second_attack_does_not_reemit(self):
        sess, db, char = _CapSession(), _CapDB(), _char()
        _run(maybe_emit_first_hit_hint(sess, db, char, "attack"))
        out2 = _run(maybe_emit_first_hit_hint(sess, db, char, "attack"))
        self.assertFalse(out2, "second attack must not re-emit")
        self.assertEqual(len(sess.sent), 1, "only one hint total")

    def test_shop_buy_sell_share_one_subsystem(self):
        sess, db, char = _CapSession(), _CapDB(), _char()
        self.assertTrue(_run(maybe_emit_first_hit_hint(sess, db, char, "shop")))
        # buy + sell share hint_key 'shop' -> already seen, no re-emit
        self.assertFalse(_run(maybe_emit_first_hit_hint(sess, db, char, "buy")))
        self.assertFalse(_run(maybe_emit_first_hit_hint(sess, db, char, "sell")))
        self.assertEqual(len(sess.sent), 1)

    def test_untracked_command_is_noop(self):
        sess, db, char = _CapSession(), _CapDB(), _char()
        out = _run(maybe_emit_first_hit_hint(sess, db, char, "look"))
        self.assertFalse(out)
        self.assertEqual(sess.sent, [])
        self.assertEqual(db.saves, [])  # no persist on a no-op

    def test_persist_writes_only_attributes(self):
        """force_sensitive is derived state — the seen-flag persist must
        write ONLY the attributes column (never a force_sensitive kwarg)."""
        sess, db, char = _CapSession(), _CapDB(), _char()
        _run(maybe_emit_first_hit_hint(sess, db, char, "craft"))
        self.assertEqual(len(db.saves), 1)
        _cid, fields = db.saves[0]
        self.assertEqual(list(fields.keys()), ["attributes"])
        self.assertNotIn("force_sensitive", fields)

    def test_distinct_subsystems_each_fire_once(self):
        sess, db, char = _CapSession(), _CapDB(), _char()
        for k in ("attack", "shop", "craft", "land"):
            _run(maybe_emit_first_hit_hint(sess, db, char, k))
        # four distinct subsystems -> four nudges
        self.assertEqual(len(sess.sent), 4)
        attrs = json.loads(char["attributes"])
        seen = attrs.get(SEEN_HINTS_KEY, {})
        self.assertEqual(set(seen), {"combat", "shop", "craft", "travel"})

    def test_preexisting_attrs_preserved(self):
        """Marking a hint seen must not clobber other attribute keys
        (e.g. tutorial_chain)."""
        sess, db = _CapSession(), _CapDB()
        char = _char({"tutorial_chain": {"chain_id": "republic_soldier",
                                         "step": 2}})
        _run(maybe_emit_first_hit_hint(sess, db, char, "attack"))
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["tutorial_chain"]["chain_id"],
                         "republic_soldier")
        self.assertTrue(attrs[SEEN_HINTS_KEY]["combat"])

    def test_best_effort_swallows_transport_error(self):
        sess, db, char = _CapSession(raise_on_send=True), _CapDB(), _char()
        # Must not raise even though send_json throws.
        out = _run(maybe_emit_first_hit_hint(sess, db, char, "attack"))
        self.assertFalse(out)

    def test_every_hint_slug_is_a_real_guide(self):
        """Phantom-consumer guard: each hint points at a guide slug that
        actually exists in data/guides/ (slug = Title.lower _->-)."""
        real = set()
        for p in (PROJECT_ROOT / "data" / "guides").glob("Guide_*.md"):
            m = re.match(r"Guide_\d+_(.+)", p.stem)
            if m:
                real.add(m.group(1).lower().replace("_", "-"))
        for cmd_key, (_hint, slug, _text) in HINTS.items():
            self.assertIn(
                slug, real,
                f"hint for '{cmd_key}' points at guide slug '{slug}' which "
                f"does not exist in data/guides/. Real slugs: {sorted(real)}"
            )

    def test_hook_is_wired_in_command_dispatch(self):
        """The producer seam: parser/commands.py must call the hint hook
        in its post-execute block with the resolved cmd.key."""
        src = (PROJECT_ROOT / "parser" / "commands.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("maybe_emit_first_hit_hint", src)
        self.assertIn("cmd.key", src)


if __name__ == "__main__":
    unittest.main()
