# SW_MUSH — Drop F.8 Dialogue Authoring Pass · Design v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, fourth half)
**Status:** Authoring pass shipped in this drop; addendum to F.8 design v1
**Drop number:** F.8 dialogue authoring (no engine work, pure content)
**Pre-reads:**
- `jedi_village_quest_design_v1.md` (the parent design — 13 sections)
- `data/worlds/clone_wars/quests/jedi_village.yaml` v1 (the mechanical
  stub this pass fills in)
- `jas_extraction_v1.md` §2 (Jedi pedagogy + voice register)

---

## 1. Why this exists

The F.8 mechanical stub shipped in v3 of this consolidated drop was
mechanically complete but dialogue-stubbed. 17 in-line `TODO(content):`
markers awaited authoring. This pass fills them.

Authoring was deferred from the original design pass because dialogue
is the writing surface, not the engineering surface — better done as a
focused content-only pass with the design spec in hand than mixed into
schema work.

---

## 2. What was authored

### 2.1 NPC speeches authored at step locations

| Step | NPC | Touchpoint | Length |
|---|---|---|---|
| 4 | Master Yarael Tinré | First Audience | 4 paragraphs (Order-rejection backstory, trial overview, dispatch to Forge) |
| 5 | Smith Daro | Trial of Skill intake | 1 paragraph + bench-side direction |
| 5 | Smith Daro | Trial of Skill success | 1 short paragraph |
| 6 | Elder Mira Delen | Trial of Courage framing | 3 paragraphs (Village gathers, Mira identifies herself, framing for the recital) |
| 7 | Elder Korvas | Trial of Flesh intake | 3 paragraphs (gear removal, the rules, the unlocked-but-don't-leave framing) |
| 7 | Elder Korvas | Trial of Flesh emergence | 2 paragraphs (the Force-comes-to-the-still teaching, hand on shoulder) |
| 8 | Master Yarael Tinré | Trial of Spirit framing | 3 paragraphs (Sanctum opening, the dishonest-vs-honest version) |
| 8 | Master Yarael Tinré | Spirit completion | 1 paragraph (silent nod, Sanctum stays open) |
| 9 | Elder Saro Veck | Trial of Insight framing | 2 paragraphs (the three fragments described, the doctrinal-error hint) |
| 9 | Elder Saro Veck | Insight success speech | 2 paragraphs (the explanation, pendant gift) |
| 10 | Master Yarael Tinré | Choice presentation | 2 variants — "two paths" (~5 paragraphs) and "Path C only" (~5 paragraphs) |
| 10 | Master Yarael Tinré | Three farewells | One per Path A / B / C |
| Fail | Master Yarael Tinré | Attacked-village expulsion | 2 paragraphs (silent procession, last words at the gate) |

### 2.2 Director prompt templates

Two Director-AI prompt templates were authored as part of completion
specs, replacing the placeholder `# TODO(content):` markers:

**Trial of Courage prompt template** (Step 6, Mira's recital). ~30
lines. Defines:
- Mira's voice constraints (direct, merciful, exact, not melodramatic)
- 4-6 sentence target length
- Required input fields (species, age, faction, +background)
- 5 fallback seeds for backstory-empty characters
- Output format constraint (plain text, no labels, end open)

**Trial of Spirit prompt template** (Step 8, dark-future-self). ~50
lines. Defines:
- The dark-future-self's persuasive register (not cackling-villain;
  argues from love or self-protection)
- Mandatory specific-event reference from candidate's history
- 5-7 turn structure with 3-option per-turn response
- Required input fields (name, species, age, faction history,
  recent kills, +background)
- Archetype template selector (engine selects at dialogue start)
- Per-turn output format (dark_self_line + 3 response_options)

### 2.3 Spirit Trial archetype templates (4 of recommended 8)

The design doc §10.3 recommended 6-8 archetype templates so the Director
seeds variants rather than generating from scratch. This pass ships
4 inline archetypes; engine session may add 4 more following the same
shape.

The 4 shipped:

| Template ID | Selector | What "falls" looks like |
|---|---|---|
| `republic_soldier_falls` | `primary_faction == 'republic'` AND ground-trooper / commander | Stayed in service past the war's end; stopped reading orders before carrying them out. |
| `smuggler_falls` | `primary_faction == 'independent'` AND cargo-run history | Stopped asking what was in the boxes. Sleeps on the ship; has no planet. |
| `bounty_hunter_falls` | `primary_faction == 'bounty_hunters_guild'` | Took contracts no one else would. Stopped feeling the difference between bounty and murder. |
| `force_falls` | `force_sign_count >= 5` AND `trials_passed >= 3` | The universal fallback — the Force-sensitive who took what was offered and kept taking. Used if no other archetype matches. |

Each archetype template contains:
- `select_when` predicate
- `premise` paragraph (the backstory the dark-future-self carries)
- `visual_cue` paragraph (what they look like in the Sanctum vision)
- `opening_hook` (one-line scene setter)
- `recurring_argument` (the dark-future-self's central claim, used as
  rhetorical anchor across turns)

The 4 not shipped (engine-session candidates): `cis_falls`,
`intelligence_falls`, `shipwright_falls`, `entertainer_falls`.

### 2.4 Holocron fragments — the doctrinal tell

The Trial of Insight (Step 9) presents 3 holocron-fragment recordings.
Authored:

**Fragment 1** — attributed to Master Hektorr Vorr (Old Republic, ~3000
BBY). The "lightsaber answers the discipline that wields it" framing.
Authentic Jedi.

**Fragment 2** — unattributed (the Sith). The doctrinal error:

> "The Force is the deepest current of all that lives. **It belongs
> to those who can wield it.** The strong are made strong by their
> grasp of it; the weak make peace with their weakness."

The tell is "the Force *belongs to* those who can wield it." A true
Jedi never says the Force belongs to anyone — the Force flows through
them; they serve it; they do not own it. Ownership language is the
Sith corruption.

**Fragment 3** — attributed to Master Phylis Alince (Kit Fisto's
master, Clone Wars era). The "patience is not slowness" framing.
Authentic Jedi.

Each fragment has an `authenticity:` field (`jedi` /
`sith_in_disguise`) and `doctrinal_notes:` explaining the canonical
basis. These are designer-side notes the engine session uses to
randomize which fragment is the Sith on each playthrough — the
content shifts but the structure (one Sith, two Jedi) is fixed.

### 2.5 NPC roster `dialogue_summary` blocks

7 NPC summaries were updated from `TODO(content):` placeholders to
descriptions of where their authored dialogue lives:

- Master Yarael Tinré → "Authored across multiple touchpoints in the
  steps below"
- Sister Vitha → kept original (gate test was already authored in v1)
- Elder Mira Delen → "Trial of Courage script Director-prompt-driven"
- Elder Korvas → "Trial of Flesh: intake + emergence speeches authored"
- Elder Saro Veck → "Trial of Insight: framing + 3 fragments + success"
- Smith Daro → "Trial of Skill: three speech blocks authored"
- Padawan Sela → "DEFERRED — peer dialogue tree intentionally left for
  optional future content drop"
- Mace Windu → "DEFERRED — Mace Windu's reception scene belongs to
  Coruscant Temple buildout, not to the Village quest YAML"

The two DEFERRED entries are the only remaining content gaps. Both
are out-of-scope for the Village quest itself per the design doc.

---

## 3. Voice register

The Village's NPCs were authored to a consistent register matching
the design doc §4 voice specs:

- **Master Yarael Tinré** (Cerean, 119): slow, exact, kind without
  being warm. Calls candidates "young one" regardless of age. Uses
  short blunt lines among longer reflective ones. Never explains
  himself fully.

- **Sister Vitha** (Twi'lek, 51): calm, unhurried. (Pre-authored in
  the v1 stub; preserved.)

- **Elder Mira Delen** (Pantoran, 64, former mercenary): direct, no
  euphemisms. Plain language. Mercifully exact.

- **Elder Korvas** (Anzati, 287, ascetic): sparing of words. Speaks in
  short declaratives. Uses the desert as the only metaphor.

- **Elder Saro Veck** (Human, 78, scholar): elderly scholar, gentle
  but sharp. Slightly more elaborated than Mira or Korvas.

- **Smith Daro** (Quarren, 56): blunt, irritable. Perfectionist with
  no patience for hurry. Talks like the work, not around it.

The Jedi-pedagogy register was anchored against the JAS extraction's
canonical samples (the Bodo Baas Holocron quotes, the praxeum/patience
framings). The Village uses the same register — a deliberate choice
since Yarael trained at the Order before leaving, and the doctrinal
inheritance shows.

---

## 4. What this drop does NOT author

Two items remain explicitly out of scope:

### 4.1 Padawan Sela's peer dialogue tree

The design doc §4.4 marks Sela's peer dialogue as "optional content
authoring." She exists as a 17-year-old Human apprentice four months
ahead of the player on the same path. The mechanic is "talk to her,
get flavor." No quest progression depends on her dialogue.

This pass leaves Sela's `dialogue_summary` set to `DEFERRED — peer
dialogue tree intentionally left for an optional future content drop.`
Engine session can wire her to the standard ambient_events pool with a
village-specific zone key as an interim until peer-dialogue content
ships.

### 4.2 Master Mace Windu's Path A reception scene

The Path A consequence in Act 3 hands the candidate off to Mace Windu
at the Coruscant Jedi Temple (drop_room: `jedi_temple_gates`,
`auto_start_chain: jedi_path`). Mace's reception scene is **live-world
content**, not Village quest content — it belongs to the Tutorial Jedi
Path chain (`chains.yaml`) once that chain is unlocked.

Authoring it here would create a content boundary problem: the same
scene would be referenced from two YAML files, and any update would
need to be made twice. By deferring it to the Tutorial chain, we keep
the Village quest cleanly bounded at "candidate is escorted to the
Temple gates" and let the Tutorial chain own the reception itself.

This is a content boundary choice, not an authoring backlog.

---

## 5. Verification

The dialogue authoring pass is a **content-only** change to a single
file. The schema is unchanged. The 209-check schema/cross-ref
verifier (`verify_jedi_village.py`) still passes green:

```bash
python3 verify_jedi_village.py
# PASS: 209    FAIL: 0
```

No new mechanical surface was introduced; no new completion types;
no new field schemas. The authored content slots into existing fields
(`npc_intro`, `npc_complete`, `director_prompt_template`,
`fragment_recordings`, `narrative`).

File grew from 700 lines to 1218 lines. The increase is roughly 70%
dialogue, 30% Director prompt templates and archetype templates.

---

## 6. What this enables

### 6.1 The Village quest is now content-complete

A future engine session can implement F.8 against this YAML directly
— no further authoring is required for any mechanically-gated content.
Engine work consists of:
- Loader extension for the quest schema (similar to Drop F.6 chain loader)
- 5 new completion type handlers (`dialogue_completion`,
  `timed_room_dwell`, `multi_turn_dialogue_completion`,
  `targeted_choice`, `path_choice`)
- Director-AI prompt scaffolding for the 2 director_authored steps
- Building the 9 Village rooms

### 6.2 The Director-AI Trial of Spirit has a working spec

Engine session can prototype Trial of Spirit against the 4 archetype
templates immediately. The Director receives:
1. Character context (name, species, age, faction history, recent kills, +background)
2. Selected archetype template (one of 4 inline; selector predicates
   defined in `archetype_templates.<id>.select_when`)
3. The Director prompt template (~50 lines, embedded in the completion
   spec)

Output is 5-7 turn dialogue with per-turn 3-option response menus.
Pass condition: 4+ rejection choices accumulated; fail condition:
3+ temptation choices triggers `lock_path_c`.

### 6.3 The doctrinal tell test is content-stable

The Trial of Insight's 3 holocron fragments are fully authored with
the doctrinal tell embedded in fragment_2's wording. The
`authenticity:` and `doctrinal_notes:` fields document the canonical
basis for each fragment, making future content audits possible
without re-deriving the doctrinal point.

The engine session can randomize *which* fragment is the Sith on each
playthrough by reshuffling the `fragment_recordings` dict at runtime,
keeping the structural rule (one Sith, two Jedi) constant.

---

## 7. Sign-off

The Village quest content surface is now closed. 17 of 19 dialogue
authoring tasks complete; 2 explicit deferrals (Sela peer dialogue,
Mace reception) are out of scope per content boundary decisions.

The 209-check verifier still passes. The Village quest is ready for
its engine session.

The dialogue authored here matches:
- ✓ The 6 NPC voice specs from `jedi_village_quest_design_v1.md` §4
- ✓ The Jedi pedagogy register from `jas_extraction_v1.md`
- ✓ The trial mechanics from `jedi_village_quest_design_v1.md` §5
- ✓ The Path A/B/C reward + flag specs from §7
- ✓ The permanent-fail attacked-village state from §7.4

*— Opus, parallel CW track, April 26 2026 (continuation pt 4)*
