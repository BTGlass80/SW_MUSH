# SW_MUSH — Claude Code Project Memory

Star Wars D6 MUSH, Clone Wars era (~20 BBY), WEG Revised & Expanded ruleset.
Stack: Python 3.14 / aiohttp / aiosqlite / SQLite, vanilla-JS SPA web client, Ollama Mistral 7B (NPC dialogue), Claude Haiku via API (Director AI, ~$20/mo circuit breaker).
Sole developer: Brian. Web-first design policy — new features target the web client; Telnet gets graceful degradation ("requires web client") and exists for admins/purists only.

## Authority order

1. `TODO.json` + `CHANGELOG.md` (repo root) — authoritative for current state.
2. Most recent `docs/design/HANDOFF_*.md` for the subsystem.
3. Most recent versioned design doc in `docs/design/` (`*_v2` beats `*_v1`).
4. `docs/design/sw_d6_mush_architecture_v51.md` — KNOWN STALE, pending v52 reconciliation. Never trust it over CHANGELOG/TODO.

See `docs/design/INDEX.md` for the full categorized document map.

## Hard invariants — verify, never assume

- **No phantom claims, in either direction.** Before claiming any symbol/feature/file exists OR is missing, grep the working tree at symbol level. Handoff docs, memory, and design docs are unreliable without verification against HEAD.
- **Extend, don't add.** Modify existing engine systems rather than creating parallel ones. New top-level systems require an explicit design decision from Brian.
- **No phantom producers/consumers.** Never render a field without a real producer. Never ship a data entry (encounter, item, event) without the code that consumes it. Never invent parser commands.
- **Faucets and sinks land together.** Any credit faucet ships in the same drop as its corresponding sink.
- **Funnel functions are mandatory:**
  - All credit movement → `adjust_credits(char_id, delta, "tag")`
  - All out-of-combat dice → `perform_skill_check()`
  - All influence changes → `adjust_territory_influence()`
- **`force_sensitive` is derived state** — reconstructed from presence of `control`/`sense`/`alter` keys in the attributes JSON blob. NEVER pass it as a `save_character` kwarg.
- **WEG R&E D6 mechanics only.** WotC-era sources are lore-only; re-stat everything to D6 from scratch. Verify each creature/item's provenance at build time.
- **Era cleanness (B3):** No Imperial/Empire/Rebel/TIE in production strings. Comments and era-mapping keys are exempt. Sanctioned do-not-touch surfaces: `village_trials.py` dark-future-self prophecy; director-axis model codes `imperial`/`rebel` (zone-tone keys, not org codes). Canonical Clone Wars figures never appear as open-world NPCs.
- **Map safety:** world YAML edits are purely additive (zero deleted lines). Coordinate golden-snapshot guard pins exterior surface rooms. Edit YAML via comment-preserving string replacement, never a yaml round-trip rewrite.
- **Equipment:** per-slot ItemInstance is canonical via `read_equipment` / `equipment_keys` / `write_equipment` in `engine/items.py`. Known bounded debt: `Character.equipped_weapon` / `worn_armor` still hold bare key strings (`TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES`).
- **Shop commands:** `vendor_kind` branches buy/sell — there is no unified "buy <slot#> from <shop>" pattern. Ground break-free is automatic at round-end; there is no `breakfree` verb.

## Testing protocol

- Ground truth: full suite via `run_all_tests.bat` (~7,700+ tests) on this Windows box.
- During iteration: run **targeted** tests for touched modules only (`python -m pytest tests/<module> -x`), plus AST/syntax validation of every touched Python file and YAML validation of every touched data file.
- Full suite is the **gate before commit/merge**, not an inner-loop step.
- Test isolation gotcha: world-events singleton is `engine.world_events._manager`; reset to `None` between tests or event state leaks.
- Hygiene tests enforce CHANGELOG.md + TODO.json updates landing in the same change as code. Per-drop new test files are required.

## Drop workflow (Claude Code era)

1. One drop = one git branch (`drop/<short-name>`). Plan in plan mode first for anything non-trivial.
2. Implement with targeted tests green and AST validation clean.
3. Update `CHANGELOG.md` and `TODO.json` in the same commit as the code.
4. Brian runs `run_all_tests.bat`; merge to main only on a green full suite.
5. Genuine design forks: do not guess. Log them in `design_calls_pending_brian` (in TODO.json) and ask. Resolved calls move to `design_calls_resolved_recent`.

## Communication style

Brian communicates tersely ("B, go", "Continue", "A"). Self-direct with minimal check-ins; surface only genuine design forks, real blockers, and completed-drop summaries. Don't narrate routine steps or ask permission for standard workflow actions.
