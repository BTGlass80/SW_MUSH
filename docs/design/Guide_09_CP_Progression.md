# SW_MUSH Detailed Systems Guide #9
# CP Progression

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

### Player Rules

Character Points (CP) are your advancement currency. You earn CP over time through a tick-based economy, then spend CP to improve your skills. The system is designed for long-term engagement — advancing a skill from 3D to 5D takes roughly 7 months of active play.

**The core loop:** Earn ticks through roleplay → accumulate 300 ticks → receive 1 CP → spend CP to train skills.

---

## 2. Earning CP: The Tick Economy

### Player Rules

**300 ticks = 1 Character Point.** There's a weekly hard cap of 300 ticks (max 1 CP/week from tick accumulation alone). Four income sources feed the tick pool:

**Source 1 — Passive Participation (Floor)**
- 5 ticks/day just for being logged in
- Guaranteed floor income — you earn just by showing up
- ~35 ticks/week at daily login = roughly 1 CP every 8.5 weeks from passive alone

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

### 🔧 Developer Internals

**File:** `engine/cp_engine.py` (~428 lines)

**Constants:**
```
TICKS_PER_CP = 300
WEEKLY_CAP_TICKS = 300
PASSIVE_TICKS_PER_DAY = 5
SCENE_MIN_POSES = 3
SCENE_TICKS_PER_POSE = 2
SCENE_MAX_TICKS = 60
SCENE_COOLDOWN_SECONDS = 600
KUDOS_TICKS = 35
KUDOS_PER_WEEK = 3
KUDOS_LOCKOUT_SECONDS = 604800  (7 days)
AI_MAX_TICKS_PER_EVAL = 15
PASSIVE_CHECK_INTERVAL = 3600
```

**`CPEngine` class** — Singleton accessed via `get_cp_engine()`:
- `tick(db, session_mgr)` — Called every game tick (1 second). Handles passive trickle via `_maybe_award_passive()` every 3,600 ticks. Checks `DAY_SECONDS` elapsed since last passive award.
- `award_scene_bonus(db, char_id, pose_count)` — Called on scene close. Validates minimum poses, cooldown, and weekly cap. Returns `{ticks, message, capped}`.
- `award_kudos(db, giver_id, target_id)` — Validates self-kudos block, 7-day lockout, weekly cap. Returns `{success, message, ticks_awarded}`.
- `award_ai_trickle(db, char_id, ticks)` — Graceful-drop: never raises exceptions. Clamps to `[0, AI_MAX_TICKS_PER_EVAL]`.
- `get_status(db, char_id)` — Returns full status dict for the `cpstatus` command.

**`_award_ticks()` — Core tick award function** (lines 342–411):
1. Gets or creates `cp_ticks` DB row
2. Handles weekly window rollover (resets `ticks_this_week` when `WEEK_SECONDS` elapsed)
3. Tracks `cap_hit_streak` — consecutive weeks at cap (admin flag at 3+)
4. Converts ticks → CP: `cp_gained = (ticks_total_after // TICKS_PER_CP) - (ticks_total_before // TICKS_PER_CP)`
5. Calls `db.cp_add_character_points(char_id, cp_gained)` to update the characters table

**DB persistence:** All tick state lives in the `cp_ticks` table: `ticks_total`, `ticks_this_week`, `week_start_ts`, `last_passive_ts`, `last_scene_ts`, `last_source`, `last_award_ts`, `cap_hit_streak`. Kudos are logged in the `kudos_log` table for lockout and cap checks.

---

## 3. Spending CP: Skill Advancement

### Player Rules

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

### 🔧 Developer Internals

**File:** `parser/cp_commands.py` — `TrainCommand` (lines 97–201):

1. Looks up skill via `SkillRegistry.get()` with partial matching
2. Loads full `Character` object from DB
3. Calculates cost: `total_pool.dice` (current total = attribute + skill bonus)
4. Applies guild discount via `organizations.get_guild_cp_multiplier(char, db)` — returns a multiplier (e.g., 0.8 for 20% discount), cost = `max(1, int(cost * multiplier))`
5. Checks `cp_available >= cost`
6. Calls `character.advance_skill(skill_name, skill_reg)` — adds 1 pip to the skill bonus
7. Deducts cost from `character.character_points`
8. Saves updated skills JSON + CP to DB
9. Logs to narrative system via `narrative.log_action()` for Director AI awareness

**`Character.advance_skill()`** in `engine/character.py`: Adds `DicePool(0, 1)` to the skill's bonus. The `DicePool.__post_init__()` auto-normalizes (3 pips → +1 die).

---

## 4. Viewing Your Progress

### Player Rules

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

### 🔧 Developer Internals

**`CPStatusCommand`** (lines 41–95): Calls `engine.get_status(db, char_id)` which returns a dict with all fields. Renders a visual progress bar using `█` (filled) and `░` (empty) characters with ANSI green/dim coloring.

---

## 5. Kudos System

### Player Rules

Kudos are the social recognition mechanic — the primary way players reward each other for good roleplay:

```
+kudos Tundra Great scene at the cantina!
```

**Rules:**
- Can't kudos yourself
- 7-day rolling lockout per giver→target pair (you can kudos Tundra once per week)
- Target can receive max 3 kudos per rolling 7-day window
- Both players must be in the same room
- Each kudos = 35 ticks toward the recipient's CP

**Why kudos matter:** At 35 ticks per kudos and 3 receivable per week, kudos are worth 105 ticks/week — over a third of the 300-tick weekly cap. A player who consistently receives kudos advances significantly faster than one who doesn't. This creates a positive feedback loop: good roleplay → kudos from peers → faster advancement.

### 🔧 Developer Internals

**`award_kudos()`** (lines 201–259):
- Self-kudos blocked
- Checks `db.kudos_last_given(giver_id, target_id)` against `KUDOS_LOCKOUT_SECONDS`
- Checks `db.kudos_count_received_this_week(target_id)` against `KUDOS_PER_WEEK`
- If target is at weekly tick cap, logs kudos (recognition event) but awards 0 ticks
- Otherwise awards `min(KUDOS_TICKS, cap_remaining)` ticks and logs to `kudos_log` table

---

## 6. Milestone CP Bonuses

### Player Rules

In addition to the tick economy, certain achievements award CP directly as one-time bonuses. These are **outside the weekly tick cap** — they're instant rewards.

**Ship's Log milestones** (from Guide #5, section 12): Visiting all 16 zones (50 CP), scanning all 19 ship types (30 CP), resolving all 7 anomaly types (30 CP), landing on all 4 planets (20 CP), 100 pirate kills (50 CP), 50 smuggling runs (50 CP), 50 trade runs (30 CP).

**Profession chain completion** also awards CP bonuses when profession milestones are reached.

These bonuses give active, exploring players a significant CP advantage over passive players — you could earn 260+ bonus CP from completing all milestones, equivalent to 260 weeks of tick accumulation.

---

## 7. Anti-Farming Measures

### Player Rules

Several design features prevent CP farming:

- **Weekly hard cap (300 ticks):** No matter how active you are, you can't earn more than 1 CP/week from ticks
- **Kudos lockout (7-day per pair):** Can't repeatedly kudos the same person
- **Scene cooldown (10 minutes):** Can't spam short scenes for ticks
- **Kudos receive cap (3/week):** Can't collect unlimited kudos
- **Admin flag (3+ consecutive cap weeks):** Characters who hit the cap every week for 3+ consecutive weeks are flagged for admin review

### 🔧 Developer Internals

**`cap_hit_streak`** in the `cp_ticks` table tracks consecutive weeks at the cap. When it reaches `ADMIN_CAP_FLAG_WEEKS = 3`, a warning is logged: "CP admin flag: char_id=X hit weekly cap Y consecutive weeks (possible farming)." This is informational — no automated action is taken, just a flag for staff review.

---

## 8. Advancement Timeline

### Player Rules

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

## 10. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/cp_engine.py` | ~428 | Tick economy, CPEngine singleton, passive/scene/kudos/AI award functions, status queries, tick→CP conversion, weekly cap, admin flags |
| `parser/cp_commands.py` | ~325 | 4 commands (cpstatus, train, kudos, scenebonus), skill advancement with guild discount, narrative logging |
| `engine/character.py` | ~588 | advance_skill(), character_points storage |
| `engine/ships_log.py` | ~266 | Milestone CP bonuses (outside tick cap) |
| `engine/organizations.py` | ~940 | Guild CP training discount multiplier |

**Total CP system:** ~753 lines of dedicated engine/parser code.

---

*End of Guide #9 — CP Progression*
*Next: Guide #10 — Organizations & Factions*
