# -*- coding: utf-8 -*-
"""
tests/test_audit_fix_faction_economy_2026_07_03.py

Regression tests for LANE C of the signal-producer-audit fixes
(drop/audit-fix-faction-economy), findings F7 / F6 / F3.

All three drive REAL production seams against a real
``db.database.Database(':memory:')`` -- no hand-injected treasury or
influence values. Fixture setup (accounts, characters, orgs, rooms,
memberships) uses direct inserts / the DB API the way sibling test files
in this suite do; every CREDIT or INFLUENCE value under test is produced
by calling the real funnel function (``adjust_org_treasury`` via the real
command/tick, ``adjust_credits``, ``adjust_territory_influence`` via the
real ``invest_influence``).

Sections
========
  1. TestF7TreasuryAddUnknownCode  -- admin `@faction treasury add` no
                                       longer silently no-ops on a typo'd
                                       org code; a known code still moves
                                       the real balance.
  2. TestF6TerritoryIncomeFaucet   -- the new territory-income faucet
                                       (engine.territory.tick_territory_income)
                                       fires from the real
                                       faction_payroll_tick seam and lands
                                       BEFORE that same tick's stipend
                                       sink debits it.
  3. TestF6DonateCommand           -- the previously-phantom `faction
                                       donate <amount>` member faucet:
                                       debits the donor, credits the
                                       treasury, awards capped weekly rep.
  4. TestF3ContestAutoDeclare      -- zone-keyed influence producers
                                       (real `invest_influence`, no
                                       region_slug) now resolve the
                                       zone's owned regions and trigger
                                       the real contest auto-declare.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────

async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(db, *, name, credits=0, room_id=1):
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid
    attrs = json.dumps({"strength": "3D", "perception": "3D"})
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, room_id, attrs, "{}", '{"items":[]}', credits, 0),
    )
    await db._db.commit()
    return cur.lastrowid


async def _make_faction(db, *, code="test_faction", name="Test Faction",
                         treasury=0):
    org_cur = await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, treasury, properties) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, name, "faction", treasury, "{}"),
    )
    await db._db.commit()
    return org_cur.lastrowid


async def _add_member(db, org_id, char_id, *, rank_level=0, standing="good"):
    await db._db.execute(
        "INSERT INTO org_memberships "
        "(char_id, org_id, rank_level, standing) "
        "VALUES (?, ?, ?, ?)",
        (char_id, org_id, rank_level, standing),
    )
    await db._db.commit()


async def _treasury(db, org_id):
    rows = await db._db.execute_fetchall(
        "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
    )
    return int(rows[0]["treasury"])


async def _credits(db, char_id):
    row = await db.get_character(char_id)
    return int(row["credits"])


class _Sess:
    """Minimal session stand-in: captures every send_line call."""

    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line):
        self.sent.append(line)

    @property
    def text(self):
        return "\n".join(self.sent)


class _Ctx:
    """Minimal CommandContext stand-in (db + args + session)."""

    def __init__(self, db, args="", character=None, session_mgr=None):
        self.db = db
        self.args = args
        self.session = _Sess(character)
        self.session_mgr = session_mgr


# ──────────────────────────────────────────────────────────────────────
# 1. F7 — admin `@faction treasury add` unknown-code guard
# ──────────────────────────────────────────────────────────────────────

class TestF7TreasuryAddUnknownCode(unittest.TestCase):

    def test_unknown_code_errors_and_touches_nothing(self):
        from parser.faction_leader_commands import AdminFactionLeaderCommand

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="republic",
                                         name="Galactic Republic",
                                         treasury=0)
            cmd = AdminFactionLeaderCommand()
            ctx = _Ctx(db, args="treasury add republick 5000")
            await cmd.execute(ctx)
            out = ctx.session.text
            self.assertIn("Unknown faction code", out)
            self.assertIn("republick", out)
            # The real republic org's treasury must be untouched.
            self.assertEqual(await _treasury(db, org_id), 0)
        _run(go())

    def test_known_code_moves_the_real_balance(self):
        from parser.faction_leader_commands import AdminFactionLeaderCommand

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="republic",
                                         name="Galactic Republic",
                                         treasury=0)
            cmd = AdminFactionLeaderCommand()
            ctx = _Ctx(db, args="treasury add republic 5000")
            await cmd.execute(ctx)
            out = ctx.session.text
            self.assertIn("New balance: 5,000 cr", out)
            self.assertEqual(await _treasury(db, org_id), 5000)
        _run(go())

    def test_unknown_code_lists_valid_codes(self):
        """The error message should help an admin fix the typo."""
        from parser.faction_leader_commands import AdminFactionLeaderCommand

        async def go():
            db = await _fresh_db()
            await _make_faction(db, code="cis", name="CIS", treasury=0)
            cmd = AdminFactionLeaderCommand()
            ctx = _Ctx(db, args="treasury add si 100")
            await cmd.execute(ctx)
            self.assertIn("cis", ctx.session.text)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 2. F6a — territory income faucet paired with the payroll sink
# ──────────────────────────────────────────────────────────────────────

class TestF6TerritoryIncomeFaucet(unittest.TestCase):

    def test_income_lands_before_stipend_tick_in_same_call(self):
        """A faction with real territory influence and zero treasury
        gets funded by tick_territory_income (called from inside
        faction_payroll_tick) BEFORE that same tick's stipend debit."""
        from engine.organizations import faction_payroll_tick, STIPEND_TABLE
        from engine.territory import (
            ensure_territory_schema, adjust_territory_influence,
        )

        async def go():
            db = await _fresh_db()
            await ensure_territory_schema(db)
            org_id = await _make_faction(db, code="test_income",
                                         name="Test Income Faction",
                                         treasury=0)
            # Real funnel: push the org's zone influence to 75
            # (THRESHOLD_DOMINANCE) via the SAME funnel invest/presence
            # use -- adjust_territory_influence, no region_slug (the
            # producer shape under audit).
            await adjust_territory_influence(
                db, "test_income", zone_id=999, delta=75,
                reason="test seed (real funnel)")

            member = await _make_char(db, name="Payee")
            await _add_member(db, org_id, member, rank_level=1)
            STIPEND_TABLE[("test_income", 1)] = 50
            try:
                total_paid = await faction_payroll_tick(db)
                # Income (75 * 7 = 525cr) landed, stipend (50cr) paid
                # from it in the SAME tick: 525 - 50 = 475 remaining.
                self.assertEqual(await _treasury(db, org_id), 475)
                self.assertEqual(total_paid, 50)
                self.assertEqual(await _credits(db, member), 50)
            finally:
                STIPEND_TABLE.pop(("test_income", 1), None)
        _run(go())

    def test_zero_influence_org_gets_no_income(self):
        from engine.organizations import faction_payroll_tick
        from engine.territory import ensure_territory_schema

        async def go():
            db = await _fresh_db()
            await ensure_territory_schema(db)
            org_id = await _make_faction(db, code="test_no_influence",
                                         treasury=0)
            await faction_payroll_tick(db)
            self.assertEqual(await _treasury(db, org_id), 0)
        _run(go())

    def test_missing_territory_schema_fails_open(self):
        """No ensure_territory_schema call at all (mirrors the
        pre-existing payroll test fixtures) -- faction_payroll_tick
        must not raise, and normal payroll still runs."""
        from engine.organizations import faction_payroll_tick, STIPEND_TABLE

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="test_faction",
                                         treasury=100)
            member = await _make_char(db, name="Solo")
            await _add_member(db, org_id, member, rank_level=1)
            STIPEND_TABLE[("test_faction", 1)] = 50
            try:
                total = await faction_payroll_tick(db)
                self.assertEqual(total, 50)
                self.assertEqual(await _credits(db, member), 50)
            finally:
                STIPEND_TABLE.pop(("test_faction", 1), None)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 3. F6b — member `faction donate <amount>` faucet
# ──────────────────────────────────────────────────────────────────────

class TestF6DonateCommand(unittest.TestCase):

    def test_donate_debits_donor_credits_org_awards_rep(self):
        from parser.faction_commands import FactionCommand

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="test_donate",
                                         treasury=0)
            char_id = await _make_char(db, name="Donor", credits=1000)
            await _add_member(db, org_id, char_id, rank_level=0)
            char = await db.get_character(char_id)
            char["faction_id"] = "test_donate"

            cmd = FactionCommand()
            ctx = _Ctx(db, args="donate 500", character=char)
            await cmd._cmd_donate(ctx, char, "500")

            self.assertEqual(await _credits(db, char_id), 500)
            self.assertEqual(await _treasury(db, org_id), 500)
            mem = await db.get_membership(char_id, org_id)
            self.assertEqual(mem["rep_score"], 5)  # 500 // 100 * 1 rep
            self.assertIn("Donated", ctx.session.text)
        _run(go())

    def test_donate_weekly_rep_cap_enforced_credits_still_move(self):
        from parser.faction_commands import FactionCommand

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="test_donate_cap",
                                         treasury=0)
            char_id = await _make_char(db, name="BigDonor", credits=5000)
            await _add_member(db, org_id, char_id, rank_level=0)
            char = await db.get_character(char_id)
            char["faction_id"] = "test_donate_cap"

            cmd = FactionCommand()
            # First donation: 1500cr -> 15 rep (under the 20 cap).
            ctx1 = _Ctx(db, args="donate 1500", character=char)
            await cmd._cmd_donate(ctx1, char, "1500")
            char = await db.get_character(char_id)
            char["faction_id"] = "test_donate_cap"
            mem = await db.get_membership(char_id, org_id)
            self.assertEqual(mem["rep_score"], 15)

            # Second donation same week: 1500cr -> only 5 more rep fits
            # under the cap (20 - 15), even though 15 would be eligible.
            ctx2 = _Ctx(db, args="donate 1500", character=char)
            await cmd._cmd_donate(ctx2, char, "1500")
            mem = await db.get_membership(char_id, org_id)
            self.assertEqual(mem["rep_score"], 20)
            # Credits/treasury still moved in full for both donations —
            # only the REP award is capped.
            self.assertEqual(await _treasury(db, org_id), 3000)
            self.assertEqual(await _credits(db, char_id), 2000)
            # Only +5 rep landed on the second donation (partial, capped),
            # not the full +15 that 1,500cr would normally earn.
            self.assertIn("+5 rep", ctx2.session.text)

            # Third donation: cap is fully exhausted (rep already at 20) —
            # credits/treasury still move, but zero rep, and the message
            # says so.
            ctx3 = _Ctx(db, args="donate 200", character=char)
            await cmd._cmd_donate(ctx3, char, "200")
            mem = await db.get_membership(char_id, org_id)
            self.assertEqual(mem["rep_score"], 20)
            self.assertEqual(await _treasury(db, org_id), 3200)
            self.assertIn("cap reached", ctx3.session.text)
        _run(go())

    def test_donate_rejects_non_member(self):
        from parser.faction_commands import FactionCommand

        async def go():
            db = await _fresh_db()
            await _make_faction(db, code="test_donate_nomember", treasury=0)
            char_id = await _make_char(db, name="Outsider", credits=1000)
            char = await db.get_character(char_id)
            char["faction_id"] = "test_donate_nomember"

            cmd = FactionCommand()
            ctx = _Ctx(db, args="donate 500", character=char)
            await cmd._cmd_donate(ctx, char, "500")
            # No membership row -> rejected, no credits moved.
            self.assertEqual(await _credits(db, char_id), 1000)
            self.assertIn("member", ctx.session.text.lower())
        _run(go())

    def test_donate_rejects_unaffordable_amount(self):
        from parser.faction_commands import FactionCommand

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, code="test_donate_broke",
                                         treasury=0)
            char_id = await _make_char(db, name="Broke", credits=10)
            await _add_member(db, org_id, char_id, rank_level=0)
            char = await db.get_character(char_id)
            char["faction_id"] = "test_donate_broke"

            cmd = FactionCommand()
            ctx = _Ctx(db, args="donate 500", character=char)
            await cmd._cmd_donate(ctx, char, "500")
            self.assertEqual(await _credits(db, char_id), 10)
            self.assertEqual(await _treasury(db, org_id), 0)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 4. F3 — zone-keyed influence producers now trigger contest auto-declare
# ──────────────────────────────────────────────────────────────────────

class TestF3ContestAutoDeclare(unittest.TestCase):

    async def _seed_rival_region(self, db, *, zone_id, region_slug,
                                  owner_code):
        """Real-shape fixture: a landmark room + a region_ownership row.
        Structural world state, not a treasury/influence value."""
        room_id = await db.create_room(
            name=f"{region_slug} landmark", zone_id=zone_id)
        await db.execute(
            "UPDATE rooms SET wilderness_region_id = ? WHERE id = ?",
            (region_slug, room_id))
        await db.execute(
            """INSERT INTO region_ownership
               (region_slug, org_code, zone_id, claimed_by, claimed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (region_slug, owner_code, zone_id, 1, time.time()))
        await db.commit()
        return room_id

    def test_invest_with_no_region_slug_still_auto_declares(self):
        """The audit's exact producer shape: invest_influence (real
        `faction invest` command function) passes NO region_slug. Per
        the F3 fix, adjust_territory_influence must still resolve the
        zone's owned regions and run the real auto-declare check."""
        from engine.territory import ensure_territory_schema, invest_influence
        from engine.organizations import seed_organizations

        async def go():
            db = await _fresh_db()
            await ensure_territory_schema(db)
            await seed_organizations(db, era="clone_wars")

            zone_id = 42
            await self._seed_rival_region(
                db, zone_id=zone_id, region_slug="contested_dune",
                owner_code="cis")

            # Challenger: republic. Real membership + rank 3 (invest
            # requires rank >= 3) + real treasury funding via the
            # actual adjust_org_treasury funnel.
            republic = await db.get_organization("republic")
            char_id = await _make_char(db, name="Investor", room_id=1,
                                       credits=0)
            await db.update_room(1, zone_id=zone_id)
            await db.join_organization(char_id, republic["id"])
            await db.update_membership(char_id, republic["id"],
                                       rank_level=3)
            await db.adjust_org_treasury(republic["id"], 20000)
            char = await db.get_character(char_id)
            char["faction_id"] = "republic"

            # Real command-level function; single 10,000cr investment ->
            # +100 influence (well past the 50-floor / zero-defender
            # auto-declare branch since 'cis' has no influence yet).
            result = await invest_influence(db, char, "republic", 10000)
            self.assertTrue(result["ok"], result.get("msg"))

            rows = await db.fetchall(
                "SELECT * FROM region_contests WHERE region_slug = ? "
                "AND status = 'active'",
                ("contested_dune",),
            )
            self.assertEqual(len(rows), 1,
                             "invest_influence (no region_slug) must "
                             "auto-declare a contest via the zone-owned "
                             "region resolved by the F3 fix")
            self.assertEqual(rows[0]["challenger_org_code"], "republic")
            self.assertEqual(rows[0]["defender_org_code"], "cis")
        _run(go())

    def test_no_owned_region_in_zone_is_a_safe_noop(self):
        """Negative control: a zone with no owned regions at all must
        not crash and must not create a contest row."""
        from engine.territory import ensure_territory_schema, invest_influence
        from engine.organizations import seed_organizations

        async def go():
            db = await _fresh_db()
            await ensure_territory_schema(db)
            await seed_organizations(db, era="clone_wars")

            zone_id = 43
            republic = await db.get_organization("republic")
            char_id = await _make_char(db, name="LoneInvestor", room_id=2,
                                       credits=0)
            await db.update_room(2, zone_id=zone_id)
            await db.join_organization(char_id, republic["id"])
            await db.update_membership(char_id, republic["id"],
                                       rank_level=3)
            await db.adjust_org_treasury(republic["id"], 20000)
            char = await db.get_character(char_id)
            char["faction_id"] = "republic"

            result = await invest_influence(db, char, "republic", 10000)
            self.assertTrue(result["ok"], result.get("msg"))

            rows = await db.fetchall(
                "SELECT * FROM region_contests WHERE status = 'active'"
            )
            self.assertEqual(len(rows), 0)
        _run(go())

    def test_self_owned_region_in_zone_is_skipped(self):
        """A region already owned by the challenger's own org must not
        be treated as a rival target (no self-contest)."""
        from engine.territory import ensure_territory_schema, invest_influence
        from engine.organizations import seed_organizations

        async def go():
            db = await _fresh_db()
            await ensure_territory_schema(db)
            await seed_organizations(db, era="clone_wars")

            zone_id = 44
            await self._seed_rival_region(
                db, zone_id=zone_id, region_slug="own_turf",
                owner_code="republic")

            republic = await db.get_organization("republic")
            char_id = await _make_char(db, name="SelfInvestor", room_id=3,
                                       credits=0)
            await db.update_room(3, zone_id=zone_id)
            await db.join_organization(char_id, republic["id"])
            await db.update_membership(char_id, republic["id"],
                                       rank_level=3)
            await db.adjust_org_treasury(republic["id"], 20000)
            char = await db.get_character(char_id)
            char["faction_id"] = "republic"

            result = await invest_influence(db, char, "republic", 10000)
            self.assertTrue(result["ok"], result.get("msg"))

            rows = await db.fetchall(
                "SELECT * FROM region_contests WHERE status = 'active'"
            )
            self.assertEqual(len(rows), 0)
        _run(go())


if __name__ == "__main__":
    unittest.main()
