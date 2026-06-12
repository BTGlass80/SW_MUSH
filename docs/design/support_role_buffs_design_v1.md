# Support Role Buffs — Design v1

**Status:** Locked decisions, ready for implementation breakdown
**Author:** Brian + Claude (design session, May 2026)
**Builds on:** Existing `perform` and `heal`/`healaccept` commands, `Guide_06_Economy.md` §6, R&E pp52–55 (Character Points & Force Points), R&E p82–84 (Combat & Healing)

---

## 0. The honest constraint

Before any design: **WEG R&E does not have an MMO-style buff system.** R&E has three explicit rules that limit what we can do:

1. **A character cannot spend Character Points on another character's actions** (R&E p55, "Character Points... limits").
2. **Force Points cannot be transferred** between characters.
3. **The only inter-character bonus mechanic is the *combined action***, where multiple characters cooperate on a single action and the leader's Command roll provides a +1D to +2D bonus to the joint action. This is per-action, not per-scene.

So we cannot give an entertainer a "play song → buff allies +1D for 10 minutes" mechanic the way SWG did. That would be a parallel mechanic competing with WEG character economics, which violates our own WEG-fidelity invariant (per architecture v37 §30: "parallel mechanics... competing with WEG ground combat... are NOT acceptable").

**But — there are three things WEG R&E *does* support that we can use:**

1. **Difficulty modifiers on opposed/skill rolls.** Per R&E throughout, the GM can apply situational modifiers to difficulty numbers. A skilled performer creating an inspiring atmosphere can lower the difficulty of subsequent morale-related rolls. A medic providing pre-combat treatment can lower the difficulty of stamina/wound-related rolls. These aren't "buffs"; they're modeled environmental factors.
2. **The `(A)medicine` skill and pharmacological modifiers.** R&E explicitly lists "adrenaline drugs" and "body chemistry boosters" as medpac contents, and references "experimental drugs to improve performance, loyalty, and morale" used by Imperial forces. This is canonical pharmacology with mechanical effect — a medic with `(A)medicine` can administer a stimulant that gives a temporary skill bonus.
3. **The combined-fire / Command bonus mechanic** — already in scope and underused. We have `Command` skill in the engine but no command surface for organized cooperation rolls.

These three give us a WEG-fidelity-clean way to reward support roles without inventing a parallel buff system.

---

## 1. Locked decisions

### 1.1 Entertainer: difficulty-reducer, not stat-buffer

The `perform` command already exists. Its current effect is "earn credits from tips." We extend it:

- A successful `perform` in a cantina-zone room creates a **morale aura** in that room.
- The aura provides a **difficulty reduction** on rolls that are explicitly morale-flavored: Willpower, Command, Persuasion, and the dark-side fall check.
- The aura affects everyone in the room, not just the org or party.
- The effect lasts for the duration of the performance (typically a single scene/cantina visit).
- The size of the reduction scales with the entertainer's `perform` skill margin.

This is not a "buff." It's a modeled environmental effect: when you're in a room with a great band playing, you feel braver, more confident, more in tune with your companions. That's a R&E-defensible difficulty modifier.

### 1.2 Medic: pharmacological action, not maintained buff

The `heal`/`healaccept` mechanic already exists for damage healing. We add:

- A new command `stim <player>` lets a character with `(A)medicine` or `first aid` administer a stimulant.
- The stimulant gives the recipient a **one-time +1D bonus on their next single skill roll** (for first aid) or **+2D for one continuous action up to 5 minutes** (for `(A)medicine`).
- This is mechanically the *same as a Force Point applied by another character*, except it costs a consumable (a stimpack or experimental drug) and uses a skill roll, not the Force.
- Strict limits: only one stim active per character at a time; cooldown to prevent stacking; pharmacological side-effects on overuse.
- This maps directly to R&E "adrenaline drugs" / "body chemistry boosters" — canonical, not invented.

### 1.3 What we are explicitly NOT building

- **No "song with persistent buff"** — entertainer-as-MMO-buffer is not WEG-defensible.
- **No "doctor maintains a buff icon"** — medic-as-MMO-doctor is not WEG-defensible.
- **No buff-stacking, no buff-bar, no buff-icons HUD.** Effects are situational and short.
- **No parallel "buff" stat anywhere in the schema.** Effects are applied as transient difficulty modifiers, not persisted state.

---

## 2. Entertainer mechanic — full design

### 2.1 The morale aura

When a character runs `perform` in a cantina-zone room and rolls successfully:

```
[perform Perception+perform skill check vs. difficulty 10]
        ↓
[Existing tip mechanic still fires — credits earned]
        ↓
[NEW: Morale aura created on the room with margin-based magnitude]
        ↓
[Aura active for 30 minutes real-time OR until performer leaves the room OR until performer rolls fumble]
```

### 2.2 Aura magnitude

| Margin above difficulty | Difficulty reduction | Flavor |
|---|---|---|
| 1–4 (basic success) | −1 to morale-flavored difficulties | "Pleasant background music" |
| 5–9 (good performance) | −2 | "An engaging performance lifts the mood" |
| 10–14 (excellent) | −3 | "A genuinely inspiring performance" |
| 15+ (heroic) | −5 | "A once-in-a-lifetime performance — the room is electric" |

These are **flat reductions to difficulty numbers** for affected rolls, not bonus dice. This matches R&E's standard situational modifier pattern.

### 2.3 What rolls are affected

The aura applies to:

- **Willpower checks** (resisting fear, persuasion, intimidation)
- **Command rolls** (when leading a combined action)
- **Persuasion rolls** (interpersonal / social)
- **Dark Side fall check** (the high-difficulty Willpower roll triggered at 6+ DSP)

It does **not** apply to:

- Combat skill rolls (Blaster, Dodge, etc.) — these are not morale-based
- Technical/mechanical/knowledge skill rolls
- Force power rolls
- Damage rolls

The narrow scope keeps the effect from becoming a default-pass for combat, which would be a parallel-mechanic violation. It also keeps the effect *thematically* tied to morale — exactly what an entertainer should provide.

### 2.4 Multiple performers in same room

If two entertainers `perform` in the same room, **the higher aura wins**. Auras do not stack. (This is consistent with R&E's "best modifier wins" pattern for environmental effects.)

### 2.5 Performance fatigue (sink)

A character can `perform` multiple times per day, but each attempt after the first incurs a **−1D fatigue penalty** to the perform roll. This penalty resets after 8 hours of no performance. This prevents one entertainer from camping a cantina indefinitely and creates space for multiple entertainers.

### 2.6 Aura visibility

When you enter a room with an active aura:

```
Chalmun's Cantina [SECURED]

A spacious cantina filled with a diverse crowd of patrons...

♪ Veska Korr is performing — an inspiring performance lifts the mood here.
   (Morale-related rolls are easier in this room.)
```

Citizens get to know which cantinas have entertainers active. This creates organic foot traffic to good performers.

### 2.7 Schema additions

```sql
CREATE TABLE IF NOT EXISTS morale_auras (
    room_id         INTEGER PRIMARY KEY,
    performer_id    INTEGER NOT NULL,
    magnitude       INTEGER NOT NULL,    -- 1, 2, 3, or 5
    started_at      REAL NOT NULL,
    expires_at      REAL NOT NULL,
    FOREIGN KEY (performer_id) REFERENCES characters(id)
);

ALTER TABLE characters ADD COLUMN perform_fatigue_resets_at REAL DEFAULT 0;
ALTER TABLE characters ADD COLUMN perform_fatigue_count INTEGER DEFAULT 0;
```

The aura is stored per-room. Lookup is on every relevant skill check (which is a small number of code paths — Willpower, Command, Persuasion, fall check).

### 2.8 Code integration

- `parser/social_commands.py::PerformCommand` — extend to write/refresh `morale_auras` row on success.
- `engine/skill_checks.py` — add `apply_morale_aura(char, difficulty)` helper. Called by `perform_skill_check()` only for the affected skill types.
- `engine/force_powers.py::_resolve_fall_check()` — apply aura to the difficulty.
- `engine/character.py::leave_room()` — clear aura if performer leaves.
- `engine/combat.py` — does NOT call the aura helper (auras don't affect combat rolls).
- Periodic tick — clean up expired auras.

---

## 3. Medic mechanic — full design

### 3.1 The stim command

```
stim <player>                    — Administer a basic stimpack
stim <player> with <consumable>  — Administer a specific drug
```

The medic must be in the same room as the target. The target must consent (no surprise injections — `stimaccept` flow, mirroring `healaccept`).

### 3.2 Resolution

```
[Medic rolls First Aid (or (A)medicine if available)]
        ↓
[Difficulty: Easy (10) for stimpack, Moderate (15) for adrenaline shot, Difficult (20) for combat stim]
        ↓
[Consumable consumed regardless of success]
        ↓
[On success: target gains a one-time bonus on their next applicable roll]
        ↓
[On failure: target takes minor side effects (see §3.5)]
```

### 3.3 Consumable types

These extend the existing crafting consumable system:

| Item | Crafting Skill | Difficulty | Effect |
|---|---|---|---|
| Stimpack | First Aid | 10 | +1D to next single Strength or Dexterity roll within 5 min |
| Adrenaline shot | (A)medicine | 15 | +2D to one continuous action up to 5 min (mirrors Force Point) |
| Combat stim | (A)medicine | 20 | +1D to all combat actions for 3 rounds; −1D Willpower for 10 min after (jitter) |
| Bacta patch | First Aid | 10 | Heals one wound level (already exists as healing item) |
| Focus stim | (A)medicine | 15 | +1D to a single Knowledge or Technical roll |

These are existing R&E-canonical consumables. Stimpack and adrenaline shot are explicitly named in R&E p82's medpac description ("body chemistry boosters" + "adrenaline drugs"). Combat stim and focus stim are extensions in the same flavor.

### 3.4 Stim economics

- **Stimpacks craftable** by anyone with First Aid + chemical ingredients (typical price 200 cr)
- **(A)medicine consumables craftable** by trained medics only — meaningfully harder difficulty, more expensive ingredients (typical price 800–2000 cr)
- This makes medic a real economic profession: their consumables are required for higher-tier effects, and only they can craft them.

### 3.5 Side effects

If the stim roll **fails**:
- Stimpack: target wastes the stim, no benefit. No further consequence.
- Adrenaline shot: target takes 1 wound level (Wounded → Wounded Twice, etc.). The body chemistry shock is real.
- Combat stim: target gets −1D Willpower for 10 minutes (jitter), no combat bonus.
- Focus stim: target gets −1D Perception for 5 minutes (over-focused, tunnel vision).

If the stim roll **fumbles** (Wild Die 1, complication):
- Target takes 2 wound levels. The medic just made things worse.
- Mirrors R&E p82's "first aid roll missed by more than 10 = no further medpacs that day."

### 3.6 Stacking limits

- A character can have **at most one active stim effect at a time**.
- Attempting to apply a second stim while one is active: medic gets a warning prompt; if they continue, the second stim's roll is at +5 difficulty (overdose risk).
- A failed overdose stim auto-incapacitates the target.
- This makes medic-as-buff-stack a non-strategy. You get one stim and it matters.

### 3.7 Self-administration

Per R&E p82, self-medpac use is at −1D. Same applies to self-stims:

- Self-stim: −1D to the medic roll.
- Combat stim and adrenaline shot **cannot be self-administered** — the recipient cannot reliably inject themselves while in the state these address. (Mirrors WEG flavor: you need a medic to give you a shot mid-firefight.)

### 3.8 Schema additions

```sql
CREATE TABLE IF NOT EXISTS active_stims (
    char_id         INTEGER PRIMARY KEY,
    stim_type       TEXT NOT NULL,     -- 'stimpack' | 'adrenaline' | 'combat' | 'focus'
    bonus_dice      INTEGER NOT NULL,  -- 1 or 2 (D)
    bonus_pips      INTEGER NOT NULL DEFAULT 0,
    affects         TEXT NOT NULL,     -- 'strength' | 'dex' | 'continuous' | 'combat' | 'knowledge_tech'
    applied_at      REAL NOT NULL,
    expires_at      REAL NOT NULL,
    medic_id        INTEGER NOT NULL,
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (medic_id) REFERENCES characters(id)
);
```

### 3.9 Code integration

- `parser/medical_commands.py::StimCommand` and `StimAcceptCommand` — new commands.
- `engine/skill_checks.py::perform_skill_check()` — check `active_stims` and apply bonus dice if applicable.
- `engine/combat.py` — same check for combat skills (combat stim).
- `engine/character.py` — clear stims when their `expires_at` passes (lazy cleanup on next read, plus periodic tick).

---

## 4. Combined-action / Command bonus surface

This is the third leg, and it's almost entirely a UI/command surface change rather than a new mechanic. Per R&E, when characters cooperate on a single action led by a Command roll, the leader provides:

- Easy Command roll (10): +1D to the joint action
- Moderate (15): +2D
- Difficult (20): +3D (cap)

Currently there's no command for this. We add:

```
+lead <action> for <player1> [<player2>...]   — Lead a combined action
+joinlead                                      — Join a leader's combined action
```

This is mechanically identical to R&E. The use case: a Command-skilled PC can lead a group through a difficult task (slicing a heavily-secured terminal, breaching a door, navigating a hyperspace jump) and provide a real bonus. The Command skill becomes worth investing in.

### 4.1 Limits

- Maximum 5 followers per leader (matching R&E "combined fire" precedent).
- Leader and followers must be in the same room (or same crew station for ship actions).
- Each follower contributes up to +1D of their own skill in the relevant skill (per R&E combined-fire rules).
- One lead action per round; if you lead, you can't take a separate action that round.

### 4.2 Schema additions

None. Combined actions resolve in a single round and don't persist.

### 4.3 Code integration

- `parser/social_commands.py::LeadCommand` and `JoinLeadCommand` — new commands.
- `engine/skill_checks.py::perform_skill_check()` — accept optional `lead_bonus` parameter.
- `engine/combat.py::resolve_combined_fire()` — already exists for blaster combined-fire; refactor to share a helper with the new lead system.

---

## 5. Why this is WEG-fidelity-clean

Each of the three mechanics (entertainer aura, medic stim, lead bonus) maps directly to a documented R&E rule:

| Mechanic | R&E source | Mapping |
|---|---|---|
| Morale aura | Situational difficulty modifiers (R&E throughout) | Lower difficulty for morale-flavored rolls in inspiring atmosphere |
| Medic stim | Medpac contents include "adrenaline drugs, body chemistry boosters" (R&E p82) | Pharmacological consumable with skill check |
| Lead bonus | Combined fire / cooperation rules (R&E p59) | Skill-check leader provides bonus to joint action |

None of these are "buffs" in the MMO sense:
- None of them stack indefinitely.
- None of them are persistent or maintained.
- None of them duplicate Force Point / Character Point economics.
- All of them have failure cases and meaningful costs.

A WEG R&E GM running a tabletop game would recognize and accept all three as natural extensions of the rules. That's the bar.

---

## 6. Cross-system interactions

### 6.1 With cantinas

The morale aura is most relevant in cantinas (per the existing cantina-zone gating on `perform`). It's also where `lead` and `+sabacc` happen. Cantinas become genuine social hubs with mechanical reasons to gather, not just RP venues.

### 6.2 With Jedi / Force Points

The Dark Side fall check is the highest-stakes Willpower roll in the game. A morale aura at the cantina before a known-tense scene could shift a fall check from Heroic to Difficult — a meaningful difference. This subtly rewards Jedi who maintain social ties and frequent supportive environments, which is *deeply* on-theme for the Light Side.

### 6.3 With combat

Combat stim is the only stim that affects combat rolls. The morale aura does not. The lead bonus does, but only on the specific cooperative action. This keeps combat from being trivialized by support stacking.

### 6.4 With the medic profession

Medics now have three economic legs:
- Heal damage (existing `heal` command + medpac sales)
- Administer stims (new `stim` command + (A)medicine consumable sales)
- Craft (A)medicine consumables (the supply side of the above)

This makes medic a substantial profession choice rather than a curiosity. A dedicated medic at a cantina could realistically earn 1,000–3,000 cr/hour from combined healing + stim work, putting them in line with other professions.

### 6.5 With the entertainer profession

Currently entertainer is a credit-trickle (`perform` for tips). With the morale aura:
- Entertainers become socially valuable beyond their tips.
- High-skill performers are sought-out party members for group expeditions (one performance before the trip = a morale aura on the staging room).
- Director AI can narrate famous performers organically ("the cantina is packed tonight — word is Veska Korr is performing").

---

## 7. Phased delivery plan

### Phase 1: Lead / combined action
- `+lead` and `+joinlead` commands
- Refactor existing combined-fire helper for general use
- `perform_skill_check()` accepts `lead_bonus`
- **Effort:** Small. ~0.5 sessions.

### Phase 2: Morale aura
- `morale_auras` table + lookup
- Extend `PerformCommand` to write auras on success
- `apply_morale_aura()` helper in `skill_checks.py`
- Wire into Willpower, Command, Persuasion, fall-check code paths
- Look output integration
- Periodic tick for cleanup
- **Effort:** Medium. ~1 session.

### Phase 3: Medic stims
- `active_stims` table
- `StimCommand` + `StimAcceptCommand`
- Stim consumable schematics added to crafting
- Bonus-dice application in `perform_skill_check()` and combat
- Side-effect flow for failures
- Overdose detection
- **Effort:** Medium-Large. ~1.5 sessions.

### Phase 4: Polish
- Help topics
- Web client UI: morale aura indicator in room banner, stim status in HUD
- Tutorial step for `stim`/`heal` flow
- **Effort:** Small. ~0.5 sessions.

**Total:** ~3.5 sessions.

---

## 8. Open questions

1. **Aura-aware Director AI.** Should the Director get notified when a high-magnitude aura is active in a high-traffic cantina? Could feed into ambient narration. Defer — nice-to-have.

2. **Performance specialization.** R&E doesn't define performance specializations (singer, dancer, holo-projection, etc.). Should we add cosmetic flavor variants? Deferred — cosmetic only.

3. **Stim addiction.** Should heavy stim use cause addiction with permanent skill penalties? On-flavor for darker storylines but adds a lot of accounting. Defer — possibly relevant for spice as a separate mechanic later.

4. **Lead bonus for ship combat.** Should a ship Captain's commanding officer be able to use `+lead` for joint engineering rolls? The existing Captain's Order system already covers ship-scale leadership. Defer; revisit if Captain's Orders feel insufficient.

5. **Aura strength tuning.** Is −5 difficulty for a Heroic perform too generous? Initial value; tune from observed play. The fall check is the most sensitive consumer.

6. **Cross-zone medic services.** Should `(A)medicine` consumables be more available in safe zones (where medics gather) than in lawless zones (where they're needed most)? This is a market-distribution question, not a mechanic question. Defer to economic tuning.

---

## 9. Architecture invariants

- All bonus-dice applications go through `perform_skill_check()` and the active-stims lookup. No combat-specific shortcuts.
- Morale aura affects ONLY the listed skills (Willpower, Command, Persuasion, fall check). No silent-extension to other skills.
- One active stim per character at a time. Enforced at `stim` command resolution.
- Auras are room-scoped, not character-scoped. Leaving the room means losing the benefit.
- All transient effects (auras, stims) clean up on a periodic tick — no stale state.
- The lead bonus is per-action, not per-scene. Resolves in a single round.

---

## 10. Test plan

### Unit / integration

- Perform with various margins; verify aura magnitudes correctly written.
- Enter a room with aura; perform a Willpower check; verify difficulty reduction applied.
- Enter a room with aura; perform a Blaster check; verify NO modifier applied.
- Performer leaves room; verify aura cleared.
- Two performers in same room; verify higher aura wins.
- Stim a target; perform their next strength roll; verify bonus applied; verify second roll has no bonus.
- Apply two stims to same target; verify second is at +5 difficulty.
- Lead a combined action with 3 followers; verify bonus calculated correctly.
- Self-administer combat stim; verify rejection.

### Manual / GM

- Run a cantina scene with a performer, observe aura visibility.
- Run a Jedi Dark Side fall check with and without aura present; observe meaningful difficulty shift.
- Run a combat scenario with a medic providing combat stims; observe pharmacology side effects on failure.
- Run a Slicing scenario with a Command-led group of 3; observe lead bonus.

---

## 11. Documentation updates required

- New help topics: `+help perform`, `+help stim`, `+help lead`, `+help aura`
- `Guide_06_Economy.md` — extend §6 to cover stim economics and the entertainer/medic income loops.
- `Guide_03_Ground_Combat.md` — add Combat Stim section.
- `Guide_08_Force_Powers.md` — note that morale auras affect the fall check.
- `Guide_10_Organizations_Factions.md` — note that lead bonus benefits faction missions.
- New page in `data/help_topics.py` for the support-role economic loops.

---

*End of design v1.*
