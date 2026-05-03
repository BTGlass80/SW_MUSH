@echo off
REM ============================================================
REM run_regression_tests.bat -- Default test suite, no smoke.
REM
REM Excludes the ~102 smoke scenarios (which boot in-process
REM GameServers and take ~2.5 minutes total) so a regression
REM run completes in ~40 seconds instead of ~3 minutes.
REM
REM For the smoke scenarios, use:
REM   pytest -m smoke
REM
REM For everything (smoke + regression), use:
REM   .\run_all_tests.bat
REM ============================================================

setlocal

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo === Running regression suite (smoke excluded) ===
echo === Output also being written to tests_regression.log ===
echo.

powershell -NoProfile -Command "python -m pytest tests/ -p no:cacheprovider --continue-on-collection-errors --maxfail=999 -o addopts= -m \"not smoke and not smoke_slow\" -q 2>&1 | Tee-Object -FilePath tests_regression.log"

echo.
echo === Failures + collection errors: ===
echo.
findstr /B "FAILED ERROR" tests_regression.log

echo.
echo (Full output saved to tests_regression.log)
endlocal
