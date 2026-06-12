# HANDOFF — Drop 3 rolled-up: B3 vanity titles + A4 commissary

**Date:** 2026-06-03
**Base:** HEAD of `SW_MUSH_upload_20260603_2148.zip` (after B2 home-prestige).
**Zip:** `SW_MUSH_drop_b3_titles_a4_commissary_2026-06-03.zip` — **rolled up** (supersedes the earlier B3-only zip; contains both B3 and A4), root-mirrored; `Expand-Archive -DestinationPath . -Force`.
**Status:** Both slices code-complete, sandbox-validated. Two Drop-3 sinks: a cosmetic one (B3) and a faction requisition one (A4). B3 also builds the worn-title *display layer* that III.2 (Drop 4) reuses.

---

## 0. ⚠ Carry-forward pre-flight finding (unchanged from the B3 handoff)

**Drop 3 B4 (gear insurance) is recorded in `CHANGELOG.md` + `TODO.json` but its code is ABSENT from this HEAD.** `engine/gear_insurance.py` / `parser/insurance_commands.py` / `tests/test_gear_insurance.py` are missing; no `gear_insur*` references in `db/database.py`, `engine/death.py`, `server/game_server.py`; `SCHEMA_VERSION` is still **38** (the B4 entry claims v39). This upload zip is one drop short of its own bookkeeping. Neither B3 nor A4 touches the main schema, so v39 stays free and nothing here collides. **Action for you:** re-apply (or formally drop) B4 on top of this HEAD; its v39 migration remains valid since this drop added no main-schema version.

---

## PART A — Drop 3 B3: vanity titles (cosmetic sink)

### A.1 What shipped
`+title` (worn/owned + an 8-tier catalog `the Wayfarer` 2,000 → `Luminary of the Core` 400,000), `+title buy <key>` (debits `vanity_title`, **auto-wears**), `+title set <key>` / `+title clear` (switch among owned titles, free). One-time unlock — keep forever, switch freely — so sink depth = catalog breadth (~824k to collect all) + the 400k headline burn. **The worn title is visible to others** on `+who`, the room "is here" listing, and `+sheet` (Telnet line + a `title` field in the web `build_sheet_payload`). Era-clean: mundane prestige honorifics only; Jedi rank etc. stay *earned*. Refund-safe (`vanity_title_refund`). Surfaces on `@economy` automatically.

### A.2 Files
- `engine/titles.py` (NEW) — catalog + pure helpers + `purchase_title`/`set_worn_title` + the two `characters` columns via the module's own idempotent `ensure_schema` column-loop (`_TITLE_COLS`), **no `SCHEMA_VERSION` bump** (same discipline as B2 — see §0 for why that matters).
- `parser/title_commands.py` (NEW) — `+title`; registered in `server/game_server.py`.
- `db/database.py` — `vanity_titles` + `display_title` added to `_CHARACTER_WRITABLE_COLUMNS` (no migration).
- `server/game_server.py` — register `+title`; `titles.ensure_schema` wired at startup beside housing's.
- `parser/builtin_commands.py` — worn title on `+who` and in the room "is here" listing.
- `engine/sheet_renderer.py` — worn-title sub-line on the Telnet sheet; `title` field in the web payload.
- `tests/test_vanity_titles.py` (NEW, +19).

### A.3 Forward-compat (intentional)
III.2 (earned status, Drop 4) grants titles for *deeds* into the same `vanity_titles` set + `display_title` surface; `set_worn_title` already falls back to an owned-but-not-in-catalog key's raw value as its label, so earned titles slot in with no second display layer.

---

## PART B — Drop 3 A4: commissary (faction requisition sink)

### B.1 What shipped
`+commissary` (a sworn member's rank-appropriate requisition list + prices), `+commissary buy <key>` (debits `commissary_purchase`, grants the gear to inventory). Stock is per-faction and **rank-gated** (per-item `min_rank`: rank-0 members requisition basic kit; rank-1 gear needs rank 1), built from the four CW non-Jedi factions' own rank-0/rank-1 issue gear — keys match `EQUIPMENT_CATALOG` so a bought item behaves identically to an issued one (**era-clean by construction**). The **Jedi Order keeps no commissary** (austere). Refund-safe (`commissary_purchase_refund`). Surfaces on `@economy` automatically.

### B.2 Files
- `engine/commissary.py` (NEW) — `COMMISSARY_STOCK` + pure helpers + `purchase_commissary`.
- `parser/commissary_commands.py` (NEW) — `+commissary`; resolves the member's rank via `get_organization` + `get_membership`; registered in `server/game_server.py`.
- `tests/test_commissary.py` (NEW, +15).

> **No schema change, no migration, `organizations.py` untouched.** The commissary reads org membership (existing), debits the existing ledger, and grants to existing inventory.

### B.3 Scope (A4 is multi-part — this is the sink piece)
Report A4 has three parts; this delivers the economically meaningful one (the commissary `commissary_purchase` sink). The other two remain clean separate slices: **(1)** populate `FACTION_MISSION_CONFIG` for Republic+CIS (mission content/config), and **(2)** a visible stipend pay-cycle (`faction_payroll`; the stipend table already exists in `organizations.py`).

---

## 4. Validation (both slices)

**Sandbox (done):**
- AST clean on all changed files; new symbols import-load (titles: 8 titles, 824k catalog; commissary: 4 factions, 13 items).
- `tests/test_vanity_titles.py` **+19** and `tests/test_commissary.py` **+15** — all green (34 together). Each covers pure helpers, an era-cleanness guard, the recording-stub purchase branches (incl. refund-on-failure), a real in-memory `Database` path (ledger debit + persistence/grant), and structural pins.
- Regression: B2 home-prestige (13) and the PvP/bond display-surface suite (7) green — B3's surfaces append only when a title is worn (title-less output byte-identical); the commissary touches no shared module beyond the `game_server` registration list.

**Pending on your box:**
- Full ~4,854-test Windows run (ground truth).
- B3 smoke: `+title buy wayfarer` (2,000 cr + `vanity_title` on `@economy velocity`, auto-wears); a second character sees the title on `+who` / `look` / their `+sheet`; `+title set`/`clear` free; relog persists owned+worn.
- A4 smoke: join `republic`, reach rank 1, `+commissary buy dc15_blaster_rifle` (1,200 cr + rifle in inventory + `commissary_purchase` on `@economy velocity`); a rank-0 member is blocked from the rank-1 rifle; a Jedi member gets "no commissary".

## 5. Bookkeeping
- `CHANGELOG.md` — A4 entry + B3 entry prepended (A4 above B3). `TODO.json` — B3 note, the §0 phantom-finding note, and the A4 note appended to `_notes`; JSON re-validated (34 notes).

## 6. Next
Remaining Drop 3, each a clean focused slice: **A4 remainder** (Republic/CIS `FACTION_MISSION_CONFIG` + the `faction_payroll` pay-cycle), **A3** spy intel-desk demand sink, **A5** Hutt-den treasury revenue, **A8** entertainer audience-weighting. (And re-apply or formally drop **B4 gear insurance** per §0.)
