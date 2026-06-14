---
category: foundations
order: 2
summary: "Species, templates, attribute dice, starting skills, and gear. Your first build, step by step."
tags: ["chargen", "species", "template", "build", "starting", "skills", "attributes"]
---

# Character Creation

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

Character creation in SW_MUSH follows the WEG D6 Revised & Expanded rules. You choose a species, distribute attribute dice within species-defined ranges, spend skill dice on the skills you want, optionally declare Force sensitivity, write a background, and finalize. The entire process happens through typed commands in a dedicated creation mode.

Two paths are available: a **guided wizard** that walks you through each step with descriptions and prompts, or a **free-form editor** where you can set any field in any order. Both paths produce the same result — a complete character saved to the database.

---

## 2. Species

Nine playable species are available. Each has different attribute ranges — the minimum and maximum dice you can put into each attribute. All species get the same total dice to distribute (18D for attributes, 7D for skills), but where those dice can go varies dramatically.

| Species | Homeworld | DEX | KNO | MEC | PER | STR | TEC | Move | Special Abilities |
|---------|-----------|-----|-----|-----|-----|-----|-----|------|-------------------|
| **Human** | Various | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 10 | None (most versatile) |
| **Bothan** | Bothawui | 1D+1–3D+2 | 2D–4D+1 | 1D–3D | 2D+1–4D+2 | 1D–2D+2 | 1D–3D+1 | 10 | — |
| **Duros** | Duro | 1D–3D+2 | 1D+1–4D | 2D+1–4D+2 | 1D–3D+1 | 1D–3D | 1D+1–4D | 10 | Natural Pilots |
| **Mon Calamari** | Mon Cala | 1D–3D | 1D+1–4D | 1D+1–3D+1 | 1D–3D+1 | 1D–3D | 1D+1–4D+1 | 10 | Amphibious, Moist Environment |
| **Rodian** | Rodia | 1D+1–4D | 1D–3D | 1D–3D+1 | 2D–4D+1 | 1D–3D | 1D–3D+1 | 10 | — |
| **Sullustan** | Sullust | 1D–3D+1 | 1D–3D | 1D+2–4D+1 | 1D–3D+1 | 1D–3D | 1D+1–3D+2 | 10 | Direction Sense, Enhanced Senses |
| **Trandoshan** | Trandosha | 1D–3D | 1D–2D+2 | 1D–2D+2 | 1D–3D | 2D–4D+2 | 1D–2D+2 | 10 | Regeneration, Claws, Vision |
| **Twi'lek** | Ryloth | 1D–3D+2 | 1D–4D | 1D–3D | 2D–4D+2 | 1D–3D | 1D–3D+1 | 10 | Lekku Communication |
| **Wookiee** | Kashyyyk | 1D–3D+2 | 1D–2D+1 | 1D–3D+2 | 1D–2D+1 | 3D–6D | 1D–3D+1 | 11 | Berserker Rage, Climbing Claws |

**Choosing a species matters.** A Wookiee can start with 6D Strength — devastating in brawling — but is capped at 2D+1 Knowledge and Perception. A Bothan excels at Perception (up to 4D+2) but caps at 2D+2 Strength. A Human has no extremes but can put 4D in anything.

**Special abilities** are species-locked traits that can't be learned by other species:

- **Wookiee Berserker Rage:** When wounded or a companion is hurt, gain +2D Strength for brawling damage. Cannot do anything except attack until passing a Moderate Perception check to calm down.
- **Wookiee Climbing Claws:** +2D to climbing checks. Using claws in combat is dishonorable — results in exile from Wookiee society.
- **Trandoshan Regeneration:** Can regrow lost limbs over time.
- **Trandoshan Claws:** Natural weapons that add to brawling damage.
- **Duros Natural Pilots:** Innate aptitude with spacecraft and navigation.
- **Mon Calamari Amphibious:** Can breathe underwater indefinitely.
- **Sullustan Direction Sense:** Almost never get lost, even in unfamiliar environments.
- **Sullustan Enhanced Senses:** Exceptional hearing and vision in low light.
- **Twi'lek Lekku Communication:** Can communicate silently via head-tail movements with other Twi'leks.

To view species details in-game: `info <species>` (e.g., `info wookiee`).

---

## 3. Attributes

You have **18D** (54 pips) of attribute dice to distribute among your six attributes. Each attribute must stay within your species' min/max range. Once you've spent all 18D (no more, no less), your attributes are set.

The six attributes and what they govern:

**Dexterity** — Your agility and hand-eye coordination. Governs all combat accuracy (blaster, melee, grenades, lightsaber), dodging, and physical nimbleness. The single most important attribute for combat characters.

**Knowledge** — Your education and worldly awareness. Governs languages, alien species knowledge, streetwise savvy, survival skills, tactics, willpower, and bureaucratic know-how. Essential for social and scholarly characters.

**Mechanical** — Your aptitude with vehicles and instruments. Governs all piloting (space transports, starfighters, capital ships), astrogation, sensors, gunnery, and vehicle operation. The key attribute for pilots and navigators.

**Perception** — Your social awareness and intuition. Governs persuasion, bargain, con, command, search, sneak, hide, gambling, and investigation. The primary attribute for face characters, spies, and leaders.

**Strength** — Your raw physical power and toughness. Governs brawling, lifting, stamina, climbing, and swimming. Also your base damage resistance — when you get shot, you roll Strength (plus armor) to resist damage. Low Strength characters are fragile.

**Technical** — Your mechanical and scientific expertise. Governs all repair skills, first aid, medicine, computer slicing, demolitions, droid programming, and security systems. Essential for engineers and medics.

**Setting attributes in-game:**
```
> set dex 3D+2        (set Dexterity to 3D+2)
> set str 4D          (set Strength to 4D)
> set kno 2D+1        (accepts abbreviations: dex, kno, mec, per, str, tec)
```

Attribute abbreviations work with any unique prefix — `dex`, `d`, `per`, `p`, `str`, `s`, etc. If the prefix is ambiguous (e.g., `s` could be Strength or Sense), you'll get an error asking you to be more specific.

---

## 4. Skills

You have **7D** (21 pips) of skill dice to distribute among the game's 75 skills. You can add 1D or 2D (or any pip amount) to any skill. Skills you don't invest in default to the raw attribute — there's no penalty for being "untrained."

**Important:** Skill dice are bonuses *above* the parent attribute. If you put 1D into Blaster and your Dexterity is 3D+1, your effective Blaster is 4D+1. The character sheet shows both the bonus and the total.

You don't have to spend all 7D. Unspent skill pips are lost — they don't convert to anything else.

**Setting skills in-game:**
```
> skill blaster 1D+1      (add 1D+1 bonus to Blaster)
> skill dodge 1D           (add 1D bonus to Dodge)
> skill space transports 2D (multi-word skill names work)
> unskill blaster           (remove Blaster skill bonus)
> list dex                  (browse all Dexterity skills)
> list all                  (browse all 75 skills)
```

Partial skill name matching works — `skill blas 1D` will match Blaster if it's unambiguous.

**Skill dice budget strategy:**

With only 7D, you need to prioritize. The WEG R&E recommends focusing on 4–6 skills that define your character concept rather than spreading thin. A smuggler might put 2D in Space Transports, 1D+1 in Blaster, 1D in Dodge, 1D in Streetwise, 1D in Bargain, and +2 pips in Starship Gunnery. A soldier might go heavier on Blaster (2D), Dodge (1D), Brawling (1D), Grenade (1D), Tactics (1D), and Stamina (1D).

---

## 5. Templates

Don't want to build from scratch? Seven pre-built templates set up reasonable attribute and skill distributions for common character archetypes. You can apply a template and then customize it — change species, adjust attributes, add or remove skills.

| Template | DEX | KNO | MEC | PER | STR | TEC | Key Skills |
|----------|-----|-----|-----|-----|-----|-----|------------|
| **Smuggler** | 3D+1 | 2D+1 | 4D | 3D+1 | 2D+2 | 2D+1 | Blaster +1D+1, Dodge +1D, Space Transports +1D+2, Gunnery +1D, Streetwise +1D, Bargain +1D |
| **Bounty Hunter** | 3D+2 | 2D+1 | 2D+2 | 3D+1 | 3D+1 | 2D+2 | Blaster +2D, Dodge +1D, Brawling +1D, Search +1D, Sneak +1D, Security +1D |
| **Separatist Pilot** | 3D | 2D+2 | 4D+1 | 2D+2 | 2D+2 | 2D+2 | Starfighter Piloting +2D, Gunnery +1D, Astrogation +1D, Sensors +1D, Starfighter Repair +1D, Blaster +1D |
| **Scoundrel** | 3D | 3D | 2D+2 | 4D | 2D+2 | 2D+2 | Con +1D+2, Persuasion +1D, Gambling +1D, Sneak +1D+1, Blaster +1D, Dodge +1D |
| **Technician** | 2D+1 | 3D | 2D+2 | 2D+2 | 2D+2 | 4D+2 | Comp Prog/Repair +1D+2, Space Transport Repair +1D+1, Droid Repair +1D, First Aid +1D, Security +1D, Blaster Repair +1D |
| **Jedi Apprentice** | 3D+1 | 3D | 2D+1 | 3D+2 | 3D | 2D+2 | Lightsaber +1D+2, Dodge +1D, Scholar +1D, Willpower +1D, Sneak +1D, Climbing/Jumping +1D+1 |
| **Soldier** | 3D+2 | 2D+2 | 2D+2 | 2D+2 | 3D+2 | 2D+2 | Blaster +1D+2, Dodge +1D, Brawling +1D, Grenade +1D, Tactics +1D, Stamina +1D+1 |

**Using templates in-game:**
```
> template              (list available templates)
> template smuggler     (apply the Smuggler template)
```

Applying a template sets the species to Human, distributes all 18D of attributes, and spends all 7D of skills. You can then change any of these — switch species (which resets attributes to minimums), adjust individual attributes with `set`, or modify skills with `skill`/`unskill`.

---

## 6. Force Sensitivity

During creation, you choose whether your character is **Force-sensitive**. This is a significant decision with lasting consequences:

**Force-sensitive (Yes):**
- Start with **2 Force Points** instead of 1
- Can learn Force skills (Control, Sense, Alter) and use Force powers
- Must be played as morally upright — the dark side temptation is real, and evil actions earn Dark Side Points that can corrupt your character
- Cannot be as mercenary or morally grey as a non-sensitive character

**Not Force-sensitive (No):**
- Start with **1 Force Point**
- Cannot learn Force skills or use Force powers
- Free to play a morally ambiguous character (smuggler, bounty hunter, etc.)

Per the WEG R&E rules: *"Force-sensitive characters can't be as mercenary as Han Solo is at the beginning of A New Hope. They must be moral, honest and honorable, like Luke Skywalker and Obi-Wan Kenobi, or the dark side will dominate them."*

Force skills (Control, Sense, Alter) cannot be added during initial creation unless they're already on your template. The Jedi Apprentice template is the primary path to starting with Force skills.

---

## 7. Starting Equipment and Credits

All characters start with **1,000 credits** and a basic equipment loadout. The WEG R&E rules say to pick "reasonable" starting equipment — the game provides defaults based on common sense for the setting:

- A blaster pistol (500 credits) or other sidearm
- A comlink (100 credits)
- Basic clothing
- Remaining credits for supplies

Specific starting equipment varies by how the character enters play. Credits can be spent at vendors, weapon shops, and other merchants in the game world once you're playing.

---

## 8. The Creation Wizard (Guided Mode)

When you create a character, the wizard walks you through these steps:

1. **Welcome & Path Choice** — Choose between using a template (quick start) or building from scratch
2. **Template Selection** (template path) or **Species Selection** (scratch path) — Pick your template or species with full descriptions
3. **Attributes** (scratch path only) — Distribute 18D across six attributes with real-time remaining count
4. **Skills** — Distribute 7D across skills with descriptions from the WEG rulebook
5. **Force Sensitivity** — Choose Yes or No with an explanation of consequences
6. **Background** — Write free-text character background/backstory
7. **Review & Confirm** — See the complete character sheet and finalize with `done`

At any step, you can:
- Type `back` to go to the previous step
- Type `sheet` to preview your character sheet
- Type `undo` to reverse the last change
- Type `free` to drop into free-form editing mode (all commands available simultaneously)
- Type `guided` to return to the step-by-step wizard from free-form mode
- Type `help` for available commands at any step

---

## 9. The Free-Form Editor

If you prefer full control, the free-form editor gives you all commands simultaneously. This is the underlying engine that the wizard wraps.

**All commands:**

| Command | Purpose | Example |
|---------|---------|---------|
| `name <n>` | Set character name (2–30 chars) | `name Kaelin Voss` |
| `species [name]` | List or set species | `species wookiee` |
| `info <species>` | View species details | `info trandoshan` |
| `template [name]` | List or apply template | `template smuggler` |
| `set <attr> <dice>` | Set attribute dice | `set dex 3D+2` |
| `skill <name> <dice>` | Add skill bonus | `skill blaster 1D+1` |
| `unskill <name>` | Remove skill bonus | `unskill dodge` |
| `list <attr\|all>` | Browse skills by attribute | `list perception` |
| `undo` | Undo last change | `undo` |
| `sheet` / `review` | Show full character sheet | `sheet` |
| `done` | Finalize character | `done` |
| `help` | Show command list | `help` |
| `quit` | Abort creation | `quit` |

The **status line** is always visible at the bottom, showing remaining attribute pips and skill pips:
```
[ Attr: 6 pips remaining | Skills: 12 pips remaining ]
```

---

## 10. Character Sheet Display

The character sheet uses a two-column layout matching the official WEG R&E character sheet format:

```
==============================================================================
  Kaelin Voss  |  Human  |  Smuggler
==============================================================================
  Status: Healthy
  CP: 5  |  FP: 1  |  DSP: 0  |  Credits: 1,000
  Move: 10

  DEXTERITY       3D+1              PERCEPTION      3D+1
    Blaster              4D+2 (+1D+1)  Bargain             4D+1 (+1D)
    Dodge                4D+1 (+1D)    Streetwise          ... (untrained)

  KNOWLEDGE       2D+1              STRENGTH        2D+2
    Streetwise           3D+1 (+1D)    ...

  MECHANICAL      4D                TECHNICAL       2D+1
    Space Transports     5D+2 (+1D+2)  ...
    Starship Gunnery     5D   (+1D)

==============================================================================
```

Left column shows DEX/KNO/MEC, right column shows PER/STR/TEC. Trained skills appear indented under their parent attribute with the total pool and the bonus in parentheses. Untrained skills are hidden unless you use `list all`.

During creation, the sheet also shows species attribute ranges in dim text next to each attribute so you know how much room you have.

---

## 11. Persistence: How Characters Are Saved

---

