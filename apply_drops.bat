@echo off
REM ────────────────────────────────────────────────────────────────────
REM SW_MUSH Field Kit Drops D-prereq + E + B (partial) — Windows applier
REM
REM Run from project root after extracting sw_mush_field_kit_drops.zip.
REM This script just verifies that the staged files are in place and
REM runs the targeted test suite. The unzip already overwrote the
REM live files (assuming you used `unzip -o`).
REM
REM v2 fix: pass encoding='utf-8' explicitly to open() in the AST
REM validation step. Windows Python defaults open() to cp1252 which
REM blows up on the multibyte chars (×, ─, etc.) in our source files.
REM ────────────────────────────────────────────────────────────────────

setlocal

echo.
echo === SW_MUSH Field Kit Drops D-prereq + E + B (partial) ===
echo.

REM Verify each file exists
set MISSING=0
for %%f in (
    engine\pose_events.py
    engine\combat.py
    engine\ambient_events.py
    engine\hazards.py
    engine\director.py
    engine\space_encounters.py
    parser\space_commands.py
    parser\npc_commands.py
    server\session.py
    static\client.html
    tests\test_field_kit_drop_b.py
    tests\test_field_kit_drop_d_prereq.py
    tests\test_field_kit_drop_e.py
) do (
    if not exist "%%f" (
        echo MISSING: %%f
        set MISSING=1
    )
)

if "%MISSING%"=="1" (
    echo.
    echo Some files are missing. Did you extract the zip from project root?
    exit /b 1
)

echo All 13 files present.
echo.

REM Quick AST validation of the modified Python files (UTF-8 explicit)
echo Running AST validation...
python -c "import ast; [ast.parse(open(p, encoding='utf-8').read()) for p in ['engine/pose_events.py','engine/combat.py','engine/ambient_events.py','engine/hazards.py','engine/director.py','engine/space_encounters.py','parser/space_commands.py','parser/npc_commands.py','server/session.py']]; print('AST OK')"
if errorlevel 1 (
    echo AST validation FAILED. Aborting.
    exit /b 1
)
echo.

echo Running targeted test suite...
echo.
python -m pytest tests\test_field_kit_drop_a.py ^
                 tests\test_field_kit_drop_b.py ^
                 tests\test_field_kit_drop_c.py ^
                 tests\test_field_kit_drop_d_prereq.py ^
                 tests\test_field_kit_drop_e.py -q

if errorlevel 1 (
    echo.
    echo Field Kit tests FAILED.
    exit /b 1
)

echo.
echo === All Field Kit drops applied and verified. ===
echo Run your full pytest suite next per standard regression discipline.
endlocal
