# HANDOFF — Overnight main-dev session, 2026-06-14 (T3.20 cluster + GCW-delete)

> **State:** `origin/main` = `585c4b3` (all 6 drops below pushed; `git branch -f main` synced).
> Author: Opus main session, worktree `C:/SW_MUSH_night` @ `drop/overnight-6-14-night`.
> Brian returned ~07:15 EDT and ended the unattended run; overnight timers deleted.

## For the FRESH session taking over main dev

- **Worktree:** `C:/SW_MUSH_night` (branch `drop/overnight-6-14-night`) is checked out AT
  `origin/main` (`585c4b3`) and clean — reuse it, or make your own worktree off `origin/main`.
  The Bash tool cwd **resets to `c:\SW_MUSH` every call** → prefix worktree commands with
  `cd /c/SW_MUSH_night && ...`. Do NOT edit `c:\SW_MUSH` / `_dev` / `_dir` / `_wild` (other lanes).
- **Auth order / next-up truth:** `TODO.json` + `CHANGELOG.md` at HEAD. The full resume protocol
  this session ran under is `C:\Users\btgla\.claude\projects\c--SW-MUSH\RESUME_unattended_2026-06-14.md`
  (worktree rules, merge ritual, gate, next-up queue).

## Shipped this session (6 drops, oldest→newest; all full-suite-gated)

1. `ac77e92` — **T3.20 reload-round-trip** for 5 board/inventory/buff entities
   (ItemInstance/Mission/BountyContract/SmugglingJob/Buff). `tests/test_persisted_entity_roundtrip.py`.
2. `94e13fa` — **T3.20 live-DB integrity/orphan validator** `db/integrity.py::scan_integrity`
   (PRAGMA integrity_check + foreign_key_check) + CLI `tools/check_db_integrity.py`. `tests/test_db_integrity.py`.
3. `b34f3ab` — **T3.20 round-trip** TrafficShip + NPCConfig; scope_notes(c) lane complete (all 8
   deserializers guarded). `tests/test_serializer_roundtrip_extra.py`.
4. `f0723d0` — **T3.20 online DB backup** `db/backup.py::backup_database` + CLI `tools/backup_db.py`
   + `docs/design/backup_restore_runbook_v1.md`. `tests/test_db_backup.py`.
5. `d5804e9` — **T3.20 self-enforcing state-preservation contract**
   `docs/design/state_preservation_contract_v1.md` + meta-test
   `tests/test_state_preservation_contract.py` (AST-scans deserializers vs a registry — a new
   serializer can't ship without a round-trip guard). **→ T3.20 cluster COMPLETE (a–f).**
6. `585c4b3` — **Delete off-era GCW profession chains** (REBEL_CELL + IMPERIAL_SERVICE) from
   `engine/tutorial_v2.py` — executes Brian's `BRIAN_ROADMAP_DECISIONS.2026-06-14` decision 1
   (OPTION A DELETE). ~319 lines removed; the rest of the profession-chain system stays live.
   `tests/test_tutorial_v2_era_cleanness.py` rewritten to assert the symbols are GONE.

**T3.20 (State-preservation / safe-migration) is DONE** — scope_notes a/b/c/d/e/f. F.7.n closed
as not-a-bug. The contract's I1–I5 invariants are owed a fold into the **v52 arch-doc consolidation**
(arch-doc lane, not main-dev).

## NEXT-UP QUEUE (collision-free, highest-leverage first)

1. **T3.13-18 features — now FULL-BODY pre-launch** (Brian `724d4da`, not just scaffolding seams).
   Design docs: `docs/design/padawan_master_system_design_v1.md`, `player_cities_design_v1_2.md`,
   `space_wildspace_design_v1.md` (+ `Guide_12_Player_Cities.md`, `Guide_14_Padawan_Master.md`).
   These are BIG + design-heavy: **slice into bounded sub-drops** (start with the schema/state seam,
   the T3.22 Phase-0/drop-46 exemplar), and **LOG genuine design forks** to
   `design_calls_pending_brian` — do NOT guess a whole feature. Migration-bearing seams are fine
   (re-fetch before push; renumber on a SCHEMA_VERSION conflict).
2. **Decided tunables ready to build** (Brian `724d4da` decisions 3-4): kyber = weekly-ceremonial
   (`ATTUNE_COOLDOWN_SECS`→7d per-character-global, `ATTUNE_DIFFICULTY` 11→15, lower `QUALITY_FLOOR`
   ~65 for occasional duds); harvest cap = +100% (cap bands at 5 → 2.0x max). See the `decided_2026_06_14`
   notes in TODO.json. The other ~18 tunables stay for T3.19.
3. **T3.19 (tunables externalization)** still flagged premature until the codebase settles; **T3.21
   (optimization + security) is last.**
4. **AVOID:** Ollama/era-guard/idle_queue, chains/NPC content, arch-doc reconciliation, parser
   command-syntax rework (other lanes). The parallel session stood down on tokens overnight.

## Operating mechanics (carry forward)

- **Merge ritual:** finish drop → full-suite gate → `git fetch origin && git merge origin/main`
  (CHANGELOG conflicts resolve by UNION — strip the 3 `<<<`/`===`/`>>>` markers; TODO.json
  auto-merges) → `git push origin HEAD:main` → `git branch -f main origin/main`. Re-fetch before EVERY push.
- **Gate:** `cd /c/SW_MUSH_night && python -m pytest tests -n auto --dist loadscope -o addopts="" --maxfail=200 -q`
  in the FOREGROUND, `timeout: 540000`. ~4–4.5 min. Known `-n auto` smoke flakes (NOT regressions,
  all pass SOLO): `test_smoke_chain_walkthrough[republic_soldier|separatist_commando|smuggler]` and
  `test_smoke_pvp.py::TestPvP::test_pv3_post_consent_attack_starts_combat`. Re-run any smoke failure
  solo (`-p no:xdist`) before believing it. If a run hangs, `taskkill //F //IM python.exe //T` (orphan
  swarm) and re-run.
- **CHANGELOG.md + TODO.json land in the SAME commit as code (hygiene tests enforce); new per-drop test file.**

## ⚠ DURABILITY LESSON (Brian, 2026-06-14 — the thing that stalled this session)

The autonomous loop stalled because I **passively waited on a background task's completion
notification** that never fired (the full-suite gate, run in background, hung near 99% and I sat
idle). Brian's ruling: *backgrounding isn't the problem — RELYING ON THE NOTIFICATION is.* **Don't
end a turn waiting to be notified.** Either (a) run long tasks FOREGROUND-BLOCKING with a generous
`timeout` (deterministic return — this is what worked for drops 1–5), or (b) if backgrounded,
ACTIVELY re-check after `expected_duration + margin` (self-schedule a poll), never just wait. Also:
session-only crons fire only while the REPL is idle AND alive — a hung foreground/poll blocks them.
