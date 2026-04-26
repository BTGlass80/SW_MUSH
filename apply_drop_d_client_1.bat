@echo off
REM ════════════════════════════════════════════════════════════════════
REM SW_MUSH — Field Kit Drop D-client.1 (Foundation)
REM
REM Applies:
REM   · static/client.html            REPLACED  (5754 -> 5831 lines, +77)
REM   · tests/test_field_kit_drop_d_client_1.py  NEW  (17 tests)
REM
REM Idempotent: safe to re-run. Does NOT touch any engine, parser, db,
REM server, or data file. Pure client-side rendering change.
REM
REM Coverage:
REM   F1   canonical 7-rung wound ladder consumed in handleCombatState
REM   F6   theatre-aware data-theatre attribute + CSS overrides
REM   F14  phase-pill pulse + per-phase visual treatment (5 phases)
REM ════════════════════════════════════════════════════════════════════

echo Applying Drop D-client.1 (Foundation)...
echo.

REM Preflight: ensure we're in the project root
if not exist "static\client.html" (
    echo ERROR: static\client.html not found. Run from SW_MUSH project root.
    exit /b 1
)
if not exist "engine\combat.py" (
    echo ERROR: engine\combat.py not found. Run from SW_MUSH project root.
    exit /b 1
)

REM Preflight: D-prereq must be in place (we depend on combat_state.theatre)
findstr /C:"\"theatre\": self.theatre" "engine\combat.py" >nul 2>&1
if errorlevel 1 (
    echo ERROR: engine\combat.py is missing the D-prereq theatre field.
    echo        Drop D-client.1 depends on Drop D-prereq landing first.
    exit /b 1
)

unzip -o sw_mush_drop_d_client_1.zip
if errorlevel 1 (
    echo ERROR: unzip failed. Make sure unzip is on PATH and the zip is here.
    exit /b 1
)

echo.
echo Files applied. Running test suite...
echo.

python -m pytest tests\test_field_kit_drop_a.py ^
                 tests\test_field_kit_drop_b.py ^
                 tests\test_field_kit_drop_c.py ^
                 tests\test_field_kit_drop_d_prereq.py ^
                 tests\test_field_kit_drop_e.py ^
                 tests\test_field_kit_drop_d_client_1.py -q

if errorlevel 1 (
    echo.
    echo TESTS FAILED — check the output above.
    exit /b 1
)

echo.
echo ============================================================
echo  Drop D-client.1 applied successfully.
echo  Expected: 145 passed (128 prior + 17 new)
echo  Run your full pytest suite next per regression discipline.
echo ============================================================
