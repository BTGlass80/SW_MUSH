# Handoff — Launch Drop (2026-05-31, rev 3 — combined rollup)

Single combined zip for the whole session. Apply: `Expand-Archive -Force` into the
project root → restart `main.py` → **hard-refresh the browser (Ctrl+Shift+R)** →
run `run_all_tests.bat`.

## Contents (8 changed files + design doc)

| File | Change | Verified in sandbox |
|---|---|---|
| `engine/npc_loader.py` | **Q3** — `is_intel_handler` pass-through (was dropped) | end-to-end pure-fn ✓ |
| `data/.../npcs_drop_g2_nar_shaddaa_lower.yaml` | **Q3** — tag Borka (hutt_cartel handler) | YAML + handler-resolve ✓ |
| `data/.../npcs_drop_g1_nar_shaddaa_topside.yaml` | **Q3** — tag Drel Mok (bounty_hunters_guild) | YAML + handler-resolve ✓ |
| `data/.../npcs_drop_c1_coruscant.yaml` | **Q3** — tag Halen Voss (jedi_order) | YAML + handler-resolve ✓ |
| `static/client.html` | **Q4** — modal exit strip + the ordering-bug fix | node --check ✓ (needs browser) |
| `parser/builtin_commands.py` | bearing NameError every move | AST ✓ (needs restart) |
| `data/.../planets/tatooine.yaml` | **Q1** — Option A build fix | dry-run ok ✓ |
| `TODO.json` | full session ledger | JSON valid ✓ |
| `painted_wilderness_and_coruscant_underworld_design_v1.md` | wilderness/Coruscant capture | — |

---

## Q3 — intel-handler seed (this session's new work)

You said "use your judgement." The pre-flight caught a **latent feature-breaker**
before any tagging: `npc_loader._build_ai_config` builds a fixed ai_config schema
plus a small pass-through (skills/trainer/gate). `faction` survives, but
`is_intel_handler` was in **neither** — so the YAML marker was silently dropped and
**no yaml-seeded NPC could ever be a handler**. Tagging alone would've been a no-op.

**Fix (engine):** added an `is_intel_handler` pass-through (mirrors the
trainer/gate pattern). **Verified end-to-end in sandbox** with the *real* YAML run
through the *real* loader: `_build_ai_config` now preserves the marker, and
`engine/intel_handlers._is_handler_npc` resolves **True** for the matching faction,
**False** for a mismatch — and I proved the fix is load-bearing (the pre-fix path
returns False). The dry-run stays green (ok, 0 errors, 29 warnings).

**Tagged — 3 of 5 static-HQ factions (all faction-matching, no retcon):**
- `hutt_cartel` → **Borka the Hutt (Emissary)** @ Hutt Emissary Tower – Audience Chamber
- `bounty_hunters_guild` → **Bounty Board Operator Drel Mok** @ Bounty Hunters' Quarter
- `jedi_order` → **Knight Halen Voss** @ Jedi Temple – Entrance Hall (discoverable, front-of-house)

**Deferred — Republic + CIS (a design call, not an oversight):** their Nar Shaddaa
HQ rooms are hosted by NPCs whose factions would be **contradicted** by tagging —
Zekka Thansen (Republic HQ) is `independent`, and Cantina Owner Brann Korr (CIS HQ)
is `hutt_cartel`. Forcing the tag would retcon established data. The right fix is a
**design decision for you**: either add a dedicated covert-contact NPC at each
front (spy-fiction appropriate — a fixer/cantina contact who's secretly the
faction's handler), or relocate those two HQs. I didn't want to silently corrupt
faction data to hit "5." (The 4 no-static-HQ factions remain on the future
`housing.py` hook.)

**Left for your pytest:** the DB seed actually placing these NPCs with the marker,
and `find_handler_in_room(db, room_id, faction)` returning them by room_id. I can't
build the DB in the sandbox, but every pure-function link is verified. A quick
manual check: as a Hutt-faction character, stand in the Hutt Emissary Tower
Audience Chamber and `+intel handover Borka` (or your handover syntax) — it should
recognize him as your faction's handler.

**Related finding (flagged, NOT changed) — `TD.CW_JEDI_HQ_ROOM_NAME`:** the Jedi
Order's `hq_room_name` in organizations.yaml is `"Coruscant - Jedi Temple Main
Hall"`, which is **not a real room** (the Temple rooms are `Jedi Temple - Entrance
Hall`, `- Commissary`, etc.). It doesn't affect the handover (that's room-based, and
the Jedi handler sits in the real Entrance Hall), but anything resolving the Jedi HQ
by name (housing HQ establishment) would miss. Recommended one-liner: set it to
`"Jedi Temple - Entrance Hall"`. I left it for you since it touches housing, not
intel.

---

## Q4 — click-to-move (rev 2, from earlier this session) — still needs your browser test

Your probe confirmed sub-case (a): the District render branch emits no
`data-room-id` for street/hub rooms (6,7,8,9,10,11,47), so only `down` was
clickable. Fix = an **exit strip** in the SECTOR MAP modal, built from each room's
real exits (`lastExits`) — works in **every** room of every area, marker or not.
Rev-1 had an ordering bug (guarded on `mapModalOpen` before it was set) that hid the
strip; **rev-2 removed the guard.** After a hard-refresh you should see exit buttons
at the bottom-centre of the map; clicking `NORTH` at Bay 94 Entrance reaches the
Tower. If still missing, run `document.getElementById('map-modal-exits')` with the
map open and tell me empty/missing/hidden.

This is the **global** nav fix (your question last turn): street/hub rooms are the
connective tissue of every city and draw no markers, so the strip — not per-area
work — is the correct fix everywhere.

## Server fix — bearing NameError (from earlier) — needs restart

`_post_move_hooks` referenced `exit_data`/`direction` that weren't params →
NameError every move ("bearing update failed"; move still succeeded, chevron never
updated). Threaded both through from `execute()`. AST-clean.

## Q1 / Q2 (from earlier)
- **Q1** `TD.CW_BUILD_EXIT_COLLISION` fixed via Option A; dry-run ok True, 1→0 errors.
- **Q2** Coruscant underworld single-level confirmed; stale "40×40×3" reconciled.

---

## Next, on your go
1. **Smoke-test Q4** (hard-refresh) + confirm the bearing chevron updates.
2. **Republic/CIS handler design call** — covert-contact NPCs vs HQ relocation (then I tag them).
3. **`TD.CW_JEDI_HQ_ROOM_NAME`** — want me to set it to "Jedi Temple - Entrance Hall"?
4. **Generalize `m3_tier_wilderness_body.js`** (region-param, substrate-first; double-duty: fixes the Coruscant underworld map).
