# -*- coding: utf-8 -*-
"""
tests/test_t321_admin_command_access_invariant.py
T3.21 hardening -- the @-namespace privilege-declaration invariant.

A command's privilege gate is its ``access_level`` class attribute, enforced
by the dispatcher (parser.commands.CommandParser._execute -> check_access).
A command that simply *forgets* to declare one inherits BaseCommand's default
of ``AccessLevel.PLAYER`` -- so a builder/admin command shipped without an
``access_level`` is silently runnable by any logged-in player. The unit suite
never catches that class because every command "works" in isolation.

This guard pins the convention: every command whose primary ``key`` is in the
``@`` (builder/admin) namespace must declare ``access_level >= BUILDER``, with
a tiny explicit allowlist for the genuine player self-commands that use the
``@`` prefix by MUSH tradition (``@desc`` = set your own description,
``@mail`` = the player mail board).

Concrete bugs this drop closed (and that this test now prevents regressing):
  * ``@housing`` (AdminHousingCommand) shipped with NO access_level -> any
    player could run ``@housing evict <player>`` (force-evict anyone) and
    enumerate every player's housing record.
  * The ``+home admin`` umbrella forwarded INTO AdminHousingCommand.execute()
    directly, bypassing the dispatcher's check_access -- so even an ADMIN
    gate on @housing would have leaked through the umbrella.
  * ``@getattr`` (GetAttrUCommand) shipped at PLAYER while its write/list
    siblings ``@setattr``/``@lattr`` are BUILDER.

Tests exercise the REAL command registry (built exactly as game_server builds
it) and the REAL Database (full schema) -- no mocks of the code under test.
"""
import ast
import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.commands import CommandRegistry, CommandContext, AccessLevel  # noqa: E402


# ── @-namespace player self-commands (MUSH tradition) ────────────────────────
# These deliberately use the @ prefix but are legitimately PLAYER-level. Keep
# this list MINIMAL -- adding to it should require a deliberate security call.
PLAYER_AT_COMMAND_ALLOWLIST = {"@desc", "@mail"}


def _build_full_registry() -> CommandRegistry:
    """Register every command exactly as server/game_server.py does.

    Mirrors the registration sequence in GameServer.__init__ so the audit
    sees the same command set the live server dispatches. If a new register_*
    module is added to the server it should be added here too; the AST drift
    guard (test_every_at_command_in_parser_is_registered) fails loudly if an
    @-command class exists in parser/ but is missing from this registry.
    """
    from parser.builtin_commands import register_all
    from parser.d6_commands import register_d6_commands
    from parser.building_commands import register_building_commands
    from parser.building_tier2 import register_building_tier2
    from parser.combat_commands import register_combat_commands
    from parser.npc_commands import register_npc_commands
    from parser.space_commands import register_space_commands
    from parser.crew_commands import register_crew_commands
    from parser.mission_commands import register_mission_commands
    from parser.bounty_commands import register_bounty_commands
    from parser.director_commands import register_director_commands
    from parser.news_commands import register_news_commands
    from parser.smuggling_commands import register_smuggling_commands
    from parser.force_commands import register_force_commands
    from parser.medical_commands import register_medical_commands
    from parser.entertainer_commands import register_entertainer_commands
    from parser.cp_commands import register_cp_commands
    from parser.sabacc_commands import register_sabacc_commands
    from parser.crafting_commands import register_crafting_commands
    from parser.tutorial_commands import register_tutorial_commands
    from parser.chain_commands import register_chain_commands
    from parser.questline_commands import register_questline_commands
    from parser.demolitions_commands import register_demolitions_commands
    from parser.restraints_commands import register_restraints_commands
    from parser.faction_commands import register_faction_commands
    from parser.faction_leader_commands import register_faction_leader_commands
    from parser.narrative_commands import register_narrative_commands
    from parser.shop_commands import register_shop_commands
    from parser.housing_commands import register_housing_commands
    from parser.spacer_quest_commands import register_spacer_quest_commands
    from parser.shipyard_commands import register_shipyard_commands
    from parser.ship_crew_commands import register_ship_crew_commands
    from parser.finances_commands import register_finances_commands
    from parser.mux_commands import register_mux_commands
    from parser.places_commands import register_places_commands
    from parser.attr_commands import register_attr_commands
    from parser.char_commands import register_char_commands
    from parser.scene_commands import register_scene_commands
    from parser.espionage_commands import register_espionage_commands
    from parser.achievement_commands import register_achievement_commands
    from parser.event_commands import register_event_commands
    from parser.plot_commands import register_plot_commands
    from parser.mail_commands import register_mail_commands
    from parser.channel_commands import register_channel_commands
    from parser.party_commands import register_party_commands
    from parser.encounter_commands import register_encounter_commands
    from parser.title_commands import register_title_commands
    from parser.commissary_commands import register_commissary_commands
    from parser.insurance_commands import register_insurance_commands
    from parser.den_commands import register_den_commands
    from parser.village_trial_commands import register_village_trial_commands
    from parser.padawan_master_commands import register_padawan_master_commands
    from parser.padawan_master_training_commands import (
        register_padawan_master_training_commands,
    )
    from parser.padawan_master_trials import register_padawan_master_trials
    from parser.pc_bounty_commands import register_pc_bounty_commands
    from parser.admin_security_commands import register_admin_security_commands
    from parser.lead_commands import register_lead_commands
    from parser.city_commands import register_city_commands
    from parser.admin_city_commands import register_admin_city_commands
    from parser.admin_weight_commands import register_admin_weight_commands
    from parser.meditate_command import register_meditate_command
    from parser.wow_counsel_retreat import register_wow_counsel_retreat_commands
    from parser.harvest_command import register_harvest_command
    from parser.attune_command import register_attune_command
    from parser.anomaly_commands import register_anomaly_commands
    from parser.communal_commands import register_communal_commands
    from parser.player_building_commands import register_player_building_commands
    from parser.region_commands import register_region_commands
    from parser.hunting_commands import register_hunting_commands

    registers = [
        register_all, register_d6_commands, register_building_commands,
        register_building_tier2, register_combat_commands, register_npc_commands,
        register_space_commands, register_crew_commands, register_mission_commands,
        register_bounty_commands, register_director_commands, register_news_commands,
        register_smuggling_commands, register_force_commands, register_medical_commands,
        register_entertainer_commands, register_cp_commands, register_sabacc_commands,
        register_crafting_commands, register_tutorial_commands, register_chain_commands,
        register_questline_commands, register_demolitions_commands, register_restraints_commands,
        register_faction_commands, register_faction_leader_commands, register_narrative_commands,
        register_shop_commands, register_housing_commands, register_spacer_quest_commands,
        register_shipyard_commands, register_ship_crew_commands, register_finances_commands,
        register_mux_commands, register_places_commands, register_attr_commands,
        register_char_commands, register_scene_commands, register_espionage_commands,
        register_achievement_commands, register_event_commands, register_plot_commands,
        register_mail_commands, register_channel_commands, register_party_commands,
        register_encounter_commands, register_title_commands, register_commissary_commands,
        register_insurance_commands, register_den_commands, register_village_trial_commands,
        register_padawan_master_commands, register_padawan_master_training_commands,
        register_padawan_master_trials, register_pc_bounty_commands,
        register_admin_security_commands, register_lead_commands, register_city_commands,
        register_admin_city_commands, register_admin_weight_commands, register_meditate_command,
        register_wow_counsel_retreat_commands, register_harvest_command, register_attune_command,
        register_anomaly_commands, register_communal_commands, register_player_building_commands,
        register_region_commands, register_hunting_commands,
    ]
    reg = CommandRegistry()
    for fn in registers:
        fn(reg)
    return reg


def _at_command_keys_in_parser_source() -> set[str]:
    """AST-scan parser/*.py for class-body ``key = "@..."`` literals.

    Returns every @-prefixed primary command key declared in source. Used as
    a drift guard: if a class declares an @-key that the built registry above
    doesn't contain, the registry list has fallen behind the codebase.
    """
    parser_dir = os.path.join(PROJECT_ROOT, "parser")
    found: set[str] = set()
    for fname in os.listdir(parser_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(parser_dir, fname)
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                if "key" not in targets:
                    continue
                val = stmt.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str) \
                        and val.value.startswith("@"):
                    found.add(val.value)
    return found


# ── Capturing session harness (for the umbrella behavioral test) ─────────────
class _CapturingSession:
    def __init__(self, account=None, character=None, is_in_game=True):
        self.account = account
        self.character = character
        self.is_in_game = is_in_game
        self.lines: list[str] = []

    async def send_line(self, text):
        self.lines.append(text)

    async def send_prompt(self):
        pass


def _make_ctx(db, session, command="@x", args=""):
    return CommandContext(
        session=session,
        raw_input=(command + " " + args).strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


# ══════════════════════════════════════════════════════════════════════════
# 1. The core invariant: @-commands require BUILDER+ (allowlist excepted)
# ══════════════════════════════════════════════════════════════════════════
class TestAtCommandPrivilegeInvariant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _build_full_registry()

    def test_registry_built_substantially(self):
        # Sanity: a broken import would silently shrink the set.
        self.assertGreaterEqual(len(self.reg.all_commands), 300)

    def test_at_commands_require_builder_or_above(self):
        offenders = []
        for cmd in self.reg.all_commands:
            if not cmd.key.startswith("@"):
                continue
            if cmd.key in PLAYER_AT_COMMAND_ALLOWLIST:
                continue
            if cmd.access_level < AccessLevel.BUILDER:
                offenders.append((cmd.key, cmd.__class__.__name__,
                                  cmd.access_level))
        self.assertEqual(
            offenders, [],
            "@-namespace commands must declare access_level >= BUILDER "
            "(or be added to PLAYER_AT_COMMAND_ALLOWLIST with a security "
            f"rationale). Offenders: {offenders}")

    def test_allowlisted_commands_exist_and_are_player(self):
        # The allowlist must not rot: every entry must still resolve to a
        # real, registered, PLAYER-level command.
        for key in PLAYER_AT_COMMAND_ALLOWLIST:
            cmd = self.reg.get(key)
            self.assertIsNotNone(cmd, f"Allowlisted @-command '{key}' missing")
            self.assertEqual(
                cmd.access_level, AccessLevel.PLAYER,
                f"Allowlisted '{key}' is no longer PLAYER -- remove it from "
                "the allowlist.")

    def test_housing_command_is_admin(self):
        cmd = self.reg.get("@housing")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.access_level, AccessLevel.ADMIN)

    def test_getattr_aligned_with_builder_siblings(self):
        getattr_cmd = self.reg.get("@getattr")
        lattr_cmd = self.reg.get("@lattr")
        setattr_cmd = self.reg.get("@setattr")
        self.assertEqual(getattr_cmd.access_level, AccessLevel.BUILDER)
        self.assertEqual(lattr_cmd.access_level, AccessLevel.BUILDER)
        self.assertEqual(setattr_cmd.access_level, AccessLevel.BUILDER)


# ══════════════════════════════════════════════════════════════════════════
# 2. Drift guard: every @-command in parser/ source is in the registry
# ══════════════════════════════════════════════════════════════════════════
class TestRegistryCoversParserSource(unittest.TestCase):
    def test_every_at_command_in_parser_is_registered(self):
        reg = _build_full_registry()
        registered = {c.key for c in reg.all_commands}
        in_source = _at_command_keys_in_parser_source()
        missing = sorted(in_source - registered)
        self.assertEqual(
            missing, [],
            "These @-command keys are declared in parser/ source but absent "
            "from the audited registry -- _build_full_registry() (and likely "
            f"game_server) has drifted behind the codebase: {missing}")


# ══════════════════════════════════════════════════════════════════════════
# 3. Behavioral: the +home admin umbrella re-checks access (no bypass)
# ══════════════════════════════════════════════════════════════════════════
class TestHomeAdminUmbrellaGate(unittest.TestCase):
    def _admin_impl(self):
        from parser.housing_commands import _HOME_SWITCH_IMPL
        return _HOME_SWITCH_IMPL["admin"]

    def test_non_admin_is_denied_through_umbrella(self):
        """A logged-in non-admin must NOT reach admin housing via +home admin."""
        async def _go():
            db = await _fresh_db()
            try:
                # A real, non-privileged account.
                boss = await db.create_account("boss", "pw123456")  # first acct: admin
                player = await db.create_account("nobody", "pw123456")  # not admin
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (player,)))[0])
                self.assertEqual(snap["is_admin"], 0)
                sess = _CapturingSession(account=snap)
                ctx = _make_ctx(db, sess, command="+home", args="admin list")
                await self._admin_impl()(ctx, "list")
                return sess.lines
            finally:
                await db.close()

        lines = _run(_go())
        joined = "\n".join(lines)
        self.assertIn("permission", joined.lower())
        # The admin "list" output header must NOT have been produced.
        self.assertNotIn("All Housing", joined)

    def test_admin_is_allowed_through_umbrella(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")  # first acct: admin
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                self.assertEqual(snap["is_admin"], 1)
                sess = _CapturingSession(account=snap)
                # `inspect <name>` only touches the core characters table, so
                # the admin path reaches execute() without depending on the
                # housing tables. A nonexistent target -> "not found", which
                # proves the gate ALLOWED (didn't deny) and forwarded.
                ctx = _make_ctx(db, sess, command="+home", args="admin inspect ghost")
                await self._admin_impl()(ctx, "inspect ghost")
                return sess.lines
            finally:
                await db.close()

        lines = _run(_go())
        joined = "\n".join(lines)
        self.assertNotIn("permission", joined.lower())
        # Reached execute(): the inspect sub reported the missing player.
        self.assertIn("not found", joined.lower())


# ══════════════════════════════════════════════════════════════════════════
# 3b. Behavioral: the +shop admin umbrella re-checks access (same vuln class)
# ══════════════════════════════════════════════════════════════════════════
class TestShopAdminUmbrellaGate(unittest.TestCase):
    def _admin_impl(self):
        from parser.shop_commands import _SHOP_SWITCH_IMPL
        return _SHOP_SWITCH_IMPL["admin"]

    def test_non_admin_is_denied_through_umbrella(self):
        async def _go():
            db = await _fresh_db()
            try:
                await db.create_account("boss", "pw123456")        # first: admin
                player = await db.create_account("nobody", "pw123456")  # not admin
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (player,)))[0])
                sess = _CapturingSession(account=snap)
                ctx = _make_ctx(db, sess, command="+shop", args="admin inspect ghost")
                await self._admin_impl()(ctx, "inspect ghost")
                return sess.lines
            finally:
                await db.close()

        lines = _run(_go())
        joined = "\n".join(lines)
        self.assertIn("permission", joined.lower())
        self.assertNotIn("not found", joined.lower())  # never reached execute

    def test_admin_is_allowed_through_umbrella(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")  # first: admin
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                sess = _CapturingSession(account=snap)
                ctx = _make_ctx(db, sess, command="+shop", args="admin inspect ghost")
                await self._admin_impl()(ctx, "inspect ghost")
                return sess.lines
            finally:
                await db.close()

        lines = _run(_go())
        joined = "\n".join(lines)
        self.assertNotIn("permission", joined.lower())
        self.assertIn("not found", joined.lower())  # reached execute()


# ══════════════════════════════════════════════════════════════════════════
# 4. Direct check_access on @housing (the registry-dispatched path)
# ══════════════════════════════════════════════════════════════════════════
class TestHousingDirectGate(unittest.TestCase):
    def test_non_admin_denied(self):
        async def _go():
            from parser.housing_commands import AdminHousingCommand
            db = await _fresh_db()
            try:
                await db.create_account("boss", "pw123456")  # first acct: admin
                player = await db.create_account("nobody", "pw123456")
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (player,)))[0])
                ctx = _make_ctx(db, _CapturingSession(account=snap))
                return await AdminHousingCommand().check_access(ctx)
            finally:
                await db.close()

        self.assertFalse(_run(_go()))

    def test_admin_allowed(self):
        async def _go():
            from parser.housing_commands import AdminHousingCommand
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")  # admin
                snap = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                ctx = _make_ctx(db, _CapturingSession(account=snap))
                return await AdminHousingCommand().check_access(ctx)
            finally:
                await db.close()

        self.assertTrue(_run(_go()))


if __name__ == "__main__":
    unittest.main()
