# Developer Internals — Guide_09_CP_Progression.md

Extracted from `data/guides/Guide_09_CP_Progression.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

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

### 🔧 Developer Internals

**`CPStatusCommand`** (lines 41–95): Calls `engine.get_status(db, char_id)` which returns a dict with all fields. Renders a visual progress bar using `█` (filled) and `░` (empty) characters with ANSI green/dim coloring.

### 🔧 Developer Internals

**`award_kudos()`** (lines 201–259):
- Self-kudos blocked
- Checks `db.kudos_last_given(giver_id, target_id)` against `KUDOS_LOCKOUT_SECONDS`
- Checks `db.kudos_count_received_this_week(target_id)` against `KUDOS_PER_WEEK`
- If target is at weekly tick cap, logs kudos (recognition event) but awards 0 ticks
- Otherwise awards `min(KUDOS_TICKS, cap_remaining)` ticks and logs to `kudos_log` table

### 🔧 Developer Internals

**`cap_hit_streak`** in the `cp_ticks` table tracks consecutive weeks at the cap. When it reaches `ADMIN_CAP_FLAG_WEEKS = 3`, a warning is logged: "CP admin flag: char_id=X hit weekly cap Y consecutive weeks (possible farming)." This is informational — no automated action is taken, just a flag for staff review.

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

