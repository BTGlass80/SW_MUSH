@echo off
REM ════════════════════════════════════════════════════════════════════
REM Field Kit Drop C — Ground UX (Datapad)
REM
REM Closes F1 (7-rung wound ladder), F5 (explicit FP_DISPLAY_MAX),
REM F8 (stun-counter strip + server active_stun_count), F10 (penalty alignment).
REM
REM PREREQUISITE: Drop A must be applied first. Drop C uses Drop A's
REM WOUND_RUNGS, stunCap(), and FK primitives. The pre-flight check below
REM verifies Drop A is present before applying Drop C.
REM
REM Run from project root (where engine/, db/, parser/, static/ live).
REM Safe to re-run: file copies are idempotent.
REM ════════════════════════════════════════════════════════════════════

setlocal

if not exist "static\client.html" (
  echo [ERROR] static\client.html not found.
  echo        Run this script from the SW_MUSH project root.
  exit /b 1
)

if not exist "engine\trading.py" (
  echo [ERROR] engine\trading.py not found - does not look like SW_MUSH root.
  exit /b 1
)

if not exist "server\session.py" (
  echo [ERROR] server\session.py not found.
  exit /b 1
)

REM Pre-flight: confirm Drop A landed first. Drop C depends on
REM WOUND_RUNGS / stunCap / FK primitives. If those are missing, abort.
findstr /C:"var WOUND_RUNGS = [" "static\client.html" > nul
if errorlevel 1 (
  echo [ERROR] Drop A primitives missing from static\client.html.
  echo        Apply Drop A first, then re-run this script.
  echo        Drop C depends on WOUND_RUNGS, stunCap, FK from Drop A.
  exit /b 1
)
findstr /C:"function stunCap" "static\client.html" > nul
if errorlevel 1 (
  echo [ERROR] Drop A stunCap helper missing from static\client.html.
  echo        Apply Drop A first.
  exit /b 1
)

echo [1/5] Backing up static\client.html to static\client.html.bak.drop_c
copy /Y "static\client.html" "static\client.html.bak.drop_c" > nul
if errorlevel 1 (
  echo [ERROR] Backup of client.html failed.
  exit /b 1
)

echo [2/5] Backing up server\session.py to server\session.py.bak.drop_c
copy /Y "server\session.py" "server\session.py.bak.drop_c" > nul
if errorlevel 1 (
  echo [ERROR] Backup of session.py failed.
  exit /b 1
)

echo [3/5] Installing patched static\client.html
copy /Y "SW_MUSH\static\client.html" "static\client.html" > nul
if errorlevel 1 (
  echo [ERROR] Install of client.html failed.
  exit /b 1
)

echo [4/5] Installing patched server\session.py
copy /Y "SW_MUSH\server\session.py" "server\session.py" > nul
if errorlevel 1 (
  echo [ERROR] Install of session.py failed.
  exit /b 1
)

echo [5/5] Installing tests\test_field_kit_drop_c.py
copy /Y "SW_MUSH\tests\test_field_kit_drop_c.py" "tests\test_field_kit_drop_c.py" > nul
if errorlevel 1 (
  echo [ERROR] Install of test_field_kit_drop_c.py failed.
  exit /b 1
)

echo.
echo ============================================================
echo Drop C applied. Next steps:
echo.
echo   1. Run the targeted pytest:
echo        python -m pytest tests\test_field_kit_drop_c.py -v
echo.
echo   2. Sanity-check Drop A still passes:
echo        python -m pytest tests\test_field_kit_drop_a.py -v
echo.
echo   3. Run the existing HUD-helpers regression:
echo        python -m pytest tests\test_hud_helpers.py -v
echo.
echo   4. (Optional) Browser verification — start the server, log in
echo      with a character, and verify:
echo        - WOUND ladder shows 7 rungs (DEAD hidden until reached)
echo        - Active rung has glow + arrow marker
echo        - Penalty column right-aligned
echo        - Stun strip appears when stunned, with capacity = STR.dice
echo        - FP dots cap at 6 with +N overflow indicator
echo.
echo   5. Run the full suite when convenient (your dev box):
echo        python -m pytest
echo.
echo   To revert:
echo     copy static\client.html.bak.drop_c static\client.html
echo     copy server\session.py.bak.drop_c server\session.py
echo     del tests\test_field_kit_drop_c.py
echo ============================================================

endlocal
exit /b 0
