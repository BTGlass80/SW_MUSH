# SW_MUSH — Clone Wars Content Gap & Remediation Plan v1
## Design / Planning Document

**Date:** April 26, 2026
**Author:** Opus parallel-track session
**Status:** Planning artifact (no code, no YAML — produces a roadmap)
**Audience:** Future content-authoring drops, future engine-session priorities

**Pre-reads:**
- `clone_wars_era_design_v3.md` (the original pivot design)
- `sw_d6_mush_architecture_v34.md` (current state)
- `roadmap_v34.md` (current roadmap)
- `from_dust_to_stars_design_v2_clone_wars.md` (the trigger for this audit)
- `data/worlds/clone_wars/era.yaml` and `organizations.yaml` (live config)

---

## 0. Why this document exists

The CW pivot was scoped in v3 of the pivot design as primarily a **lore + tutorials + quests + faction set** rework. The implicit assumption — never written down explicitly — was that the existing 55-NPC GG7 Mos Eisley roster (`data/npcs_gg7.yaml`) would carry over to CW essentially unchanged, since it was already loaded by `engine/npc_loader.py` and was framed as "canonical Mos Eisley" rather than "canonical GCW Mos Eisley."

That assumption is wrong in two ways:

1. **~27% of the GG7 roster is era-broken in CW.** 7 NPCs are explicitly Imperial (an entity that does not exist in 20 BBY) and 8 more are GCW-coupled in their backstories or factional alignments.
2. **The non-Tatooine CW planets are effectively unpopulated.** 229 CW rooms across 6 planets (Coruscant, Geonosis, Kamino, Kuat, Nar Shaddaa, Tatooine) currently host 7 CW-specific NPCs total (Vela Niree + 6 Uscru brokers). Outside Mos Eisley — where the era-portable GG7 NPCs still work as-is — the CW world is roughly 46× less NPC-dense than the GCW Mos Eisley we built.

This document catalogs the gap, identifies what source material is and is not available, surfaces policy decisions that have to be made before mass authoring, and breaks the remediation work into drop-sized chunks with sources identified per chunk. **No content authoring happens in this drop.** The output is a plan that future drops execute against.

The trigger for this audit was a question about whether the FDtS v2 quest chain should reuse Mak Torvin (a bespoke FDtS v1 NPC, not GG7-canon) or pull from CW source material. Investigating that question revealed the larger scope problem documented here.

---

## 1. Audit findings (concrete numbers)

### 1.1 GG7 NPC roster — era-portability breakdown

55 NPCs total in `data/npcs_gg7.yaml`. Loaded for both eras by current `engine/npc_loader.py`.

**7 Imperial-keyed (cannot exist in CW — Empire not formed until end of Episode III):**
- Prefect Talmont
- Lieutenant Harburik
- Imperial Stormtrooper
- Imperial Customs Inspector
- Imperial Patrol Trooper
- Feltipern Trevagg (Imperial intelligence agent)
- Het Nkik (whose entire arc is anti-Imperial Jawa rebellion)

**8 GCW-coupled but salvageable (need re-skin):**
- Lady Valarian (Whiphid crime boss — extant in CW lore but with different operations)
- Momaw Nadon (Ithorian exile — backstory works, but the framing references the rising Empire)
- Armanda Durkin (smuggler — generic enough, but mentions Imperial blockades)
- Garindan (Imperial snitch — could be a Republic/CIS snitch, or cut)
- Lup, Heist (criminal NPCs with Imperial-bribery angles)
- Sergeant Kreel (specifically named GCW Imperial trooper)
- General Cracken (Rebel Alliance — definitively does not exist in CW)

**40 era-portable as-is** — cantina denizens, Jawas, Tuskens, generic underworld characters whose framings don't specifically tie to a war that hasn't started yet.

### 1.2 CW-specific NPC roster — current state

| File | NPCs | Coverage |
|---|---|---|
| `data/worlds/clone_wars/npcs_cw_additions.yaml` | 1 | Vela Niree (Mos Eisley rumor producer for Village quest) |
| `data/worlds/clone_wars/wilderness/uscru_fringe_brokers.yaml` | 6 | Uscru Fringe brokers (Coruscant Underworld) |
| **Total CW-specific** | **7** | — |

### 1.3 Planet/room density check

| Planet | Rooms (approx) | CW-specific NPCs | GG7 era-portable | Effective coverage |
|---|---|---|---|---|
| Tatooine (Mos Eisley) | 40 | 0 | ~40 | Reasonable (GG7 carries it) |
| Tatooine (Dune Sea wilderness) | 4 | 0 | 0 | Sparse — Anchor Stones, Village landmarks |
| Coruscant | ~50 | 6 (Uscru brokers, all in one room) | 0 | Effectively empty |
| Nar Shaddaa | ~40 | 0 | 0 | Effectively empty |
| Kamino | ~30 | 0 | 0 | Empty |
| Geonosis | ~30 | 0 | 0 | Empty |
| Kuat | ~30 | 0 | 0 | Empty |

Numbers are approximate (CW rooms are split across `zones.yaml` and `planets/*.yaml` with some rooms defined inline in build scripts). The order-of-magnitude conclusion holds: **outside Mos Eisley, the CW world is unpopulated**.

### 1.4 Dangling references found during audit

- `data/worlds/clone_wars/era.yaml` `content_refs.npcs` points at `npcs.yaml` — that file does not exist. Either era.yaml is wrong, or there is an unspecified expectation that a `data/worlds/clone_wars/npcs.yaml` will be authored as part of this work.
- The FDtS v2 design doc (`from_dust_to_stars_design_v2_clone_wars.md`) uses faction codes `hutt`, `bh_guild`, `traders`, `underworld` in JSON examples. Live `organizations.yaml` uses `hutt_cartel`, `bounty_hunters_guild`, has no `traders`, and has no `underworld`. **The design doc as authored is inconsistent with the live faction roster.** This must be reconciled before FDtS step content authoring (see §5.1).

---

## 2. Gap inventory

The remediation work decomposes into ten distinct chunks. Each is sized to be a parallel-safe content drop on its own (1–2 sessions). They are not strictly sequential — some can run in parallel — but §6 proposes an ordering.

### Gap A — GG7 era-coupling remediation
Audit and resolve the 15 GCW-coupled GG7 NPCs (7 Imperial-keyed + 8 salvageable). The Imperial-keyed NPCs need either (a) replacement with CW-canon analogs (clone trooper patrol, Republic customs officer, etc.) or (b) era-conditional loading where they only spawn in GCW. The salvageable 8 need re-skinned descriptions and faction tags.

**Source:** No external source needed for re-skin. For replacement NPCs (Republic clone trooper, Republic customs officer, etc.), CW canon (TCW series, Episode II/III) provides templates. WEG D6 has no native Republic-trooper stat block, so we extrapolate from existing trooper templates in GG7 (Imperial Stormtrooper) and the WEG core book — the d6 stats are mechanically identical, only the faction and equipment names change.

**Estimated size:** 1 session.

### Gap B — Mos Eisley CW-specific additions
Mos Eisley in CW exists in canon — Anakin's mother Shmi is referenced as living in Mos Espa, and the Jedi visit Tatooine in Episode II. The era flavor for Mos Eisley should reflect: light Republic clone trooper presence (passing through, not garrisoned), Hutt enforcement still dominant, no Imperial customs office (yet). A small content set of CW-specific Mos Eisley NPCs: a clone patrol trio that occasionally passes through, a Republic customs liaison (minor functionary, not a garrison commander), a Hutt enforcer or two who feature in the Vela Niree / Village storyline cross-reference.

**Source:** GG7 (Mos Eisley geography — already in use), GG6 Tramp Freighters (smuggler/freighter archetypes).

**Estimated size:** 1 session.

### Gap C — Coruscant NPC roster
Largest hole. Coruscant in CW is the seat of the Republic, the Jedi Temple, the Senate, and (in the lower levels) a sprawling underworld that is canonical TCW / TPM territory. We have 50 rooms and 6 NPCs, all crowded into one Uscru room. Need NPCs across:
- Senate District (Senators, aides, Republic functionaries)
- Jedi Temple (if accessible — see §4 policy questions; at minimum some greeters/initiates as flavor)
- Coco Town (FDtS-relevant freelance-job hub, mid-levels)
- Underworld (level-1313-style criminal underbelly — already partially covered by Uscru brokers)
- Galactic City spaceport (clone trooper customs, transit officials)

**Source:** CW canon (TCW series Coruscant episodes, Episode II/III), JAS for Jedi Temple flavor (era-skewed but Jedi pedagogy carries), Star Wars Sourcebook Old Republic / Jedi Order section.

**Estimated size:** 2 sessions (probably split as Senate+Temple in one drop, Coco Town+Underworld in another).

### Gap D — Kamino NPC roster
Kamino is the canonical CW clone production world. NPCs needed: Kaminoan administrators (Lama Su, Taun We — are these canonical-character cameos? policy decision), clone trainers, ARC trooper instructors, some clone trainees. Geographic scope is Tipoca City and adjacent training facilities.

**Source:** CW canon (Episode II prologue, TCW series). No D6 source.

**Estimated size:** 1 session.

### Gap E — Geonosis NPC roster
Geonosis is a CIS war-zone planet in CW (the Battle of Geonosis is the war's opening battle). NPCs needed: Geonosian hive workers, droid foundry overseers, Separatist liaisons, and — crucially — a population of combat-eligible enemy droid templates (B1 battle droid, B2 super, droideka). Geonosis is the most combat-flavored planet in the CW roster.

**Source:** CW canon (Episode II), the WEG core book droid stats can be re-skinned for B1/B2/droideka templates with minor faction-tag changes.

**Estimated size:** 1 session.

### Gap F — Kuat NPC roster
Kuat is the shipbuilding hub and FDtS Phase 5's required destination (Lira Shan as KDY broker). NPCs needed: KDY personnel (engineers, bureaucrats, ship brokers), Kuati customs officers, possibly orbital-shipyard workers. Compact roster — Kuat is a destination but not a hangout.

**Source:** CW canon mentions Kuat throughout. No D6-specific source. GG6 Tramp Freighters provides the broker archetype that Lira Shan exemplifies.

**Estimated size:** 1 session (small drop — could be combined with another).

### Gap G — Nar Shaddaa CW-specific roster
Nar Shaddaa is era-portable in concept (the Smuggler's Moon is canonically active in any era) but currently has zero CW NPCs. The FDtS v2 design names three: Zekka Thansen (smuggler network operator), Renna Dox (shipwright), Doc Myrra (underground medic). Plus background population: cantina patrons, dock workers, Hutt enforcers, fixers.

**Source:** GG6 Tramp Freighters (smuggler archetypes), CW canon for any specifically-CW Nar Shaddaa material.

**Estimated size:** 1 session.

### Gap H — Combat NPC templates
Currently combat enemies in CW are sparse on the ground and mostly archetypal in space (the 5 traffic archetypes). Ground combat needs CW-flavored enemy templates: B1 battle droid (low-tier), B2 super battle droid (mid-tier), droideka (heavy), CIS commando, Separatist mercenary, and Republic-side combat NPCs for missions where the player works against the CIS. These are NPC templates (template_id, stats, behavior) that mission-generation and combat-respawn systems can reference, not unique named characters.

**Source:** CW canon (films + TCW series), WEG core book droid stat patterns.

**Estimated size:** 1 session.

### Gap I — Canonical character cameo policy and (optional) authoring
Whether and how players encounter canonical CW characters (Anakin, Obi-Wan, Yoda, Mace, Dooku, Grievous, Palpatine, named clone commanders) is a **policy decision** (see §4). If the answer is "yes, with restrictions," authoring a tightly-controlled cameo roster (Yoda at the Temple, Obi-Wan briefly on Tatooine, Mace already authored for Village quest Path A) is a separate drop. If the answer is "no," skip this gap and rely on referenced-only canonical characters (mentioned in dialogue, never spawned as NPCs).

**Source:** CW canon (films + TCW series). All authoring is canon-grounded by definition.

**Estimated size:** 1 session if pursued; 0 sessions if policy says no.

### Gap J — Source extractions
Deep extraction passes on source material whose templates feed several other gaps:
- **GG6 Tramp Freighters extraction** — produces a `gg6_tramp_freighters_extraction_v1.md` analogous to the gg10/jas/totj extractions. Outputs: tramp-captain archetypes (foundation for Mak Torvin, Lira Shan in Gap F, Zekka in Gap G, the entire FDtS economic loop), the loanshark-debt mechanic with WEG-canon framing, the ship-as-character-in-its-own-right convention.
- **JAS Jedi templates re-skin pass** — produces a CW-coupled supplement to the existing `jas_extraction_v1.md` covering Padawan / Knight / Master archetypes that work in 20 BBY. Useful for any future Jedi NPC authoring (Gap C Temple, Gap I cameos).
- **Star Wars Sourcebook galaxy/Old Republic chapter extraction** — useful for Coruscant Senate flavor and any deep-history references the CW lore wants to lean on.

**Source:** WEG40027 (GG6), WEG40114 (JAS — already extracted, only needs CW re-skin pass), Star Wars Sourcebook 2nd Ed (we still have WEG400931/WEG400932 in the project).

**Estimated size:** GG6 extraction = 1 session. JAS CW re-skin = 0.5 session (additive). Star Wars Sourcebook galaxy chapter = 1 session if pursued.

### Summary table

| Gap | Description | Source | Sessions |
|---|---|---|---|
| A | GG7 era-coupling remediation | GG7, WEG core | 1 |
| B | Mos Eisley CW additions | GG7, GG6 | 1 |
| C | Coruscant roster | CW canon, JAS, SWS | 2 |
| D | Kamino roster | CW canon | 1 |
| E | Geonosis roster + droid combat templates | CW canon, WEG core | 1 |
| F | Kuat roster | CW canon, GG6 | 1 (combinable) |
| G | Nar Shaddaa CW roster | GG6, CW canon | 1 |
| H | CW combat NPC templates | CW canon, WEG core | 1 |
| I | Canonical character cameos (optional) | CW canon | 0 or 1 |
| J | Source extractions (GG6 + JAS reskin + SWS) | WEG D6 + SWS | 1.5–2.5 |
| **Total** | — | — | **10–12 sessions** |

---

## 3. Source material inventory and limitations

### What we have (in the project)

- **WEG40027 — Galaxy Guide 6: Tramp Freighters.** GCW-era but archetypes are era-portable. Foundation for the entire FDtS arc (tramp captains, loanshark debt, the freighter-as-home convention).
- **WEG40069 — Galaxy Guide 7: Mos Eisley.** GCW. Already mined. Geography is era-portable; the 7 Imperial NPCs are the era-broken subset.
- **WEG40114 — Jedi Academy Sourcebook.** GCW post-RotJ (Luke's academy era), but Jedi templates carry well to CW with re-skinning. Already extracted to `jas_extraction_v1.md`.
- **WEG40124 — Galaxy Guide 1: A New Hope.** GCW. Not directly relevant to CW NPC authoring.
- **WEG40048 — Gamemaster Kit.** GCW supplement. Not directly relevant.
- **WEG40120 — RPG 2nd Edition R&E Core.** Era-agnostic. Generic stat blocks (trooper, customs officer, criminal) usable as templates.
- **Star Wars Sourcebook 2nd Edition (WEG400931 / WEG400932).** GCW core but contains a galaxy chapter and Old Republic / Jedi Order historical material useful for Coruscant Senate flavor.
- **Tales of the Jedi extraction.** Old Republic era (~4000 BBY). Jedi templates from a different period; useful as inspiration but not direct.
- **Galaxy Guide 10 Bounty Hunters extraction.** GCW. Era-portable bounty hunter archetypes.
- **Cracken's Rebel Field Guide extraction.** GCW. Rebel-keyed; not directly useful for CW (the CIS resistance is structurally different from the Rebel Alliance).

### What we don't have

- **No native WEG D6 Clone Wars sourcebooks.** WEG's D6 line ended ~1998, before the prequels released. Genuine WEG D6 CW source material does not exist as a published product.
- **No d20 era WotC sourcebooks** (Republic Sourcebook, Geonosis and the Outer Rim Worlds, Coruscant and the Core Worlds). These are the closest published-RPG analogs to a "WEG CW sourcebook" but in d20 not D6 format. We don't have them in-project, and even if we did, the stat conversion overhead is real.
- **No structured TCW series episode/character database.** The Clone Wars TV series is the largest single body of CW canonical NPC content but is only available as video — extracting from it would mean curated Wookieepedia-style mining.

### Implication

For CW NPC authoring at scale, the source-mining workflow we've used for GCW (extract a sourcebook PDF → produce a canonical-template extraction doc → ground bespoke authoring on it) is **not directly available**. The replacement workflow has three options:

1. **Re-skin GG6/GG7/JAS templates with CW flavor.** Highest source fidelity, lowest creative latitude. Works for archetypes that genuinely carry across eras (tramp captain, cantina patron, Jedi Master).
2. **Author bespoke CW NPCs grounded in canonical CW media.** Requires curating a reference list (Wookieepedia is the practical option). The "extraction doc" for this kind of source is a curated character-and-archetype reference rather than a PDF re-key.
3. **Author bespoke CW NPCs with no specific source ground.** What we did with Vela Niree. Lowest creative friction, lowest source fidelity — same issue this whole audit was triggered by.

Recommended default: option 1 where possible (FDtS NPCs, generic background population), option 2 for canon-distinctive content (Coruscant Jedi Temple, Kamino, Geonosis), option 3 only as a last resort with documentation of the choice.

---

## 4. Policy questions requiring decisions before authoring

These are the design questions that have to be answered by the user before any authoring drop runs. Each question is bounded — it has a small set of reasonable answers, not an open canvas.

### Q1 — Canonical character cameo policy

**Question:** Do players encounter Anakin Skywalker, Obi-Wan Kenobi, Yoda, Mace Windu, Count Dooku, General Grievous, or Palpatine as in-game NPCs?

**Options:**
- **(a) No cameos.** Canonical characters are referenced in dialogue and lore but never spawn as interactive NPCs. Player experience is grounded in original characters.
- **(b) Restricted cameos.** A specific small set of canonical characters can appear in tightly-controlled contexts. Mace Windu in Village quest Path A reception is already authored under this policy implicitly. Yoda at the Jedi Temple as a brief greeter, Obi-Wan as a transient Mos Eisley patron, etc. — each cameo needs explicit policy approval.
- **(c) Open cameos.** Canonical characters appear normally in contextually-appropriate locations. High immersion, high IP-handling exposure, and high "did the engine just have Yoda say something stupid" risk.

**Default if not answered:** (b) — the Mace Windu Village reception is already in place under this policy implicitly.

### Q2 — Era period precision

**Question:** Where in the Clone Wars are we?

**Status:** `era.yaml` says ~20 BBY (mid-war). This is settled in config. The policy question is whether we treat this as a fixed timeline reference or a sliding window. Mid-war means: post-Geonosis (2 years in), pre-Outer Rim Sieges (~19 BBY), Anakin is a Knight, Ahsoka has been Anakin's Padawan for ~1 year, the Republic has been at war long enough that public weariness is canonical. NPC backstories must be consistent with this period.

**Recommended:** Treat mid-war as fixed. Any cameo (Q1) must be consistent with their mid-war activities (Anakin is at the front, not on Coruscant most of the time; Mace is on Coruscant; Yoda is on Coruscant or commanding clones; Dooku is in deep CIS space; Grievous is at the front).

### Q3 — Imperial NPC handling

**Question:** What happens to the 7 Imperial-keyed GG7 NPCs in CW?

**Options:**
- **(a) Era-conditional load.** Engine session adds an `era_compatibility` field to NPC records; Imperial NPCs only spawn when active era is GCW. Lowest content effort. Future-proof.
- **(b) Replace in-place.** Each Imperial NPC is replaced with a CW-equivalent (Imperial Stormtrooper → Clone Trooper Sergeant; Imperial Customs Inspector → Republic Customs Liaison; Prefect Talmont → a CW analog official). Highest content effort, most contextually appropriate.
- **(c) Hybrid.** Generic Imperial NPCs (Stormtrooper, Patrol) get CW analogs by replacement. Named individuals (Talmont, Harburik, Trevagg) get era-conditional loaded out of CW with no replacement (their roles vanish, no new character fills them).

**Recommended:** (c). It's the cheapest path to "CW Mos Eisley feels right" without inventing forced replacements for named individuals whose roles don't really exist in CW (a Republic prefect of Tatooine is canonically dubious — the Republic has minimal presence on Tatooine in CW).

### Q4 — Faction code reconciliation

**Question:** Several CW design docs (notably FDtS v2) use faction codes that don't exist in `organizations.yaml`. The codes used in the design doc (in JSON examples and reward specs) are: `hutt`, `bh_guild`, `traders`, `underworld`. The codes that actually exist in `organizations.yaml` are: `republic`, `cis`, `jedi_order`, `hutt_cartel`, `bounty_hunters_guild`, `independent`, plus NPC-only `sith`, `separatist_council`, plus 6 era-portable guilds (`mechanics_guild`, `shipwrights_guild`, `medics_guild`, `slicers_guild`, `entertainers_guild`, `scouts_guild`).

The mismatch: `hutt` vs `hutt_cartel`, `bh_guild` vs `bounty_hunters_guild`, no `traders` faction, no `underworld` faction.

**Options:**
- **(a) Add `traders` and `underworld` factions to `organizations.yaml`.** Requires designing what those organizations are (organizational structure, ranks, HQ rooms). Engine surface change.
- **(b) Map the design-doc codes to existing factions.** `traders` → `shipwrights_guild` (closest commerce/utility analog) or `mechanics_guild`; `underworld` → `hutt_cartel` (since Hutts run the underworld in this era anyway). `hutt` → `hutt_cartel`, `bh_guild` → `bounty_hunters_guild`.
- **(c) Author new factions in a future drop and use placeholders meanwhile.** Hybrid — code FDtS against (b) now, swap in real factions later.

**Recommended:** (b) for now. The "Traders' Coalition" as a distinct faction is an FDtS v1 invention and never had a design pass. Adding it to organizations.yaml without a real design is worse than mapping it. This decision affects FDtS step content authoring directly — must be made before FDtS v2 ships as content.

### Q5 — Authoring approach default

**Question:** When a CW NPC has no direct WEG D6 source, what's the default authoring approach?

**Options:** As listed in §3 — re-skin existing template, source from canonical CW media (Wookieepedia-style), or author bespoke.

**Recommended:** Re-skin first; source from canon when archetype-extraction isn't a fit; bespoke last with documented justification in the file's header comments.

### Q6 — NPC density target

**Question:** What's the right NPC count per zone in CW?

**Context:** GCW Mos Eisley has ~55 NPCs across 40 rooms (1.4 NPCs/room). Some are stationary (named characters in specific rooms), some are mobile (patrols, wanderers). For CW, no zone outside Mos Eisley currently approaches this density.

**Options:**
- **(a) Match GCW density.** Author until each CW planet has ~1 NPC per room. ~189 NPCs needed for 5 non-Tatooine planets. Significant authoring.
- **(b) Aim for half-density.** ~95 NPCs across 5 planets. Less authoring, more sparse feel.
- **(c) Variable density per planet.** Coruscant and Nar Shaddaa to GCW density (busy planets), Kamino/Geonosis/Kuat sparse (utilitarian planets, less hangout potential).

**Recommended:** (c). Coruscant and Nar Shaddaa get full populations because players spend time there; Kamino/Geonosis/Kuat get smaller rosters because they're destinations, not homes.

---

## 5. Cross-cutting issues surfaced by the audit

### 5.1 Faction code drift in CW design docs

The faction-code mismatch identified in Q4 above isn't unique to FDtS v2. Several CW-era design docs were authored before `organizations.yaml` was finalized and use earlier-draft codes that drifted from the live config. Any drop that touches CW NPC content should grep its source for `hutt`, `bh_guild`, `traders`, `underworld` and reconcile against the live `organizations.yaml` codes before authoring. A small validator script (`verify_faction_codes_in_design_docs.py`) could automate this check.

### 5.2 The dangling `npcs.yaml` reference

`era.yaml` `content_refs.npcs` points at `npcs.yaml`, which doesn't exist. This implies the original era.yaml authoring expected a single CW-era NPC consolidation file. Two options: (a) collapse `npcs_cw_additions.yaml` and future-authored CW NPC files into a single `npcs.yaml` (matching era.yaml), or (b) update era.yaml to list the actual files (`npcs_cw_additions.yaml`, future files) as a list. Option (b) scales better as we add more CW NPC files.

### 5.3 The engine's era-conditional NPC loading does not exist

The era flavor substitutions in `era.yaml` (`default_trooper_type: clone`, `default_imperial_substitute: republic`) imply the engine has architectural support for era-flavor swaps in NPCs. Investigation of `engine/npc_loader.py` would be needed to confirm whether this is wired up; if not, Gap A's option (a) — era-conditional load of Imperial NPCs — depends on an engine session that adds the loader logic. **This is an engine-surface check that should happen before any drop locks in option (a).**

### 5.4 Scope-creep risk for FDtS

FDtS step content authoring has been the next-up drop on the parallel content track since v7. With this audit's findings, two things become true:

- FDtS v2 cannot ship as content without the §4 Q4 faction-code reconciliation being decided.
- FDtS v2 references NPCs (Mak, Lira, Grek) whose authoring is improved by the Gap J GG6 extraction.

So the FDtS drop now depends on at least one prior drop (the Q4 decision) and benefits from another (Gap J GG6 extraction). It can no longer be the next-up drop in isolation.

### 5.5 The Vela Niree precedent

`npcs_cw_additions.yaml` already establishes a working pattern for CW NPC authoring with rich fields (`rumor_producer`, `directed_responses`, `personality`, `dialogue_style`). All CW NPC authoring in subsequent drops should match this schema unless engine-side schema changes are explicitly part of the drop. This also means the Vela Niree NPC is the canonical reference example — future drops should view it before authoring new NPCs.

---

## 6. Proposed sequencing

Sequencing is constrained by dependencies and decision gates. The proposed order:

**Stage 1 — Decisions and one cheap drop (next 1–2 sessions)**

1. **User decides on Q1–Q6** (this document is the input).
2. **Drop J1: GG6 Tramp Freighters extraction.** Produces the `gg6_tramp_freighters_extraction_v1.md` artifact. Foundation for Mak Torvin, Lira Shan, and Nar Shaddaa archetypes. Parallel-safe (pure documentation; no YAML, no code).

**Stage 2 — Foundation drops (3–4 sessions)**

3. **Drop A: GG7 era-coupling remediation.** Implements Q3's chosen option. Adds CW-era replacements or era-conditional flags. Touches `data/npcs_gg7.yaml` directly OR authors a `data/worlds/clone_wars/npcs_cw_replacements.yaml` if option (c) is chosen.
4. **Drop B: Mos Eisley CW additions.** Authors clone patrol, Republic customs liaison, Hutt enforcers, etc. Depends on J1 (GG6 archetypes for the Hutt enforcers).
5. **Drop H: CW combat NPC templates.** Authors B1 / B2 / droideka / clone trooper / CIS commando templates. No story; just stats and behaviors. Independent of other drops.
6. **(Optional) J2: JAS CW re-skin pass.** If we know we're going to need Jedi NPC authoring soon, this is a small additive drop. If not, defer.

**Stage 3 — FDtS unblocked (1–2 sessions)**

7. **FDtS v2 step content authoring drop.** Uses the Q4 faction-code reconciliation, Mak Torvin / Lira Shan / Grek grounded in J1, the existing tutorial-chains.yaml and jedi_village.yaml schema patterns. No longer scope-creeping because the cross-cutting issues are resolved.

**Stage 4 — Planetary roster build-out (4–6 sessions)**

8. **Drop C1: Coruscant Senate + Jedi Temple roster.**
9. **Drop C2: Coruscant Coco Town + Underworld roster.** (Or merge C1+C2 if scope allows.)
10. **Drop G: Nar Shaddaa CW roster.** Authors Zekka, Renna, Doc Myrra (per FDtS), plus background population.
11. **Drop D: Kamino roster.**
12. **Drop E: Geonosis roster.** (Combat-heavy; benefits from H landing first.)
13. **Drop F: Kuat roster.** (Smallest; could be combined with another or done last.)

**Stage 5 — Optional polish (0–1 sessions)**

14. **(Optional) Drop I: Canonical character cameos.** Only if Q1 = (b) or (c) and a specific cameo set is approved.
15. **(Optional) J3: Star Wars Sourcebook galaxy chapter extraction.** Only if Coruscant / lore-heavy drops want deeper grounding.

**Total: 10–14 sessions of parallel-safe content work.**

---

## 7. What this document doesn't do

- **No code.** Every gap requires content authoring; some require engine-side support. Engine-side is out of scope for parallel content sessions and gets deferred to engine drops as usual.
- **No final NPC authoring.** Even concrete-sounding gaps (Mak Torvin grounded in GG6) are deferred to their respective drops. This document scopes them and identifies sources; it doesn't author them.
- **No locked-in policy answers.** The §4 questions are real decisions for the user; the doc proposes defaults but the user is the policy owner.
- **No commit on canonical character handling.** Policy Q1 is a meaningful design choice with downstream content implications. This doc surfaces it; the user decides.

---

## 8. Open questions for the user

These are the action items needed to unblock the next drop:

1. **§4 Q1–Q6 decisions.** All six policy questions need answers.
2. **Drop J1 priority confirmation.** Is GG6 Tramp Freighters extraction the right next drop, or should something else come first? (Recommended: yes, J1 next.)
3. **Whether to attempt §5.3 engine investigation now or defer.** If Q3 = (a), this matters before Drop A. If Q3 = (b) or (c), it's lower-priority.
4. **Whether the dangling `npcs.yaml` reference (§5.2) should be fixed in Drop A or in a tiny separate cleanup drop.** Recommend: in Drop A, since Drop A touches the NPC loading layer.
5. **Drop sizing approval.** The 10–14 session total is a rough estimate. Is that acceptable as a path forward, or should some gaps be cut? (Gap I is the easiest cut; Gap C2 could be merged into C1; Gap F could be merged with G.)

---

## 9. What this document changes in v34 of the architecture

When the architecture rollup happens next, two updates are needed:

- **Add a §20 (or appropriate section) "CW Content Gap Plan" reference** pointing at this document and tracking which drops have closed which gaps.
- **Update §19 Priority F** (or wherever the CW pivot drops are tracked) to reflect that FDtS step content is gated on Q4 faction-code reconciliation and benefits from J1 GG6 extraction. The current roadmap_v34 lists FDtS as next-up; after this audit, it isn't.

---

*End of CW Content Gap & Remediation Plan v1.*

*"We didn't notice the floor was missing because we were looking at the ceiling."*
