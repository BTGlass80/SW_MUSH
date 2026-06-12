# SW_MUSH — Tales of the Jedi Companion Extraction
## Version 1.0 — April 18, 2026
### Source: WEG40082 — Tales of the Jedi Companion (George R. Strayton, November 1996, 177 pages, scanned JPEG)

---

## 1. Book Identity & Mining Assessment

**Source confirmed.** WEG40082, *Tales of the Jedi Companion*, by George R. Strayton. West End Games, first printing November 1996. 177 pages. Image-based scan.

**Era note.** Companion to the *Tales of the Jedi* and *Freedon Nadd Uprising* Dark Horse Comics series, set ~4000 BBY — the Old Sith Wars era. Characters include Ulic Qel-Droma, Nomi Sunrider, Exar Kun, Freedon Nadd, Master Arca Jeth, Thon.

**Value for Clone Wars pivot:**
- **Ch.3 Jedi Powers** — the most comprehensive WEG D6 Force power index ever published (complete summary table on p.42-43), including 15+ powers not found in JAS. Full mechanics for Battle Meditation, Life Bond, Force Lightning, Force Harmony, Create Force Storms, Doppleganger, Drain Life Essence, Transfer Life.
- **Ch.5 Sith Powers** — new Sith power mechanics: Bolt of Hatred, Dark Side Web, Waves of Darkness. Plus Sith Holocron lore and crystal mechanics that cross-validate JAS lightsaber construction framing.
- **Ch.10 Technology** — lightsaber stat block (p.125): Unavailable for sale, Avail 4,X, Skill: Lightsaber, Difficulty: Difficult, Damage: Varies (avg 5D), game note re self-injury on miss by 10+.
- **Ch.2 Characters** — Adegan crystals named as "the best gems for constructing lightsabers" (p.18). No construction ritual rule — confirmed absent. The construction is narrative, not procedural in WEG D6.
- **Era-agnostic applicability** — all powers and lore are fully era-agnostic; the Old Republic framing predates both Clone Wars and GCW.

**Pages mined:** Ch.2 pp.17-34 (characters, Adegan crystal mention), Ch.3 pp.36-65 (Jedi Powers), Ch.5 pp.77-92 (Sith Powers), Ch.10 pp.121-127 (Technology).

---

## 2. Deliverable A: New Jedi Powers (Ch.3)

### 2.1 Complete Power Summary Table (from p.42-43)

The book contains a "Jedi Powers Summary" listing **all WEG D6 Force powers published up to November 1996**. This is the canonical master list.

**Control powers:** Absorb/Dissipate Energy, Accelerate Healing, Concentration, Contort/Escape, Control Disease, Control Pain, Detoxify Poison, Emptiness, Enhance Attribute, Force of Will, Hibernation Trance, Instinctive Astrogation (Control), Rage, Reduce Injury, Remain Conscious, Remove Fatigue, Resist Stun, Short-Term Memory Enhancement.

**Sense powers:** Beast Languages, Combat Sense, Danger Sense, Instinctive Astrogation (Sense), Life Detection, Life Sense, Life Web, Magnify Senses, Postcognition, Predict Natural Disaster, Receptive Telepathy, Sense Force, Sense Force Potential, Sense Path, Shift Sense, Translation, Weather Sense.

**Alter powers:** Injure/Kill, Telekinesis.

**Control and Sense:** Farseeing, Life Bond, Lightsaber Combat, Projective Telepathy.

**Control and Alter:** Accelerate Another's Healing, Control Another's Disease, Control Another's Pain, Control Breathing, Detoxify Poison in Another, Feed on Dark Side, Force Lightning, Inflict Pain, Place Another in Hibernation Trance, Remove Another's Fatigue, Return Another to Consciousness, Transfer Force.

**Control, Sense, and Alter:** Affect Mind, Battle Meditation, Control Mind, Create Force Storms, Doppleganger, Drain Life Essence, Enhanced Coordination, Force Harmony, Projected Fighting, Telekinetic Kill, Transfer Life.

**Sense and Alter:** Dim Other's Senses, Lesser Force Shield.

---

### 2.2 Powers New to This Source (not in JAS extraction)

**LIFE BOND** (Control Moderate / Sense Moderate, modified by proximity; keep-up)
- Required Powers: Life detection, life sense, magnify senses, receptive telepathy
- Effect: Permanently forms a mental link with one other individual (usually mate, sibling, parent/child, or very close friend). Both must agree. Takes 1D weeks to form. Benefits active only while both use the power.
  - Easy sense roll: aware of other's general location and emotional state (frightened, in pain, happy, etc.)
  - Moderate sense roll: see/hear/smell/taste/feel what other senses; share pain — if one is injured, other suffers an injury level lower.
  - Difficult sense roll: telepathic link; surface thoughts readable if willing.
  - Very Difficult sense roll: full telepathic conversation.
- Severing: only by death of one partner. Survivor enters near-catatonic shock of 1D days; all die codes reduced by -1D for same time it took to form the bond.
- Death of partner: survivor grieves, all die codes -1D for duration.
- Cannot share skills, attributes, Force Points, or Character Points.
- Dark side actions by one partner give the other DSP too.
- Life bonding is a serious commitment; forming a second bond takes 2D weeks; a third, 3D weeks; and so on.
- **SW_MUSH application:** This is the mechanical backbone for the Padawan-Master bond system. The bond gives the Master awareness of the Padawan's emotional state and Weight of War condition, which cross-references `padawan_master_system_design_v1.md` §5.1 `+forcebond` command. The "injury propagation" mechanic (partner suffers level lower) should be implemented as a narrative effect rather than literal mechanical damage propagation — too harsh for MUSH balance.

**LIGHTSABER COMBAT** (Control Moderate / Sense Easy; keep-up)
- Effect: To use a lightsaber most effectively, a Jedi learns this power. Adds *sense* dice to lightsaber skill roll when trying to hit or parry; adds/subtracts up to the number of *control* dice to the lightsaber's 5D damage when it hits. Players must declare how many control dice they are adding/subtracting before the roll.
- If Jedi fails the power roll: must use lightsaber with only lightsaber skill, normal 5D damage, cannot attempt the power again for the duration of combat.
- Can be used to parry blaster bolts (declare parrying at start of round, use lightsaber skill as normal).
- Can attempt to control where deflected bolts go (additional action penalty applies).
- **SW_MUSH application:** Already partially implemented in `engine/force_powers.py`. This is the canonical full mechanics. The "declare control dice before roll" element adds interesting decision-making; implement as a modifier input at power activation.

**BATTLE MEDITATION** (Control Special / Sense Special / Alter Special; keep-up, 5 min activation)
- Sense Difficulty: Based on number of targets affected — Very Easy (1–2), Easy (3–20), Moderate (21–100), Difficult (101–1000), Very Difficult (1001–10,000), Heroic (10,001+).
- Alter Difficulty: Based on number of individuals — same scale as Sense.
- Effect: Two possible effects (Jedi declares which):
  1. Force adversaries to abandon assault and turn on each other.
  2. Alter the tide of battle: enemies lose 1D per every 4D in Jedi's best Force skill (to minimum 1D), allies receive equal bonus to an attribute of the Jedi's choosing. The Jedi must maintain; once dropped, effects wear off instantly.
- The Jedi picks 3 specific skills for allies (must be Dexterity, Technical, or Strength skills). For every 3D those allies have in those skills, they receive +1D bonus.
- **Nomi Sunrider's signature power.** The exemplar NPC use is: control 1D+1, sense 2D+1, alter 1D — affecting a dozen Sith minions, giving allies +2D+1 Dexterity bonus while enemies suffer -2D+1 Strength penalty.
- **SW_MUSH application:** High-level Clone Wars general power. Perfect for the "Jedi general commanding a battle" archetype. Could be implemented as a zone-wide buff/debuff during major conflict events rather than individual combat. For the Director AI, Battle Meditation events could be announced as zone-wide narrative effects.

**FORCE HARMONY** (Control Difficult / Sense Difficult, modified by relationship / Alter Moderate; keep-up)
- Required Powers: Life detection, life sense, projective telepathy, receptive telepathy
- Effect: Links several willing Jedi to manifest the power of the light side. Creates a 5D shield against dark-side powers for all linked Force-users. For every Force-user involved (up to max = control or sense dice, whichever is lower), +5D resistance vs dark-side powers. The Jedi calling the power suffers a 2D penalty to all actions. Can interrupt dark-side powers mid-use — if both shields exceed dark-side power's success roll, the power is interrupted. Cannot cancel presence of dark side, but can make dark-side servants' actions harder.
- **SW_MUSH application:** Multi-PC cooperative power for the Jedi faction. Implementation: `+forceharmony` command that creates a party-wide Force Shield buff. Requires all participants to have Life Bond or at minimum a Force connection. Rare, high-story-value use.

**FORCE LIGHTNING** (Control Difficult, modified by proximity, limited to line of sight / Alter: target's Perception or control roll)
- Warning: Auto-DSP on any use.
- Effect: Bolts of white or blue energy fly from fingertips. Force-generated, so can be Force-repelled (dissipate energy). Courses over and into target, convulsing with pain, siphoning power, eventually killing. Armor does not protect. Damage: 1D per 2D of alter skill (round down); e.g., alter 5D = 2D damage.
- **SW_MUSH application:** NPC-only at launch (Count Dooku, Sidious). Same DSP-gating as JAS Sith powers. Auto-DSP means even Jedi who use it fall. The Bolt of Hatred (TOTJ Ch.5) is a distinct power.

**INFLICT PAIN** (Control Very Easy, modified by proximity / Alter: target's control or Perception, modified by proximity)
- Required Power: Control pain, life sense
- Warning: Auto-DSP.
- Effect: Target experiences great agony. User rolls alter vs target's control/Perception/willpower for damage as stun; if target takes any damage at all they are so crippled by pain they cannot act for the round and the next round.

**FEED ON DARK SIDE** (Control Moderate when activated, Very Easy each round thereafter / Alter Moderate when raised, no roll thereafter; keep-up)
- Required Power: Sense Force
- Warning: Auto-DSP on activation.
- Effect: Allows a Jedi to feed on the fear, hatred, or negative emotions of others to make themselves more powerful. In any round where a light-side Force-sensitive gains a Dark Side Point, the user gains a Force Point. If multiple characters gain DSP in the same round, user gains multiple FP. FP must be spent within 5 minutes.
- **SW_MUSH application:** The power that feeds the dark spiral. A Jedi who activates this is one step from falling. Makes a great dramatic mechanic — using it guarantees DSP but grants power if the battle is going dark for allies.

**CONTROL BREATHING** (Control Moderate / Alter Very Difficult; keep-up)
- Required Powers: Concentration, hibernation trance, telekinesis
- Effect: Controls amount of oxygen flowing into the body; pulls oxygen molecules through skin into lungs. Can breathe underwater; water-breather can survive on land. In space/vacuum: power would be of little use (not enough oxygen to grab). Remains up until character takes incapacitating damage or willfully drops it.

**PLACE ANOTHER IN HIBERNATION TRANCE** (Control Very Easy / Alter Very Easy, modified by relationship and proximity)
- Required Power: Hibernation trance
- Time to use: 5 minutes
- Effect: Places another character into hibernation trance. Must be in physical contact and target must agree ("shut down" — cannot be used as attack). Can also bring a character OUT of hibernation trance, but alter difficulty increases by +10.

**RETURN ANOTHER TO CONSCIOUSNESS** (Control Easy / Alter Easy for incapacitated; Difficult for mortally wounded; modified by proximity and relationship)
- Required Power: Remain conscious
- Effect: Returns target to consciousness; same restrictions as *remain conscious*.

**TRANSFER FORCE** (Control Easy, modified by relationship / Alter Moderate; modified by proximity)
- Required Power: Control another's pain
- Time to use: 1 minute
- Effect: Saves a mortally wounded character from dying by transferring the Jedi's own life force to the target. Character receiving remains mortally wounded but will not die provided not injured again; enters Force-sustained state for up to 6 weeks. User must spend a Force Point (the life force being transferred). Considered heroic, so the FP returns at session end. Recipient must be willing.

**CONTROL ANOTHER'S DISEASE** (Control Very Easy / Alter: Special, based on disease severity)
- Effect: Works same as *control disease* on the target rather than the user.

**REMOVE ANOTHER'S FATIGUE** (Control Easy / Alter Moderate, modified by proximity and relationship)
- Required Powers: Accelerate healing, accelerate another's healing, control pain, control another's pain, remove fatigue
- Effect: Removes fatigue effects from another. Must wait until target is actually fatigued before offering assistance.

**CREATE FORCE STORMS** (Control Heroic / Sense Heroic / Alter Heroic, modified by proximity, +5 per 100m, +10 per km, +2 per additional km of diameter, +5 per 1D of damage; keep-up requires Heroic rolls each round)
- Required Powers: Hibernation trance, life detection, life sense, magnify senses, receptive telepathy, sense Force, telekinesis, farseeing, projective telepathy, instinctive astrogation, rage
- Warning: Auto-DSP. Very Difficult to dissipate.
- Effect: Perhaps the single most destructive Force power known. Twists the space-time continuum to create vast storms of Force. Can create annihilating vortices capable of swallowing whole fleets or tearing surfaces off worlds. Use requires focusing of hate and anger to an almost palpable degree. Those who fail to control the storm are often consumed by it.
- **SW_MUSH note:** NPC-only, narrative/Director AI use only. No player should ever access this. Represents Exar Kun / Darth Sidious tier power.

**DOPPLEGANGER** (Control Very Difficult / Sense Very Difficult / Alter Heroic; keep-up, 5 min activation)
- Required Powers: Control pain, emptiness, life detection, life sense, magnify senses, receptive telepathy, sense Force, telekinesis, projective telepathy, control another's pain, transfer Force, affect mind, dim other's senses
- Warning: Auto-DSP.
- Effect: Creates an illusory doppleganger of the Force-user. Those interacting with it sense all normal senses through the doppleganger; registers as normal on droid audio/video sensors. Acts with half the skill dice of the person using the power. Must re-roll every 5 minutes; if the Jedi is fatally injured, the doppleganger simply fades.

**DRAIN LIFE ESSENCE** (Control Very Difficult, inversely modified by relationship / Sense: see chart / Alter Easy; keep-up)
- Sense Difficulty by number of victims: Very Easy (1-5), Easy (6-50), Moderate (51-1000), Difficult (1001-50,000), Very Difficult (50,001-1 million), Heroic (1 million to 10 million).
- Alter Difficulty: Easy for willing/worshipful; Difficult for ambivalent; Heroic for enemies; +10 if imbued with light side.
- Required Powers: Control pain, hibernation trance, life detection, life sense, magnify senses, receptive telepathy, sense Force, telekinesis, farseeing, projective telepathy, control another's pain, transfer Force, affect mind, control mind, dim other's senses
- Warning: Auto-DSP.
- Effect: Draws life energy from those around the user and channels the negative effects of the dark side into those victims. The user draws FP from surrounding beings; all living things are part of and contribute to the Force. Power must be rolled once per day; kept up at all times; user suffers appropriate die penalties.
  - For individuals drained <1 week and >1 month: 1-5 victims = 1 FP/week; 6-50 = 1 FP/5 days; 51-1000 = 1 FP/3 days; etc.
  - For individuals drained >1 week but <1 month: same scale but faster FP accrual.

**ENHANCED COORDINATION** (Control Moderate / Sense Difficult / Alter by number of individuals; keep-up)
- Effect: Coordinates activities of a group to increase their effectiveness at a given task. Links troops on a subconscious level; they fight more proficiently with better organization. Jedi picks 3 specific skills (must be Dexterity, Technical, or Strength). For every 3D those troops have in those skills, they receive +1D bonus. Originally used by the Emperor to drive clone troopers; also usable by any Jedi general for clone army coordination.
- Jedi can only affect Dexterity, Technical, and Strength skills.

**PROJECTED FIGHTING** (Control Difficult / Sense Difficult / Alter Moderate, modified by proximity; target must be in line of sight)
- Required Powers: Concentration, telekinesis
- Effect: Allows a Jedi to strike at an opponent without physically touching them. More than risky: using projected fighting to cause serious rather than stun damage auto-grants a DSP.

**TELEKINETIC KILL** (Control Easy / Sense Easy / Alter: target's control or Perception; modified by proximity and proximity)
- Required Powers: Control pain, inflict pain, injure/kill, life sense
- Warning: Auto-DSP.
- Effect: Telekinetically injures or kills a target. When user's alter roll exceeds target's control/Perception, determine damage. Exact method varies: collapse the trachea, stir the brain, squeeze the heart, etc.

**TRANSFER LIFE** (Control Heroic, modified by relationship, +15 if unwilling / Sense Heroic, modified by proximity, +15 if unwilling / Alter: variable by willingness and Force affinity)
- Required Powers (the longest list in WEG D6): Absorb/dissipate energy, accelerate healing, control pain, detoxify poison, emptiness, hibernation trance, reduce injury, remain conscious, resist stun, life detection, life sense, magnify senses, receptive telepathy, sense Force, injure/kill, telekinesis, farseeing, projective telepathy, accelerate another's healing, control another's pain, feed on dark side, inflict pain, return another to consciousness, transfer Force, affect mind, control another to consciousness [sic], control mind, dim other's senses
- Warning: 2 DSP for willing host; 4 DSP for unwilling host.
- Effect: Transfers the user's life energy into another body — the key to immortality. To overcome a spirit already residing in a body is nearly impossible; nearly useless without a prepared clone host body. If the user's body fails, their life energy is lost, dispersed to the void.
- **SW_MUSH application:** This is Exar Kun's mechanism (and Palpatine's). NPC-only. Could be used as a Director AI narrative event trigger: a discovered Sith spirit trying to possess a PC.

**LESSER FORCE SHIELD** (Sense Easy / Alter Moderate; keep-up) — already in game from other sources.

**DIM OTHER'S SENSES** (Sense Easy, modified by proximity / Alter: target's control or Perception; keep-up) — cross-validated with JAS v1.1 entry. TOTJ version confirms: alter margin determines reduction (-1 pip at 0-5, -2 pips at 6-10, -1D at 11-15, -2D at 16-20, -3D at 21+). Can affect multiple targets simultaneously with +3 to sense difficulty per additional target.

---

## 3. Deliverable B: New Sith Powers (Ch.5)

### Ch.5 Sith Philosophy Summary

**The Essence of the Sith (p.78-79):** The Sith existed for over 100,000 years. They organized in tribal "circles" led by one or more sorcerers, not as a unified order. A fallen Jedi dominated them, became the first Dark Lord of the Sith lineage. After the Fall of the Sith Empire, some escaped to remote worlds with dark knowledge. Only recently (from the Clone Wars vantage at ~4000 BBY ago) have these caches been rediscovered.

**Sith Disciplines taxonomy (p.83-84):** General, Body, Energy, Illusions, Mind, Mechanical, Protection, Transference. Most mechanical and some transference powers are lost. This is why powers have disappeared over millennia.

**Sith Holocrons (p.79-80):** Made from rare crystalline components found on only a few remote worlds. Crystals form a latticework that can absorb and reproduce light and sound — the **same fundamental crystal principle** as lightsaber construction. Each Holocron focuses on one Sith discipline (the creator's specialization). Finding one with all Sith powers is impossible by design.

**Sith Talismans:** Three categories — Healing (heals one wound level per die of Force skill sacrificed for 10 hours), Ensnarement (traps light-siders in cumulative willpower check spiral), Shield (absorbs 1D/2D/3D versions, must be recharged weekly). Swords of the Sith: alchemically reinforced, parry lightsabers, STR+2D damage, auto-lose FP and gain DSP on use.

### New Sith Power Mechanics:

**BOLT OF HATRED** (Alter Moderate; single-use, no keep-up)
- Warning: Auto-DSP.
- Effect: Creates a radiant sphere of pure hatred in the user's hand; hurled at any target within line of sight. Alter roll launches it; target hit for 6D damage AND automatically loses 1 Character Point.

**DARK SIDE WEB** (Alter Difficult; keep-up)
- Warning: Auto-DSP.
- Effect: Summons strands of dark-side power that wrap around the target in a mesh of brilliance. Severs the target's connection to the Force. Target loses Force skill dice equal to the user's alter dice (e.g., alter 6D = lose 6D from Force skills total, distributed across control/sense/alter as user chooses, minimum 1D per skill reduced). Can include Strength in the reduction if the user desires. While the power is kept up the reduction persists.

**WAVES OF DARKNESS** (Control Moderate–Heroic by area / Alter Moderate–Heroic by area; keep-up)
- Area/Difficulty table: 1-2 meters Moderate, 3-10 meters Difficult, 11-20 meters Very Difficult, 21-30 meters Heroic.
- Warning: Auto-DSP.
- Effect: User delves into their own spirit and dredges up feelings of hatred, jealousy, greed, and rage — expels these vile emotions outward in an expanding sphere. Anyone caught in the area must make willpower or control roll against the user's control total; failure means they cannot take their next action (this round or the next) and must flee on the successive round. Those who succeed become confused — one action maximum per combat round until they exit the field of dark side energy.

### Previously-captured Sith powers cross-validated:
- **Aura of Uneasiness** (p.88) — matches JAS v1.1 exactly.
- **Electronic Manipulation** (p.88) — matches JAS v1.1 exactly.
- **Force Wind** (p.89) — matches JAS v1.1 exactly.
- **Drain Life Energy** (p.89) — matches JAS v1.1 exactly (nonsentient-only, keep-up, fatigue prevention).
- **Memory Wipe** (p.89) — matches JAS v1.1 exactly.

---

## 4. Deliverable C: Lightsaber Construction — Definitive Finding

**Adegan crystals (p.18):** Named as "the best gems for constructing lightsabers." Master Chamma gave Andur Sunrider "several Adegan crystals — the best gems for constructing lightsabers — to present as a gift to his new Master, Thon."

**Sith Holocron crystal mechanics (Ch.5, p.79-80):** Holocrons have "special organic crystalline components, a rare commodity found only on a few remote worlds… When arranged properly, these crystals form a latticework of energy that can both absorb and later reproduce light and sound wave information." This is the same principle as lightsaber construction — crystals channel and focus energy.

**Lightsaber stat block (Ch.10, p.125):**
```
LIGHTSABER
Type: Custom-made melee weapon
Scale: Character
Skill: Lightsaber
Cost: Unavailable for sale
Availability: 4, X
Difficulty: Difficult
Damage: Varies (average 5D)
Game Notes: If an attacking character misses the difficulty
number by more than 10 points (the base difficulty; not an
opponent's parry total), the character has injured himself
on the lightsaber blade. The wielding character sustains
normal damage.
```

**Conclusion on construction ritual:** There is **no discrete "build your lightsaber" game mechanic** in WEG D6. Construction is a narrative event — a Jedi obtains Adegan crystals, crafts the hilt (Technical skill, Moderate difficulty per GM discretion), and the result is a custom weapon with the stat block above. The JAS "secret construction" framing (Gantoris building one in secret as a transgression) is narrative, not mechanical. For SW_MUSH, the Jedi Village quest chain should include a construction scene as a narrative milestone, not a crafting system roll. The Director AI describes the construction; the reward is the weapon entry in the character's inventory.

---

## 5. Deliverable D: Lore Entries for engine/world_lore.py

Three new lore entries ready to add to `SEED_ENTRIES`:

```python
{
    "title": "The Life Bond",
    "keywords": "life bond,jedi,master,padawan,force,link,telepathy,bond,connection",
    "content": "The Life Bond is one of the most profound and perilous commitments a Jedi can make. Through deep meditation and mutual consent, two Force-sensitives can permanently link their minds and their life forces. Bonded pairs are aware of each other's location and emotional state across any distance, and can sense each other's injuries as if they were their own. Masters and Padawans sometimes form such bonds, though the Order's teachers warn that the bond is not to be taken lightly — when one half of a life bond dies, the survivor enters a state of grief so profound it echoes in the Force itself. A life bond cannot be severed while both parties live.",
    "category": "jedi",
    "priority": 8,
},
{
    "title": "Battle Meditation",
    "keywords": "battle meditation,jedi,war,army,force,nomi sunrider,general",
    "content": "Battle Meditation is among the rarest and most powerful abilities in the Jedi Order's arsenal — and among the most troubling. A Jedi who has mastered this power can extend her awareness across an entire battlefield, strengthening the resolve and coordination of her allies while sowing confusion and doubt among her enemies. Nomi Sunrider was perhaps the most gifted practitioner of her age, capable of turning the tide of engagements involving thousands of combatants. In the Clone Wars, Jedi generals commanding clone armies sometimes employ this power in desperate moments. The Council debates whether doing so makes the Order complicit in the war in ways that will take generations to undo.",
    "category": "jedi",
    "priority": 7,
},
{
    "title": "The Adegan Crystal",
    "keywords": "adegan crystal,lightsaber,kyber,jedi,construction,force,crystal,weapon",
    "content": "The Adegan crystal — sometimes called a kyber crystal in archaic Jedi texts — is the heart of every lightsaber. Found on only a handful of remote worlds, these rare gems possess a natural affinity for the Force that makes them ideal focusing elements for the blade. When arranged within the lightsaber's internal lattice, an Adegan crystal channels and focuses the weapon's energy field into the distinctive blade. Jedi Masters traditionally present Adegan crystals to their Padawans when the time comes to construct their first lightsaber — the quality of the crystal shapes the weapon's character, and finding one's crystal is considered a formative act of self-discovery.",
    "category": "jedi",
    "priority": 8,
},
```

---

## 6. Remaining Unmined Pages

| Chapter | Pages | Priority | Notes |
|---|---|---|---|
| Ch.1 Era of Conflict | 7-15 | Medium | Old Sith Wars history; Freedon Nadd backstory. Lore for Jedi Village "ancient darkness" framing. |
| Ch.4 The Sith Reborn | 66-76 | Medium | Exar Kun, Ulic Qel-Droma's fall. Direct cautionary tale content for Jedi lore entries. |
| Ch.6 Neutrals | 93-99 | Low | Fringe characters; limited Clone Wars relevance. |
| Ch.7 Species | 100-104 | Low | Nazzri, Gotal (already in game), others. |
| Ch.8 Creatures | 105-109 | Low | Era-specific fauna; skip for now. |
| Ch.9 Vehicles | 110-119 | Low | Old Republic vehicles; era-locked. |
| Ch.11 Sites | 128-135 | **High** | Ossus, Onderon, Ambria, Krayiss Two, Dxun. Direct Jedi Village / dark-side-site lore. |
| Ch.12 Running a Campaign | 136-146 | **High** | Jedi Village quest chain design fuel. "Destroying a Sith Talisman," "Running a Tales of the Jedi Campaign," encounter tables. |
| Ch.13 Solitaire Adventure | 147-169 | Medium | "Ruins of Kabus-Dabeh" — may contain Sith ruin room descriptions useful for Village zone. |
| Ch.14 Character Templates | 170-177 | Medium | Old Republic Jedi templates; era-translate to Clone Wars Padawan starting stat reference. |

**Recommended next mining pass (before Drop 10 Jedi Village):** Ch.11 Sites + Ch.12 Running a Campaign. These are the fuel for the Village quest chain's tone and structure. Not needed before Drop 2.

---

*End of TOTJ Extraction v1.0 — April 18, 2026*
*Source: WEG40082, Tales of the Jedi Companion, November 1996.*
*Paired with: jas_extraction_v1.md + v1.1_appendix.md, clone_wars_era_design_v3.md, padawan_master_system_design_v1.md.*
*Life Bond mechanics directly inform padawan_master_system_design_v1.md §4-5.*
*Ready to drive Drop 2 YAML authoring (Coruscant chapter sourced from WotC Coruscant book).*
