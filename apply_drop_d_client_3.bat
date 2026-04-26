@echo off
REM ════════════════════════════════════════════════════════════════════
REM SW_MUSH — Field Kit Drop D-client.3 (Posing Panel + Target Color)
REM
REM This is the FINAL sub-drop in the D-client trio. After this lands,
REM Priority A1 from architecture v34 §16F is ✅ DELIVERED.
REM
REM Applies:
REM   · static/client.html                          REPLACED  (~6026 -> 6310 lines)
REM   · parser/space_commands.py                    REPLACED  (target_lock + contacts gain condition field)
REM   · tests/test_field_kit_drop_d_client_1.py     INCLUDED  (prereq)
REM   · tests/test_field_kit_drop_d_client_2.py     INCLUDED  (prereq)
REM   · tests/test_field_kit_drop_d_client_3.py     NEW  (38 tests)
REM
REM Idempotent: safe to re-run.
REM
REM Coverage:
REM   F3   Body-level posing panel with `cpose` primer + 3:00 timer
REM   F11  Target hull condition rendered with conditionColor() severity
REM   F13  Title-case condition keys consumed end-to-end (engine -> client)
REM   F14  POSE_PANEL_DEFAULT_SECONDS = 180 (R&E default), urgent at <30s
REM   F4   Comprehensive fullDefense scrub (parser + client final pass)
REM ════════════════════════════════════════════════════════════════════

echo Applying Drop D-client.3 (Posing Panel + Target Color)...
echo.

REM Preflight: ensure we're in the project root
if not exist "static\client.html" (
    echo ERROR: static\client.html not found. Run from SW_MUSH project root.
    exit /b 1
)
if not exist "parser\space_commands.py" (
    echo ERROR: parser\space_commands.py not found. Run from SW_MUSH project root.
    exit /b 1
)
if not exist "engine\combat.py" (
    echo ERROR: engine\combat.py not found. Run from SW_MUSH project root.
    exit /b 1
)

REM Preflight: D-prereq must be in place
findstr /C:"\"theatre\": self.theatre" "engine\combat.py" >nul 2>&1
if errorlevel 1 (
    echo ERROR: engine\combat.py is missing the D-prereq theatre field.
    echo        D-client.3 depends on Drop D-prereq landing first.
    exit /b 1
)

REM Preflight: cpose parser command must exist (PRIME button targets it)
findstr /C:"class CombatPoseCommand" "parser\combat_commands.py" >nul 2>&1
if errorlevel 1 (
    echo ERROR: parser\combat_commands.py is missing CombatPoseCommand.
    echo        PRIME cpose button has no parser target.
    exit /b 1
)

unzip -o sw_mush_drop_d_client_3.zip
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
                 tests\test_field_kit_drop_d_client_1.py ^
                 tests\test_field_kit_drop_d_client_2.py ^
                 tests\test_field_kit_drop_d_client_3.py -q

if errorlevel 1 (
    echo.
    echo TESTS FAILED — check the output above.
    exit /b 1
)

echo.
echo ============================================================
echo  Drop D-client.3 applied successfully.
echo  Expected: 209 passed (171 prior + 38 new)
echo  PRIORITY A1 IS NOW CLOSED — all 13 F-findings traceable.
echo  Run your full pytest suite next per regression discipline.
echo ============================================================
