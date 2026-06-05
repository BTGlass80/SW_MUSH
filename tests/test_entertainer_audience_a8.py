# -*- coding: utf-8 -*-
"""
tests/test_entertainer_audience_a8.py — Drop 3 A8: entertainer audience-weighting.

The perform faucet is already metered through the ledger (tag `entertainer`,
Drop 1). A8 adds **audience-weighting**: a modest, capped bonus when other
online players are present in the room, so performing rewards being a social
hub rather than a solo timer-tap.

Covers:
  * the pure `audience_multiplier` math (bounds + cap);
  * `_count_audience` against a fake session manager (counts *other* players,
    excludes self by id, defensive 0 on failure);
  * `_audience_flavor` branches;
  * structural pins that the perform handler applies the multiplier, routes the
    payout through the `entertainer` ledger tag, and no longer carries the dead
    pre-ledger direct credit mutation.
"""

import os
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.entertainer_commands import (                               # noqa: E402
    audience_multiplier, _audience_flavor, _count_audience,
    _AUDIENCE_BONUS_PER, _AUDIENCE_CAP,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure multiplier math
# ─────────────────────────────────────────────────────────────────────────────
class TestAudienceMultiplier(unittest.TestCase):
    def test_no_audience_is_neutral(self):
        self.assertEqual(audience_multiplier(0), 1.0)

    def test_scales_per_head(self):
        self.assertAlmostEqual(audience_multiplier(1), 1.0 + _AUDIENCE_BONUS_PER)
        self.assertAlmostEqual(audience_multiplier(2),
                               1.0 + 2 * _AUDIENCE_BONUS_PER)

    def test_caps_at_cap(self):
        at_cap = 1.0 + _AUDIENCE_CAP * _AUDIENCE_BONUS_PER
        self.assertAlmostEqual(audience_multiplier(_AUDIENCE_CAP), at_cap)
        # Beyond the cap, no further growth.
        self.assertAlmostEqual(audience_multiplier(_AUDIENCE_CAP + 5), at_cap)

    def test_modest_ceiling(self):
        # Sanity: the bonus stays modest (≤ +100%) by design.
        self.assertLessEqual(audience_multiplier(999), 2.0)

    def test_garbage_inputs_safe(self):
        self.assertEqual(audience_multiplier(-3), 1.0)
        self.assertEqual(audience_multiplier(None), 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. _count_audience — fake session manager
# ─────────────────────────────────────────────────────────────────────────────
class _FakeSession:
    def __init__(self, cid):
        self.character = {"id": cid, "room_id": 50}


class _FakeSessionMgr:
    def __init__(self, sessions, *, raise_exc=False):
        self._sessions = sessions
        self._raise = raise_exc

    def sessions_in_room(self, room_id, *, source_char=None):
        if self._raise:
            raise RuntimeError("session mgr boom")
        # Mirrors the real method: returns ALL in-room sessions, INCLUDING the
        # source character (it does not self-exclude).
        return list(self._sessions)


class TestCountAudience(unittest.TestCase):
    def _char(self, cid=1):
        return {"id": cid, "room_id": 50}

    def test_excludes_self_counts_others(self):
        # Performer (1) plus two other players (2, 3) in the room → audience 2.
        mgr = _FakeSessionMgr([_FakeSession(1), _FakeSession(2), _FakeSession(3)])
        self.assertEqual(_count_audience(mgr, self._char(1), 50), 2)

    def test_solo_performer_has_zero_audience(self):
        mgr = _FakeSessionMgr([_FakeSession(1)])
        self.assertEqual(_count_audience(mgr, self._char(1), 50), 0)

    def test_session_without_character_ignored(self):
        bad = _FakeSession(2)
        bad.character = None
        mgr = _FakeSessionMgr([_FakeSession(1), bad, _FakeSession(3)])
        self.assertEqual(_count_audience(mgr, self._char(1), 50), 1)

    def test_exception_yields_zero(self):
        mgr = _FakeSessionMgr([], raise_exc=True)
        self.assertEqual(_count_audience(mgr, self._char(1), 50), 0)

    def test_none_session_mgr_yields_zero(self):
        self.assertEqual(_count_audience(None, self._char(1), 50), 0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. _audience_flavor branches
# ─────────────────────────────────────────────────────────────────────────────
class TestAudienceFlavor(unittest.TestCase):
    def test_branches(self):
        self.assertIn("packed", _audience_flavor(_AUDIENCE_CAP).lower())
        self.assertIn("crowd", _audience_flavor(2).lower())
        self.assertIn("onlooker", _audience_flavor(1).lower())


# ─────────────────────────────────────────────────────────────────────────────
# 4. Structural pins
# ─────────────────────────────────────────────────────────────────────────────
def _src(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_handler_applies_audience_weighting(self):
        src = _src("parser", "entertainer_commands.py")
        self.assertIn("_count_audience(ctx.session_mgr", src)
        self.assertIn("audience_multiplier(audience)", src)

    def test_payout_still_routes_through_entertainer_ledger_tag(self):
        src = _src("parser", "entertainer_commands.py")
        self.assertIn('adjust_credits(', src)
        self.assertIn('"entertainer"', src)

    def test_dead_pre_ledger_mutation_removed(self):
        # The old redundant in-memory credit write (overwritten by the ledger
        # call) is gone — no unlogged credit mutation in the perform payout.
        src = _src("parser", "entertainer_commands.py")
        self.assertNotIn('new_credits = char.get("credits", 0) + payout', src)


if __name__ == "__main__":
    unittest.main()
