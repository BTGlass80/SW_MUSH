# SW_MUSH — v7 Small Additions · Design v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, seventh half)
**Status:** Content shipped in this drop
**Drop number:** Three small content additions, no engine work
**Pre-reads:**
- `jedi_village_quest_design_v1.md` §3.3 (Mos Eisley old-Jedi rumor NPC)
- `coruscant_underworld_landmarks_design_v1.md` §4.3 (Uscru jobs hub)
- `jedi_village_dialogue_authoring_design_v1.md` §10.3 (8-archetype recommendation)

---

## 1. Why this exists

After v6 the parallel-safe outstanding items list was:

> 1. FDtS step content authoring — Bigger; deferred to a fresh chat.
> 2. Uscru Fringe broker NPC roster
> 3. Mos Eisley Twi'lek old-Jedi rumor NPC
> 4. Padawan Sela peer dialogue
> 5. 4 additional Spirit archetype templates

The user requested knocking out as much small stuff as remaining context
allowed, saving FDtS for a fresh thread. Items 2-5 are all small and
parallel-safe. This drop addresses three of them; the fourth (Sela) was
already authored in v4-v6 by an earlier session pass that I had lost
track of in the staging-vs-canonical drift.

### 1.1 What I actually shipped

- **Item 1: Vela Niree (Mos Eisley old-Jedi rumor NPC)** — authored
  full NPC entry in a new file `data/worlds/clone_wars/npcs_cw_additions.yaml`.
- **Item 2: Uscru Fringe broker roster** — authored 6 brokers in
  `data/worlds/clone_wars/wilderness/uscru_fringe_brokers.yaml`.
- **Item 3: 3 additional Spirit archetypes** — authored in
  `data/worlds/clone_wars/quests/jedi_village_archetype_additions.yaml`,
  bringing the total to 8 (canonical 5 + additions 3).
- **Item 4 (Sela peer dialogue)** — already shipped in v4 canonical;
  no further work.

### 1.2 The staging-vs-canonical drift correction

While auditing what was shipped in v6 vs what I had in my session
staging, I discovered that the canonical `final_drop` Village quest
YAML had been authored *more thoroughly* than my staging file
suggested. Specifically:

- Padawan Sela's 4-state peer dialogue: shipped in v4-v6 canonical.
  My staging marked it DEFERRED.
- Master Mace Windu's Path A reception: shipped in v4-v6 canonical.
  My staging marked it as a content-boundary deferral.
- 5 Spirit archetypes (not 4): shipped in v4-v6 canonical.
- 6 Trial of Courage archetypes: shipped in v4-v6 canonical.

The canonical file is correct; my staging was stale. v7 follows
canonical reality. The validator's `CANONICAL_ARCHETYPE_IDS` constant
encodes the actual canonical archetype set so future additions can't
drift from it.

---

## 2. What ships

### 2.1 `data/worlds/clone_wars/npcs_cw_additions.yaml` (NEW)

A new NPC roster file for CW-era Mos Eisley additions to the GG7 base
roster. Schema mirrors `data/npcs_gg7.yaml` exactly, plus two new
optional sub-fields under `ai_config`:

- **`rumor_producer`** — declares an NPC has the room-entered rumor
  trigger mechanic. Fields: `trigger`, `chance_per_visit`,
  `cooldown_minutes`, `rumor_lines` (list).
- **`directed_responses`** — declares topic-specific dialogue
  branches. Used by `talk <npc> about <topic>` extension.

The single NPC authored is **Vela Niree** — a Twi'lek dancer at
Chalmun's Cantina who carries the Mos Eisley old-Jedi rumor (per
Village design §3.3). On any cantina visit, 3% chance per visit she
mutters one of 5 rumor lines about "the old hermit in the deep
dunes." 24h cooldown per character. She also has 3 directed-response
topics for players who explicitly ask about the hermit / Anchor
Stones / Jedi.

The rumor is **foreshadow only** — Vela does not set any flags, does
not increment force_sign_count, and does not unlock anything. Her
job is to produce the satisfying "oh, that" click when the player
later receives the Village invitation.

### 2.2 `data/worlds/clone_wars/wilderness/uscru_fringe_brokers.yaml` (NEW)

Six broker NPCs filling out the v6 Uscru Fringe landmark's
"NPC cluster, jobs hub" role. Each broker covers 1-3 of the 5 job
categories the Fringe handles, with redundancy so any 4-7 concurrent
subset still covers most categories:

| Broker | Species | Tier | Categories |
|---|---|---|---|
| Yenn Tarra | Sullustan | 1 (cautious) | courier, information |
| Brokk Vesh | Devaronian | 2 (balanced) | find-person, information |
| Marra Sundvik | Zabrak | 3 (balanced, sober) | lose-pursuer, find-person |
| Kel Doran | Human | 3 (balanced, smuggling) | smuggling, courier |
| Vesh Nokal | Bothan | 4 (high-risk) | information, find-person |
| Zhett Marn | Twi'lek | 5 (dangerous) | find-person, lose-pursuer, information |

Roster diversity:
- 6 different species
- Reliability tier distribution spans 1-5 (every player session has
  a likely tier-1-2 and tier-4-5 encounter)
- Each broker has a distinct conversational tic
- Each broker has 4+ fallback lines and faction/knowledge data
- Total broker-category slots: 13. Engine session reads
  `job_categories_handled` to populate procedural job records per
  broker.

The 5 categories (`off_record_courier`, `off_record_information`,
`find_a_specific_person`, `lose_a_specific_pursuer`,
`low_tier_smuggling`) are a v7 *spec extension* to the v6 landmark
file. The v6 canonical landmark only marks Uscru as a `jobs_hub`
with `npc_cluster: true` and `job_board: true` — it does not
enumerate categories. This file establishes the categories.

### 2.3 `data/worlds/clone_wars/quests/jedi_village_archetype_additions.yaml` (NEW)

Three additional Spirit Trial archetype templates, taking the total
from 5 (canonical inline) to 8 (the upper bound recommended in
`jedi_village_quest_design_v1.md` §10.3).

| ID | Faction match | Sub-match |
|---|---|---|
| `intelligence_compromised` | republic | intel_role |
| `shipwright_complicit` | shipwrights_guild | any |
| `entertainer_used` | entertainers_guild | any |

Each archetype:
- ~5-sentence template in first-person plural ("we did", "I am what we
  became when X")
- `faction_match` predicate
- `sub_match` predicate (soft — engine session decides whether to
  enforce strictly or use as flavor preference)
- `selection_priority` (high / medium / low) for tie-breaking when
  multiple archetypes match the candidate

The file uses `merge_mode: append` — the engine session merges these
additions into the inline canonical list when loading the Trial of
Spirit Director prompt template. Until the engine session lands,
this file is inert.

The 3 additions match the canonical voice (short, persuasive, never
theatrical, anchored to a specific faction). Each archetype's pivot
point follows the canonical pattern: "I am what we became when [the
compromise solidified]."

### 2.4 `verify_v7_small_additions.py` (NEW)

106 schema + cross-reference checks across the three new files:

- **Test 1 (Vela rumor producer):** schema, room placement at
  Chalmun's, knowledge entries, rumor_producer block shape (trigger,
  probability, cooldown, 4+ rumor lines), directed_responses for
  the three foreshadow topics.
- **Test 2 (Uscru brokers):** exactly 6 brokers, schema completeness
  per broker, all 5 job categories covered by the roster, reliability
  tiers span 1-5, no name or species duplicates.
- **Test 3 (archetype additions):** exactly 3 entries, no id collisions
  with canonical (5+3=8 total), template length minimum, selection_priority
  in {high, medium, low}.
- **Test 4 (Uscru cross-ref):** the v6 landmark file's Uscru entry
  has `properties.gameplay_role: jobs_hub` and `properties.npc_cluster:
  true` and `properties.job_board: true`; the v7 brokers' room slug
  matches the v6 landmark id; the brokers cover the v7 spec's 5
  categories exactly.

---

## 3. What this enables

### 3.1 Village quest discovery becomes more substantive

Vela's rumor producer is the **fourth and final** Village quest §3.3
foreshadow source authored:

| Foreshadow source | Authored in |
|---|---|
| `forgotten_jedi_shrine` (Coruscant Underworld) | v5 (force_resonant_landmarks) |
| `dune_sea_anchor_stones` ambient | v5 (force_resonant_landmarks) |
| `dune_sea_ruined_obelisk` ambient | v5 (force_resonant_landmarks) |
| `bantha_graveyard` ambient | v5 (force_resonant_landmarks) |
| **Mos Eisley Twi'lek rumor (Vela)** | **v7 (this drop)** |

A player visiting Chalmun's Cantina semi-regularly will hear Vela's
rumor at least once before they accumulate enough Force-signs to
trigger the Village invitation. The rumor will then click with the
landmarks they may have visited in the wilderness regions. The
discovery feels earned rather than arbitrary.

Per Village design §3.3, two additional foreshadow sources remain
unauthored — both content-boundary deferrals to other drops:
- Tatooine moisture farmer flavor NPC (Tatooine NPC pass)
- Coruscant Jedi Archives research mission (Republic-faction
  content drop)

### 3.2 The Uscru Fringe is now a populated room

Before v7, the Uscru landmark existed as a description with no NPCs.
Engine session would have built the room and players would arrive
to find an empty plaza with a job board. v7 fills it with 6 brokers
across 5 reliability tiers. Engine session reads
`uscru_fringe_brokers.yaml` when building the room and spawns 4-7
brokers from the roster.

The 5 job categories are now explicitly enumerated. Engine session
generates procedural job records from the categories — the first
concrete content the off-record jobs system will consume.

### 3.3 Spirit Trial archetype coverage is at design's upper bound

`jedi_village_quest_design_v1.md` §10.3 recommended 6-8 archetype
templates. Canonical shipped 5. v7 adds 3, bringing the total to 8.
Coverage now spans:

- `republic_corrupted` (canonical) — Republic soldiers
- `cis_disillusioned` (canonical) — CIS commandos
- `smuggler_ruthless` (canonical) — independent smugglers
- `bounty_hunter_unbound` (canonical) — BHG hunters
- `generic_fall` (canonical) — universal fallback
- `intelligence_compromised` (v7) — Republic Intelligence officers
- `shipwright_complicit` (v7) — Shipwrights Guild
- `entertainer_used` (v7) — Entertainers Guild

This covers all 8 player tutorial chains (chains.yaml) with at least
one archetype each. The Force-sensitive chargen flag intersects with
each chain's primary archetype, so dark-future-self generation can
be character-grounded for any candidate.

---

## 4. What this drop does NOT do

- **Does not author FDtS step content.** Saved for a fresh chat.
- **Does not implement engine integration.** All three files are
  inert until their respective engine sessions.
- **Does not author the Tatooine moisture farmer flavor NPCs.**
  Belongs to a Tatooine NPC content pass.
- **Does not author the Coruscant Jedi Archives research mission.**
  Belongs to a Republic-faction content drop.
- **Does not modify chargen, era.yaml, or anything engine-side.**

---

## 5. Sign-off

Three small parallel-safe content drops shipped, 106 verifications
green. Combined with the canonical v6 contents, the parallel-safe
small-stuff backlog is now down to:

| Item | Status |
|---|---|
| Vela Niree (Mos Eisley old-Jedi rumor NPC) | ✅ v7 |
| Uscru Fringe broker roster | ✅ v7 |
| Padawan Sela peer dialogue | ✅ already in canonical |
| Mace Windu Path A reception | ✅ already in canonical |
| 3 additional Spirit archetypes (8 total) | ✅ v7 |
| Tatooine moisture farmer flavor NPCs | ⏳ Tatooine NPC pass |
| Coruscant Jedi Archives research mission | ⏳ Republic-faction drop |
| FDtS step content (30 steps) | ⏳ fresh-chat session |
| Optional CW lore enrichment | ⏳ pure additive |
| Reaper miniboss combat content | ⏳ combat-content design first |

*— Opus, parallel CW track, April 26 2026 (continuation pt 7)*
