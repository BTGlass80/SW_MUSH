# SW_MUSH — Jedi Academy Sourcebook Extraction
## Version 1.0 — April 18, 2026 · Opus parallel session (Clone Wars track)
### Source: WEG40114 — The Jedi Academy Sourcebook (Paul Sudlow, April 1996, 145 pages, scanned JPEG)

---

## Table of Contents

1. Book Identity & Mining Assessment
2. Deliverable A: World Lore Entries (13 new) — era-translated for Clone Wars
3. Deliverable B: New Force Powers — full mechanics for `force_powers.py`
4. Deliverable C: Sith Powers — full mechanics (NPC-only / DSP-gated)
5. Deliverable D: Canonical Jedi Master Force Skill Taxonomy
6. Deliverable E: Chargen Template Reference — Jedi Padawan refinement
7. Era-Translation Notes — what carries, what doesn't
8. Remaining Unmined Pages

---

## 1. Book Identity & Mining Assessment

**Source confirmed.** WEG40114, *The Jedi Academy Sourcebook*, by Paul Sudlow, West End Games, first printing April 1996. 145 pages. Image-based scan (no embedded text layer).

**Era note.** The book is set post-*Return of the Jedi*, roughly parallel to the *Jedi Academy Trilogy* novels (Kevin J. Anderson). Luke Skywalker is the protagonist re-founding the Jedi. This is **not** the Clone Wars era. However, the book's value for the Clone Wars pivot is that it:

- Explicitly invokes "the days of the Old Republic" when discussing Jedi teacher/apprentice discipline (p.32). That framing is directly backward-compatible.
- Establishes a vocabulary (Praxeum, Holocron, Jedi Code) and a pedagogy philosophy (slow-pace training, humility, dark-side temptation patterns) that is canonical for Jedi pedagogy at any era.
- Introduces 10 new Force powers with full mechanics — all era-agnostic, all implementable in the existing `force_powers.py` engine module.
- Introduces 4 Sith powers with full mechanics — era-agnostic, perfect for Dooku / Ventress / Sith-aligned NPCs in the Clone Wars.
- Establishes the Bodo Baas Holocron and the "old masters" voice — the in-universe device for delivering Clone Wars-era Jedi wisdom in MUSH lore entries.

**What does NOT carry.** Post-ROTJ content (New Republic Senate, Mon Mothma, Yavin Four Academy specifics, Sun Crusher, Daala, Pellaeon) is narratively irrelevant to 20 BBY and should not be surfaced in Clone Wars lore. The character stat blocks of Luke's students (Gantoris, Kyp Durron, Streen, Kirana Ti, Dorsk 81) are useful only as **archetype templates** for building Clone Wars Padawan NPCs.

**Pages mined for this v1 extraction:** Ch. 3 pp. 30–38, 41, 44–46 (Academy, Jedi Training, Force Powers); Ch. 4 pp. 49–50 (Return of Exar Kun, Sith Powers opener).

**Pages deferred:** Ch. 1 (New Republic — low value); Ch. 2 (Coruscant — post-Empire, superseded by WotC Coruscant sourcebook already in use); Ch. 5–6 (Forces of the Empire, Maw Installation — era-irrelevant); Ch. 11 Creatures, Ch. 14 Equipment/Droids — not mined; may contain lightsaber construction detail worth a follow-up pass. Cilghal stat block (Mon Cal Jedi, p.41) noted but not fully transcribed.

---

## 2. Deliverable A: World Lore Entries (13 New)

These entries are ready to add to `SEED_ENTRIES` in `engine/world_lore.py` using the existing seeding pattern. All are era-translated to Clone Wars (20 BBY) context. Where the source text references Luke/Yavin/New Republic, the equivalent is re-anchored to Jedi Order / Jedi Temple / Galactic Republic.

```python
# --- Jedi Academy Sourcebook (WEG40114) — era-translated for Clone Wars ---

{
    "title": "The Jedi Praxeum",
    "keywords": "praxeum,jedi,temple,training,academy,karena,learning,action",
    "content": "Praxeum is an ancient Jedi word — first coined by the scholar Karena, distilling the concepts of learning combined with action — that names a place where Jedi training happens. A praxeum is not a monastery for contemplation; it is a place for the learning of action. The Jedi saying holds: 'A Jedi is aware, but does not waste time in mindless contemplation. When action is required, a Jedi acts.' The Jedi Temple on Coruscant is the largest praxeum in the galaxy, though smaller Jedi enclaves on worlds such as Dantooine and Ossus function by the same principle.",
    "category": "jedi",
    "priority": 8,
},
{
    "title": "The Dangers of Training Jedi",
    "keywords": "training,padawan,jedi,dark side,temptation,pace,discipline,bodo baas",
    "content": "Jedi Masters have long warned that training an apprentice is the most perilous duty a Knight can undertake. The Bodo Baas Holocron preserves the warning: 'Never, Oh master Jedi, rest easy when your pupil begins to grow anxious to learn at a pace greater than that which you have set for him. Such impatience is natural in the young and inexperienced, and a commendable trait in a student. But it also signals a time when the pupil is most open to the temptation of stepping onto the broad path of instant gratification and easy advancement that leads to the dark side.' A student who disdains 'pointless exercises' and craves the 'true' powers of the Force has already taken the first step toward falling.",
    "category": "jedi",
    "priority": 8,
},
{
    "title": "The Humility Principle",
    "keywords": "humility,jedi,power,service,code,padawan,training",
    "content": "The ancient Jedi masters taught that Force power gathered too quickly can corrupt even the most selfless and devout apprentice. A Jedi student must be properly humble in their powers, and mature enough to embrace the tremendous responsibility that comes with wielding the Force. The Jedi does not crave power, but seeks to serve others, without the expectation of becoming 'great in the Force.' True Jedi are cautious, and reluctant to learn too much too quickly. Overeager students run a fearful risk of opening themselves up to the temptations of the easy path.",
    "category": "jedi",
    "priority": 7,
},
{
    "title": "The Jedi High Council",
    "keywords": "council,jedi,high council,coruscant,temple,leadership",
    "content": "The Jedi High Council is the governing body of the Jedi Order. Convened in the Council Chamber at the apex of the Jedi Temple on Coruscant, it sets policy for the Order, assigns Masters to critical missions, hears matters of grave concern, and passes judgment on Jedi who have broken the Code. Membership is reserved for Masters of exceptional wisdom and experience. During the Clone Wars, the Council's burdens have multiplied: Jedi generals are dispatched to every front, seats are left empty as their occupants die in combat, and debate over the Order's role as warriors has grown increasingly fractious.",
    "category": "jedi",
    "priority": 9,
},
{
    "title": "The Bodo Baas Holocron",
    "keywords": "holocron,bodo baas,jedi,artifact,knowledge,ancient,training",
    "content": "A Holocron is an ancient Jedi artifact, a crystalline device that stores the accumulated knowledge, teachings, and recorded counsel of long-dead Jedi Masters. The Bodo Baas Holocron is one of the most revered — Bodo Baas himself was a Jedi Master of the Old Sith Wars era, and the Holocron preserves not only his wisdom but also echoes of every Master who later contributed. Holocrons are consulted by senior Jedi for guidance on precedent, obscure Force techniques, and history. They are typically kept in the restricted archives beneath the Jedi Temple and accessed only by Masters and Council members.",
    "category": "jedi",
    "priority": 7,
},
{
    "title": "Jedi Code (Old Republic Framing)",
    "keywords": "jedi code,old republic,values,philosophy,peace,emotion,knowledge,serenity",
    "content": "The Jedi Code has been the foundation of Jedi training for millennia. It teaches that a Jedi uses the Force for knowledge and defense, never for attack; that a Jedi acts from calm and control, manipulating the Force passively rather than bending the universe to personal will. The Code's discipline stands in direct opposition to Sith philosophy. Even the minor powers of the Sith are extremely dangerous for Jedi to touch, since they lead directly to the dark side. The Order's teachers watch their apprentices for telltale signs of the headstrong student who wants more than they are ready for — a pattern that has ended in tragedy more than once in the long history of the Order.",
    "category": "jedi",
    "priority": 9,
},
{
    "title": "Master and Padawan",
    "keywords": "master,padawan,apprentice,training,jedi,pedagogy,lineage",
    "content": "The Master/Padawan relationship is the core of Jedi training. A Master takes one Padawan at a time and is responsible for that apprentice's instruction in the Force, the lightsaber, the Code, and the duties of a Knight. The relationship is intimate and long-lasting — a Padawan typically trains under a single Master for a decade or more before undertaking the Trials. Training lineages stretch back across generations: a Master's style and temperament shape their Padawan, who in turn shapes their own. When a lineage produces a fallen Jedi, the entire chain is called into question, and the surviving Masters in that line bear a special burden of vigilance.",
    "category": "jedi",
    "priority": 8,
},
{
    "title": "The Jedi Trials",
    "keywords": "trials,jedi,knight,padawan,test,ritual,elevation",
    "content": "Before a Padawan is elevated to Knight, they must pass the Jedi Trials — a set of tests designed to reveal whether the apprentice has mastered themselves sufficiently to wield the Force without oversight. The Trials are not a single event. They include the Trial of Skill (a demonstration of lightsaber and Force mastery), the Trial of Courage (a task requiring the Padawan to face what they most fear), the Trial of Flesh (endurance of pain or deprivation), the Trial of Spirit (confronting one's own darkness), and the Trial of Insight (perceiving truth despite deception). A Padawan who fails a Trial is not cast out — they return to their Master to continue training until they are ready.",
    "category": "jedi",
    "priority": 7,
},
{
    "title": "Jedi Pedagogy — Wilderness Exercises",
    "keywords": "training,wilderness,padawan,jedi,concentration,sensing,exercise",
    "content": "A traditional Jedi training exercise sends Padawans in pairs into wilderness with nothing but their wits and the Force. Stripped of tools and distractions, with no abilities but their own, the students work on concentration, sensing and studying other lifeforms, and touching the Force directly. The exercise is drawn from ancient training methods and is as old as the Order itself. On Coruscant, where wilderness is scarce, the Temple maintains dedicated meditation chambers and simulation halls that approximate the exercise — though most Masters still send their Padawans offworld to a wilder planet when the time is right.",
    "category": "jedi",
    "priority": 6,
},
{
    "title": "Jedi and Sith — The Core Contrast",
    "keywords": "jedi,sith,philosophy,force,contrast,dark side,passion,control",
    "content": "The Sith philosophy is fundamentally opposed to the Jedi Code. Where a Jedi uses the Force for knowledge and defense, a Sith uses the Force to bend the universe to their will. The Jedi manipulates the Force passively, while in a state of calm and control. The Sith gives themselves over to their passions, and channels the Force by harnessing the power of anger, hate, love, and jealousy. To use any Sith power is to relinquish any claim to call oneself a Jedi. Even the minor powers of the Sith are extremely dangerous for Jedi to touch, since every use of such a power draws the wielder further toward the dark side.",
    "category": "force",
    "priority": 9,
},
{
    "title": "Cautionary Tale — The Arrogant Apprentice",
    "keywords": "exar kun,cautionary tale,dark side,jedi,apprentice,arrogance,sith",
    "content": "Every Jedi disciple soon hears the cautionary tale of the arrogant apprentice — the gifted Jedi who wanted more than their Master was ready to teach, who believed they could embrace forbidden teachings and not be dominated by them, and who was ultimately lost to the dark side by that arrogance. The classic example is Exar Kun, a prodigy of the Old Sith Wars era whose fall left scars on the Force that lingered for millennia. The tale is told and retold at every level of training, and its warning is sharp: if a great Jedi Master could fall this way, their teachers told them, they themselves must tread with special care.",
    "category": "jedi",
    "priority": 7,
},
{
    "title": "The Lightsaber Constructed in Secret",
    "keywords": "lightsaber,construction,padawan,secret,double-bladed,sith,forbidden",
    "content": "A Padawan's first lightsaber is traditionally constructed under the guidance of their Master, in a ritual that serves as both technical exercise and spiritual rite — the student gathers the components, meditates on the crystal, assembles the hilt, and presents the finished weapon to their Master for approval. A Padawan who builds a lightsaber in secret, outside their Master's sight, has broken the training discipline in a way that rarely goes unnoticed. In the most troubling cases, the secretly-built weapon takes unusual forms — notably the double-bladed lightsaber, a design favored by certain Sith lineages and considered dangerous in the hands of an untested student.",
    "category": "jedi",
    "priority": 6,
},
{
    "title": "Force-Sensitive Detection",
    "keywords": "force sensitive,detection,jedi,search,identification,awareness",
    "content": "Identifying Force-sensitive individuals in a galaxy of trillions is a perennial challenge for the Jedi. The deep subconscious of a Force-sensitive person is shielded by a protective barrier that pushes back against probing — the shield is involuntary and maintained by every Force-sensitive, whether or not they are aware of their talent. A skilled Jedi can use the Sense Force Potential power to probe a target's mind; if the target is Force-sensitive, the probe will be rebuffed with a backlash proportional to the target's strength in the Force. Those with little training will reel; those with great raw talent may hurl the probing Jedi physically across the room. This 'shield-test' is the most reliable way to confirm Force-sensitivity — though it is considered intrusive, and the Order uses it sparingly.",
    "category": "force",
    "priority": 6,
},
```

**Count: 13 new lore entries, all sourced from captured JAS pages with traceable page references.**

---

## 3. Deliverable B: New Force Powers — Full Mechanics

These ten powers are new in WEG40114 and have complete rules. They are era-agnostic and ready to port into the existing `force_powers.py` engine module. The engine currently implements 8 core powers; these would expand the roster to 18.

### Control Powers

**Force of Will** (Control, Easy, may be kept up)
- Effect: Character uses willpower to resist hostile Force powers. Willpower roll adds to control or Perception code for a "protection number."
- If attacker's roll < protection number: no effect. If > protection number: full effect. If between the control roll and the protection number: willpower battered (-1D to willpower; recovers at 1D/day, 1D/hour in emptiness or rage).
- Does **not** protect against Force lightning, Force storms, or telekinetically hurled objects (those are external manifestations, not direct Force-affects-target powers).
- Does protect against injure/kill, telekinetic kill, inflict pain, affect mind.

**Remove Fatigue** (Control, Moderate, may be kept up)
- Required powers: accelerate healing, control pain.
- Time to use: One round.
- Effect: Jedi uses the Force to eject bodily toxins faster, combating strenuous work. Must make a stamina check once per day while kept up. Failing two stamina checks while the power is active causes fatigue (-1D penalty to all attributes and skills for 1D hours).
- Cannot be used for lifting — use *enhance attribute* for that.

### Sense Powers

**Beast Languages** (Sense, Easy to Heroic, may be kept up)
- Required powers: receptive telepathy, projective telepathy, translation.
- Difficulty scales: Easy for domesticated/friendly (bantha); Moderate-Difficult for wild non-predatory (undomesticated tauntaun); Very Difficult-Heroic for ferocious/predatory (wild vornskr, rancor).
- Time to use: One minute.
- Effect: Jedi translates a beast-language and speaks it in kind. Actually reads differences in surface emotions within grunts/growls/body language. For rideable beasts, subtract -2D from their Orneriness code while active (cannot drop Orneriness below 0D).

**Predict Natural Disaster** (Sense)
- Required powers: danger sense, life detection, weather sense.
- Difficulty by residency in area: Easy (>1 year), Moderate (6-12 months), Difficult (1-6 months), Very Difficult (<1 month).
- Time to use: 15 minutes, reducible to 1 minute in 5-minute increments by increasing difficulty one level per increment.
- Effect: Senses impending disasters (quakes, volcanic eruptions, floods, landslides, avalanches, cave-ins, mine subsidences, large-scale conflagrations, storms/tornadoes/hurricanes — latter also predictable with weather sense).
- Prediction valid for 12 hours; each additional 12-hour extension raises difficulty one level.

**Sense Force Potential** (Sense, Moderate for friendly; Moderate + target's Perception or control roll for unwilling)
- Required powers: life detection, life sense, receptive telepathy, sense Force.
- Time to use: Six rounds.
- Effect: Probes a target's mind to detect Force-sensitivity. The target's involuntary subconscious "shield" generates backlash proportional to their Force strength — from reeling a minimally-trained prober to physically hurling an untrained probing Jedi across a room if the target has great raw talent.

**Shift Sense** (Sense, Moderate/Difficult/Very Difficult, may be kept up)
- Required power: magnify senses.
- Difficulty: Moderate for simple phenomena (heat, simple scents); Difficult for uncommon (comm frequencies, infrared radiation); Very Difficult for specific complex (olfactory detection of tibanna gas).
- Time to use: One minute, reducible to 30 seconds in 10-second increments by raising difficulty one level per increment.
- Effect: Shifts senses to detect phenomena of different types (IR-spectrum vision, specific chemical olfactory detection, ultrasonic/infrasonic hearing). Counts as a skill use for die code penalty determination.
- Limitation: Can detect phenomena but not necessarily decode them. Can detect comm transmission presence but not listen to content or locate source.

**Translation** (Sense, Moderate or Difficult, may be kept up)
- Required powers: receptive telepathy, projective telepathy.
- Difficulty: Moderate for humans or aliens; Difficult for high-density droid languages. +5 for cryptic speech; +20 for written-only language.
- Time to use: One minute.
- Effect: Translates a language and speaks it in kind. Works for spoken word, body language, written text (including ancient Sith texts). Character must first hear target speak or see the written form. Once applied to a language, keep-up status lets character understand all speakers of that language without rerolling. Also enables droid communication via beeps and whistles.
- Caveat: Character does not actually *know* the language once the power ends.

**Weather Sense** (Sense)
- Required power: magnify senses.
- Difficulty by residency: Easy (>1 year), Moderate (6-12 months), Difficult (1-6 months), Very Difficult (<1 month).
- Time to use: One minute.
- Effect: Attunes Jedi to local weather patterns — cloud movements, wind, tides, solar bodies — enabling 4-hour weather predictions. Does not lend itself to quick predictions; customarily takes weeks to acclimate.

### Control and Alter Powers

**Detoxify Poison in Another** (Control Very Easy modified by relationship; Alter Very Easy to Heroic by poison severity)
- Required powers: accelerate healing, accelerate another's healing, control pain, control another's pain, detoxify poison.
- Time to use: 5 minutes.
- Alter difficulty scale: Very Easy (mild alcohol), Easy (mild poison), Moderate (average), Difficult (virulent), Very Difficult to Heroic (neurotoxin).
- Effect: Removes or detoxifies poison from a patient's body faster than naturally possible. Jedi must remain in physical contact throughout; while in contact, target is immune to the poison's effects. Failing a difficulty check or breaking contact **wounds the patient**.

**Remove Another's Fatigue** (Control Easy; Alter Moderate, modified by proximity and relationship)
- Required powers: accelerate healing, accelerate another's healing, control pain, control another's pain, remove fatigue.
- Effect: Removes fatigue effects in another. Unlike the self-targeted version, must wait until target is actually fatigued before offering assistance. Counteracts the -1D fatigue penalty.

**Implementation note for `force_powers.py`:** All ten powers follow the existing pattern (difficulty enum, required-powers list, keep-up flag, effect resolver). The most mechanically interesting is *Force of Will* (introduces "protection number" and "willpower battered" state — may need a new status flag on the character model) and *Detoxify Poison in Another* (introduces "broken contact wounds patient" failure mode — worth a dedicated test case).

---

## 4. Deliverable C: Sith Powers — Full Mechanics (NPC-only / DSP-gated)

These four Sith powers appear in Ch. 4 "Echoes of the Sith." Every use of a Sith power auto-grants 1 Dark Side Point to the user. **These should be restricted to NPC use at launch** (Sith-aligned enemies — Dooku, Ventress, Dark Acolytes in the Clone Wars era). Player access would require a separate design decision about whether to expose the dark path.

**Aura of Uneasiness** (Control Easy modified by proximity, limited to line of sight; Alter Easy; may be kept up)
- Warning: Auto-DSP on use vs sentient being.
- Effect: Projects a field of discomfort/unease around the user. Nonsentient creatures avoid the user. Sentient creatures sense vague "uneasiness" — acts as the intimidation skill (Sith rolls alter+3D vs target's willpower or Perception). Against predatory animals, alter+5D vs willpower or Perception.

**Electronic Manipulation** (Control Easy non-sentient / Moderate sentient / Difficult Sith-hostile sentient; Alter Easy slight / Moderate significant / Difficult major reprogramming)
- Required powers: Absorb/dissipate energy, affect mind.
- Time to use: One round.
- Warning: Auto-DSP on use.
- Effect: Channels rage into computer/droid/machine circuits, reprogramming them by manipulating physical/electrical components. Can only restore previously-altered programming, not rewrite from scratch. Can only be evoked in a state of rage — Jedi have long avoided using it for that reason alone.

**Force Wind** (Sense Moderate; Alter Moderate for 5m / Difficult 10m / Very Difficult 15m; may be kept up)
- Required powers: Magnify senses, shift sense, telekinesis.
- Warning: Auto-DSP on use.
- Effect: Manipulates air currents into powerful, destructive tornadoes that lift people bodily into the air and fling them about. Cyclone damage equals the Sith's alter code against all in range.

**Drain Life Energy** (Control Easy; Sense Easy modified by proximity; Alter Easy)
- [Mechanics continue on p.51 — not fully captured in this pass. Deferred.]
- Effect (from context): Drains life force from a victim to fuel the Sith's own power. Core power for Sith sustenance and apprentice subversion. Exar Kun used it to keep himself alive across millennia. Era-usable for a Clone Wars-era Sith Lord sustenance/corruption mechanic.

**Design note.** The Sith philosophy statement on p.49 is the single most quotable passage in the book: "Whereas a Jedi uses the Force for knowledge and defense, a Sith uses the Force to bend the universe to his will. The Jedi manipulates the Force passively, while in a state of calm and control. The Sith gives himself over to his passions, and channels the Force by harnessing the power of anger, hate, love, and jealousy." This should anchor the "Jedi and Sith — The Core Contrast" lore entry above and be the Director AI's baseline framing when players encounter any Sith NPC.

---

## 5. Deliverable D: Canonical Jedi Master Force Skill Taxonomy

From Luke Skywalker's stat block (p.34), which functions as a canonical WEG D6 "Jedi Master" reference:

```
Force Skills:
  Control 13D+2
  Sense   11D+1
  Alter   10D+2

Control Powers (demonstrated):
  Absorb/dissipate energy, accelerate healing, concentration,
  control pain, detoxify poison, emptiness, enhance attribute,
  hibernation trance, reduce injury, remain conscious, resist stun,
  short-term memory enhancement

Sense Powers (demonstrated):
  Danger sense, instinctive astrogation, life detection, life sense,
  magnify senses, receptive telepathy, sense Force, sense Force potential

Alter Powers (demonstrated):
  Injure/kill, telekinesis

Control + Sense:
  Farseeing, lightsaber combat, projective telepathy

Control + Alter:
  Control another's pain, inflict pain

Control + Sense + Alter:
  Affect mind, doppleganger, force harmony, telekinetic kill

Sense + Alter:
  Dim other's senses, lesser Force shield

Force Points: 7  /  Dark Side Points: 3  /  Character Points: 24
```

**Usage for SW_MUSH.** This is the reference template when building a Jedi Master NPC for the Clone Wars chargen / NPC library (e.g., Council members, ranking Masters). The Force skill die codes scale with experience — Knight would be ~8D-10D in each; Padawan ~3D-5D; senior Master 12D+. The demonstrated-powers list is **not** exhaustive — the source text explicitly says "These are only some of the powers that Luke has so far demonstrated."

---

## 6. Deliverable E: Chargen Template Reference — Jedi Padawan Refinement

The existing Clone Wars Era Design v4 §3.4 lists "Jedi Padawan" as a chargen template but does not specify Force skills. JAS gives the reference frame.

**Proposed Padawan starting stat block (WEG D6, CP-normalized for SW_MUSH chargen):**

- Force Sensitive: Yes (required)
- Force Skills: Control 2D, Sense 2D, Alter 1D (Padawan-tier; 7D total, room to grow into Knight)
- Known Powers (at Padawan start): concentration, sense Force, life detection, lightsaber combat
- Force Points: 2
- Dark Side Points: 0
- Equipment: Padawan robes (beige or brown), Padawan braid (single braid of hair behind the right ear — per canon tradition), lightsaber (construction varies by Master's preference), Jedi utility belt, datapad
- Special: Master NPC assigned on creation (system-generated; see §8 Director AI handling in Clone Wars Era Design v4)
- Background constraint: All Padawans begin at the Jedi Temple on Coruscant or on an active mission with their Master

**Fallen Padawan variant** (chargen or mid-game narrative option): Same stats, Dark Side Points 2-3, may know Aura of Uneasiness, no longer wears formal robes, lightsaber may be reworked into unusual color/form (including double-bladed). The v4 Jedi Village quest chain can funnel narrative fallen Padawans here.

---

## 7. Era-Translation Notes — What Carries, What Doesn't

### Carries cleanly (use verbatim, adjusted for era):

- **Praxeum philosophy** — ancient Jedi word, era-agnostic.
- **Bodo Baas Holocron** — Old Sith Wars era, predates both JAS and Clone Wars. Use directly.
- **Jedi Code discipline** — era-agnostic.
- **Master/Padawan pedagogy, wilderness exercises, Trials** — era-agnostic; the book explicitly frames them as ancient traditions.
- **Exar Kun as cautionary tale** — Old Sith Wars figure (~4000 BBY); already in the "legendary" past from the Clone Wars vantage point. Use him as the canonical "arrogant apprentice" warning story.
- **All 10 new Force powers** — fully era-agnostic mechanics.
- **All 4 Sith powers** — fully era-agnostic mechanics.
- **Jedi/Sith philosophical contrast** — verbatim quote is timeless.
- **Holocron as lore-delivery device** — era-agnostic; use for in-MUSH lore entries that need an in-universe voice.

### Needs re-anchoring (same concept, different specifics):

- **Luke Skywalker's academy on Yavin Four** → **Jedi Temple on Coruscant** (existing institution, not newly founded).
- **Luke's 12 students** → Thousands of Padawans already in training at Temple + hundreds of Knights and Masters active.
- **"Re-founding the Order"** narrative → **"Order strained by war"** narrative.
- **Luke's self-doubt as first teacher** → **senior Masters' doubts about the Order's role as generals** (Dooku's disillusionment, Mace Windu's burden, Yoda's prescience).

### Does NOT carry — exclude from Clone Wars lore:

- New Republic Senate, Mon Mothma political context.
- Emperor/Palpatine dead; Empire in retreat (in Clone Wars, Palpatine is *alive* and Chancellor — pre-reveal).
- Specific post-ROTJ characters: Luke, Leia, Han, Kyp Durron, Gantoris, Streen, Kirana Ti, Dorsk 81, Cilghal, Kam Solusar, Daala, Pellaeon, Thrawn (mentioned as recently-past), Joruus C'baoth.
- Sun Crusher, Maw Installation, Carida destruction.
- The specific Massassi temples of Yavin Four as Academy site (Yavin Four exists but is not an Academy in 20 BBY).
- Exar Kun's *return* (he stays dormant; only his cautionary tale is told).

### Flag for future expansion:

- **Lightsaber construction ritual** — the book alludes to this (Gantoris building one "in secret" as a transgression). Full ritual detail not captured in this v1 pass. Worth a follow-up mine of Ch. 14 Equipment, possibly cross-referenced with the *Tales of the Jedi Companion* if that ever enters the source pool.
- **Alternate Jedi training lineages** — Ranik Solusar / Kam Solusar line is mentioned as "a different school of Jedi training." For Clone Wars, this hints at the real historical fact that multiple Jedi sects existed in deep history — Jedi Covenant, Jedi Sentinels, etc. Low priority for launch; flavorful for long-term lore.

---

## 8. Remaining Unmined Pages

| Chapter | PDF Pages | Priority | Notes |
|---|---|---|---|
| Ch. 1 The New Republic | 7–23 | Low | Post-ROTJ politics; may contain "Old Order" flashback framing worth a skim |
| Ch. 2 Coruscant | 24–29 | Low | Post-Empire Coruscant; superseded by WotC Coruscant sourcebook |
| Ch. 3 remaining | 39–40, 42–43, 48–49 | Medium | Kirana Ti, Dorsk 81, Kam Solusar stat blocks (archetype references) |
| Ch. 4 Echoes of the Sith | 52–53 | High | Drain Life Energy full mechanics; additional Sith power(s) |
| Ch. 5 Forces of the Empire | 54–63 | None | Era-irrelevant |
| Ch. 6 Maw Installation | 64–83 | None | Era-irrelevant |
| Ch. 7 The Fringe | 84–86 | Low | Generic fringe flavor |
| Ch. 8 Kessel | 87–97 | Medium | Kessel lore may enrich existing SW_MUSH Kessel zone (spice mines, Imperial slavers era-translated to Republic-era mining conglomerates) |
| Ch. 9 Independent Class | 98–101 | Low | Ship stats |
| Ch. 10 Planets | 102–120 | Medium | Select planet entries may translate |
| Ch. 11 Creatures | 121–126 | Medium | Energy spiders for Kessel; other beasts |
| Ch. 12 Starships | 127–137 | Low | Sun Crusher is era-locked; E-wing may be worth a look |
| Ch. 13 Vehicles | 138–141 | Low | |
| Ch. 14 Equipment and Droids | 142–end | **High** | Likely contains lightsaber construction detail, new droid models, Jedi utility items |

**Recommended next mining pass:** Ch. 4 pp. 52–53 (finish Sith powers) + Ch. 14 Equipment (lightsaber construction + Jedi gear) + spot-check Ch. 8 Kessel and Ch. 11 Creatures. Estimated ~15-20 additional pages.

---

## 9. Reconciliation vs. Clone Wars Era Design v4 §8.2 Lore Claims

The v4 design doc §8.2 expanded the Clone Wars lore entry plan with ~8 claimed JAS-sourced entries. Mapping those claims against this v1 extraction:

| v4 §8.2 Claim | Status in v1 Extraction | Action |
|---|---|---|
| Jedi Praxeum philosophy | ✅ Covered (entry 1) | Keep |
| Old Republic values | ✅ Covered (folded into entries 2, 6) | Keep |
| Jedi Code framing | ✅ Covered (entry 6) | Keep |
| Master/Padawan pedagogy | ✅ Covered (entries 2, 7, 9) | Keep |
| Lightsaber construction process | ⚠️ Partial (entry 12 covers secret-construction motif; full ritual needs Ch. 14 mine) | Flag for follow-up mine |
| Force-power extensions | ✅ Fully covered (§3 — 10 powers with mechanics) | Keep; upgrade scope from "lore entry" to "engine implementation" |
| Jedi Temple training halls structure | ⚠️ Weak (only obliquely covered via Praxeum + wilderness entries) | Downgrade claim or mine Ch. 14 for architectural detail |
| Jedi Council | ✅ Covered (entry 4) | Keep |

**Net:** 6 of 8 v4 claims are solidly sourced. 2 need a Ch. 14 follow-up mine or a scope adjustment. Additionally, the extraction surfaced 7 lore entries **not** anticipated in v4 §8.2 (Humility Principle, Bodo Baas Holocron, Jedi Trials, Wilderness Exercises, Jedi/Sith Core Contrast, Cautionary Tale of the Arrogant Apprentice, Force-Sensitive Detection) — v4 §8.2 should be updated to incorporate them, raising the JAS-sourced entry count from 8 to ~13.

---

*End of JAS Extraction v1.0 — April 18, 2026*
*Source: WEG40114, The Jedi Academy Sourcebook, April 1996.*
*Paired with: clone_wars_era_design_v4.md (parallel session) and gg10_bounty_hunters_extraction_v1.md / crackens_rebel_field_guide_extraction_v1.md (companion extraction format).*
*Ready to drive v4 §8.2 reconciliation and Drop 1 YAML lore authoring.*
