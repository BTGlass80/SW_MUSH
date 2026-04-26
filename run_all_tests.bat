@echo off
REM ============================================================
REM run_all_tests.bat -- Full pytest suite, with logging.
REM Uses PowerShell's Tee-Object (Windows lacks `tee`).
REM Adds --continue-on-collection-errors so a single broken
REM import (e.g. tests.harness ModuleNotFoundError) doesn't
REM abort the entire run.
REM ============================================================

setlocal

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo === Running full pytest suite ===
echo === Output also being written to tests_output.log ===
echo.

powershell -NoProfile -Command "python -m pytest tests/ -p no:cacheprovider --continue-on-collection-errors --maxfail=999 -o addopts= -q 2>&1 | Tee-Object -FilePath tests_output.log"

echo.
echo === Failures + collection errors: ===
echo.
findstr /B "FAILED ERROR" tests_output.log

echo.
echo (Full output saved to tests_output.log)
endlocal
