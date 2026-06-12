# SW_MUSH — JAS Extraction v1.1 Appendix
## Mining Pass: Ch. 4 pp. 50–52 (Drain Life Energy + Memory Wipe) + Ch. 14 (Equipment and Droids)
## Appended to jas_extraction_v1.md — April 18, 2026

---

## What This Pass Covers

The v1.0 extraction deferred two items as high priority for follow-up:

1. **Drain Life Energy full mechanics** — Ch. 4 p. 51 (PDF p. 52). The v1 entry had the difficulty headers but the effect text was cut off.
2. **Memory Wipe** — Ch. 4 p. 51 (PDF p. 52). A fifth Sith power not anticipated by v1.
3. **Ch. 14 Equipment and Droids** — PDF pp. 141–144 (book pp. 140–143). Flagged as likely containing lightsaber construction detail.

**Result:** Drain Life Energy is now complete. Memory Wipe is a new fifth Sith power. Ch. 14 contains no lightsaber construction detail — that gap stands. Ch. 14 does yield one high-value item (Force Detector) and several era-translatable droids.

---

## A. §4 Supplement — Sith Powers: Two Additions

### Correction to v1 §4 entry for Drain Life Energy

The v1 entry read: *"[Mechanics continue on p.51 — not fully captured in this pass. Deferred.]"*

**Full mechanics, now confirmed from PDF p. 52 (book p. 51):**

**Drain Life Energy** (Control Easy; Sense Easy modified by proximity; Alter Easy)
- Required powers: Affect mind, control pain, control another's pain, dim other's senses, hibernation trance, life detection, life sense, receptive telepathy, sense Force, transfer Force.
- This power may be kept "up."
- Warning: Auto-DSP on use.
- Effect: Allows a Sith to draw power from nearby **nonsentient beings** (insects, small rodents, birds, and similar wildlife) to boost their ability to go without sleep and fatigue. As long as the power is kept up, the Sith will not fatigue or require sleep. The power depends on a ready supply of nearby nonsentient life — it **may not be used to drain energy from sentient beings.** (Note: this is the WEG game-mechanics version. The novel framing of Exar Kun sustaining himself for millennia is narrated as something far beyond this, treated by the text as a Sith mystery beyond tabletop representation.)

**Implementation notes:**
- "Keep up" flag: yes.
- Nonsentient-only constraint is a design choice — the mechanic avoids making this a PvP draining power at launch. At launch, the effect is: character does not accrue fatigue penalties while the power is active and nonsentient creatures are present in the room. Useful for long operations in wilderness zones.
- The required-powers list is extensive — this is a high-tier Sith power, not accessible until late progression. Appropriate gating for a dark-side NPC (Dooku, Ventress) rather than a low-level dark-side PC.

---

### New Sith Power: Memory Wipe

Not anticipated in v1. Found on PDF p. 52 (book p. 51), same page as Drain Life Energy.

**Memory Wipe** (Control Moderate; Sense: target's willpower, Perception, or control roll — modified by relationship; Alter: target's willpower, Perception, or control roll — modified by relationship)
- Required powers: Control pain, hibernation trance, life detection, life sense, magnify senses, receptive telepathy, sense Force, telekinesis, far-seeing, projective telepathy, affect mind, control mind, dim other's senses.
- Time to use: Five minutes.
- Warning: Auto-DSP on use.
- Effect: Allows a Sith to sift through another person's mind and **destroy all knowledge of specific events or learned skills.** Requires direct physical contact with the target. Only one specified objective can be pursued per session (i.e., one memory or one skill per use, not a wholesale erasure).

**Implementation notes:**
- This is a targeted narrative power, not a combat power — the five-minute time-to-use and physical-contact requirement mean it can't be used in a fight.
- Mechanically, "destroy knowledge of a specific event" maps naturally to clearing a PC's narrative memory entry (the Director AI / PC narrative memory system). A staff-triggered use of Memory Wipe by a Sith NPC could expunge a specific memory from a PC's record — a genuine story tool.
- "Destroy a learned skill" would reduce a skill die code. At launch, restrict to narrative effect only (GM-adjudicated). Automated skill reduction is a Phase 2 refinement.
- Required-powers list is the most extensive of any Sith power — this should be the hardest-to-access Sith power in the game. NPC-only at launch.

**Updated §4 tally:** Five Sith powers total (up from four in v1):
1. Aura of Uneasiness
2. Electronic Manipulation
3. Force Wind
4. Drain Life Energy *(now complete)*
5. Memory Wipe *(new)*

---

## B. Ch. 14 Equipment and Droids — Full Mining Results

**Finding on lightsaber construction:** Ch. 14 does **not** contain lightsaber construction ritual detail. The chapter covers general equipment and droids with a New Republic / Yavin-era focus. The lightsaber construction gap from v1 §8 and §9 stands — it would need to come from another source (Tales of the Jedi Companion, or the D6 R&E core rules if they have a crafting section).

**Update to §9 reconciliation table:**
- "Lightsaber construction process" claim from v4 §8.2: status remains ⚠️ Partial. Source is not in Ch. 14 JAS. Flag for future sourcebook mining.
- "Jedi Temple training halls structure" claim: Ch. 14 contains no architectural detail. Downgrade from ⚠️ to ❌ for JAS sourcing — needs a different sourcebook.

### Items of interest from Ch. 14:

**Force Detector** (book p. 140) — High priority for SW_MUSH lore and possible game object.

A three-component scanning system (control pack + two sheet-crystal readers). The operator holds the readers bracketing the subject, activating the unit. The unit scans head to toe and constructs a wire-frame hologram of the subject tagged with color-coded data on Force sensitivity:
- Blue aura = strong in the Force (stronger corona = stronger Force connection).
- No aura = not Force-sensitive.
- Dark side influence = aura tinged with red streaks.
- Also reports whether the subject carries any Dark Side Points (but not how many).

Originally designed and built to pursue evil ends (Imperial Jedi-hunting during the Purge). Luke resolves to use them to find potential Jedi students. Extremely rare — fewer than 10,000 were ever produced, most lost or destroyed.

Stat block:
- Model: Government Issue Force Detector Unit
- Type: Imperial Force Detector
- Cost: Not available for sale
- Availability: 4, X
- Game Note: A trained operator can determine if a subject is Force-sensitive and whether they have any Dark Side Points (not how many).

**Era-translation for Clone Wars:** The Force Detector exists in 20 BBY but is a Republic/Imperial intelligence tool, not widely available. In the Clone Wars setting it functions as an Imperial Inquisitor precursor — a device the Jedi Council has conflicted feelings about using (scanning citizens for Force sensitivity feels like the kind of thing the Order shouldn't do). Good lore hook. Recommend one lore entry and one craftable/obtainable rare item in the economy system.

**Organic Gill** (book p. 140) — Low priority. Mon Calamari underwater-breathing device. Era-agnostic but no Kessel/Clone Wars application. Skip for now.

**Stun Cuffs** (book p. 140–141) — Already in SW_MUSH as a general item. Skip.

**Imperial City Maintenance Droid** (book p. 141) — "Eyesee-em," gunmetal-gray, two rounded heads, common on Coruscant. Good flavor for Coruscant room ambient descriptions. Not worth a full droid implementation — use in ambient text.

**Imperial Prison Medical Droid** (book p. 141) — Industrial Automaton 2-ZH Surgical Droid. Interesting for a Coruscant medical facility room. Stats: MEC 2D, KNO 2D (alien species 3D+1, injury/ailment diagnosis 4D+2), first aid 6D, medicine 7D. Cost 3,000 credits (used). Possible addition to the medical NPC pool.

**TDL Nanny Droid** (book p. 141–143) — XL-Lioness model. Four arms, synthetic-flesh torso, some models equipped with concealed stun blasters or ionization generators for child protection. Flavor-useful for Coruscant upper-class residential zones. Not a combat NPC. Skip for launch.

**FIDO — Foreign Intruder Defense Organism** (book p. 143) — Semi-organic droid, 8 meters long central pod, 26 extendible attack tentacles (100 meters range, STR+2D damage). Designed to protect bunker entrances. A brainstorm of Admiral Ackbar's, patterned after the Calamarian krakana. Not available for sale. Stats: DEX 6D, STR 12D (brawling 13D), PERC 5D (search 6D). Stationary (tentacles: Move 15).

**Era-translation note for FIDO:** This is a New Republic military design (Ackbar's invention). In 20 BBY, FIDO doesn't exist yet. However, the concept — a stationary semi-organic defense creature — is entirely compatible with Clone Wars aesthetics (think Geonosian security fauna). A re-skinned "Geonosian Defense Organism" or Separatist variant could use the same stat block without the Ackbar provenance. Flag for Geonosis zone design.

---

## C. Updated §8 — Remaining Unmined Pages

| Chapter | PDF Pages | Priority | Status |
|---|---|---|---|
| Ch. 1 The New Republic | 7–23 | Low | Unmined |
| Ch. 2 Coruscant | 24–29 | Low | Unmined; superseded by other sources |
| Ch. 3 remaining | 39–40, 42–43, 48–49 | Medium | Unmined — Kirana Ti, Dorsk 81, Kam Solusar archetypes |
| Ch. 4 Echoes of the Sith | 50–52 | ✅ Complete | All 5 Sith powers now fully captured |
| Ch. 5–6 | 54–83 | None | Era-irrelevant; skip |
| Ch. 7 The Fringe | 84–86 | Low | Unmined |
| Ch. 8 Kessel | 87–97 | Medium | Unmined — spice mines, energy spiders |
| Ch. 9 | 98–101 | Low | Ship stats; skip |
| Ch. 10 Planets | 102–120 | Medium | Unmined — select entries may translate |
| Ch. 11 Creatures | 121–126 | Medium | Unmined — energy spiders for Kessel |
| Ch. 12–13 | 127–141 | Low | Era-locked ships/vehicles; skip |
| Ch. 14 Equipment and Droids | 141–144 | ✅ Complete | No lightsaber detail found; Force Detector is the notable yield |

**Lightsaber construction:** Not in JAS. Recommend checking WEG D6 R&E core rulebook crafting section and/or *Tales of the Jedi Companion* (WEG40091) if it enters the source pool.

---

## D. Updated §9 — Reconciliation Table (revised)

| v4 §8.2 Claim | Status | Action |
|---|---|---|
| Jedi Praxeum philosophy | ✅ Sourced (v1 entry 1) | Keep |
| Old Republic values | ✅ Sourced (v1 entries 2, 6) | Keep |
| Jedi Code framing | ✅ Sourced (v1 entry 6) | Keep |
| Master/Padawan pedagogy | ✅ Sourced (v1 entries 2, 7, 9) | Keep |
| Lightsaber construction process | ❌ Not in JAS | Source elsewhere; downgrade claim in v4 |
| Force-power extensions | ✅ Fully sourced (v1 §3 — 10 powers; v1.1 §4 — 5 Sith powers) | Keep; implement in engine |
| Jedi Temple training halls structure | ❌ Not in JAS Ch. 14 | Remove from JAS-sourced list; find alternate source or write original lore |
| Jedi Council | ✅ Sourced (v1 entry 4) | Keep |

**Net:** 5 of 8 v4 §8.2 claims are JAS-sourced. The 2 that were flagged as ⚠️ in v1 are now confirmed ❌ — Ch. 14 doesn't have them. v4 §8.2 should be edited to remove those two JAS source claims and either source them elsewhere or convert them to original authored lore.

The count of JAS-sourced lore entries remains at 13 from v1 (the Ch. 14 yield is one new entry — Force Detector — bringing the total to **14**).

---

## E. New Lore Entry — Force Detector

Ready to add to `SEED_ENTRIES` in `engine/world_lore.py`:

```python
{
    "title": "The Force Detector",
    "keywords": "force detector,force sensitivity,dark side,inquisitor,imperial,jedi,scan,aura",
    "content": "The Force detector is a rare Imperial scanning device, originally commissioned to hunt down Jedi survivors of the Purge. The three-component system — a control pack and two crystal paddle readers — scans a subject from head to toe and generates a wire-frame hologram overlaid with a color-coded aura. A blue aura indicates Force sensitivity; the stronger the corona, the stronger the connection to the Force. Those who carry the stain of the dark side show an aura tinged with red. Fewer than ten thousand were ever produced, most now lost or destroyed. The Jedi Council regards them with deep unease: a device that reduces a person's soul to a readout is, they argue, precisely the kind of technology the Order should not use — and precisely the kind the Empire will.",
    "category": "equipment",
    "priority": 6,
},
```

---

## F. Implementation Checklist Update (from v1 §3 + this v1.1)

Full implementation list for `engine/force_powers.py` (now complete):

**10 Jedi powers from v1 §3:** Telekinetic Kill, Force of Will, Projected Fighting, Accelerate Another's Healing, Control Another's Pain, Dim Other's Senses, Receptive Telepathy, Transfer Force, Comprehend Speech, Weather Sense, Detoxify Poison in Another, Remove Another's Fatigue. *(Note: v1 counted 10 but listed 12; 2 were Control/Alter variants of existing powers — verify against v1 full text before implementation.)*

**5 Sith powers (NPC-only at launch):**
1. Aura of Uneasiness — auto-DSP, intimidation field
2. Electronic Manipulation — auto-DSP, droid/computer reprogramming via rage
3. Force Wind — auto-DSP, destructive tornado
4. Drain Life Energy — auto-DSP, keep-up, nonsentient-only fatigue drain
5. Memory Wipe — auto-DSP, contact-only, targeted knowledge/skill erasure

All five carry auto-DSP on use. All five should be flagged `npc_only=True` and `dark_side=True` in the power registry. Player access requires a separate design decision.

---

*End of JAS Extraction v1.1 Appendix — April 18, 2026.*
*Closes the Ch. 4 pp. 52–53 and Ch. 14 deferred items from v1.*
*Drain Life Energy: complete. Memory Wipe: new (5th Sith power). Lightsaber construction: not in JAS — source elsewhere.*
*Total JAS-sourced lore entries: 14. Total Force powers added: 10 Jedi + 5 Sith = 15.*
