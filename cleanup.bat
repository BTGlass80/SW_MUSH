@echo off
REM ============================================================================
REM  SW_MUSH — Project Cleanup Script
REM  Generated: April 15, 2026 (Session 30)
REM
REM  Removes:
REM    1. Old/superseded cleanup scripts (previous versions of this file)
REM    2. Root-level files that have been moved or are no longer needed
REM    3. Applied patch scripts (patches/ directory)
REM    4. Python bytecode caches (__pycache__/, *.pyc, *.pyo)
REM    5. Database WAL/SHM temporary files (safe when server is stopped)
REM    6. Pytest caches
REM    7. Backup/temp files (*.bak, *.orig, *.old, *~)
REM    8. Log files
REM
REM  SAFE TO RUN: Does not touch source code, database, venv, or .git.
REM  RUN FROM:    Project root (the directory containing main.py)
REM  IMPORTANT:   Stop the game server before running this script.
REM ============================================================================

echo.
echo  ============================================
echo   SW_MUSH Project Cleanup
echo  ============================================
echo.

REM ── Verify we're in the right directory ─────────────────────────
if not exist main.py (
    echo ERROR: main.py not found. Run this from the SW_MUSH project root.
    pause
    exit /b 1
)

REM ── 1. Old cleanup scripts ──────────────────────────────────────
echo [1/8] Removing old cleanup scripts...
if exist "cleanup (1).bat" del "cleanup (1).bat" && echo       Removed: cleanup (1).bat
if exist "cleanup.sh" del "cleanup.sh" && echo       Removed: cleanup.sh
if exist "cleanup_backups.bat" del "cleanup_backups.bat" && echo       Removed: cleanup_backups.bat

REM ── 2. Root-level files no longer needed ────────────────────────
echo [2/8] Removing superseded root-level files...

REM client.html in root is the old 1,468-line version; current is static/client.html (6,892 lines)
if exist "client.html" (
    if exist "static\client.html" (
        del "client.html" && echo       Removed: client.html (old root copy; current is static\client.html)
    )
)

REM Design doc that was rolled into architecture doc long ago
if exist "npc_crew_and_traffic_design.md" del "npc_crew_and_traffic_design.md" && echo       Removed: npc_crew_and_traffic_design.md (superseded by architecture doc)

REM audit_exits.py — one-off utility script, useful but can be regenerated
if exist "audit_exits.py" del "audit_exits.py" && echo       Removed: audit_exits.py (one-off audit tool)

REM ── 3. Applied patch scripts ────────────────────────────────────
echo [3/8] Removing applied patch scripts...
if exist "patches" (
    del /q patches\*.py 2>nul
    rmdir patches 2>nul && echo       Removed: patches\ directory
    if exist "patches" echo       Note: patches\ not empty, left in place
)

REM ── 4. Python bytecode caches ───────────────────────────────────
echo [4/8] Cleaning Python bytecode caches...
for /d /r %%d in (__pycache__) do (
    if exist "%%d" (
        rmdir /s /q "%%d" 2>nul
    )
)
echo       Removed __pycache__ directories
del /s /q *.pyc 2>nul
del /s /q *.pyo 2>nul

REM ── 5. Database temporary files ─────────────────────────────────
echo [5/8] Cleaning database temporary files...
echo       (Make sure the game server is STOPPED before this step)
if exist "sw_mush.db-shm" del "sw_mush.db-shm" && echo       Removed: sw_mush.db-shm
if exist "sw_mush.db-wal" del "sw_mush.db-wal" && echo       Removed: sw_mush.db-wal
if exist "sw_mush.db-journal" del "sw_mush.db-journal" && echo       Removed: sw_mush.db-journal

REM ── 6. Pytest / mypy / ruff caches ─────────────────────────────
echo [6/8] Cleaning test and linter caches...
for /d /r %%d in (.pytest_cache) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)
for /d /r %%d in (.mypy_cache) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)
for /d /r %%d in (.ruff_cache) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)
echo       Cleaned test/linter caches

REM ── 7. Backup and temp files ────────────────────────────────────
echo [7/8] Cleaning backup and temp files...
del /s /q *.bak 2>nul
del /s /q *.orig 2>nul
del /s /q *.old 2>nul
del /s /q *~ 2>nul
echo       Cleaned *.bak, *.orig, *.old, *~ files

REM ── 8. Log files ────────────────────────────────────────────────
echo [8/8] Cleaning log files...
del /s /q *.log 2>nul
if exist "logs" rmdir /s /q "logs" 2>nul
echo       Cleaned log files

REM ── Summary ─────────────────────────────────────────────────────
echo.
echo  ============================================
echo   Cleanup complete!
echo  ============================================
echo.
echo  Preserved:
echo    - All Python source code (engine/, parser/, server/, db/, ai/)
echo    - static/ (client.html, chargen.html, portal.html)
echo    - data/ (YAML configs, schematics, guides)
echo    - tests/ (test suite source only, caches removed)
echo    - sw_mush.db (game database)
echo    - venv/ (Python virtual environment)
echo    - .git/ (version control)
echo    - main.py, build_mos_eisley.py, build_tutorial.py
echo    - requirements.txt, pytest.ini, README.md
echo    - .gitignore, .gitattributes
echo    - This cleanup.bat
echo.
echo  To rebuild the database from scratch:
echo    del sw_mush.db
echo    python main.py
echo.
pause
