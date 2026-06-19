# HANDOFF — Parsec launch-drive session (2026-06-18)

**Purpose:** resume this attended launch-drive cold in a fresh chat. The prior chat
got cluttered. Everything below is grounded in HEAD / the git log / files on disk —
verify any symbol at HEAD before trusting it (hard invariant: no phantom claims).

---

## TL;DR — where to pick up

1. **Branch `drop/sidebar-contract-handoff-capture`** holds **13 unpushed-to-main commits**
   (Parsec rebrand + 7 concurrency verify-fixes + Nano TLS fix). Pushed to
   `origin/drop/sidebar-contract-handoff-capture` as backup. **Gate before merge:**
   Brian runs `run_all_tests.bat`; merge to main only on green.
2. **Map-automation test (Nano/Gemini): VERDICT IN — do NOT switch for launch.** The
   current hand-made painting beats every automated candidate. Pipeline + integration +
   safety all PROVEN. One untried high-value lever remains (style-reference). Full detail §3.
3. **Movement-safety question ANSWERED** (Brian's big worry): a painting swap is purely
   cosmetic and **cannot** break click-to-move / navigation / find-players. Proof in §3.
4. Open follow-ups: concurrency §2 (uptime-counter HIGH is launch-relevant for a
   restart-prone home box), map next-lever §3, hosting §4.

---

## Branch & git state

- Current branch: **`drop/sidebar-contract-handoff-capture`** (env header said
  `t321-read-pool` — that was stale).
- **13 commits ahead of origin/main**, newest first:
  - `7d433f3` gitignore Nano candidate-batch dir
  - `1ce8db3` Nano TLS (truststore through Norton) — see §3
  - `e08da26` Verify-findings doc — see §2
  - `bbe754a` Verify-fix 4 (WS-routing group)
  - `6de83a6` Verify-fix 3 (hint-timer leak)
  - `1306ca4` Verify-fix 2 (read-pool poisoning)
  - `94319d3` Verify-fix 1 (`sm.sessions` blocker)
  - `c762f13` Parsec rebrand pt.2 (chargen/map-preview/help corpus/parser)
  - `5e2057a` Parsec rebrand (nav logo + screenshots)
  - `1271457` Public rebrand → Parsec (portal/client/banner)
  - `3432a4f` merge origin/main
  - `ea4d604` Claude Design in-session UI/UX punch-list
- Tree is clean (untracked `.agents/`, `.codex/`, `AGENTS.md` are external tooling, not ours).

---

## 1. Rebrand: SW_MUSH → **Parsec** (public name only)

Brian confirmed the public name is **Parsec** (2026-06-18). Scope discipline:
- **Only public-facing branding flips to Parsec** (portal/client/banner/nav-logo, chargen,
  map-preview, help/guide corpus, in-game strings).
- **Internal stays SW_MUSH**: repo name, db filename (`sw_mush.db`), env vars, code
  comments, directory names. Do not rename the repo or db.
- Tests: `tests/test_public_name_parsec.py` guards the public-name flip.

---

## 2. Concurrency / tick verify-fixes (committed)

Source-of-truth doc: **`docs/design/VERIFY_FINDINGS_2026-06-18.md`** (commit `e08da26`).
An adversarial Workflow probe of the never-load-tested runtime surfaces (read-pool/WAL,
throttle/session state, ticks/timers, WS routing) found 18 issues. **7 fixed with
regression tests** (the root cause was `sm.sessions` — the real API is `SessionManager.all`;
the bug hid because old test stubs defined a fake `.sessions`).

**Fixed (commits 94319d3 / 1306ca4 / 6de83a6 / bbe754a):** wound-recovery + Hutt-debt ticks
(were silent no-ops), read-pool poisoning (`isolation_level=None` + rollback-on-release),
tutorial hint-timer leak, area-map memo-before-send, combat broadcast `asyncio.gather`,
`broadcast_chat` global-branch dict-values, dead duplicate `pose_event` case.

**Open follow-ups (in the findings doc, NOT yet fixed):**
- **HIGH / launch-relevant:** tick-scheduler uptime counter (`server/game_server.py:478`
  `self._tick_count=0` resets every restart → long-interval economy ticks never fire on a
  reboot-prone home box). Two fix options sketched (wall-clock window vs. DB-anchored
  idempotency per handler). **Pick deliberately; gate on full suite.** This matters because
  the launch is **home-hosted** (restarts happen) — see §4.
- MEDIUM: rate-bucket `id(session)` leak; per-IP throttle empty-key leak; double-login
  TOCTOU; ship-systems JSON lost-update race; no per-session send-buffer bound.
- LOW: kicked session keeps running its loop; SpaceGrid not rehydrated on boot.

---

## 3. Map-automation TEST (Nano / Gemini 2.5 Flash Image) — full state

Brian's framing: *"try this as a test… totally parallel… testing the waters. I don't want
to switch to something that's worse."* He added **$10 to Gemini** to enable it.

### 3a. What is PROVEN to work (end-to-end on Brian's box)
- **Auth + Norton TLS:** `tools/mapgen/nano_client.py` now has `_build_ssl_context()`
  (mirrors `ai/claude_provider`) → `truststore.SSLContext` so Gemini's HTTPS passes through
  Norton's MITM cert. Without it: `CERTIFICATE_VERIFY_FAILED`. Committed `1ce8db3`. Verified
  (request reached Gemini → real HTTP responses).
- **Billing:** live after Brian's $10 (was HTTP 429 before).
- **Pipeline:** `python -m tools.mapgen.cli paint --area mos_eisley --n 3 --timestamp <id>`
  runs batch → Haiku vision screen → rank. Candidates land in **gitignored**
  `static/tools/batches/<area>/<id>/candidates/`. Non-destructive.
- **`create_nano_client()` is async** (must `await`). Area slug is the **city** key
  (`mos_eisley`), not `tatooine.mos_eisley` — `seed_for` builds `mos_eisley_tight_seed.png`.

### 3b. The MOVEMENT-SAFETY answer (Brian's big worry — definitive)
Brian worried a painting might place buildings such that players can't logically walk
room-to-room via click-to-move. **It cannot. Walkability is 100% data, independent of art:**
- Click-to-move targets are invisible **room cells** (`L_SubstrateRooms`) drawn at each
  room's **coordinates** (from the area YAML) as an overlay **on top of** the painting.
- Clicking an adjacent room moves you via the **exit graph** — the DB `exits`
  (`parser/builtin_commands.py:507,1113` read exits, never x/y/pixels).
- Substrate PNG renders only at **city + wilderness tiers** (`m3_composition_engine.js`),
  stretched to the bounds rect via `preserveAspectRatio='none'`. Outer tiers are procedural SVG.
- **A painting swap is overwriting `static/maps/<area>_substrate.png`** at the YAML-named
  path. It changes ZERO click targets and ZERO connections. Worst case a misaligned painting
  *looks* incoherent (a cell over painted sand); it still walks perfectly.
- The **seed is generated FROM the room/district coords**, so a seed-following painting puts
  buildings where the rooms are → cells land on buildings → looks natural. That's the whole
  point of the seed→paint pipeline.
- (Integration trace from Workflow `wwh2349qv` / `map-substrate-integration`.)

### 3c. Iterations done + the verdict
| # | Change | Result |
|---|---|---|
| 1 | original seed | water-in-desert + text labels + tactical/VTT type |
| 2 | warm desert `DISTRICT_HUES` (no slate-blue index 0) | **water FIXED** |
| 3 | name-free brief + muted markers (`LM_DIST/LM_GEN` toned) | text mostly gone, but style → **"tactical grid / VTT"** (Haiku screen scored ~20/100 off-theme) |

**VERDICT: the current hand-made painting `static/maps/mos_eisley_substrate.png` is clearly
better** (painterly, atmospheric, warm desert, hand-shaded buildings, sail-barge, domed
arena, badlands). Automated candidates are competent top-down atlas/VTT maps but **less
painterly**. Per Brian's "don't switch to something worse" → **keep current maps for launch.**

Root pattern: Gemini-via-img2img-from-a-schematic-seed trends toward schematic/labeled
output. The brief can fix specific defects (water, text) but can't fully override the seed's
schematic pull on *style*. The original 8 paintings were better because Brian **manually
curated** them.

### 3d. The ONE untried high-value lever: STYLE-REFERENCE
`cli.py` supports **`--style <png>`** (plumbed through `batch.py:75,103,130` →
`NanoClient.generate_image(seed, style_ref, brief)`; both images go in one multipart call as
`inline_data` parts). **Not yet tried.** Feeding the *existing painterly plate*
(`static/maps/mos_eisley_substrate.png`) as the style anchor should pull Gemini toward
painterly + away from grid/text. **This is the next experiment if continuing the test.**

To run it you must first re-apply the two good iterations (they were **restored to originals**
on disk after each run — the test is non-destructive):
1. Regenerate the **desert seed**: override `tools/make_substrate_seed.DISTRICT_HUES` to warm
   desert hues (drop the slate-blue index-0; Gemini paints index-0 as WATER) + mute
   `LM_DIST`/`LM_GEN`, then call `render('mos_eisley', 'clone_wars', ...)`.
2. Write the **name-free brief** (`static/tools/seeds/mos_eisley_paint_brief.md`): strip
   proper-noun landmark names, describe features by type+position, strong
   "WORDLESS PAINTING / NO TEXT / NO water / NO blue" framing.
3. `python -m tools.mapgen.cli paint --area mos_eisley --n 3 --timestamp styleref1 --style static/maps/mos_eisley_substrate.png`
4. Restore seed+brief in a `finally`.
(Backup/restore + desert-seed + name-free-brief were done as a self-contained venv script
with `GEMINI_API_KEY` in env — rebuild it; the prior temp script wasn't persisted.)

### 3e. Discipline / gotchas (carry forward)
- **Key never committed:** `GEMINI_API_KEY` passed via env ONLY. (Verified no leak.)
- **Never run `select` until Brian approves** a candidate. When you do, there's a slug bug:
  `batch.py` select-naming uses `result.area_key.replace('.','_')` — for `mos_eisley` it's
  fine, but for a dotted area key it should `rsplit('.',1)[-1]`. Fix before a real select.
- **Owed: a painted-city screenshot for the Claude Design handoff.** The current screenshot
  set (`09_map_preview`) used the *procedural* preview page, NOT a painted city — that's why
  "it didn't even look like we were using the painted maps." When capturing, turn on the
  room-cell + click overlay so the clickable rooms are visibly floating ON the painting
  (visual proof of §3b walkability).
- Background context memory: `maps-quality-automation-future.md`.

---

## 4. Hosting & branding decisions

- **Public name = Parsec** (decided). Internal = SW_MUSH (see §1).
- **Hosting = Brian's HOME machine** (NOT corporate/Lockheed — he has never run Claude from
  Lockheed). Ollama stays ON (local Mistral 7B for NPC dialogue) — that was the whole reason
  for the local-LLM route. The MEMORY index line that said "corporate box behind a wall" was
  WRONG and has been corrected (it's Norton AV on a home PC).
- **Norton TLS** intercepts HTTPS on the home box → Python certifi fails. Fix = `truststore`
  reading the Windows cert store. Applied to `nano_client.py` (§3). **The Director's Anthropic
  path (`ai/claude_provider`) already has the fix; verify any OTHER outbound aiohttp path
  (e.g. future API callers) gets the same `_build_ssl_context()` before launch.**
- **Open hosting work (not finished):** a home box must be reachable from the internet — a
  tunnel (Cloudflare Tunnel / Tailscale Funnel), dynamic DNS, and a domain. Cost target:
  cheap. This thread did not stand up hosting; it's a launch task to resume.
- Budget: **$30 Anthropic** (Director only, $20/mo circuit breaker) + **$10 Gemini** (maps).

---

## 5. The 3 parallel tasks Brian greenlit ("I lean towards all 3")

1. **UI auto-fixes** from the Claude Design review (`ea4d604` logged the ranked punch-list).
   Rebrand items landed (§1). Remaining punch-list items: verify against the review doc +
   TODO.json.
2. **Concurrency verification campaign** — **DONE** (§2: 7 fixes + findings doc).
3. **Bounded help-sweep** — verify status against TODO.json / CHANGELOG (not clearly in this
   branch's commits; earlier help-corpus work was on the loops).

---

## 6. Loops

Both durable loops were **disarmed at the 6 AM wind-down** (commits `9893b8e`, `06a04c6`).
Brian said "restart the loops" later — confirm current arm-state via
`tools/durable_loop.py` / Task Scheduler before assuming either is running. Sonnet =
CONTENT loop; Opus = QUALITY loop; coordinated via `OPUS_CLAIM.md`. See memory
`inflight-overnight-2026-06-15-solo.md`.

---

## 7. Open decisions / next-step menu for the new chat

- [ ] Run `run_all_tests.bat` gate → merge `drop/sidebar-contract-handoff-capture` to main.
- [ ] Concurrency HIGH: pick fix (a) or (b) for the tick-scheduler uptime counter (launch-relevant).
- [ ] Map: either run the style-reference experiment (§3d) OR formally park map-automation as
      a post-launch polish pass and keep current hand-made maps (recommended for launch).
- [ ] Capture a painted-city screenshot w/ room-cell overlay for Claude Design (§3e).
- [ ] Hosting: stand up internet reachability for the home box (§4).
- [ ] Confirm loop arm-state (§6).

**Time-to-launch (held steady):** ~1 week of hardening/QA tail; the binding constraint is
QA + Brian's decisions, not throughput (memory `launch-estimate-and-qa-campaign-2026-06-16`).
