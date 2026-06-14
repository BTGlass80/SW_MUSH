---
category: paths
order: 1
summary: "Control, Sense, and Alter. How Force-sensitives roll powers, light/dark side, and corruption."
tags: ["force", "jedi", "sith", "powers", "lightsaber", "control", "sense", "alter"]
---

# Force Powers

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

The Force Powers system implements 8 powers across three disciplines from the WEG D6 R&E Chapter 12 rules. Only **Force-sensitive** characters can use Force powers — this is a decision made during character creation (see Guide #2).

Force powers are fueled by three Force attributes: **Control** (mastery over your own body), **Sense** (perception of the living Force around you), and **Alter** (manipulating the physical world through the Force). Each is a dice pool like any other attribute, but Force attributes start at 0D and must be trained up with Character Points.

The dark side is a constant temptation. Two of the eight powers are marked as dark side — using them *always* earns Dark Side Points, regardless of intent. Accumulate too many and you risk falling to the dark side permanently.

---

## 2. The Three Disciplines

| Discipline | Attribute | Governs | Starting |
|-----------|-----------|---------|----------|
| **Control** | Control | Mastery over your own body — healing, endurance, pain suppression | 0D |
| **Sense** | Sense | Awareness of the living Force — detecting beings, feeling Force users | 0D |
| **Alter** | Alter | Manipulating the physical world — telekinesis, Force attacks, mind tricks | 0D |

Some powers require only one discipline. **Combination powers** require multiple — Affect Mind needs all three (Control + Sense + Alter). For combination powers, you roll the **weakest** of your required disciplines.

---

## 3. The Eight Powers

#### Control Powers (3)

**Accelerate Healing** — Heal one wound level immediately.
- Discipline: Control
- Difficulty: Moderate (15)
- Target: Self
- Limit: Once per day of rest
- *Channel the Force inward to speed natural recovery. On success, your wound level improves by one step (Wounded → Healthy, Incapacitated → Wounded Twice, etc.).*

**Control Pain** — Ignore wound penalties for the rest of the scene.
- Discipline: Control
- Difficulty: Easy (10)
- Target: Self
- *Shut out pain and act normally despite injuries. The damage remains — wounds still apply when the power fades. You're not healed, you're just pushing through.*

**Remain Conscious** — Stay active despite Incapacitation.
- Discipline: Control
- Difficulty: Difficult (20)
- Target: Self
- Limit: Once per combat
- *Through sheer Force of will, act normally for one round despite being Incapacitated. This won't save you from further damage — it just gives you one more chance to act.*

#### Sense Powers (2)

**Life Sense** — Detect all living beings in the room.
- Discipline: Sense
- Difficulty: Easy (10)
- Target: Room
- *Extend your perception to feel every living presence nearby. Reveals the number and rough emotional state of all beings in the area.*

**Sense Force** — Detect Force users and dark side presence.
- Discipline: Sense
- Difficulty: Easy (10)
- Target: Room
- *Feel the currents of the Force around you. Force-sensitive beings and echoes of the dark side shimmer at the edges of your perception.*

#### Alter Powers (2)

**Telekinesis** — Move objects or disarm opponents.
- Discipline: Alter
- Difficulty: Easy (10) + 5 per range band beyond touch
- Target: Object or character
- *Move objects with the Force. Can be used to disarm opponents (opposed by their Dexterity). Range increases difficulty — the further away, the harder it is.*

**Injure/Kill** ⚠️ DARK SIDE — Force-damage a target.
- Discipline: Alter
- Difficulty: Easy (10), opposed by target's Strength
- Target: Character
- **Always earns 1 Dark Side Point.**
- *Use the Force as a weapon, crushing or striking the target. Roll Alter vs. target's Strength. The margin of success determines damage, resolved through the normal wound chart.*

#### Combination Powers (1)

**Affect Mind** ⚠️ DARK SIDE — Implant a suggestion on an NPC.
- Disciplines: Control + Sense + Alter (uses the weakest)
- Difficulty: Moderate (15) for simple suggestions; higher for complex commands
- Target: NPC
- **Always earns 1 Dark Side Point.**
- *Reach into a being's mind and implant a suggestion or emotion. Margin determines suggestion strength: 10+ = strong (firmly takes hold), 5–9 = moderate (target may resist later), 1–4 = weak (faint impression, easily shaken off).*

### Using Powers In-Game

```
force accelerate_healing          — Use a self-targeting power
force telekinesis <target>        — Use a targeted power
force injure_kill <target>        — Dark side power (DSP warning)
powers                            — List all powers you can use
forcestatus                       — Show Force attributes and DSP count
```

---

## 4. Power Resolution

When you use a Force power:
1. The game checks your Force attribute pool for the required discipline(s)
2. Wound penalties are applied
3. For combination powers, the **weakest** discipline is used
4. You roll against the power's difficulty
5. Success applies the power's effect
6. If the power is dark side, you gain 1 DSP regardless of success or failure

---

## 5. The Dark Side

Two powers — **Injure/Kill** and **Affect Mind** — are marked as dark side. Using either one *always* awards **1 Dark Side Point**, even if the roll fails. There is no "justified" use of dark side powers.

**Dark Side Point accumulation:**
- 1–3 DSP: Warning messages escalate ("The darkness grows within you.")
- 4–5 DSP: Serious warnings ("The darkness is consuming you.")
- **6+ DSP: Fall check triggered.** Roll Willpower vs. (DSP × 3). Failure = your character falls to the dark side permanently.

**The fall check** is harsh by design. At 6 DSP, the difficulty is 18 — you need very strong Willpower to resist. At 8 DSP, the difficulty is 24. At 10 DSP, it's virtually impossible. The dark side is a one-way ratchet — every use of dark powers makes the next fall check harder.

**Per R&E rules:** Force-sensitive characters must be played as morally upright. Using dark side powers is a choice with permanent mechanical consequences — there's no "I was just testing it" exemption.

---

## 6. Force Points vs. Force Powers

Don't confuse **Force Points** (the dramatic resource that doubles all dice for one round — available to everyone, not just Force users) with **Force Powers** (the discipline-based abilities only Force-sensitive characters can use). They're completely separate systems.

- **Force Points** = A finite resource. Everyone has them. Spend to double all dice for one round.
- **Force Powers** = Abilities requiring trained Force attributes. Only Force-sensitive characters.
- **Force Attributes** = Control, Sense, Alter — dice pools that power Force abilities.

A Force-sensitive character can spend a Force Point AND use a Force power in the same round — the FP doubles their Force attribute dice for that power use, making it much more likely to succeed.

---

## 7. Advancement

Force attributes (Control, Sense, Alter) advance the same way as regular skills — by spending Character Points between sessions. The CP cost to advance follows the same formula as other skills: the cost equals the number of dice in the current rating.

Because Force attributes start at 0D, the first die costs 1 CP (from 0D to 1D). Getting to 3D costs 1+2+3 = 6 CP total. Getting to 5D costs 1+2+3+4+5 = 15 CP total. This is relatively affordable compared to high-level combat skills, but Force-sensitive characters have three Force attributes to advance on top of their regular skills, creating a meaningful CP budget tradeoff.

---

## 8. Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `force` | `force <power> [target]` | Use a Force power |
| `powers` | `powers` | List all powers available to you |
| `forcestatus` | `forcestatus` | Show Force attributes and Dark Side Points |

---

