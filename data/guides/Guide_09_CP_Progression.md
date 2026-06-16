---
category: foundations
order: 4
summary: "Character Points: how you earn them, what they cost to raise skills and attributes, and milestone rewards."
tags: ["cp", "progression", "advancement", "improve", "leveling", "milestones"]
---

# CP Progression

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

Character Points (CP) are your advancement currency. You earn CP over time through a tick-based economy, then spend CP to improve your skills. The system is designed for long-term engagement — advancing a skill from 3D to 5D takes roughly 7 months of active play.

**The core loop:** Earn ticks through roleplay → accumulate 200 ticks → receive 1 CP → spend CP to train skills.

---

## 2. Earning CP: The Tick Economy

**200 ticks = 1 Character Point.** There's a weekly hard cap of 400 ticks (max 2 CP/week from tick accumulation alone). Four income sources feed the tick pool:

**Source 1 — Passive Participation (Floor)**
- 10 ticks/day just for being logged in
- Guaranteed floor income — you earn just by showing up
- ~70 ticks/week at daily login = roughly 1 CP every ~3 weeks from passive alone

**Source 2 — Scene Completion Bonus**
- Earn ticks when a roleplay scene ends based on how many poses you contributed
- 2 ticks per pose above a 3-pose minimum, capped at 60 ticks per scene
- 10-minute cooldown between scene bonuses
- A 30-pose scene earns the maximum 54 ticks

**Source 3 — Kudos (Dominant Source)**
- Other players award you kudos for good roleplay: `+kudos <player>`
- **35 ticks per kudos** received
- Max 3 kudos receivable per rolling 7-day window
- 7-day lockout per giver→target pair (prevents farming)
- Three kudos = 105 ticks/week — this is the fastest way to earn CP

**Source 4 — AI Evaluator Trickle**
- The Director AI can award up to 15 ticks per evaluation for quality roleplay
- Lowest priority; degrades gracefully when GPU is busy
- Bonus, not something to rely on

**Target progression:** ~1 CP per 10–12 days for an actively roleplaying player who receives regular kudos.

---

## 3. Spending CP: Skill Advancement

The `train` command improves a skill by one pip:

```
train blaster             — Advance Blaster by 1 pip
train space transports    — Advance Space Transports by 1 pip
```

**Cost formula:** The cost to advance a skill by 1 pip equals the **number of dice in the total pool** (attribute + skill bonus).

**Example progression for a character with 3D+1 Dexterity and Blaster +1D (total 4D+1):**

| Current Pool | Cost per Pip | Running Total |
|-------------|-------------|---------------|
| 4D+1 → 4D+2 | 4 CP | 4 CP |
| 4D+2 → 5D | 4 CP | 8 CP |
| 5D → 5D+1 | 5 CP | 13 CP |
| 5D+1 → 5D+2 | 5 CP | 18 CP |
| 5D+2 → 6D | 5 CP | 23 CP |

So going from 4D+1 to 6D costs 23 CP total. At ~1 CP per 10–12 days, that's roughly 7–9 months. This is intentionally slow — skill advancement is the long-term progression carrot.

**Three pips = one die.** Each pip costs the same (the current dice count), and every third pip rolls up to a new die. The cost increases at each die boundary.

**Guild training discount:** Members of certain guilds receive a **20% discount** on training costs. If your guild reduces a 5 CP cost, you pay 4 CP instead.

**Per WEG R&E rules:** Characters need training time and ideally a teacher whose skill is at least equal to the target level. A teacher halves training time (5 days vs. 10 days at the 5D level). NPC trainers exist in the game world for this purpose.

---

## 4. Viewing Your Progress

```
+cpstatus                 — Full progression dashboard
```

Shows:
- CP Available (spendable balance)
- Ticks total (lifetime accumulation)
- Ticks to next CP conversion
- Weekly progress bar with visual fill indicator
- Kudos received/remaining this week
- Weekly cap status

The display includes a 20-character progress bar showing how close you are to the weekly tick cap.

---

## 5. Kudos System

Kudos are the social recognition mechanic — the primary way players reward each other for good roleplay:

```
+kudos Tundra Great scene at the cantina!
```

**Rules:**
- Can't kudos yourself
- 7-day rolling lockout per giver→target pair (you can kudos Tundra once per week)
- Target can receive max 3 kudos per rolling 7-day window
- Players do not need to be in the same room to give kudos
- Each kudos = 35 ticks toward the recipient's CP

**Why kudos matter:** At 35 ticks per kudos and 3 receivable per week, kudos are worth 105 ticks/week — over a quarter of the 400-tick weekly cap. A player who consistently receives kudos advances significantly faster than one who doesn't. This creates a positive feedback loop: good roleplay → kudos from peers → faster advancement.

---

## 6. Milestone CP Bonuses

In addition to the tick economy, certain achievements award CP directly as one-time bonuses. These are **outside the weekly tick cap** — they're instant rewards.

**Ship's Log milestones** (from Guide #5, section 12): Visiting all 16 zones (50 CP), scanning all 19 ship types (30 CP), resolving all 7 anomaly types (30 CP), landing on all 4 planets (20 CP), 100 pirate kills (50 CP), 50 smuggling runs (50 CP), 50 trade runs (30 CP).

**Profession chain completion** also awards CP bonuses when profession milestones are reached.

These bonuses give active, exploring players a significant CP advantage over passive players — you could earn 260+ bonus CP from completing all milestones, equivalent to 260 weeks of tick accumulation.

---

## 7. Anti-Farming Measures

Several design features prevent CP farming:

- **Weekly hard cap (400 ticks):** No matter how active you are, you can't earn more than 2 CP/week from ticks
- **Kudos lockout (7-day per pair):** Can't repeatedly kudos the same person
- **Scene cooldown (10 minutes):** Can't spam short scenes for ticks
- **Kudos receive cap (3/week):** Can't collect unlimited kudos
- **Admin flag (3+ consecutive cap weeks):** Characters who hit the cap every week for 3+ consecutive weeks are flagged for admin review

---

## 8. Advancement Timeline

Realistic advancement timeline for an active player (~1 CP every 10–12 days):

| Goal | CP Needed | Time |
|------|-----------|------|
| One pip (e.g., 4D → 4D+1) | 4 CP (at 4D) | ~6 weeks |
| One die (4D → 5D) | 12 CP (4+4+4) | ~4 months |
| Two dice (3D → 5D) | 21 CP (3+3+3+4+4+4) | ~7 months |
| Three dice (3D → 6D) | 36 CP | ~12 months |
| Specialist peak (3D → 7D) | 57 CP | ~19 months |

This pacing is designed so that character advancement is meaningful but never a wall. A dedicated player sees steady, visible progress without anyone becoming overpowered quickly. The spread between a new character (3D–4D skills) and a veteran (~6D–7D) is significant but not insurmountable.

---

## 9. Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `+cpstatus` | `cpstatus` | View your CP progression dashboard |
| `train` | `train <skill>` | Spend CP to advance a skill by 1 pip |
| `+kudos` | `kudos <player> [message]` | Give kudos to a player for good RP |
| `scenebonus` | `scenebonus` | Claim scene completion bonus (usually automatic) |

---

