@echo off
REM ============================================================================
REM  prune_local_cache.bat -- reclaim disk on the Windows box (LOCAL ONLY).
REM
REM  IMPORTANT: this does NOT shrink the AI upload zip. Your zip builder
REM  (make_upload_zip.ps1) already excludes every cache below, so the upload
REM  never contained them. The 12 MB upload is the painted map substrates --
REM  use the patched make_upload_zip.ps1 (default behavior) to drop those from
REM  the zip. This .bat just cleans regenerable junk off your actual disk.
REM
REM  Deletes (recursively, from this script's folder):
REM    __pycache__\  .pytest_cache\  .mypy_cache\  .ruff_cache\
REM    *.pyc  *.pyo  *.log
REM
REM  Leaves untouched: venv\ and .git\ (and everything else).
REM  Everything removed regenerates on the next test/import run.
REM
REM  Usage:  put in C:\SW_MUSH, double-click, or run from a prompt.
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  Local cache prune
echo  Target folder : %CD%
echo  Skipped       : venv\  .git\
echo ============================================================
echo.
echo This removes __pycache__, .pytest_cache, .mypy_cache, .ruff_cache,
echo and *.pyc / *.pyo / *.log files. All are regenerable.
echo.
set "CONFIRM="
set /p "CONFIRM=Proceed? (Y/N): "
if /i not "!CONFIRM!"=="Y" (
    echo Aborted. Nothing changed.
    goto :end
)

echo.
echo [1/2] Removing cache directories...
for /f "delims=" %%d in ('dir /s /b /ad __pycache__ .pytest_cache .mypy_cache .ruff_cache 2^>nul ^| findstr /v /i "\venv\ \.git\"') do (
    echo   rd  %%d
    rd /s /q "%%d" 2>nul
)

echo.
echo [2/2] Removing compiled bytecode and logs...
for /f "delims=" %%f in ('dir /s /b /a-d *.pyc *.pyo *.log 2^>nul ^| findstr /v /i "\venv\ \.git\"') do (
    del /q "%%f" 2>nul
)

echo.
echo ============================================================
echo  Done. Caches cleared. (Upload size is unchanged -- that is
echo  handled by make_upload_zip.ps1.)
echo ============================================================

:end
endlocal
pause
