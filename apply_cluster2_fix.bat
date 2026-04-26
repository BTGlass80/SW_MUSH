@echo off
REM ============================================================
REM apply_cluster2_fix.bat -- Full umbrella + help cluster
REM verification (S54, S55, S56, S57b, S58, S47).
REM
REM ASSUMPTION: Files have already been GUI-extracted to the
REM SW_MUSH project root. This script does NOT extract anything.
REM
REM Expected results:
REM   AST: 18/18 OK (no \c \m \s warnings)
REM   Umbrella + help suites: 290/290 GREEN
REM     - S54 combat:   23 tests
REM     - S55 jobs:     64 tests (mission + smuggle + bounty + quest)
REM     - S56 craft/crew: 41 tests
REM     - S57b space:   67 tests
REM     - S58 cleanup:  46 tests
REM     - S47 help:     48 tests
REM     - HelpEntry:     1 test
REM ============================================================

setlocal

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo === Step 1/3: AST-validating modified files ===
echo.

set MODIFIED=parser\combat_commands.py ^
parser\mission_commands.py ^
parser\smuggling_commands.py ^
parser\bounty_commands.py ^
parser\narrative_commands.py ^
parser\crafting_commands.py ^
parser\crew_commands.py ^
parser\spacer_quest_commands.py ^
parser\entertainer_commands.py ^
parser\sabacc_commands.py ^
parser\housing_commands.py ^
parser\faction_commands.py ^
parser\shop_commands.py ^
parser\places_commands.py ^
parser\medical_commands.py ^
parser\espionage_commands.py ^
parser\builtin_commands.py ^
data\help_topics.py

REM Use raw string for path inside print() so backslashes don't
REM trigger Python escape-sequence warnings/corruption.
for %%F in (%MODIFIED%) do (
    python -c "import ast; ast.parse(open(r'%%F', encoding='utf-8').read()); print('  OK:', r'%%F')" || (
        echo   FAIL: %%F
        exit /b 1
    )
)

echo.
echo === Step 2/3: Umbrella suites (S54 + S55 + S56 + S57b + S58) ===
echo.

python -m pytest tests/test_session54_combat_umbrella.py tests/test_session55_jobs_umbrellas.py tests/test_session56_craft_crew_umbrellas.py tests/test_session57b_space_umbrellas.py tests/test_session58_cleanup_umbrellas.py -p no:cacheprovider -o addopts= -q
if errorlevel 1 (
    echo.
    echo Umbrella tests FAILED -- see output above.
) else (
    echo.
    echo Umbrella suites GREEN: 241/241 expected.
)

echo.
echo === Step 3/3: S47 help-system + HelpEntry schema ===
echo.

python -m pytest tests/test_session47_help_rendering.py tests/test_session47_help_system.py tests/test_helpentry_schema_fix.py -p no:cacheprovider -o addopts= -q
if errorlevel 1 (
    echo.
    echo Help tests FAILED -- see output above.
) else (
    echo.
    echo Help suites GREEN: 49/49 expected.
)

echo.
echo === Done. Combined: 290/290 expected across umbrella + help. ===
endlocal
