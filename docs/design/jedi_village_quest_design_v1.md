# SW_MUSH — Drop F.8 Design: The Jedi Village Quest Chain · v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, third half)
**Status:** Design doc — content authoring follows in a future drop
**Drop number:** F.8 (design + content stub; engine work is a separate session)
**Pre-reads:**
- `clone_wars_era_design_v3.md` §4 (Jedi Village Unlock — architectural)
- `clone_wars_era_design_v3.md` §0 (Force-sign fairness directive)
- `jas_extraction_v1.md` §2 (Jedi pedagogy + the 5 canonical Trials)
- `cw_tutorial_chains_design_v1.md` (the locked Jedi Path stub this unlocks)
- `wilderness_system_design_v1.md` (Dune Sea wilderness region this lives in)

---

## 1. Why this design exists

`clone_wars_era_design_v3.md` §4 sketches the Village quest at the
architectural level: a 3-act SWG-inspired chain that gates Jedi Order
membership behind a hand-crafted hidden questline. What §4 doesn't have:

- Per-room layout for the Village
- Per-step trial mechanics
- NPC roster with dialogue tree branches
- Concrete completion criteria (typed against engine event hooks)
- Integration shape with the `chains.yaml` schema shipped in Drop F.6
- State-tracking JSON layout
- Force-sign accumulation rules (the threshold is hand-waved as "~5")

This drop fills those gaps. The roadmap currently lists Drop F.8 as a
single line with no underlying design; the previous design's authoring
ran out at "the dialogue tree, the Master's identity, and the trials
need fleshing out before this can be built."

That's what this is.

The drop ships **two artifacts**:

1. **This design doc** (`jedi_village_quest_design_v1.md`) — comprehensive
   spec with NPC roster, room layout, trial mechanics, dialogue summaries.
2. **A content stub** (`data/worlds/clone_wars/quests/jedi_village.yaml`) —
   the structured authoring file matching the `chains.yaml` schema from
   Drop F.6, with NPC/room placeholders and the three-path completion
   spec. The Master's full dialogue trees are placeholders pending a
   later content authoring pass; everything mechanical is concrete.

The design pass + content stub together unblock Drop F.8 engine work
*and* clarify the Tutorial Jedi Path stub (`cw_tutorial_chains_design_v1.md`
§5) by giving its `jedi_path_unlocked` flag a producer.

---

## 2. SWG inspiration and our specific differences

### 2.1 What SWG did

SWG's "Village" was a hidden questline on Dathomir (technically Mustafar
in revisions). Pre-Combat Upgrade, it required ~3-6 weeks of grinding
specific skills to flag yourself as Force-Sensitive, then traveling to
the Village, then completing 4 phases of branching content (Heal Self,
Sense, Crafting, Defender) over weeks. Each phase had a 1-week cooldown.

The community's lasting reaction: **the theme was perfect, the grind
was hostile**. People remember the dawn approach to the Village across
the swamp; they don't remember enjoying the skill-grind.

### 2.2 What we keep, what we cut

**Keep:**
- The hidden physical location with discovery mechanic
- The "you don't pick this at chargen, you find it" thematic frame
- The slow-burn "signs" accumulating before discovery
- The Master/elder NPC who recognizes Force-sensitivity in you
- The branching path-choice at the end (Path A/B/C from §4.2 of
  `clone_wars_era_design_v3.md`)

**Cut:**
- The skill-grind to flag Force-sensitivity (we use chargen 50% +
  wilderness exploration triggers instead of forced grinding)
- The phase-cooldowns (replaced with narrative pacing — see §6)
- The Dathomir/Mustafar setting (we use Tatooine Dune Sea per
  `clone_wars_era_design_v3.md` §4.4)
- The MMO-style "you're now a Force-Sensitive class" UI prompt
  (replaced with in-fiction dialogue from the Master)

### 2.3 Why Tatooine Dune Sea

Per `clone_wars_era_design_v3.md` §4.4: Tatooine fits the
"hermit retreat" archetype (Obi-Wan did it ~19 years later in canonical
timeline). The Dune Sea wilderness region is built into the launch
architecture by `wilderness_system_design_v1.md`; the Village is a
hand-authored landmark cluster within the coordinate grid.

The Village is a **secondary wilderness landmark**, sized at roughly
8-12 rooms — small enough to author in one sitting, big enough to
feel like a place, not a corridor.

---

## 3. Discovery mechanic (Act 1)

### 3.1 Two parallel tracks for "Force-sign accumulation"

`clone_wars_era_design_v3.md` §0 directive: "Force-sign fairness — No
one fully gated. Non-seeded characters pursue Village via longer/harder
path; roads exist for all." That requires two tracks:

**Track A — chargen-seeded.** During chargen, every CW character has
a 50% probability of being flagged `force_sensitive: true` (set as a
character attribute by the chargen wizard). This is the "fast" track.

**Track B — accumulation track.** Characters who failed the chargen
roll can still earn Force-sensitivity through gameplay over weeks.
The mechanic:

```
Each character has an attribute force_sign_count: int (default 0).

Every game session, on certain trigger conditions, the engine has
a small probability (~3% per trigger) of incrementing force_sign_count
and emitting a brief in-fiction "sign" message:

  - You wake from a dream you can't quite remember, but the feeling
    that something is coming stays with you.
  - For a moment, in the noise of the cantina, you swear you can hear
    every voice clearly — yours included, though you said nothing.
  - The blaster bolt should have hit. You don't know why it didn't.

Trigger conditions (any of):
  - Combat resolution — you take damage but survive a round you
    "shouldn't have" (low-probability dodge success, narratively).
  - Entering a wilderness room flagged force_resonant: true (e.g.
    forgotten_jedi_shrine in Coruscant Underworld, Bantha Graveyard
    on Tatooine, several Dune Sea coordinate tiles).
  - Sleeping/resting in a player home or cantina.

Threshold: when force_sign_count reaches 5, an attribute flag
force_sensitive: true is set automatically and the Act 2 invitation
is queued for the player's next login.
```

**Calibration target:** Track B should average to ~6-10 weeks of
moderate play before triggering. Players who play heavily can hit it
in 3-4 weeks; players who play casually may take 12+. Both are fine —
it's not a race. Calibration gets dialed in via Director AI telemetry
in the first launch month.

The 50% chargen seed means about half of characters get there in zero
sessions; the other half via Track B. **No character is ever fully
gated out** (per the §0 directive).

### 3.2 The invitation

Once a character has `force_sensitive: true` (regardless of which
track), they receive a one-time in-fiction message on next login (or
session-end-and-relogin to avoid mid-session disruption):

```
═══════════════════════════════════════════════════════════════
A message has reached you through channels you don't recognize.

The sender's identity is encrypted; the routing is impossibly old.
Some part of you understands it anyway.

  "I have seen you in my meditations. You are not what you think
   you are. Come to the Jundland Wastes — the deep dunes, where
   sandcrawlers do not go. Walk west from the Anchor Stones at
   first light. You will find what is left of us, if you mean to.

   Come alone. Tell no one. The Order does not know I exist."

The signature, if it can be called that, is a single character:
a circle of three points joined.

[Type +quest jedi_village to accept this lead.]
═══════════════════════════════════════════════════════════════
```

The Anchor Stones are a Dune Sea wilderness landmark — a tile that's
already on the map regardless of Village content (a real wilderness
landmark, not Village-specific). Walking west from there at first
light is the navigation puzzle.

### 3.3 Optional pre-discovery: lore foreshadowing

Independent of the invitation mechanic, characters can learn that the
Village exists through **passive lore exposure**: the
`forgotten_jedi_shrine` in Coruscant Underworld already includes lore
hints. Other foreshadow sites:

- **Mos Eisley old-Jedi rumor** — A drunken Twi'lek in Chalmun's
  Cantina has a 3% chance per visit of muttering about "the old hermit
  in the deep dunes who knows things he shouldn't."
- **Tatooine moisture farmer NPC** — Some moisture farmers (random
  flavor) reference "those people who don't trade with us, out past the
  Anchor Stones."
- **Holonet history feed** — A research mission in the Coruscant
  Jedi Archives (only available to Republic-faction characters with
  Archives access) mentions a "lost lineage" that left the Order
  during the New Sith Wars era and was last reported in the Jundland
  Wastes ~1100 years ago.

These don't unlock the Village. They make the Village feel **discovered,
not assigned** when the invitation arrives — players who bothered to
talk to the Twi'lek will have the satisfying click of "oh, that".

---

## 4. The Village (Act 2)

### 4.1 Physical layout — 9 rooms

```
                 [Outer Watch]
                       │
                       │ (path, sand, the wind picks up)
                       │
                 [Village Gate]
                /      │       \
               /       │        \
       [Council     [Common      [Apprentice
        Hut]        Square]      Tents]
          │            │             │
          │            │             │
       [Master's    [The Forge]   [Meditation
        Chamber]                   Caves]
                       │
                       │
                  [The Sealed
                   Sanctum]
                  (locked until
                   Trial of Spirit)
```

Room IDs (all `village_*` prefix to keep namespace clean):

- `village_outer_watch` — entry tile from the Dune Sea wilderness
- `village_gate` — an NPC sentry stops you here for the dialogue test
- `village_common_square` — central gathering, primary NPC presence
- `village_council_hut` — small council of 3-4 elders (NPC group)
- `village_masters_chamber` — Master Yarael Tinré's quarters
- `village_apprentice_tents` — where the resident apprentices live
- `village_forge` — for Trial of Skill / lightsaber crafting hint
- `village_meditation_caves` — for Trial of Spirit
- `village_sealed_sanctum` — locked deep room, opens after Spirit

All rooms get the `wilderness_landmark: true` property. Player housing
and ambient events are excluded. NPCs in this zone are hand-authored,
not Director-managed — the Village exists **outside** the Director's
faction-influence model (it has no faction code; it is its own thing).

### 4.2 The dialogue test at the Gate

Per `clone_wars_era_design_v3.md` §4.2: "Passing an NPC conversation
test (not a skill check — a dialogue tree)."

The Gate sentry is **Sister Vitha** — a middle-aged Twi'lek hermit who
has been turning visitors away for 30 years. She is calm, unhurried,
and can read intent better than most Force-blind NPCs.

```
Vitha: "You stand at the edge of where you should not be."
       (Three response options surface; choose one.)

  [1] "I received a message. I came alone, as instructed."
  [2] "I'm looking for the Master. Take me to him."
  [3] "I don't know why I'm here. Something told me to come."

Vitha responds based on choice:

  → [1]: "Many receive messages they cannot trace. Few choose to
     follow. You may pass."   [GATE OPENS]

  → [2]: "Many come demanding what they have not earned. They do not
     pass."   [GATE CLOSES; you must wait 24 RL hours and try again.]

  → [3]: "Honesty. Rare. The Master will see you."   [GATE OPENS]
```

This is a single-turn test, not a multi-step dialogue tree. The
"correct" answers are [1] and [3]; [2] is a soft-fail (24h cooldown,
not permanent rejection). Players who fail can retry — the Village's
patience is the point of the test.

The dialogue test is **not** stored as completion-criteria in YAML the
same way `chains.yaml` step completions are stored. It's a custom
NPC dialogue branch handler. The chain step records `gate_passed: true`
on success and the step advances.

### 4.3 The Master

**Master Yarael Tinré** — Cerean (the four-lobed-brain species, like
Ki-Adi-Mundi). 119 years old. Lineage: trained as Padawan in the late
Old Republic; became disenchanted with the Order's drift toward Senate
politics; left ~80 years ago and has been here ever since. Knows the
Order is at war (heard via traders); has no intention of returning to
fight. Trains a small rotating cadre of Force-sensitives the Order
never knew about.

Voice: slow, exact, kind without being warm. Calls everyone "young one"
regardless of age. Never explains himself fully. The first time you
meet him he seems to already know more about you than you've told.

He is the canonical Master for the Village quest. (The Council Hut
elders are supporting cast for the Trials; see §5.)

**Why a non-canon Master, not Yoda or Mace Windu:** The Village is
explicitly *outside* the Order. Using a canonical Council Master would
break the framing — those characters are on the front lines or in the
Temple. Yarael Tinré is the Order's lost cousin: someone who could have
been on the Council in another timeline, but isn't.

### 4.4 The resident NPCs

Beyond Vitha and Master Yarael, the Village has:

- **Elder Saro Veck** (Council, Trial of Insight examiner) — Elderly
  Human, scholar, quiet
- **Elder Mira Delen** (Council, Trial of Courage examiner) — Pantoran,
  former mercenary, now serene
- **Elder Korvas** (Council, Trial of Flesh examiner) — Anzati, ascetic,
  known for endurance fasts that have killed weaker apprentices in
  spirit if not in body
- **Smith Daro** (the Forge) — Quarren, lightsaber-construction expert,
  blunt and irritable
- **Padawan Sela** (apprentice tents) — Human teen, 4 months ahead of
  the player on the same path; exists to be talked to, not to compete

All NPCs are non-combat-flagged. The Village is a **safe zone** for
its inhabitants. The player can attack them (game-mechanically) but
this immediately triggers the **Dark-side fail state** (§7.4) and
permanently fails the chain.

---

## 5. The Trials (Act 2 mechanics)

### 5.1 The five canonical trials

Per `jas_extraction_v1.md` §2, the Jedi Order traditionally tests
Padawans against five Trials before Knighthood: Skill, Courage, Flesh,
Spirit, and Insight. The Village uses the same five as its own
sequence — a deliberate doctrinal choice by Master Yarael, who trained
under the Order before leaving.

The Village trials are **not equivalent to becoming a Knight**. They
are a form of vetting that allows the Master to teach you. Passing
all five and choosing Path A does not make you a Knight — it makes
you eligible to be presented to the Jedi Order as a candidate Padawan.
Path B (independent) and Path C (dark whisper) bypass the Order
entirely.

### 5.2 Trial-by-trial mechanics

Each trial is one step in the chain, with a typed completion criterion
(slotting into the same schema as `chains.yaml` from Drop F.6). The
trials must be done in sequence (Skill → Courage → Flesh → Spirit →
Insight); each unlocks the next.

#### Trial 1: Skill — at the Forge

**Examiner:** Smith Daro (gruff Quarren, Forge custodian).

**The test:** A demonstration of fundamental coordination and patience,
not lightsaber duel. Daro hands you a piece of unworked Adegan crystal
and tells you to score it true along its single natural fracture line —
without breaking it.

**Mechanic:** A 3-step `skill_check_passed` sequence. Each step is a
`craft_lightsaber` skill check at increasing difficulty (8/12/15).
Failing any step does not break the crystal; Daro takes it back and
lets you try again after a 1-hour cooldown. There is no upper limit
on retries — patience is the point.

**Completion type:**
```yaml
completion:
  type: skill_check_passed
  skill: craft_lightsaber
  difficulty: 15
  steps_required: 3
  retry_cooldown_minutes: 60
```

**Reward:** The successfully scored crystal. (Stored as item
`village_trial_crystal` in inventory; consumed only if Path A is taken
later — see §7.1.)

**Why this and not lightsaber duel:** The Village does not have
lightsabers to issue or train with. Combat skill is not what they test
because combat skill is not what they cultivate. Patience and precision
under instruction are.

#### Trial 2: Courage — in the Common Square

**Examiner:** Elder Mira Delen (former mercenary).

**The test:** Mira has identified, through her own sources, the worst
moment of your life that you've never told anyone about. She tells it
back to you, in the Common Square, with the entire Village present.
You must remain in the Square and hear it through.

**Mechanic:** A scripted scene driven by character backstory data. If
the player has populated `+background` (the narrative system), the
Director AI uses one of those entries. If `+background` is empty, the
Director generates a plausible "buried memory" using the character's
species, age, and faction history.

The mechanic is `dialogue_completion`: the player must respond to
Mira's recital with one of three options:

- **[1] "I won't deny it."** — Pass.
- **[2] "How did you know?"** — Pass with elder approval (small bonus).
- **[3] (`leave`)** — Fail; cooldown 24 RL hours, then retry.

The "fail" path isn't punitive — it's narratively coherent. Some
people aren't ready to face what Mira found; the Village waits.

**Completion type:**
```yaml
completion:
  type: dialogue_completion
  dialogue_id: trial_courage_mira
  pass_choices: [1, 2]
  fail_choice: 3
  fail_cooldown_minutes: 1440  # 24 hours
```

**Reward:** None tangible. Mira nods and walks away. The Village's
attitude toward you shifts a notch (`village_standing` attribute
increments; see §6.4).

#### Trial 3: Flesh — in the Meditation Caves

**Examiner:** Elder Korvas (Anzati, ascetic).

**The test:** A 6-hour real-time fast in the meditation caves with no
food, no water, and no exit. The character is locked into the room
for 6 hours of session time (not 6 hours real-time; the player can
log out and return).

**Mechanic:** The chain step records `flesh_trial_started_at: <ts>`.
The room exit is closed for the chain-step's duration. The player can
do anything in the room except `leave` — meditate (`+meditate`), look
around, examine the cave walls (which have ancient inscriptions —
trickle Force-power lore), say or emote (no one will respond). The
`+inv` command shows their gear is gone — taken at intake.

After 6 hours, Korvas appears at the cave entrance and the exit opens.

**Completion type:**
```yaml
completion:
  type: timed_room_dwell
  room: village_meditation_caves
  duration_hours: 6
  allow_logout: true
  on_session_logout: pause_timer  # idle clock pauses on logout
```

**Trade-off note:** The 6-hour duration is intentionally a *real session
time* commitment (with logout-pausing). 6 hours of in-game session time
is approximately 2-3 typical play sessions. A common-sense alternative
would be a 24-hour wall-clock timer (nice for casuals, bad for
power-players); we chose session time so the trial has narrative
weight. The mechanic is an open question for engine session — see §10.2.

**Reward:** Korvas teaches the player a single new Force power:
`enhance_attribute` (Strength variant), per JAS extraction. Stored as
`learned_force_powers` array entry on character.

#### Trial 4: Spirit — in the Sealed Sanctum

**Examiner:** Master Yarael Tinré himself.

**The test:** The Sealed Sanctum is the deepest room in the Village —
a black-walled cave inside the Meditation Caves that opens for the
first time when the Master leads you in. Yarael invites you to sit.
He says nothing. Then the room shows you who you would become if you
fell.

**Mechanic:** A Director-AI-generated dark-future vignette using the
character's history, faction, and choices. Played out as a 5-7 turn
solo dialogue. The character speaks; the dark-future-self (Director
AI as antagonist) speaks back. The Director uses the character's
backstory + recent kills + faction rep to populate the dark-future-self.

The player must reject the dark-future-self in 5-7 turns. The mechanic
is `multi_turn_dialogue_completion` — each turn, the player picks
one of several response options. Some options bring them closer to
"I am that person already" (fail); others push toward "I am not that
person and I will not become him" (pass).

**Pass condition:** Accumulate 4+ "rejection" choices over 5-7 turns.
Each turn offers 3 choices: ~rejection / ~temptation / ~ambivalent.
The temptation choices increment a `dark_pull` counter; if it hits
3, the player is irreversibly on Path C (see §7.3).

**Completion type:**
```yaml
completion:
  type: multi_turn_dialogue_completion
  dialogue_id: trial_spirit_sealed_sanctum
  director_authored: true   # Director generates the dark-future-self
  required_rejections: 4
  max_turns: 7
  failure_threshold:
    counter: dark_pull
    value: 3
    on_fail: lock_path_c    # see §7.3
```

**Reward:** Master Yarael nods. He does not speak. The Sealed Sanctum
unseals permanently (you can re-enter for ambient meditation
post-quest).

#### Trial 5: Insight — in the Council Hut

**Examiner:** Elder Saro Veck (the scholar).

**The test:** A puzzle. Saro presents three holocron fragments — small
recordings of three different Jedi Masters from the past, each saying
something contradictory about the Force. The character must identify
which one is the *Sith* speaking in disguise.

**Mechanic:** The three holocron fragments are pre-authored short
recordings (~3 lines each). One contains a doctrinal tell — a phrase
that no true Jedi would say about the Force, regardless of era (the
specific tell: "the Force *belongs* to those who can wield it"; true
Jedi say the Force *flows through* them, never *belongs* to anyone).

The player examines each fragment (`examine fragment_1`, etc.) and
then declares the Sith with `accuse <fragment_id>`.

**Completion type:**
```yaml
completion:
  type: targeted_choice
  choice_command: accuse
  options: [fragment_1, fragment_2, fragment_3]
  correct: fragment_2  # the "belongs" line; randomized in implementation
  on_wrong: hint_and_retry  # Saro says "Listen again" and resets
```

**Reward:** Saro hands the player a small Holocron-shape pendant —
`village_pendant`, a worn item with the in-game effect of a +1 to
Sense Force checks. Symbolizes Insight earned.

### 5.3 Trial cooldown / pacing summary

| Trial | Duration | Retry cooldown on fail |
|---|---|---|
| Skill | ~30 min active | 1 hour |
| Courage | ~10 min active | 24 hours (real time) |
| Flesh | 6 hours session time | n/a (cannot fail) |
| Spirit | ~30 min active | none, but Path C lock-in is permanent |
| Insight | ~15 min active | hint + immediate retry |

Total trial duration: ~7-10 hours of session time across the trials,
spread over 1-3 weeks of play. This matches the §4 estimate of "a
multi-session quest chain (~5-10 sessions)."

---

## 6. State tracking

The Village quest state lives in `attributes` JSON, alongside the
existing `tutorial_chain` key from Drop F.6:

```json
{
    "force_sensitive": true,
    "force_sign_count": 5,
    "force_sign_history": [
        {"trigger": "shrine_entry", "timestamp": 1714000000},
        {"trigger": "combat_dodge", "timestamp": 1714200000},
        ...
    ],
    "village_quest": {
        "act": 2,
        "step": 4,
        "started_at": 1714500000,
        "invitation_received_at": 1714500000,
        "gate_passed": true,
        "village_standing": 2,
        "trials_completed": ["skill", "courage", "flesh"],
        "current_trial": "spirit",
        "dark_pull_counter": 1,
        "path_c_locked": false,
        "completed": false,
        "chosen_path": null
    }
}
```

State transitions:

- **`act`** — 1 (signs accumulating), 2 (in Village, doing trials),
  3 (post-trials, choosing path)
- **`step`** — sub-step within the act
- **`village_standing`** — increments on positive trial outcomes; this
  is local to the Village, not a faction code
- **`dark_pull_counter`** — incremented during Trial of Spirit
  ambivalent/temptation choices; 3 = permanent Path C lock-in
- **`path_c_locked`** — true once `dark_pull_counter >= 3`. Once true,
  Master Yarael presents only Path C as the choice (no A, no B).
- **`completed`** — true after path choice
- **`chosen_path`** — `a_jedi_order` | `b_independent` | `c_dark` |
  null

The `force_sign_history` array exists for diagnostics — the Director
AI can use it to flavor ambient events ("you remember the dream from
the cantina, weeks ago — it makes more sense now"). It is bounded at
20 entries (oldest dropped).

---

## 7. The Choice (Act 3)

Per `clone_wars_era_design_v3.md` §4.2: three paths after the trials.
This section gives each path concrete completion mechanics.

### 7.1 Path A — Report to the Jedi Order

Master Yarael writes a letter of introduction sealed with his old
Order signet (a relic from before he left). The character is escorted
by an NPC convoy mission to the Coruscant Jedi Temple. Once at the
Temple, **Master Mace Windu** receives them in person — Yarael's
signet is recognized, and Mace honors the introduction even though
the lineage is decades-cold.

Mace tests the character once more (a quick perception/courage check —
non-failable, narrative only) and then formally accepts them as a
late-age Padawan candidate. The character:

- Gains the `jedi_order` faction at rank 0 (Initiate)
- Has the `jedi_path_unlocked` flag set (this unblocks the Tutorial
  Jedi Path chain from Drop F.6)
- Has their `village_trial_crystal` consumed in a brief Forge scene at
  the Temple — the character helps construct their first lightsaber
  (mechanically: gains a `lightsaber_basic` item and the
  `craft_lightsaber` skill is bumped to 4D minimum)
- Drops into the live world at `jedi_temple_gates` with the Tutorial
  Jedi Path chain auto-started

This is the **canonical** Path. Most players will choose it.

### 7.2 Path B — Stay with the Village / Independent

Master Yarael nods and tells the character the Village is theirs as
much as anyone's now. They are free to come and go. The character:

- Gains 50 rep with `independent` faction (does NOT join `jedi_order`)
- Has the `force_sensitive` flag remain `true`
- Has the `jedi_path_unlocked` flag set as well — the Tutorial Jedi
  Path chain is available, but starts from a different opening (not
  through the Temple — through Master Yarael's continued tutelage at
  the Village)
- Keeps the `village_trial_crystal` (uncommitted; can be used later
  via the alternative-lightsaber-construction chain that's a Drop
  F.10+ candidate)
- Drops into the live world at `village_common_square` and can return
  to it at will

Path B is the **subversive** path — Force-sensitive but politically
unaligned. Mechanically, Path B characters do not get the Order's
support network (no Temple, no Knight superiors, no automatic rank
progression in `jedi_order`) but also have no Order obligations
(can refuse missions, can openly trade with the Hutts, can avoid
the war). Path B characters are a small minority but are the most
interesting from a roleplay perspective.

### 7.3 Path C — Dark whispers

Path C is **only available** if `dark_pull_counter >= 3` was triggered
during Trial of Spirit. There is no way to reach Path C through
positive choices. It is the failure mode of the Spirit trial repurposed
as a deliberate path.

When `path_c_locked: true`, Master Yarael's Act 3 dialogue changes.
He looks at the character with sadness, not anger. He says:

> "You are not what we hoped. You are something else. The Order would
> turn you away. The Sith — they would not. There is a contact. I will
> not stop you from finding him. You may not return here."

The character receives:
- A single-use cryptic comlink frequency (item: `dark_contact_freq`)
- 0 faction rep changes
- The `force_sensitive` flag stays
- The `jedi_path_unlocked` flag is **NOT** set
- The `dark_path_unlocked` flag is set instead
- They are escorted out of the Village (cannot return)

Drop in: live world at `tatooine_anchor_stones` (the wilderness
landmark from §3.2).

**Important:** Path C is **not playable as launch content**. The
`dark_path_unlocked` flag is the *seed* for future dark-side content
(Drop F.13+ candidate). At launch, a Path C character has Force
sensitivity, no Order training, and a comlink frequency that returns
"static — no answer" when called. The flag exists; the content does
not.

This was a deliberate design call from `clone_wars_era_design_v3.md`
§4.2: "Path C: A third NPC (hidden, requires specific dialogue
branches earlier) offers Sith-adjacent guidance. This path is flagged
but not implemented in launch — it's the seed for future dark-side
content."

Players who lock into Path C at launch are not punished — they have a
Force-sensitive character with no Jedi affiliation, mechanically
similar to Path B. The narrative framing differs (Path B's Village
welcome vs Path C's Village expulsion). Future dark-side content
would activate their `dark_contact_freq`.

### 7.4 Dark-side fail state (orthogonal to Path C)

Independent of the Trials and Path mechanics: at any point during the
Village chain, if the character attacks a Village NPC, the chain
**permanently fails**. Master Yarael appears, the rest of the Village
gathers around him, and the character is escorted out. The `village_quest`
state is set to:

```json
{
    "completed": true,
    "chosen_path": "fail_attacked_village",
    "permanent_fail": true
}
```

`force_sensitive` stays true; `jedi_path_unlocked` stays false. The
character can never re-attempt the Village chain on this character.
A new character can. This is the only permanent-fail state in the
chain.

---

## 8. Integration with existing systems

### 8.1 Drop F.6 Tutorial Jedi Path

Drop F.6's `chains.yaml` includes a locked `jedi_path` chain:

```yaml
chain_id: jedi_path
locked: true
prerequisites:
  - chargen_complete
  - jedi_path_unlocked
  - force_sensitive
```

Path A and Path B both set `jedi_path_unlocked: true`. Path C does NOT.
Once the flag is set, the Tutorial Jedi Path chain unlocks at the
chain selector. The Tutorial chain teaches the *Order's procedural
side* (Padawan duties, Council protocols, deployment to a Jedi
General); the Village chain teaches the *Force itself*.

A Path A character runs both chains in sequence: Village → Tutorial
Jedi Path. A Path B character can also run the Tutorial Jedi Path
chain if they want — but the chain narrative reframes for them as
"the Village taught me the Force; now I'm visiting the Temple as a
guest, not joining."

A Path C character has `jedi_path_unlocked: false` — the Tutorial
Jedi Path stays locked for them. They are Force-sensitive but
unaffiliated, with the dark-path seed.

### 8.2 Drop 0 wilderness coordinate system

The Village rooms live inside the Dune Sea wilderness region. Per
`wilderness_system_design_v1.md`, that region uses coordinate-based
tiles with hand-authored landmarks. The Village is one of those
landmarks — 9 hand-authored rooms attached to coordinate tile
`(x=42, y=18)` (illustrative; engine session picks the exact spot).

The wilderness engine treats Village rooms as a closed sub-zone:
movement within the Village is room-to-room (no coordinate movement);
exiting via `village_outer_watch` returns to the Dune Sea coordinate
grid.

### 8.3 Director AI

The Village exists *outside* the Director's faction-influence model.
It has no faction code; it is its own thing. The Director:

- Does NOT manage NPCs in the Village (no faction shifts, no behavior
  drift)
- DOES generate the Trial of Spirit dark-future-self vignette (§5.2
  Trial 4)
- DOES use `force_sign_history` to flavor ambient events outside the
  Village ("the dream comes again — different this time")

The Trial of Spirit is the Director's *one* gameplay-critical role
in the Village quest. Engine session must verify the Director output
parses cleanly and the rejection-detection works (text-classification
or keyword-match against the Director's response).

### 8.4 Achievements

Suggested achievements (drop into existing `data/achievements.yaml`):

- `village_invitation` — received the Act 1 invitation (set on Track A
  chargen-seeded characters automatically; on threshold for Track B)
- `gate_passed` — Sister Vitha admitted you
- `trial_skill` / `trial_courage` / `trial_flesh` / `trial_spirit` /
  `trial_insight` — passed each trial
- `path_a_padawan` — chose Path A (Jedi Order)
- `path_b_hermit` — chose Path B (Independent)
- `path_c_silence` — locked into Path C (not advertised in achievement
  UI; visible only retroactively on character sheet)
- `attacked_village` — failed via dark-side fail state (negative
  achievement; visible to the player as warning)

---

## 9. Content stub shipped in this drop

`data/worlds/clone_wars/quests/jedi_village.yaml` (NEW) — the structured
authoring file for this quest chain, in the same shape as Drop F.6's
`chains.yaml` schema, with extensions:

- Top-level `quest_id: jedi_village` (not `chain_id` — distinct from
  tutorial chains)
- `act` field on each step (1, 2, or 3)
- `village_standing_delta` reward field
- `path_choice` step type for Act 3
- `force_sign_seed_locations` top-level array
- NPC roster as a top-level `npcs:` block with display name, species,
  role description, and dialogue summary placeholders

The file is **mechanically complete** (all completion criteria typed,
all room/NPC/faction cross-references resolve, all flags named) but
the **dialogue text is placeholder-stubbed**: the trial dialogue trees,
Master Yarael's full speech, and Mira's Trial of Courage scripts are
left as `# TODO(content): ...` markers for a future content authoring
pass.

This is deliberate. The mechanics are the engineering surface; the
dialogue is the writing surface. Mechanics can be locked in now;
dialogue benefits from a focused content-only pass with the design
spec in hand.

---

## 10. Open questions for engine session

### 10.1 Force-sign Track B trigger calibration

The 3% per-trigger probability targeting 6-10 weeks of moderate play
is a guess. It needs telemetry-driven adjustment in the first launch
month. Engine session should ship the trigger with a config knob
(e.g. `force_sign_probability_per_trigger` in era.yaml) for live
tuning.

### 10.2 Trial of Flesh duration mechanic

The "6 hours session time, logout pauses" mechanic is unusual. The
alternatives:

- **Wall-clock 24h timer** — easier to implement, friendlier for
  casuals, less narratively heavy
- **Session time 6h** (proposed) — heavier weight, demands real
  commitment, harder to implement (need session-time accounting)
- **Hybrid: session time 4h with wall-clock floor of 12h** — whichever
  is greater triggers completion; ensures both casuals and grinders
  hit comparable wait

Engine session picks. This design proposes session-time-only as the
narratively strongest option, but is open to the hybrid.

### 10.3 Director-authored Trial of Spirit content quality

The Trial of Spirit asks the Director AI to generate a 5-7 turn
dark-future-self vignette tailored to the character. The risk: the
Mistral 7B output is flat or repetitive across players. Mitigation
options:

- **Pre-author 6-8 archetype templates** that the Director seeds
  variants of (Republic-soldier-falls, Smuggler-falls, etc.). Director
  fills in character-specific details, doesn't generate the whole arc
  from scratch.
- **Allow Director full generation** with light-touch content guards
  (no character names from real galaxy, no copyrighted phrases).

Recommendation: ship with archetype templates. Director-only generation
is a fallback if archetype lookup misses.

### 10.4 Path C re-entry possibility

If a future dark-side drop activates `dark_contact_freq`, what does the
returning Path C character look like? Some options:

- They are exiled from the Village forever (canonical). Dark-content
  starts from `tatooine_anchor_stones`.
- They can return as a corrupting influence on visiting Force-sensitive
  characters (NPC role for veteran players).

Dark-side drop design decides. The Village door is closed; the
character has the seed.

---

## 11. What this drop does NOT do

- **Does not author the trial dialogue.** Placeholders only. Future
  content drop.
- **Does not build the 9 Village rooms.** Engine task — needs the Dune
  Sea wilderness region to be partially built first.
- **Does not implement the Director-authored Trial of Spirit.** Engine
  task — needs a Director prompt + content-guard layer.
- **Does not ship Path C content.** Only the seed flag and exit
  mechanics.
- **Does not modify chargen.** The 50% Force-sensitive seed is already
  designed in `clone_wars_era_design_v3.md`; chargen wizard work is
  Drop F.7.

---

## 12. Drop scope and dependencies

This drop ships:
- `jedi_village_quest_design_v1.md` (this doc)
- `data/worlds/clone_wars/quests/jedi_village.yaml` (mechanical
  authoring stub)

This drop **depends on**:
- Drop F.6 (tutorial chains schema) for the chain shape
- Drop 0 / Drop F.5 (wilderness Dune Sea region) for room placement
- Drop F.7 (chargen wizard) for the 50% Force-sensitive seed mechanic
- Drop F.6 engine session (tutorial chains loader + state machine) so
  the Village quest's loader/state machine extension is conceptually
  similar

This drop **unblocks**:
- Drop F.6 Tutorial Jedi Path (currently locked with no producer for
  `jedi_path_unlocked`)
- Drop F.8 engine session (loader + state machine + Director prompt)
- Drop F.13+ dark-side content (Path C seed)
- Future content authoring drop for trial dialogue

---

## 13. Sign-off

The Village quest is now designed at implementation grade. The
mechanical surface is fully specified; only the dialogue authoring and
engine implementation remain. The Tutorial Jedi Path lock has a
producer. The 3-act SWG-inspired structure is preserved without the
SWG grind.

The architectural directives from `clone_wars_era_design_v3.md` §0 and
§4 are respected:
- ✓ No one fully gated (50% chargen + Track B accumulation)
- ✓ SWG-style hidden-village discovery preserved
- ✓ 3-path choice (A/B/C) with C as launch-time seed only
- ✓ Tatooine Dune Sea location
- ✓ Master/Padawan pedagogy from JAS sourcebook

*— Opus, parallel CW track, April 26 2026 (continuation pt 3)*
