SW_MUSH — GCW RETIREMENT DROP (2026-06-06)
==========================================

APPLY (from project root, PowerShell):
    Expand-Archive -Path SW_MUSH_gcw_retirement_drop_20260606.zip -DestinationPath . -Force

This overwrites the changed/new files. It does NOT delete anything.
You MUST then run the deletions below (Expand-Archive cannot delete).

DELETIONS (run from project root, PowerShell):
    Remove-Item -Recurse -Force data\worlds\gcw
    Remove-Item -Force data\organizations.yaml
    Remove-Item -Force tests\test_f1a_npc_loader.py
    Remove-Item -Force tests\test_f1b_ship_loader.py
    Remove-Item -Force tests\test_f1c_test_character_loader.py
    Remove-Item -Force tests\test_f5b3a_gcw_housing_host_rooms.py
    Remove-Item -Force tests\test_build_pass_a.py
    Remove-Item -Force APPLY_GCW_RETIREMENT_README.txt   # (optional; do not commit this readme)

Then: run_all_tests.bat (full ~7,700 suite).

SMOKE (clone_wars boot):
  - chargen template list has NO rebel_pilot (clone_trooper/republic_officer/etc. present)
  - a SECURED city / customs reads era-clean (no "Imperial")
  - @spawn of a retired GCW org_code is graceful (no crash, no faction finding)

NOTES:
  - The org-axis legacy rewicker (apply_org_rewicker/get_org_rewicker_map) was KEPT
    on purpose as a permanent migration safety net (empire->republic, etc.).
  - Architecture doc NOT touched (stale; held for the v52 reconciliation).
  - Dead GCW faction entries remain (unreachable, test-pinned) in ~13 modules
    (territory/director/tutorial_v2/bounty_board/vendor_droids/npc_generator/
    npc_combat_ai/security/space_anomalies/contest + director-axis codes +
    village_trials prophecy) — a future optional full-B3-strip.
