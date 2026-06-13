@echo off
REM ============================================================
REM run_all_tests.bat -- Full pytest suite, with a reliable log.
REM
REM Changes (E3, 2026-06-04) -- fixes "hangs on Ctrl+C, no log":
REM  * Plain `> file 2>&1` redirection instead of PowerShell
REM    Tee-Object. Tee buffered output and lost the log when the
REM    run was interrupted; plain redirection writes the file as
REM    the run proceeds and survives a Ctrl+C.
REM  * --timeout=120 kills any single hanging test after 120s so
REM    the run actually finishes (and writes the log) instead of
REM    hanging forever. Requires pytest-timeout.
REM  * --continue-on-collection-errors so one broken import does
REM    not abort the whole run.
REM
REM Changes (2026-06-05) -- fixes "ERROR: usage: ... [file_or_dir]":
REM  * The --timeout / --timeout-method flags are ONLY valid when
REM    the pytest-timeout plugin is installed. If it is missing,
REM    pytest rejects the flags with a usage / "unrecognized
REM    arguments" error and writes no useful log. We now PROBE for
REM    the plugin and add the timeout flags only when it imports;
REM    otherwise we warn and run without the per-test timeout. So
REM    the suite runs either way.
REM ============================================================

setlocal

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo === Running full pytest suite (writing tests_output.log) ===

REM -- Detect pytest-timeout; only pass --timeout flags if present.
set "TIMEOUT_ARGS="
python -c "import pytest_timeout" 1>nul 2>nul
if errorlevel 1 (
    echo === pytest-timeout NOT installed -- running without a    ===
    echo === per-test timeout. A single hung test can stall the   ===
    echo === run. To restore the 120s safety net, install it:     ===
    echo ===     pip install pytest-timeout                       ===
    echo ===     ^(or: pip install -r requirements.txt^)            ===
) else (
    set "TIMEOUT_ARGS=--timeout=120 --timeout-method=thread"
    echo === Per-test timeout is 120s; full run is ~11 min.       ===
)
echo.

REM Hard-exit the pytest process once the summary is written, to dodge the
REM post-run interpreter-exit hang (a leaked non-daemon resource keeps the
REM process alive after all tests finish, so the run never returns and has to
REM be Ctrl+C'd). The results are already complete at that point. The guard is
REM in tests/conftest.py::pytest_sessionfinish and only fires under this env.
set "SW_MUSH_HARD_EXIT=1"

python -m pytest tests/ -p no:cacheprovider --continue-on-collection-errors --maxfail=999 %TIMEOUT_ARGS% -o addopts= -q > tests_output.log 2>&1

echo.
echo === Run complete. Failures + collection errors: ===
echo.
findstr /B "FAILED ERROR" tests_output.log

echo.
echo === Full output saved to tests_output.log ===
endlocal
