@echo off
echo SW_MUSH Project Cleanup
echo =======================
echo Removing applied patch scripts, empty module remnants, and superseded files.
echo.

:: Confirm before proceeding
set /p CONFIRM=This will permanently delete stale files. Continue? (y/N): 
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    exit /b 0
)

:: -----------------------------------------------------------------------
:: Root-level stale scripts (all applied to live files)
:: -----------------------------------------------------------------------
echo.
echo [1/5] Removing root-level patch/drop scripts...

del /q drop7_verb_flavor.py         2>nul && echo   deleted: drop7_verb_flavor.py
del /q drop11_smuggling_patch.py    2>nul && echo   deleted: drop11_smuggling_patch.py
del /q drop12a_starships_patch.py   2>nul && echo   deleted: drop12a_starships_patch.py
del /q drop12b_commands_patch.py    2>nul && echo   deleted: drop12b_commands_patch.py
del /q drop13_components_patch.py   2>nul && echo   deleted: drop13_components_patch.py
del /q drop14_space_missions_patch.py 2>nul && echo   deleted: drop14_space_missions_patch.py

del /q add_npccrew_help_topic.py    2>nul && echo   deleted: add_npccrew_help_topic.py
del /q add_space_help_topics.py     2>nul && echo   deleted: add_space_help_topics.py
del /q update_space_help_topic.py   2>nul && echo   deleted: update_space_help_topic.py
del /q world_builder_patch.py       2>nul && echo   deleted: world_builder_patch.py

:: Root-level web_client.py — old standalone prototype (live version is server\web_client.py)
del /q web_client.py                2>nul && echo   deleted: web_client.py (root prototype)

:: Root-level test duplicates (live copies are in tests\)
del /q test_npc_crew.py             2>nul && echo   deleted: test_npc_crew.py (dup of tests\)
del /q test_npc_crew_migration.py   2>nul && echo   deleted: test_npc_crew_migration.py (dup of tests\)

:: -----------------------------------------------------------------------
:: patches\ — 64 applied patch scripts
:: -----------------------------------------------------------------------
echo.
echo [2/5] Removing patches\ directory (64 applied scripts)...
if exist patches\ (
    rmdir /s /q patches\
    echo   deleted: patches\
) else (
    echo   patches\ not found, skipping.
)

:: -----------------------------------------------------------------------
:: Empty module remnants
:: -----------------------------------------------------------------------
echo.
echo [3/5] Removing empty module remnants...

if exist space\ (
    rmdir /s /q space\
    echo   deleted: space\  (empty __init__.py remnant)
) else (
    echo   space\ not found, skipping.
)

if exist world\ (
    rmdir /s /q world\
    echo   deleted: world\  (empty __init__.py remnant)
) else (
    echo   world\ not found, skipping.
)

:: -----------------------------------------------------------------------
:: web_client_v3\ — superseded by static\client.html
:: -----------------------------------------------------------------------
echo.
echo [4/5] Removing web_client_v3\ (superseded by static\client.html)...
if exist web_client_v3\ (
    rmdir /s /q web_client_v3\
    echo   deleted: web_client_v3\
) else (
    echo   web_client_v3\ not found, skipping.
)

:: -----------------------------------------------------------------------
:: Python cache cleanup (bonus)
:: -----------------------------------------------------------------------
echo.
echo [5/5] Removing __pycache__ directories...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
    )
)
echo   done.

:: -----------------------------------------------------------------------
echo.
echo Cleanup complete.
echo.
echo Kept:
echo   build_mos_eisley.py   -- world builder (active)
echo   build_tutorial.py     -- tutorial zone builder (active)
echo   main.py               -- server entry point
echo   tests\                -- test suite
echo   engine\, parser\, server\, db\, data\, ai\, static\
echo.
