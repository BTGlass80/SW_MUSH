@echo off
REM SW_MUSH Cleanup Script — run from project root (Windows)
REM Removes dead code, backup files, and archives patch scripts.

echo === SW_MUSH Cleanup ===

echo.
echo [1/4] Removing dead code...
del /q engine\space_commands.py 2>nul
del /q parser\starships.py 2>nul
echo   Deleted: engine\space_commands.py (1,073 lines, superseded by parser\space_commands.py)
echo   Deleted: parser\starships.py (877 lines, superseded by engine\starships.py)

echo.
echo [2/4] Removing .bak files...
del /q db\database.py.bounty_bak 2>nul
del /q parser\combat_commands.py.bounty_combat_bak 2>nul
del /q server\game_server.py.bak 2>nul
del /q server\game_server.py.bounty_bak 2>nul
del /q server\game_server.py.mission_bak 2>nul
echo   Deleted 5 backup files.

echo.
echo [3/4] Removing duplicate patch...
del /q "bounty_combat_patch (1).py" 2>nul
echo   Deleted: bounty_combat_patch (1).py

echo.
echo [4/4] Archiving patch scripts to patches\...
if not exist patches mkdir patches
move /y bounty_combat_patch.py patches\ 2>nul
move /y bounty_wire_patch.py patches\ 2>nul
move /y drop1_apply_patches.py patches\ 2>nul
move /y evasive_engine_patch.py patches\ 2>nul
move /y evasive_parser_patch.py patches\ 2>nul
move /y force_wire_patch.py patches\ 2>nul
move /y hazard_engine_patch.py patches\ 2>nul
move /y hazard_parser_patch.py patches\ 2>nul
move /y mission_wire_patch.py patches\ 2>nul
move /y tailing_apply_patch.py patches\ 2>nul
move /y tailing_parser_patch.py patches\ 2>nul
move /y db\database_traffic_patch.py patches\ 2>nul
move /y db\mission_db_patch.py patches\ 2>nul
echo   Moved 13 patch scripts to patches\

echo.
echo === Cleanup complete ===
echo   Removed:  ~1,950 lines of dead code
echo   Removed:  5 backup files + 1 duplicate
echo   Archived: 13 patch scripts to patches\
pause
