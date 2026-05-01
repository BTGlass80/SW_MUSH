@echo off
REM apply_drop_bugfix2.bat — Schema bump + Tutorial DB-path fix
REM Run from project root.

echo === Applying Bugfix2: Schema + Tutorial DB ===

if not exist main.py (
    echo ERROR: must be run from the project root.
    exit /b 1
)

echo Files installed:
echo   db\database.py                                ^(MODIFIED^)
echo   build_tutorial.py                             ^(MODIFIED^)
echo   tests\harness.py                              ^(MODIFIED^)
echo   tests\smoke\scenarios\foundation.py           ^(MODIFIED^)
echo.
echo Engine changes:
echo   1. SCHEMA_VERSION 16 -^> 17 ^(migration 17 now runs on fresh DBs^)
echo   2. build_all^(^) accepts db_path ^(tutorial lands in correct DB^)
echo.

echo === Bugfix2 applied ===
echo.
echo Verify:
echo   pytest -m smoke
echo Expected: 64 passed
echo.
echo See HANDOFF_MAY01_BUGFIX2_SCHEMA_TUTORIAL.md for details.
