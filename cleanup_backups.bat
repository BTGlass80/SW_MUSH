@echo off
REM ============================================================================
REM  SW_MUSH — Backup & Patch Script Cleanup
REM  Generated: April 10, 2026
REM
REM  Removes all .bak files, applied patch scripts, and pre-patch backups
REM  that have accumulated across Drops 1–19 and prior sessions.
REM
REM  SAFE TO RUN: These are all backups of files that have already been
REM  successfully patched. The live code is untouched.
REM
REM  Total files removed: ~90
REM ============================================================================

echo.
echo  SW_MUSH Backup Cleanup
echo  ======================
echo.
echo  This will delete ~90 backup files and applied patch scripts.
echo  Your live code files are NOT affected.
echo.
pause

REM ── AI module backups ──
del /q "ai\claude_provider.py.circ_bak" 2>nul
del /q "ai\providers.py.drop4_bak" 2>nul

REM ── Data backups ──
del /q "data\help_topics.py.bak" 2>nul
del /q "data\help_topics.py.npccrew.bak" 2>nul
del /q "data\help_topics.py.space.bak" 2>nul
del /q "data\npcs_gg7.yaml.bak_drop13" 2>nul
del /q "data\schematics.yaml.bak_drop13" 2>nul
del /q "data\starships.yaml.bak_drop12b" 2>nul

REM ── DB backups ──
del /q "db\database.py.bak_pre_v8" 2>nul
del /q "db\database.py.director_bak" 2>nul
del /q "db\database.py.smug_bak" 2>nul

REM ── Engine backups ──
del /q "engine\combat.py.bak_drop7" 2>nul
del /q "engine\creation_wizard.py.pre_fmt_bak" 2>nul
del /q "engine\director.py.drop4_bak" 2>nul
del /q "engine\director.py.drop4fix_bak" 2>nul
del /q "engine\director.py.inf_bak" 2>nul
del /q "engine\director.py.pre_tier1_bak" 2>nul
del /q "engine\missions.py.bak_drop14" 2>nul
del /q "engine\missions.py.drop5_bak" 2>nul
del /q "engine\npc_space_traffic.py.drop5_bak" 2>nul
del /q "engine\sheet_renderer.py.bak_drop3" 2>nul
del /q "engine\sheet_renderer.py.bak_visual" 2>nul
del /q "engine\sheet_renderer.py.pre_fmt_bak" 2>nul
del /q "engine\smuggling.py.bak_drop11" 2>nul
del /q "engine\starships.py.bak_drop12a" 2>nul
del /q "engine\world_events.py.pre_tier1_bak" 2>nul

REM ── Parser backups ──
del /q "parser\bounty_commands.py.bak_20260409_163223" 2>nul
del /q "parser\bounty_commands.py.skill_bak" 2>nul
del /q "parser\building_commands.py.bak_20260409_163223" 2>nul
del /q "parser\building_tier2.py.bak_20260409_163223" 2>nul
del /q "parser\builtin_commands.py.bak_20260409_163223" 2>nul
del /q "parser\builtin_commands.py.bak_20260409_164311" 2>nul
del /q "parser\builtin_commands.py.bak_20260409_165754" 2>nul
del /q "parser\builtin_commands.py.bak_drop3" 2>nul
del /q "parser\builtin_commands.py.bak_visual" 2>nul
del /q "parser\builtin_commands.py.drop5_bak" 2>nul
del /q "parser\builtin_commands.py.pre_bargain_bak" 2>nul
del /q "parser\builtin_commands.py.pre_hud_bak" 2>nul
del /q "parser\builtin_commands.py.pre_medical_help_bak" 2>nul
del /q "parser\channel_commands.py.bak_20260409_163223" 2>nul
del /q "parser\combat_commands.py.bak_20260409_163223" 2>nul
del /q "parser\combat_commands.py.bak_20260409_165754" 2>nul
del /q "parser\combat_commands.py.bak_drop3" 2>nul
del /q "parser\commands.py.pre_hud_bak" 2>nul
del /q "parser\cp_commands.py.bak_20260409_163223" 2>nul
del /q "parser\cp_commands.py.bak_20260409_165754" 2>nul
del /q "parser\crafting_commands.py.bak_drop13" 2>nul
del /q "parser\crew_commands.py.bak_20260409_163223" 2>nul
del /q "parser\d6_commands.py.bak_20260409_163223" 2>nul
del /q "parser\d6_commands.py.bak_20260409_165754" 2>nul
del /q "parser\force_commands.py.bak_20260409_163223" 2>nul
del /q "parser\medical_commands.py.bak_20260409_163223" 2>nul
del /q "parser\mission_commands.py.bak_20260409_163223" 2>nul
del /q "parser\mission_commands.py.bak_20260409_165754" 2>nul
del /q "parser\mission_commands.py.bak_drop14" 2>nul
del /q "parser\mission_commands.py.skill_bak" 2>nul
del /q "parser\news_commands.py.bak_20260409_163223" 2>nul
del /q "parser\npc_commands.py.bak_pre_trainer" 2>nul
del /q "parser\party_commands.py.bak_20260409_163223" 2>nul
del /q "parser\smuggling_commands.py.bak_20260409_163223" 2>nul
del /q "parser\smuggling_commands.py.bak_drop11" 2>nul
del /q "parser\space_commands.py.bak" 2>nul
del /q "parser\space_commands.py.bak_20260409_163223" 2>nul
del /q "parser\space_commands.py.bak_drop12b" 2>nul
del /q "parser\space_commands.py.bak_pre_effective_fix" 2>nul
del /q "parser\space_commands.py.drop5_bak" 2>nul
del /q "parser\space_commands.py.pre_bargain_bak" 2>nul
del /q "parser\space_commands.py.pre_skill_patch_bak" 2>nul
del /q "parser\space_commands.py.smug_bak" 2>nul

REM ── Server backups ──
del /q "server\config.py.pre_splash_bak" 2>nul
del /q "server\game_server.py.ambient_bak" 2>nul
del /q "server\game_server.py.bak" 2>nul
del /q "server\game_server.py.bak_20260409_164311" 2>nul
del /q "server\game_server.py.bak_chargen_wizard" 2>nul
del /q "server\game_server.py.bak_drop11" 2>nul
del /q "server\game_server.py.bak_drop14" 2>nul
del /q "server\game_server.py.bak_pre_crafting" 2>nul
del /q "server\game_server.py.director_bak" 2>nul
del /q "server\game_server.py.drop4_bak" 2>nul
del /q "server\game_server.py.pre_fmt_bak" 2>nul
del /q "server\game_server.py.pre_medical_bak" 2>nul
del /q "server\game_server.py.smug_bak" 2>nul
del /q "server\game_server.py.worldevents_bak" 2>nul
del /q "server\session.py.pre_hud_bak" 2>nul
del /q "server\session.py.pre_tier1_bak" 2>nul
del /q "server\session.py.pre_zone_mood_bak" 2>nul

REM ── Static backups ──
del /q "static\client.html.bak" 2>nul
del /q "static\client.html.pre_splash_bak" 2>nul

REM ── Applied patch scripts (all drops delivered, scripts no longer needed) ──
del /q "drop12_effective_stats_patch.py" 2>nul
del /q "drop14_space_missions_patch.py" 2>nul
del /q "drop15_power_allocation_patch.py" 2>nul
del /q "drop16_captains_orders_patch.py" 2>nul
del /q "drop17_trade_goods_patch.py" 2>nul
del /q "drop18_transponder_patch.py" 2>nul
del /q "drop19_quirks_log_patch.py" 2>nul
del /q "patch_skill_trainer.py" 2>nul

echo.
echo  Cleanup complete. Run 'dir /s *.bak*' to verify.
echo.
pause
