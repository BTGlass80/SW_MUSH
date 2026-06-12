# SW_MUSH Detailed Systems Guide #3
# Ground Combat

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## How to Read This Guide

**Player Rules** sections explain combat from a player's perspective — commands, flow, and what you see. **Developer Internals** (🔧) sections explain the engine: data structures, resolution algorithms, and code paths. Ground combat is the largest system in the game (~70,000 lines across four files), so this guide is correspondingly detailed.

---

## 1. Combat Flow: The Round

### Player Rules

Combat is turn-based, organized into rounds. Each round follows four phases:

**Phase 1 — Initiative.** Everyone in combat rolls Perception. Highest goes first. The game displays the turn order.

**Phase 2 — Declaration.** Starting from lowest initiative to highest, each combatant declares what they'll do this round: attack a target, dodge, parry, aim, take cover, flee, or use a Force power. You can declare multiple actions (attack + dodge, for example), but each extra action applies a multi-action penalty (−1D per extra action to ALL your rolls). You can also declare a full dodge or full parry — your entire round is spent on defense, but it's much more effective.

**Phase 3 — Resolution.** Actions resolve in initiative order (highest first). The game rolls all dice, applies damage, and narrates results. You see a two-line output for each action: a bold story line ("▸ Kaelin fires at the Stormtrooper — HIT! Wounded!") and a dim mechanics line showing the exact rolls.

**Phase 4 — Cleanup.** Stun timers tick down. Mortally wounded characters make death rolls. Fled or dead combatants are removed. If only one side remains, combat ends.

Then a new round begins at Phase 1.

### 🔧 Developer Internals

**File:** `engine/combat.py` — `CombatInstance` class (line 337, ~1,400 lines)

**Phase tracking:** `CombatPhase` enum: `INITIATIVE`, `DECLARATION`, `RESOLUTION`, `POSING`, `CLEANUP`, `ENDED`.

**Round flow in code:**
```
combat.roll_initiative()     → DECLARATION phase, events returned
    ↓ (players declare actions)
combat.declare_action(id, action) → validates, appends to Combatant.actions
    ↓ (when all_declared() is True)
combat.resolve_round()       → RESOLUTION → POSING phase, events returned
    ↓ (pose window for narrative)
    ↓ (then command layer starts next round)
combat.roll_initiative()     → next round
```

**`CombatInstance.__init__()`**: Takes `room_id`, `skill_reg`, `default_range` (RangeBand), `cover_max`. Maintains `combatants: dict[int, Combatant]`, `initiative_order: list[int]`, `events: list[CombatEvent]`.

**`is_over` property**: Returns True when `len(active_combatants) <= 1`. Active = `wound_level.can_act and not is_fleeing`.

---

## 2. Initiative

### Player Rules

At the start of each round, every combatant rolls **Perception** (with wound penalties applied). The results determine turn order — highest roll acts first during resolution. Ties are broken by the sort (stable, so consistent ordering).

You don't type anything for initiative — it happens automatically.

### 🔧 Developer Internals

**`roll_initiative()`** (lines 418–467):
1. Increments `round_num`, sets phase to DECLARATION
2. For each combatant: rolls `Perception` pool via `roll_d6_pool()`, applies wound penalty
3. Stores individual roll displays in `_last_initiative_rolls` (for `combat rolls` command)
4. Sorts `initiative_order` by roll total (descending)
5. Resets per-round state: clears actions, `has_acted`, `dodge_roll_cached`, `soak_cp`
6. Returns single summary event: `"Turn order: Kaelin (18) → Trooper (14) → ..."`

---

## 3. Actions and Declaration

### Player Rules

**Available actions:**

| Command | Action | Notes |
|---------|--------|-------|
| `attack <target>` | Attack someone | Optionally: `attack trooper with melee combat` |
| `dodge` | Normal dodge | Counts as an action (multi-action penalty applies) |
| `fulldodge` | Full dodge | Entire round dedicated to dodging — no other actions |
| `parry` | Normal parry | Melee defense, counts as an action |
| `fullparry` | Full parry | Entire round dedicated to parrying |
| `aim` | Aim at target | +1D to next attack, stackable to +3D over multiple rounds |
| `cover` | Take cover | Uses room's available cover level |
| `flee` | Attempt to escape | Opposed Running roll vs. fastest opponent |
| `pass` | Do nothing | Generates a generic auto-pose |

**Multi-action declaration:** You can declare multiple actions in one round. Each additional action imposes −1D to ALL rolls:
```
> attack trooper          (1 action: full dice)
> dodge                    (2nd action: −1D to both attack and dodge)
```

**Full defense rules:**
- `fulldodge` or `fullparry` must be your ONLY action — you can't attack and full dodge
- Full dodge ADDS your dodge roll to the difficulty for ALL incoming ranged attacks
- Normal dodge REPLACES the base difficulty — which can be worse if you roll low

**CP spending on attacks:** `attack trooper cp 3` spends 3 Character Points on the attack roll. CP dice are rolled after your attack roll and added (they explode on 6, no mishap on 1). CP and Force Points cannot be used in the same round.

**Soak CP:** `soak 2` pre-declares 2 CP to add to your Strength resistance roll if you're hit. Max 5 per R&E. Only spent if you're actually hit.

### 🔧 Developer Internals

**`CombatAction` dataclass** (lines 162–172): `action_type: ActionType`, `skill`, `target_id`, `weapon_damage`, `weapon_key`, `cp_spend`, `stun_mode`, `description`.

**`ActionType` enum** (lines 117–128): ATTACK, DODGE, FULL_DODGE, PARRY, FULL_PARRY, AIM, FLEE, COVER, USE_ITEM, FORCE_POWER, OTHER.

**`declare_action()`** (lines 591–629): Validation rules:
- Full dodge/parry must be the only action (and no other actions can follow)
- CP and FP are mutually exclusive in the same round (R&E p55)
- Must have enough CP to spend
- Appends to `Combatant.actions` list

**`clear_actions()`**: Wipes the action list and resets dodge cache (re-declare means fresh roll).

**`all_declared()` / `undeclared_combatants()`**: Check if every active combatant has at least one action declared. Used by the command layer to trigger auto-resolve.

---

## 4. Ranged Attack Resolution

### Player Rules

When you fire a blaster (or any ranged weapon), the attack works like this:

1. **Base difficulty** comes from the range band to your target:
   - Point-blank: Very Easy (5)
   - Short range: Easy (10)
   - Medium range: Moderate (15)
   - Long range: Difficult (20)

2. **Dodge modifies difficulty:**
   - If the target declared a normal dodge: their dodge roll **replaces** the base difficulty (which can backfire if they roll low!)
   - If the target declared a full dodge: their dodge roll **adds** to the base difficulty
   - Dodge is rolled once per round and cached — the same roll applies to all incoming ranged attacks

3. **Cover adds to difficulty:** If the target is behind cover, additional dice are rolled and added to the difficulty (+1D for quarter cover, +2D for half, +3D for three-quarter). Full cover blocks targeting entirely.

4. **You roll your weapon skill** (Blaster, Bowcaster, etc.) with all modifiers (wound penalty, multi-action penalty, armor DEX penalty, aim bonus, Force Point doubling, CP spending).

5. **If your roll ≥ total difficulty: HIT.** Proceed to damage resolution.

### What You See

```
  ▸ Kaelin fires at Stormtrooper with blaster — HIT — Wounded!
    (Roll: 18 vs Diff: Short(10) + Cover(1/2) 6 = 16 · Damage 14 vs Soak 9 → Wounded)
```

A miss looks dimmer:
```
  Kaelin shoots at Stormtrooper with blaster — barely misses!
    (Roll: 12 vs Diff: Short(10) + FullDodge 8 = 18)
```

### 🔧 Developer Internals

**`_resolve_ranged_attack()`** (lines 825–981):

1. Determines range band via `get_range(actor_id, target_id)` → `RangeBand` enum (5/10/15/20/99)
2. Checks full cover (level 4) — blocks targeting entirely
3. Attacking from cover degrades attacker's cover to quarter (peeking out)
4. **Dodge calculation** (v22 audit #7, #8):
   - Uses `target_c.dodge_roll_cached` if already rolled this round (one roll per round rule)
   - Otherwise: rolls dodge pool with wound/multi-action/armor/FP penalties
   - Normal dodge: `dodge_replaces = True`, dodge value replaces base difficulty
   - Full dodge: dodge value adds to base difficulty
5. **Cover bonus**: Rolls `COVER_DICE[level]`D, adds total to difficulty
6. **Total difficulty**: `base + dodge_bonus + cover_bonus` (or `dodge_value + cover_bonus` for replacement)
7. Rolls attack pool, applies CP spending, checks `attack_total >= total_difficulty`
8. On hit: calls `_apply_damage()`

**Attack pool construction** (lines 776–793):
```python
attack_pool = char.get_skill_pool(action.skill, skill_reg)
attack_pool = apply_wound_penalty(attack_pool, char.total_penalty_dice)
attack_pool = apply_multi_action_penalty(attack_pool, num_actions)
# Armor DEX penalty (v22)
attack_pool = apply_wound_penalty(attack_pool, armor_dex_pen.dice)
# Force Point doubles
if actor.force_point_active:
    attack_pool = apply_force_point(attack_pool)
# Aim bonus
attack_pool.dice += actor.aim_bonus
```

---

## 5. Melee Attack Resolution

### Player Rules

Melee combat (fists, vibroblades, lightsabers) uses **opposed rolls** — your attack skill vs. the defender's parry skill. The higher total wins.

**Defense skill matching:**
- Brawling attacks → defended by Brawling Parry
- Melee weapon attacks → defended by Melee Parry (or Lightsaber if the defender has it and it's higher)
- Lightsaber attacks → defended by Lightsaber or Melee Parry (whichever is higher)

**R&E melee modifiers:**
- Unarmed defender vs. armed attacker: **+10 flat bonus** to the attacker's roll
- Armed defender (parry/lightsaber) vs. unarmed attacker: **+5 flat bonus** to the parry roll

If no defense is declared, the attacker rolls against the weapon's listed difficulty number instead (Easy/Moderate/Difficult from weapons.yaml).

### 🔧 Developer Internals

**`_resolve_melee_attack()`** (lines 983–1106):
1. Builds defense pool via `get_defense_skill()` (lines 73–112) — determines appropriate parry skill
2. If defender declared parry: opposed roll with melee modifiers as FLAT bonuses to roll totals (not DicePool additions — v22 audit #15 fix)
3. If no defense declared: difficulty check against weapon's `melee_difficulty` field (v22 audit #16)
4. CP spending added to attack total after roll
5. Applies `_apply_damage()` on hit

**`get_defense_skill()`** (lines 73–112): Returns `(skill_name, pool)`:
- Ranged → dodge
- Brawling → brawling parry
- Lightsaber → lightsaber if defender has it (by pips comparison), else melee parry
- Other melee → melee parry, with lightsaber override if defender's lightsaber is higher

---

## 6. Damage Resolution

### Player Rules

When an attack hits, the game rolls weapon damage vs. target's resistance (Strength + armor). The difference determines the wound:

| Damage Margin | Result |
|---------------|--------|
| ≤ 0 | No Damage |
| 1–3 | Stunned (−1D, wears off in 2 rounds) |
| 4–8 | Wounded (−1D permanent until healed) |
| 9–12 | Incapacitated (out of the fight) |
| 13–15 | Mortally Wounded (death roll each round) |
| 16+ | Dead |

**Melee damage** uses STR + weapon bonus. A character with 3D Strength swinging a Vibroblade (STR+3D) rolls 6D damage.

**Force Point on melee:** Doubles your Strength but NOT the weapon bonus. So 3D STR + 3D vibroblade with FP = 6D STR + 3D weapon = 9D total (not 12D).

**Armor** adds to your Strength for resistance. A character with 3D STR wearing Stormtrooper Armor (+1D energy / +2D physical) resists a blaster bolt with 4D (3D + 1D energy protection).

**Stun mode:** Blasters set to stun roll damage normally, but any result more severe than Stunned becomes "Stunned — Unconscious" instead. You can't kill someone with a stun blast.

### 🔧 Developer Internals

**`_apply_damage()`** (lines 1108–1253):

1. **Parse damage string:** Handles `"STR+2D"` notation for melee (splits STR pool + weapon bonus, Force Point doubles STR only) and flat `"4D"` for ranged (FP doubles entire pool)
2. **Build soak pool:** `target.strength + armor_protection(energy=is_ranged)` with wound penalty applied
3. **Soak CP:** If defender pre-declared soak CP and was hit, rolls CP dice (max 5) and adds to soak total, deducts from character_points
4. **Damage margin:** `damage_roll.total - soak_total`
5. **Stun mode:** If `action.stun_mode` and margin > 3, caps at "Stunned — Unconscious" (v22 audit #11)
6. **Wound application:** Calls `target.apply_wound(damage_margin)` which uses `WoundLevel.from_damage_margin()` and handles escalation
7. **Narrative generation:** Two-line format with verb variety, wound color escalation (dim for no damage, yellow for stunned, bright yellow for wounded, bold red for incap/mortal/dead), and wound drama text for severe results

---

## 7. Cover System

### Player Rules

Some rooms have cover available. Use the `cover` command to take cover:

| Cover Level | Bonus to Attacker's Difficulty | Notes |
|-------------|-------------------------------|-------|
| None | +0 | No cover in this room |
| 1/4 Cover | +1D | Peeking around a corner |
| 1/2 Cover | +2D | Behind a crate or wall section |
| 3/4 Cover | +3D | Barely exposed |
| Full Cover | Can't be targeted | But you can't attack either |

**Key rules:**
- Cover level is limited by the room's `cover_max` property (set by builders)
- Attacking from cover **degrades your cover to 1/4** (you have to peek out to shoot)
- Cover persists across rounds until you attack or move
- Cover only protects against ranged attacks, not melee

### 🔧 Developer Internals

**Constants** (lines 131–159): `COVER_NONE` through `COVER_FULL` (0–4), `COVER_DICE` dict mapping level to bonus dice count, `COVER_NAMES` for display.

**`_resolve_cover()`** (lines 1304–1342): Parses requested level from action description, clamps to `self.cover_max`. Sets `actor.cover_level`.

**Cover applied in ranged attacks** (lines 919–927): Rolls `COVER_DICE[level]`D and adds the total to the difficulty.

---

## 8. Fleeing Combat

### Player Rules

Type `flee` to attempt to escape. The game makes an **opposed Running roll** — your Running skill vs. the highest-initiative opponent's Running skill. Win and you escape; lose and you're stuck for another round.

If no opponents remain, you flee automatically.

### 🔧 Developer Internals

**`_resolve_flee()`** (lines 1344–1379): Uses `opposed_roll()` with actor's Running vs. highest-initiative opponent's Running, both with wound/multi-action penalties. On success, sets `c.is_fleeing = True` — removed during cleanup.

---

## 9. Aim

### Player Rules

Type `aim` to spend your action taking careful aim. You gain **+1D to your next attack**, stackable up to **+3D** over multiple rounds of aiming. The bonus resets to 0 after you fire. Aiming is most effective when used 2–3 rounds in succession before a single devastating shot.

### 🔧 Developer Internals

**`_resolve_aim()`** (lines 1296–1302): `actor.aim_bonus = min(actor.aim_bonus + 1, 3)`. Applied in `_resolve_attack()` at line 792 and reset to 0 after firing.

---

## 10. PvP Consent and Security Zones

### Player Rules

PvP combat is gated by security zones:

| Zone | PvE | PvP | Example |
|------|-----|-----|---------|
| Secured | Blocked | Blocked | Mos Eisley Core, Imperial Garrison |
| Contested | Allowed | Requires challenge/accept | Spaceport, Cantina, most urban |
| Lawless | Unrestricted | Unrestricted | Jundland Wastes, Nar Shaddaa Undercity |

In contested zones, you must `challenge <player>` and they must `accept` before PvP can begin. Challenges expire after 10 minutes.

**Bounty Hunter override:** Guild members with an active claimed contract can bypass PvP consent in contested zones for their target.

### 🔧 Developer Internals

**File:** `parser/combat_commands.py` — PvP consent tracking (lines 41–47):
- `_pvp_consent: dict[tuple, float]` — Pending challenges with timestamps
- `_pvp_active: dict[tuple, float]` — Accepted PvP pairs
- `_PVP_CHALLENGE_TTL = 600` — 10-minute expiry

Security zone checks are performed before attack commands are processed, gating on the zone's effective security level (which can be temporarily modified by the Director AI).

---

## 11. NPC Combat AI

### Player Rules

NPCs fight using one of five behavioral profiles that determine how they select targets, when they dodge, and when they flee:

| Profile | Attack Style | Defense | Flees At | Target Selection |
|---------|-------------|---------|----------|-----------------|
| **Aggressive** | Attacks best target | Dodges when wounded | Mortally Wounded | Most wounded (easiest kill) |
| **Defensive** | Attacks opportunistically | Prefers dodge/cover | Incapacitated | Random |
| **Cowardly** | Only fights if cornered | Takes cover first | Wounded | Most wounded (safest) |
| **Berserk** | Always attacks | Never dodges | Never | Strongest (biggest threat) |
| **Sniper** | Aims then attacks | Uses cover | Wounded | Most wounded (easiest kill) |

Default archetype mappings: Stormtroopers are aggressive, thugs are berserk, merchants are cowardly, scouts are defensive, dark jedi are berserk.

### 🔧 Developer Internals

**File:** `engine/npc_combat_ai.py` (~461 lines)

**`CombatBehavior` enum** (lines 39–44): AGGRESSIVE, DEFENSIVE, COWARDLY, BERSERK, SNIPER.

**`npc_choose_actions()`** (lines 239–350): Decision tree:
1. Check wound level vs. `_FLEE_THRESHOLD[behavior]` → FLEE if exceeded
2. `_select_target()` — Berserk picks healthiest (min wound_level), Aggressive/Sniper/Cowardly pick most wounded (max wound_level), Defensive picks random
3. `_get_npc_weapon()` — Reads `equipped_weapon` from Character, falls back to brawling
4. Behavior-specific logic:
   - Berserk: single attack, no defense, never dodges
   - Sniper: aims for first 1–2 rounds, then attacks from cover
   - Aggressive: attack + dodge (2 actions with multi-action penalty) when wounded, single attack when healthy
   - Defensive: dodge + attack (prioritizes defense), takes cover when available
   - Cowardly: takes cover first, attacks only if already in cover

**`build_npc_character()`** (lines 108–143): Constructs a `Character` object from NPC DB row's `char_sheet_json`. Reads weapon from `ai_config_json` as fallback.

**`DEFAULT_ARCHETYPE_BEHAVIOR`** and **`DEFAULT_ARCHETYPE_WEAPONS`** (lines 57–91): Maps like `"stormtrooper" → "aggressive"` and `"stormtrooper" → "blaster_rifle"`.

---

## 12. Combat Narrative and Flavor

### Player Rules

Combat output uses a two-line format for every action:

**Line 1 (Story):** Bold text with narrative verb variety and wound color escalation.
**Line 2 (Mechanics):** Dim text showing exact rolls, difficulties, damage, and soak.

Miss margin affects flavor text: narrow misses say "barely misses!" or "grazes the air!" while wide misses say "misses wildly!" or "the shot sails well past!" Severe wounds get drama beats: "staggers, struggling to stay on their feet" for Wounded Twice, "collapses, unable to continue" for Incapacitated.

Target players see a special "◆ YOU" variant in bright red so they immediately notice they've been hit.

### 🔧 Developer Internals

**Verb variety pools** (lines 243–274): Keyed by weapon skill. `_pick_verb(skill, seed)` selects from the pool using `seed % len(pool)` for reproducibility.

**Miss flavor** (lines 259–274): `_miss_flavor(margin, ranged)` selects "close" or "wide" pool based on margin threshold (≤3 vs >3).

**Wound color** (lines 223–238): `_wound_color()` maps wound text to ANSI colors: DIM for no damage, YELLOW for stunned, BRIGHT_YELLOW for wounded, BRIGHT_RED for incapacitated, BOLD+BRIGHT_RED for mortal/dead.

**File:** `engine/combat_flavor.py` (~280 lines) — FLAVOR_MATRIX auto-pose system:
- `APPROACH_VERBS`: Per-skill verb pools for narrative attack descriptions
- `MARGIN_RANGES`: miss_wild (-999 to -6), miss_close (-5 to -1), graze (0 to 2), solid (3 to 7), devastating (8+)
- `generate_auto_pose()`: Combines approach verb + connection text (margin-dependent) + wound result into a complete pose sentence
- `generate_pass_pose()`: Generic inaction pose for `pass` command
- `generate_compound_npc_pose()`: Combines multiple action fragments into one sentence for multi-action NPCs

---

## 13. The Posing System

### Player Rules

After resolution, there's a short **pose window** where you can write a custom narrative description of what your character did:

```
> pose Kaelin ducks behind the cargo crate, snapping off two quick shots at the trooper. The first goes wide but the second catches him in the shoulder.
```

If you don't write a pose within the grace period, the system generates an auto-pose using the flavor matrix. Type `pass` to explicitly skip posing and use the auto-generated text.

Poses are delivered in initiative order — highest initiative poses appear first in the action log.

### 🔧 Developer Internals

**Pose state** tracked in `CombatInstance._pose_state: dict[int, dict]` with keys: `status` ("pending"/"ready"/"passed"), `text`, `initiative`.

**`set_pose_status()`**: Updates a combatant's pose state.
**`all_poses_in()`**: Returns True when no combatants are "pending".
**`get_sorted_poses()`**: Returns `(initiative, char_id, text)` tuples sorted by initiative descending for the action log.
**`generate_auto_pose()`** (lines 1507–1567): Delegates to `combat_flavor` module, assembles one pose fragment per `ActionResult` in `_round_results`.
**`build_private_briefing()`** (lines 1569–1650): Builds a personal summary for each player showing their actions and outcomes plus incoming attacks targeting them, with a prompt to write their pose.

---

## 14. Death, Mortal Wounds, and Stun Recovery

### Player Rules

**Mortal wound death roll:** Each round you're mortally wounded, roll 2D. If the result is less than the number of rounds you've been mortally wounded, you die. Round 1: need to roll ≥ 1 (impossible to die). Round 7: need ≥ 7 (50/50). The longer you go without medical attention, the worse your odds.

**Stun recovery:** Each stun hit has a 2-round timer. When all stun timers expire, you recover to Healthy (if no other wounds). Multiple stuns stack their −1D penalties, and if total stuns ≥ STR dice, you're knocked unconscious.

**Death and respawn:** When killed, your character respawns at a safe location. No permadeath. Equipment is preserved.

### 🔧 Developer Internals

**`_cleanup()`** (lines 1381–1453):
1. Resets `force_point_active` flag on all combatants
2. Ticks stun timers: decrements each timer, removes expired ones. If all stuns expire and wound_level is STUNNED, resets to HEALTHY
3. **Death roll**: For mortally wounded, increments `mortally_wounded_rounds`, rolls 2D, if `roll < rounds_MW` → DEAD
4. Removes fled combatants (`is_fleeing` flag) and dead combatants

---

## 15. Web Client Combat Panel

### Player Rules

The web client displays a dedicated combat panel with:
- **Wound pips** — Color-coded health indicators for all combatants
- **Initiative order** — Who goes when
- **Declared actions** — What each combatant plans to do
- **★ Viewer marker** — Your character highlighted
- **Phase labels & round badge** — Current phase and round number
- **Cover and aim indicators** — Visual status for tactical information

### 🔧 Developer Internals

**`to_hud_dict(viewer_id)`** (lines 471–561): Serializes combat state for WebSocket clients. Returns JSON-safe dict with:
- `active`, `round`, `phase`
- `combatants[]`: Each has `id`, `name`, `is_player`, `wound_level`, `wound_name`, `initiative`, `declared`, `action_summary`, `pose_status`, `cover`, `aim_bonus`, `is_fleeing`
- `your_actions[]`: Viewer's own declared actions
- `waiting_for[]`: Names of undeclared combatants
- `pose_deadline`: ISO timestamp for pose window expiry

---

## 16. Player Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `attack` | `attack <target> [with <skill>] [cp <n>]` | Attack a target |
| `dodge` | `dodge` | Normal dodge (counts as action) |
| `fulldodge` | `fulldodge` | Full dodge (only action this round) |
| `parry` | `parry` | Normal melee parry |
| `fullparry` | `fullparry` | Full melee parry |
| `aim` | `aim` | +1D to next attack (max +3D) |
| `cover` | `cover [half\|full\|quarter]` | Take cover |
| `flee` | `flee` | Attempt to escape combat |
| `pass` | `pass` | Skip posing, use auto-pose |
| `combat` | `combat` | Show combat status |
| `combat rolls` | `combat rolls` | Show detailed dice for this round |
| `challenge` | `challenge <player>` | Request PvP in contested zone |
| `accept` | `accept` | Accept PvP challenge |
| `decline` | `decline` | Decline PvP challenge |
| `soak` | `soak <n>` | Pre-declare CP for damage resistance (max 5) |
| `resolve` | `resolve` | Force-resolve round (admin) |
| `disengage` | `disengage` | Leave combat when it's over |

---

## 17. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/combat.py` | ~1,738 | CombatInstance, initiative, declaration, ranged/melee resolution, damage/soak, cover, flee, aim, posing system, HUD serialization |
| `engine/combat_flavor.py` | ~280 | FLAVOR_MATRIX auto-pose generation, approach verbs, margin ranges, compound NPC poses |
| `engine/npc_combat_ai.py` | ~461 | 5 behavior profiles, target selection, weapon resolution, action selection, flee thresholds, archetype defaults |
| `parser/combat_commands.py` | ~1,954 | 19+ player commands, PvP consent, NPC auto-declare, security zone gates, combat lifecycle management |
| `engine/character.py` | ~588 | WoundLevel, wound escalation, stun timers, armor penalties, Character Points |
| `engine/dice.py` | ~381 | Roll engine, multi-action penalty, wound penalty, CP dice, Force Point doubling |
| `data/weapons.yaml` | ~279 | 22 weapon/armor definitions with damage, ranges, melee difficulties |

**Total combat system:** ~4,900 lines of engine code + ~1,954 lines of command code = ~6,854 lines dedicated to ground combat, plus shared dependencies.

---

*End of Guide #3 — Ground Combat*
*Next: Guide #4 — Security Zones*
