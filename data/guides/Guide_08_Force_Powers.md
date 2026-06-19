---
category: paths
order: 1
summary: "Control, Sense, and Alter. How Force-sensitives roll powers, light/dark side, and corruption."
tags: ["force", "jedi", "sith", "powers", "lightsaber", "control", "sense", "alter"]
---

# Force Powers

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.1**

---

## 1. Overview

The Force Powers system implements 13 powers across three disciplines from the WEG D6 R&E Chapter 12 rules — including two **combination powers** that draw on all three. Only **Force-sensitive** characters can use Force powers — this is a decision made during character creation (see Guide #2).

Force powers are fueled by three Force attributes: **Control** (mastery over your own body), **Sense** (perception of the living Force around you), and **Alter** (manipulating the physical world through the Force). Each is a dice pool like any other attribute, but Force attributes start at 0D and must be awakened and developed (see §7).

The dark side is a constant temptation. Two powers are marked as dark side — **Injure/Kill** and **Dominate Mind** — and using either one *always* earns a Dark Side Point, regardless of intent. Accumulate too many and you risk falling to the dark side permanently.

---

## 2. The Three Disciplines

| Discipline | Attribute | Governs | Starting |
|-----------|-----------|---------|----------|
| **Control** | Control | Mastery over your own body — healing, endurance, pain suppression | 0D |
| **Sense** | Sense | Awareness of the living Force — detecting beings, feeling Force users | 0D |
| **Alter** | Alter | Manipulating the physical world — telekinesis, Force attacks, mind tricks | 0D |

Most powers require only one discipline. The two **combination powers** — Affect Mind and Dominate Mind — require all three (Control + Sense + Alter). For a combination power you roll the **weakest** of your required disciplines, so a mind power is only as strong as your thinnest Force attribute.

---

## 3. The Powers

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

#### Sense Powers (6)

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

**Telepathy** — Touch another mind with the Force.
- Discipline: Sense
- Difficulty: Moderate (15)
- Target: Character
- *Reach out to another mind. Between a bonded Master and Padawan it carries across any distance and you feel their condition (see Guide #14); otherwise it is a wordless mind-touch offered to another player to answer, or a skim of an NPC's surface thoughts.*

**Sense Deception** — Weigh another's sincerity.
- Discipline: Sense
- Difficulty: Moderate (15)
- Target: Character
- *Read the truth of someone's words against the Force. On a being who is concealing something you sense the deceit, and may glimpse what lies beneath; on an honest one you feel their truth. A player target is offered the read to play out.*

**Farseeing** — Glimpse what is to come.
- Discipline: Sense
- Difficulty: Difficult (20)
- Target: Self
- *Still your mind and let the Force show you a portent of danger near at hand. Never precise — the future is always in motion.*

**Danger Sense** — Feel a threat before it strikes.
- Discipline: Sense
- Difficulty: Moderate (15)
- Target: Self
- *Sharpen your awareness to imminent danger. In combat you react first — your next initiative is rerolled, keeping the better. Out of combat it is an early warning.*

#### Alter Powers (2)

**Telekinesis** — Move objects or disarm opponents.
- Discipline: Alter
- Difficulty: Easy (10) + 5 per range band beyond touch
- Target: Object or character
- *Move objects with the Force, or wrench a weapon from an opponent's grip. Range increases difficulty — the further away, the harder it is. To **disarm**, you must beat the difficulty by a margin of 3 or more; a smaller success only shoves the target back without breaking their hold.*

**Injure/Kill** ⚠️ DARK SIDE — Force-damage a target.
- Discipline: Alter
- Difficulty: Easy (10), opposed by target's Strength
- Target: Character
- **Always earns 1 Dark Side Point.**
- *Use the Force as a weapon, crushing or striking the target. Roll Alter against the difficulty, then the target resists with Strength — the damage is how far your margin beats their resistance roll, resolved through the normal wound chart.*

#### Combination Powers (2)

Both require **Control + Sense + Alter**, and you roll the weakest of the three.

**Affect Mind** — The Jedi mind trick: plant a suggestion in a weak mind.
- Disciplines: Control + Sense + Alter (uses the weakest)
- Difficulty: Moderate (15), contested by the target's will
- Target: Character or NPC
- *Press a quiet suggestion toward a weak-willed mind. Against an NPC the contest is an opposed willpower roll the engine resolves (distract a guard, pry loose a fact); against another player it is offered for them to play out — it never overrides another player's agency. Margin determines how firmly it takes: 10+ = strong, 5–9 = moderate, 1–4 = weak. This is a **light-side** power — it earns **no** Dark Side Point.*

**Dominate Mind** ⚠️ DARK SIDE — Coerce a will into submission.
- Disciplines: Control + Sense + Alter (uses the weakest)
- Difficulty: Difficult (20), contested by the target's will
- Target: Character or NPC
- **Always earns 1 Dark Side Point.**
- *The dark counterpart to Affect Mind. Where a suggestion nudges, domination seizes a will and bends it — overriding resistance a suggestion cannot. Against a player it is still offered, never forced; against an NPC the engine compels their compliance.*

### Using Powers In-Game

```
force accelerate_healing          — Use a self-targeting power
force telekinesis <target>        — Use a targeted power
force affect_mind <target>        — Light mind trick (no DSP)
force injure_kill <target>        — Dark side power (DSP warning)
+powers                           — List all powers you can use
+forcestatus                      — Show Force attributes and DSP count
```

---

## 4. Power Resolution

When you use a Force power:
1. The game checks your Force attribute pool for the required discipline(s)
2. Wound penalties are applied
3. For combination powers, the **weakest** discipline is used
4. You roll against the power's difficulty. For the mind powers (Affect Mind, Dominate Mind) against an NPC, that difficulty rises to whatever the target rolls to resist with willpower — an opposed contest, so a strong-willed being is genuinely hard to sway
5. Success applies the power's effect
6. If the power is dark side, you gain 1 DSP regardless of success or failure

---

## 5. The Dark Side

Two powers — **Injure/Kill** and **Dominate Mind** — are marked as dark side. Using either one *always* awards **1 Dark Side Point**, even if the roll fails. There is no "justified" use of dark side powers. (Affect Mind, the light Jedi mind trick, is *not* dark side — it costs no DSP. Dominate Mind is its corrupting counterpart.)

**Dark Side Point accumulation:**
- 1–3 DSP: A point is noted each time ("You gain 1 Dark Side Point.")
- 4–5 DSP: Warnings escalate ("The darkness grows within you.")
- **6+ DSP: Fall check triggered**, with the warning "The darkness is consuming you." Roll Willpower vs. (DSP × 3). Failure = your character falls to the dark side permanently.

**The fall check** is harsh by design. At 6 DSP, the difficulty is 18 — you need very strong Willpower to resist. At 8 DSP, the difficulty is 24. At 10 DSP, it's virtually impossible. The dark side is a one-way ratchet — every use of dark powers makes the next fall check harder.

**Weight of War.** Jedi who have carried the Weight of War — the accumulated trauma of battle — resist the fall *less* well. Past a threshold their fall-check difficulty rises further by tier (+2 / +5 / +10), and the most war-weary lose an extra Dark Side Point when a fall check fails. A Jedi worn down by war is closer to the edge than the raw DSP count alone suggests.

**Per R&E rules:** Force-sensitive characters must be played as morally upright. Using dark side powers is a choice with permanent mechanical consequences — there's no "I was just testing it" exemption.

---

## 6. Force Points vs. Force Powers

Don't confuse **Force Points** (the dramatic resource that doubles all dice for one round — available to everyone, not just Force users) with **Force Powers** (the discipline-based abilities only Force-sensitive characters can use). They're completely separate systems.

- **Force Points** = A finite resource. Everyone has them. Spend to double all dice for one round.
- **Force Powers** = Abilities requiring trained Force attributes. Only Force-sensitive characters.
- **Force Attributes** = Control, Sense, Alter — dice pools that power Force abilities.

A Force-sensitive character can spend a Force Point AND use a Force power in the same round — the FP doubles their Force attribute dice for that power use, making it much more likely to succeed.

---

## 7. Developing the Force

Control, Sense, and Alter are not ordinary skills, and the `train` command does **not** raise them — the Force is taught, not self-studied. A Force-sensitive character begins with the disciplines they awakened during character creation and the Jedi Village trials (see Guide #2 and Guide #18), and develops new ones through the **Master–Padawan training bond**.

A Master who knows a power can `+teach` it to a bonded Padawan; the Padawan's own Character Points pay to bring the underlying discipline up to 1D (the cost scales with the governing attribute, and a guild/bond discount is applied automatically). If the Padawan already meets the prerequisite, the teaching is a free reinforcing lesson. Bonded pairs also earn CP together through `+spar`. The full teaching loop — bonding, `+teach`/`+learn`, sparring, and the trials — is covered in **Guide #14 (Padawan & Master)**.

Because a Force-sensitive must split their Character Points between their Force disciplines and their ordinary skills, every point spent awakening the Force is a point not spent on blaster, dodge, or a trade — a meaningful budget tradeoff that shapes what kind of Jedi (or fallen one) you become.

---

## 8. Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `force` | `force <power> [target]` | Use a Force power |
| `+powers` | `+powers` | List all powers available to you |
| `+forcestatus` | `+forcestatus` | Show Force attributes and Dark Side Points |

---

