# SW_MUSH — CW Content Gap Plan v1.1 — Policy Decisions Addendum

**Date:** April 26, 2026 (same session)
**Supplements:** `cw_content_gap_design_v1.md`
**Purpose:** Capture user decisions on §4 Q1–Q6 and resolve dependent design issues.

---

## Decisions captured

### Q1 — Canonical character cameo policy

**Decision: Extremely restricted.** Canonical characters (Anakin, Obi-Wan, Yoda, Mace, Dooku, Grievous, Palpatine, named clone commanders, etc.) **never appear as Ollama-driven open-world NPCs**. They may appear:

- (a) **In tightly-controlled instanced quest contexts** with **fully scripted dialogue** (no Ollama generation). The currently-authored Mace Windu 3-turn Path A reception in `jedi_village.yaml` is grandfathered under this policy — it is scripted, not Ollama-driven, and instanced to Path A acceptance.
- (b) **As future PC slots** under direct player control. This is a long-term vision, not a near-term deliverable, but it shapes how cameo NPCs are stored in the data layer (see schema implication §1 below).

**Implications for the gap plan:**
- Drop I (Canonical character cameos) is reframed: it is not "author Ollama-driven cameos." It is "author scripted-only quest-instanced cameo dialogue blocks for any quest that wants one." The currently-authored Mace Path A is the reference precedent.
- Drop I shrinks from 1 session to 0–0.5 sessions of incremental authoring, only as future quest content explicitly requests a cameo. Not a standalone drop.
- The future-PC vision is recorded as a design consideration for the architecture rollup — see §3 below.

### Q2 — Era period precision

**Decision: Treat mid-war ~20 BBY as fixed**, with latitude for "whatever makes sense for gameplay/fun" when a specific narrative beat would benefit from period drift. Practical effect: NPC backstories are mid-war consistent (post-Geonosis, pre-Outer Rim Sieges), but a flashback or aged-NPC reference can stretch this when it improves the scene.

### Q3 — Imperial NPC handling

**Decision: (b) Replace in-place.** Each of the 7 Imperial-keyed GG7 NPCs is replaced with a CW-equivalent. Specific mappings (provisional — Drop A finalizes):

| Current GG7 NPC | CW Replacement |
|---|---|
| Imperial Stormtrooper | Clone Trooper (transient patrol) |
| Imperial Customs Inspector | Republic Customs Liaison |
| Imperial Patrol Trooper | Clone Patrol Trooper |
| Prefect Talmont | Republic Liaison Officer (lower-status — Republic has light footprint on Tatooine in CW) |
| Lieutenant Harburik | Clone Lieutenant (Republic outpost) |
| Feltipern Trevagg (Imperial intelligence) | Republic Intelligence Operative (or cut — see Drop A discussion) |
| Het Nkik (anti-Imperial Jawa) | Anti-Hutt Jawa (his arc shifts from Imperial-resistance to Hutt-resistance, a more era-appropriate antagonism) |

Drop A authors these in detail.

### Q4 — Faction code reconciliation

**Decision: (b) Map design-doc codes to existing factions.** Mappings:

| Design-doc code (used in FDtS v2 etc.) | Live `organizations.yaml` code |
|---|---|
| `hutt` | `hutt_cartel` |
| `bh_guild` | `bounty_hunters_guild` |
| `traders` | `shipwrights_guild` (closest commerce/utility analog in CW guild roster) |
| `underworld` | `hutt_cartel` (Hutts run the CW underworld; no separate underworld faction exists) |
| `republic`, `cis`, `independent` | unchanged (already match) |

**Action item:** A future drop (recommend folding into Drop J1 as a small validator) authors `verify_faction_codes_in_design_docs.py` to grep all design docs for the deprecated codes and confirm reconciliation. This catches the issue if it recurs in future design authoring.

### Q5 — Authoring approach default

**Decision: Re-skin first, source from CW canon when not a fit, bespoke last** with documented justification in NPC YAML file headers. The "documented justification" requirement means future bespoke NPCs (like the existing Vela Niree) need a header comment block explaining why no source-grounding was possible.

### Q6 — NPC density target

**Decision: (c) Variable density per planet.** Specific targets:

| Planet | Target NPC density | Rationale |
|---|---|---|
| Tatooine (Mos Eisley) | ~1.4 NPCs/room (matches GCW) | Already at this density via GG7 carryover — only needs Drop A remediation and Drop B additions |
| Coruscant | ~1.4 NPCs/room | Players spend time here; needs to feel populated |
| Nar Shaddaa | ~1.4 NPCs/room | Players spend time here; smuggler-moon density expectation |
| Kuat | sparse (~0.3 NPCs/room) | Destination, not hangout — small functional roster |
| Kamino | sparse (~0.3 NPCs/room) | Tipoca City is bureaucratic; small functional roster |
| Geonosis | sparse-but-combat-dense (~0.3 NPC + heavy combat templates) | War-zone planet — fewer named NPCs, many combat enemy spawns |

This produces an estimated CW NPC roster (excluding combat templates) of roughly:
- 50 Coruscant NPCs (50 rooms × 1.4 ≈ 70, minus ~20 already covered by Uscru brokers and reasonable density compression)
- 50 Nar Shaddaa NPCs
- 9 Kuat, 9 Kamino, 9 Geonosis named NPCs
- ~0–10 Mos Eisley CW additions (Drop B)
- ~7 GG7 Imperial replacements (Drop A)

Total: **~135–145 CW-specific NPCs** to author across Drops B, C1, C2, D, E, F, G. Plus the combat templates from Drop H. This is consistent with the §6 sequencing (~10 sessions total) — averaging ~14 NPCs per session, which matches the v7 Uscru brokers drop pace (6 NPCs in part of a session).

---

## Schema implication from Q1

Q1's "no Ollama for canonical characters" requires a small NPC schema extension. Currently every NPC in `npcs_gg7.yaml` and `npcs_cw_additions.yaml` has an `ai_config` block with `personality`, `dialogue_style`, `fallback_lines`, etc. — and the engine dispatches these to Ollama for runtime dialogue generation.

For canonical-character NPCs (the Mace Windu Path A authoring is the only current example, but more may come), the engine must NOT dispatch to Ollama. Two options:

- **Option A — Add a `dialogue_mode` field.** Values: `ollama_driven` (default) or `scripted_only`. Engine session adds a check: if `dialogue_mode == scripted_only`, skip Ollama and only respond from a defined dialogue tree.
- **Option B — Detect by absence.** If an NPC has `scripted_dialogue` block and no `ai_config.personality`, treat as scripted-only. More implicit, fewer explicit fields, but more brittle.

**Recommendation: Option A.** Explicit field is cleaner and forward-compatible for the future-PC vision (a `dialogue_mode: pc_controlled` value can be added when that lands).

This is an engine-surface change. **Drop I and Drop A do not depend on it being implemented immediately** — Drop A's clone-trooper replacements are Ollama-driven (they're generic clone troopers, not canonical characters). Drop I's first instance (Mace Windu) is already authored as scripted dialogue inside a quest YAML, which the engine session can special-case until the broader schema lands.

**Action item:** Engine session that touches `engine/npc_loader.py` for any reason should consider folding the `dialogue_mode` field in. Not gating any near-term content drop.

---

## Future-PC vision for canonical characters

Q1's note that "the vision is major characters to eventually be PCs" is recorded here for the architecture rollup but does not produce immediate work. Implications to track:

- Canonical-character NPC records (when and if any are authored in Drop I or beyond) should be designed so that the same record can later be repurposed as a PC template. This means: stat blocks complete and accurate, equipment lists complete, faction affiliations explicit, no ad-hoc shortcuts that would be embarrassing if a PC inherited them.
- A future engine drop adds the `dialogue_mode: pc_controlled` value (extending the §1 schema implication).
- The "ASOC" pattern — Authored Specifically Occupied Character — is a PC-control mechanic that future architecture work should design. Not in scope here.
- Until the future-PC infrastructure exists, canonical-character cameos remain scripted-only quest-instanced dialogue blocks.

---

## Updated sequencing (consolidated from gap doc §6)

Decisions Q1–Q6 are answered. The path forward consolidates:

**Stage 1 — Source extraction (next drop, fully unblocked)**

1. **Drop J1: GG6 Tramp Freighters extraction.** Pure documentation drop. Output is `gg6_tramp_freighters_extraction_v1.md` matching the format of `gg10_bounty_hunters_extraction_v1.md`. Foundation for FDtS, Drop B, Drop F, Drop G. Parallel-safe.

**Stage 2 — Foundation drops (3–4 sessions)**

2. **Drop A: GG7 era-coupling remediation.** Implements Q3 mappings. Authors `npcs_cw_replacements.yaml` (or merges into `npcs_cw_additions.yaml`). Reconciles `era.yaml`'s dangling `npcs.yaml` reference (likely by updating era.yaml to a list).
3. **Drop B: Mos Eisley CW additions.** Republic clone patrol presence, customs liaison, possibly Hutt enforcers grounded in J1 archetypes.
4. **Drop H: CW combat NPC templates.** B1 / B2 / droideka / clone trooper / CIS commando templates for combat respawn and mission generation.
5. **(Optional) J2: JAS CW reskin pass.** Defer unless near-term Jedi authoring is queued.

**Stage 3 — FDtS unblocked (1–2 sessions)**

6. **FDtS v2 step content authoring drop.** With Q4 reconciled and Mak/Lira/Grek grounded in J1.

**Stage 4 — Planetary roster build-out (per Q6 density targets)**

7. **Drop C1+C2: Coruscant Senate + Temple + Coco Town + Underworld** (~50 NPCs, possibly split across two sessions per gap doc).
8. **Drop G: Nar Shaddaa CW roster** (~50 NPCs).
9. **Drop D, E, F: Kamino, Geonosis, Kuat sparse rosters** (~9 NPCs each, possibly batched into a single session).

**Stage 5 — Polish**

10. **(Optional) Drop I: Cameo dialogue authoring** as future quests request it. No standalone session.
11. **(Optional) J3: Star Wars Sourcebook Old Republic / galaxy chapter extraction.** Defer until Coruscant authoring needs deeper grounding.

**Total revised session estimate: 8–10 sessions** (down from 10–14 in the v1 doc, mainly from absorbing Drop I and trimming Drop F into a combined drop).

---

## Open items for the next drop

The next drop is **J1: GG6 Tramp Freighters extraction**.

Scope of J1 in detail:

- **Source:** WEG40027 (Galaxy Guide 6: Tramp Freighters), PDF in project as zip-of-jpegs format. Two copies present (`WEG40027_..._compressed142.pdf` and `WEG40027_..._compressed4382.pdf`).
- **Extraction approach:** Standard WEG-PDF pattern — copy as `.zip`, unzip to JPEGs, read pages visually, transcribe canonical material into structured deliverables.
- **Expected deliverables** (matching `gg10_bounty_hunters_extraction_v1.md` format):
  - World Lore Entries — tramp freighter culture, smuggler networks, the loanshark-debt convention as a canonical mechanic, Outer Rim trade routes
  - Bounty Board / Mission Board enrichment — smuggling job archetypes, salvage missions
  - NPC Stat Block Templates — tramp captain (foundation for Mak Torvin), broker (foundation for Lira Shan), Hutt fixer (foundation for Grek), mechanic, gunner, fence
  - Equipment Catalog — Ghtroc 720 specs, common modifications, smuggling-mod conventions, sensor masks, hidden compartments
  - Design Stubs — the loanshark debt mechanic with WEG-canon framing (informs FDtS Phase 5 Hutt debt design); the freighter-as-character convention (informs ship-personality authoring)
  - Faction-code validator script (folded in per Q4 action item)
- **Estimated session size:** 1 full session.
- **Output filename:** `gg6_tramp_freighters_extraction_v1.md`
- **Parallel-safe:** Yes — no engine code, no DB migration, no YAML changes.

**Awaiting confirmation to proceed with J1.**

---

*End of CW Content Gap Plan v1.1 — Policy Decisions Addendum.*
