# SW_MUSH — Competitive Analysis Feature Designs
## Consolidated Design Documents v1.0
### April 13, 2026 · Opus Session

This document contains individual design specifications for each feature
identified in `competitive_analysis_feature_mining_v1.md` that requires
a dedicated design. Features are organized by the tier system from that
document. Each section is self-contained and can be handed off to Sonnet
independently.

---

# DESIGN A: Consensual Permadeath System

## A.1 Design Philosophy

SW_MUSH does not have permadeath by default. Characters respawn on death.
However, for players who want the highest-stakes PvP experience, consensual
permadeath creates narratively powerful moments — the kind of scene that
becomes server legend.

The system requires:
1. **Explicit mutual consent** — both combatants opt in before the fight
2. **AI review** — Haiku analyzes the combat log post-mortem for legitimacy
3. **Appeal window** — the killed player can appeal to human staff
4. **Full logging** — every action, roll, and pose is preserved
5. **Irrevocability safeguards** — prevent heat-of-the-moment regret

This is WEG's "Game Option: Severe Injuries" (R&E Chapter 11) taken to its
logical conclusion, with modern safety rails.

## A.2 The Consent Protocol

### A.2.1 Initiating a Permadeath Duel

```
challenge <player> /permadeath    — Challenge to a permadeath duel
```

The challenger receives a confirmation gate:

```
═══════════════════════════════════════════════════════════════
  ⚠  PERMADEATH CHALLENGE  ⚠
═══════════════════════════════════════════════════════════════
  You are about to challenge Kael Voss to a fight where the
  loser's character is PERMANENTLY KILLED.

  This cannot be undone. Your character's story ends here if
  you lose. All equipment, credits, CP, and narrative history
  are lost.

  Type 'confirm permadeath' to proceed.
  Type 'cancel' to withdraw.
═══════════════════════════════════════════════════════════════
```

The target receives:

```
═══════════════════════════════════════════════════════════════
  ⚠  PERMADEATH CHALLENGE RECEIVED  ⚠
═══════════════════════════════════════════════════════════════
  Renna Dox has challenged you to a fight to the death.
  If you lose, your character is PERMANENTLY KILLED.

  You are under NO obligation to accept.
  Declining carries no IC or OOC penalty.

  Type 'accept permadeath' to accept.
  Type 'decline' to refuse.
  This challenge expires in 5 minutes.
═══════════════════════════════════════════════════════════════
```

### A.2.2 Consent Requirements

Both players must:
- Type the full confirmation phrase (no aliases, no macros)
- Have been logged in for at least 30 minutes this session (prevents
  impulse-login-and-fight)
- Not be under any buff/debuff effects (fair fight)
- Be in a Lawless or Contested security zone (no arena duels in secured
  space — this is a narrative event, not a sport)
- Have at least 100 hours of total playtime on this character (prevents
  throwaway characters used as griefer tools)

### A.2.3 The 60-Second Cooling Period

After both players confirm, there is a **mandatory 60-second cooling
period** before combat begins. During this time, either player can type
`withdraw` to cancel with no penalty. A countdown is displayed:

```
  Permadeath duel begins in 60 seconds.
  Either combatant may type 'withdraw' to cancel.
  ... 45 seconds ...
  ... 30 seconds ...
  ... 15 seconds ...
  The duel has begun. May the Force be with you.
```

This cooling period is non-negotiable. It exists to prevent social
pressure from overriding judgment.

## A.3 Combat Mechanics

### A.3.1 Modified Combat Rules

Permadeath duels use the standard combat engine (`engine/combat.py`) with
these modifications:

- **No fleeing.** The `flee` command is disabled.
- **No external interference.** Other characters cannot join, attack either
  combatant, or use skills/Force powers on them. The room is "sealed" for
  the duel's duration.
- **Force Points are allowed.** These are dramatically appropriate.
- **Character Points are allowed.** CP spending is the player's choice.
- **The Dead wound level is fatal.** Instead of triggering respawn, a
  DEAD result triggers the permadeath sequence.
- **Mortally Wounded still allows death rolls.** The loser only dies if
  they actually reach DEAD (via the death roll failing, or another hit
  while MW). A lucky MW character can still survive.

### A.3.2 The Kill Moment

When a combatant reaches DEAD:

1. Combat ends immediately.
2. Both players are shown a narrative summary.
3. The killed character enters a **72-hour grace period** during which the
   appeal process runs.
4. The character is flagged `permadeath_pending` — they cannot log in or be
   played, but are not yet deleted.
5. The AI review fires automatically (see A.4).
6. The surviving character receives no immediate reward beyond the narrative
   consequence. (No loot — this isn't a loot mechanic.)

### A.3.3 The Death Narrative

The auto-pose system generates a final death narrative using the combat
flavor matrix, but extended with a gravitas tier:

```
  Kael Voss crumples to the ground, the light fading from his eyes.
  The blaster wound in his chest still smokes. In the silence that
  follows, only the hum of Nar Shaddaa's ventilation systems remains.

  Kael Voss has been permanently killed.
```

The surviving player may write a final pose describing the aftermath. The
killed player may write a final "last words" pose if they choose. Both are
preserved in the scene log.

## A.4 AI Review System

### A.4.1 Purpose

The AI review exists to catch obvious exploitation:
- One character with 12D combat skills vs. one with 2D (stat mismatch)
- Manipulation or coercion in the pre-duel conversation
- Signs of OOC coordination for griefing
- Suspicious timing (new character immediately challenged by veteran)

The AI review does NOT second-guess legitimate PvP outcomes. A fair fight
where one player gets unlucky is valid.

### A.4.2 Implementation

Within 5 minutes of the kill, a Haiku API call fires:

```python
PERMADEATH_REVIEW_PROMPT = """
You are reviewing a consensual permadeath duel in a Star Wars MUSH game.
Both players explicitly consented to permanent character death before
the fight began.

KILLER: {killer_name}
  Account playtime: {killer_hours} hours
  Character age: {killer_char_age} days
  Combat skills: {killer_combat_summary}

KILLED: {killed_name}
  Account playtime: {killed_hours} hours
  Character age: {killed_char_age} days
  Combat skills: {killed_combat_summary}

COMBAT LOG:
{full_combat_log}

PRE-DUEL CONVERSATION (last 20 lines in the room before challenge):
{pre_duel_chat}

Evaluate this duel on three criteria:

1. FAIRNESS: Was there a severe stat mismatch (>4D difference in primary
   combat skills) that suggests exploitation? Note: some mismatch is
   normal and expected. Flag only extreme cases.

2. CONSENT INTEGRITY: Does the pre-duel conversation show signs of
   coercion, manipulation, or pressure to accept? Signs include: repeated
   asks after initial refusal, threats of OOC consequences, promises
   contingent on accepting.

3. SUSPICIOUS PATTERNS: Is the killed character suspiciously new (created
   within 7 days)? Is there any sign this was coordinated to grief?

Respond in JSON:
{
  "verdict": "LEGITIMATE" | "FLAG_FOR_REVIEW" | "BLOCK",
  "fairness_score": 1-10,
  "consent_score": 1-10,
  "suspicion_score": 1-10,
  "reasoning": "One paragraph explaining your assessment.",
  "recommended_action": "none" | "admin_review" | "reverse_death"
}
"""
```

### A.4.3 Verdict Handling

| AI Verdict | Action |
|---|---|
| `LEGITIMATE` (all scores ≥ 7) | Death proceeds. Appeal window still open. |
| `FLAG_FOR_REVIEW` (any score 4-6) | Death paused. Admin notified. Manual review required within 72 hrs. |
| `BLOCK` (any score ≤ 3) | Death auto-reversed. Both players notified. Admin notified for investigation. |

### A.4.4 Cost

One Haiku call per permadeath event. ~2,000 tokens input, ~300 tokens output.
Cost: ~$0.004 per review. At even 10 permadeaths per month (extremely high),
this is $0.04/month — negligible against the $20 budget.

## A.5 The Appeal Process

### A.5.1 Filing an Appeal

The killed player can appeal within 72 hours:

```
@appeal                           — File a permadeath appeal
@appeal/reason <text>             — Explain why you believe the death
                                    should be reversed
```

Appeals are stored in a `permadeath_appeals` table and flagged for admin
review.

### A.5.2 Admin Review

Admins use `@permadeath/review <appeal_id>` to see:
- Full combat log with dice rolls
- Pre-duel conversation transcript
- AI review verdict and scores
- The appellant's stated reason
- Both characters' full stat sheets at time of duel
- Account history (previous permadeaths, appeals, warnings)

The admin can:
- `@permadeath/uphold <id>` — Death stands. Character is permanently deleted
  after the 72-hour window.
- `@permadeath/reverse <id>` — Death is reversed. Character is restored.
  The killer is notified (but not penalized unless abuse is found).
- `@permadeath/extend <id> <hours>` — Extend the review window.

### A.5.3 No-Appeal Closure

If no appeal is filed within 72 hours, and the AI verdict was `LEGITIMATE`,
the death is finalized automatically.

## A.6 Character Deletion

When a permadeath is finalized:
1. The character's `+sheet`, equipment, credits, and narrative records are
   preserved in a `deceased_characters` archive table.
2. The character is removed from all organizations, housing guest lists,
   vendor droid ownership.
3. Housing owned by the character enters a 7-day foreclosure period (can be
   claimed by org members or goes to market).
4. Ships are flagged as "abandoned" in their current location.
5. The Director AI is notified and may generate a "death news" event:
   "Reports indicate that [name] was killed on [planet]. [Faction] forces
   are investigating."
6. The PC narrative short record is updated one final time: "[Name] — 
   Deceased. Killed by [killer] on [date] at [location]."

## A.7 The Scar System (Non-Permadeath Companion)

For ALL combat (not just permadeath duels), when a character reaches
Incapacitated or Mortally Wounded and survives:

### A.7.1 Scar Record

```sql
-- Added to characters table or character attributes JSON
-- Each scar is an entry in a JSON array
{
  "scars": [
    {
      "date": "2026-04-13",
      "wound_level": "mortally_wounded",
      "weapon": "Heavy Blaster Pistol",
      "attacker": "Renna Dox",
      "location": "Lower Nar Shaddaa",
      "description": "Blaster wound to the chest"
    }
  ]
}
```

### A.7.2 Scar Display

Scars appear on `+sheet` in a dedicated section:

```
═══════════════════════════════════════════════════════════
  SCARS
───────────────────────────────────────────────────────────
  ● Blaster wound to the chest (Mortally Wounded)
    From Renna Dox on Nar Shaddaa — 2026.04.13
  ● Vibroblade slash across the left arm (Incapacitated)
    From a Rodian Thug on Tatooine — 2026.03.28
═══════════════════════════════════════════════════════════
```

### A.7.3 Narrative Integration

Scars are injected into the PC narrative short record during the nightly
Haiku summarization. NPCs can reference them: "I see you've taken some
hits. That chest wound looks recent."

The scar `description` is auto-generated from the weapon type and a random
body location using the existing hit location logic.

## A.8 Schema

```sql
CREATE TABLE IF NOT EXISTS permadeath_duels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    killer_id       INTEGER NOT NULL,
    killed_id       INTEGER NOT NULL,
    room_id         INTEGER NOT NULL,
    combat_log      TEXT NOT NULL,           -- full combat log JSON
    pre_duel_chat   TEXT,                    -- last 20 lines before challenge
    ai_verdict      TEXT,                    -- JSON from Haiku review
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/upheld/reversed
    appeal_text     TEXT,
    admin_reviewer  INTEGER,
    admin_notes     TEXT,
    created_at      REAL NOT NULL,
    resolved_at     REAL
);

CREATE TABLE IF NOT EXISTS deceased_characters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    char_name       TEXT NOT NULL,
    char_data       TEXT NOT NULL,            -- full character JSON snapshot
    killer_name     TEXT,
    death_location  TEXT,
    narrative_record TEXT,                    -- final short record
    duel_id         INTEGER REFERENCES permadeath_duels(id),
    created_at      REAL NOT NULL
);
```

## A.9 Files Affected

| File | Changes |
|---|---|
| `parser/combat_commands.py` | New `ChallengePermadeathCommand`, modified `AttackCommand` for duel mode |
| `engine/combat.py` | Duel mode flag, disable flee, sealed room, death handler override |
| `engine/permadeath.py` | NEW — consent protocol, AI review, appeal handling, character archival |
| `parser/admin_commands.py` | `@permadeath/review`, `@permadeath/uphold`, `@permadeath/reverse` |
| `db/migrations/` | `permadeath_duels` and `deceased_characters` tables |
| `engine/director.py` | Death news event generation |

**Estimated effort:** 12-16 hours total.

---

# DESIGN B: Think Command & Internal Monologue

## B.1 Purpose

The `think` command lets players write internal monologue visible only to
themselves and the AI systems. It feeds into the PC Narrative Memory
pipeline, giving NPCs and the Director insight into character motivation
without the character saying anything aloud.

## B.2 Command

```
think <text>              — Record an internal thought
```

Output to the player:

```
  You think: I don't trust this Rodian. Something about the way
  he keeps glancing at the door...
```

No one else in the room sees this. It is not broadcast.

## B.3 Storage

Thoughts are logged to the existing `pc_action_log` table:

```python
await db.insert_action_log(
    char_id=char["id"],
    event_type="thought",
    event_summary=thought_text[:500],  # cap at 500 chars
    zone=current_zone,
    room_id=room_id
)
```

No new table required. The `pc_action_log` table from the PC Narrative
Memory design doc already handles this.

## B.4 Summarization Integration

The nightly Haiku summarization prompt (PC Narrative Memory doc §4.3) is
modified to include thoughts:

```
RECENT THOUGHTS (last 24 hours):
{thought_entries}

When updating the long record and short record, you may reference the
character's internal state if it has observable consequences. Do NOT
include private thoughts in the short record — the short record is
what NPCs would know. Instead, note behavioral patterns: "seems
paranoid," "appears conflicted," "has been unusually quiet."
```

## B.5 Cooldown

No cooldown. Players should be encouraged to use `think` freely. However,
only the most recent 20 thoughts per 24-hour period are included in the
summarization prompt to prevent context bloat.

## B.6 Implementation

| File | Changes |
|---|---|
| `parser/builtin_commands.py` or new `parser/rp_commands.py` | `ThinkCommand` class |
| `engine/narrative.py` | Include thoughts in summarization prompt |

**Estimated effort:** 1-2 hours.

---

# DESIGN C: World Lore System (Lorebook Pattern)

## C.1 Purpose

A keyword-triggered context injection system for the Director AI and NPC
dialogue. Instead of carrying the entire world state in every prompt,
relevant lore entries are dynamically loaded based on current game context.

## C.2 Schema

```sql
CREATE TABLE IF NOT EXISTS world_lore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    keywords    TEXT NOT NULL,       -- comma-separated: "empire,imperial,stormtrooper"
    content     TEXT NOT NULL,       -- the lore text (max ~200 tokens / 800 chars)
    category    TEXT NOT NULL,       -- faction, location, npc, event, item, history
    zone_scope  TEXT,               -- NULL = global, or comma-separated zone IDs
    priority    INTEGER DEFAULT 5,  -- 1-10, higher = inserted first when space is tight
    active      INTEGER DEFAULT 1,  -- 0 = disabled (e.g., outdated event lore)
    created_at  REAL NOT NULL,
    updated_at  REAL
);

CREATE INDEX idx_world_lore_category ON world_lore(category);
CREATE INDEX idx_world_lore_active ON world_lore(active);
```

## C.3 Keyword Matching

```python
def get_relevant_lore(context_text: str, zone_id: str = None, 
                       max_entries: int = 5, max_tokens: int = 800) -> list[dict]:
    """
    Scan context_text for keyword matches against world_lore entries.
    Returns highest-priority matches that fit within max_tokens.
    
    context_text: recent game state text (faction names, location names,
                  player dialogue, recent events)
    zone_id: current zone for scope filtering
    """
    all_entries = _get_active_entries()  # cached, refreshed every 5 min
    matches = []
    
    context_lower = context_text.lower()
    for entry in all_entries:
        # Zone scope check
        if entry["zone_scope"] and zone_id:
            if zone_id not in entry["zone_scope"].split(","):
                continue
        
        # Keyword match
        keywords = [k.strip() for k in entry["keywords"].split(",")]
        if any(kw in context_lower for kw in keywords):
            matches.append(entry)
    
    # Sort by priority (highest first), then by specificity (most keywords matched)
    matches.sort(key=lambda e: e["priority"], reverse=True)
    
    # Fit within token budget
    result = []
    total_tokens = 0
    for entry in matches:
        entry_tokens = len(entry["content"].split()) * 1.3  # rough token estimate
        if total_tokens + entry_tokens > max_tokens:
            break
        result.append(entry)
        total_tokens += entry_tokens
    
    return result[:max_entries]
```

## C.4 Integration Points

### C.4.1 Director Faction Turn

In `engine/director.py`, before constructing the faction turn prompt:

```python
# Gather context: which zones have players, which factions are active
context_text = " ".join([
    zone_name for zone_name in active_zones
] + [
    faction_name for faction_name in factions_with_online_members
] + [
    recent_event.summary for recent_event in last_3_events
])

lore_entries = get_relevant_lore(context_text, max_entries=5, max_tokens=600)
lore_block = "\n".join([
    f"[{e['category'].upper()}] {e['title']}: {e['content']}"
    for e in lore_entries
])

# Insert into faction turn prompt
faction_turn_prompt = f"""
{existing_system_prompt}

RELEVANT WORLD CONTEXT:
{lore_block}

{existing_faction_data}
"""
```

### C.4.2 NPC Dialogue

In `npc_brain.py`, before constructing the NPC prompt:

```python
# Context = player's last message + NPC's location + NPC's faction
context_text = f"{player_message} {npc_zone} {npc_faction}"
lore_entries = get_relevant_lore(context_text, zone_id=npc_zone, 
                                  max_entries=3, max_tokens=400)

# Inject into NPC prompt as "things this NPC would know"
```

### C.4.3 Admin Management

```
@lore                             — List all active lore entries
@lore/add <title> = <content>     — Add a new lore entry (interactive prompts for keywords, category, scope)
@lore/edit <id>                   — Edit an existing entry
@lore/disable <id>                — Deactivate an entry
@lore/search <keyword>            — Search entries by keyword
```

## C.5 Seed Data

The initial lore entries are seeded from the architecture doc's world
description. Examples:

```yaml
- title: "The Galactic Empire"
  keywords: "empire,imperial,emperor,palpatine,stormtrooper,vader"
  content: "The Galactic Empire rules the galaxy through military might. Emperor Palpatine dissolved the Senate and rules through fear. The Imperial military includes stormtroopers, Star Destroyers, and TIE fighters. Imperial presence is strongest in Core worlds and along major hyperspace lanes. Dissent is crushed. The Empire's secret weapon, the Death Star, was recently destroyed at Yavin."
  category: "faction"
  zone_scope: null
  priority: 8

- title: "Mos Eisley"
  keywords: "mos eisley,tatooine,cantina,docking bay"
  content: "Mos Eisley is a lawless spaceport on the desert planet Tatooine, in the Outer Rim. Controlled loosely by the Hutt Cartel, it serves as a haven for smugglers, bounty hunters, and criminals. The cantina is the social hub. Imperial patrols are present but stretched thin. Water and shade are precious commodities."
  category: "location"
  zone_scope: "tatooine_mos_eisley,tatooine_outskirts,tatooine_docking"
  priority: 7
```

## C.6 Files Affected

| File | Changes |
|---|---|
| `engine/world_lore.py` | NEW — lore table queries, keyword matching, caching |
| `engine/director.py` | Inject lore context into faction turn prompt |
| `engine/npc_brain.py` | Inject lore context into NPC dialogue prompt |
| `parser/admin_commands.py` | `@lore` admin commands |
| `db/migrations/` | `world_lore` table |
| `data/world_lore_seed.yaml` | Initial lore entries |

**Estimated effort:** 4-6 hours.

---

# DESIGN D: Narrative Tone Per Zone

## D.1 Purpose

Each zone in the game should have a narrative tone string that influences
both Director AI event generation and NPC dialogue style.

## D.2 Configuration

Added to `data/zones.yaml` (or equivalent zone configuration):

```yaml
zones:
  tatooine_mos_eisley:
    narrative_tone: >
      Dangerous and lawless. Deals happen in whispered conversations.
      Everyone is armed. Trust is the scarcest resource. The heat is
      oppressive. Strangers are watched carefully.
  
  tatooine_jundland:
    narrative_tone: >
      Desolate and hostile. The twin suns beat down mercilessly.
      Sandpeople raids are common. Only the desperate or the brave
      travel here. Ancient ruins dot the landscape.
  
  nar_shaddaa_lower:
    narrative_tone: >
      Neon-lit squalor. The Smugglers' Moon never sleeps. Every
      shadow hides a deal or a danger. Credits talk. Morality is
      a luxury. The Hutts control everything that matters.
  
  corellia_coronet:
    narrative_tone: >
      Orderly and proud. Corellians value independence and
      craftsmanship. The Empire maintains a visible but not
      oppressive presence. Shipyards dominate the skyline.
      People are direct and no-nonsense.
  
  kessel_mines:
    narrative_tone: >
      Claustrophobic and toxic. The spice mines are a death
      sentence for prisoners. The air burns. Escape seems
      impossible. Imperial guards are brutal. Hope is a
      dangerous commodity.
```

## D.3 Integration

### D.3.1 Director Faction Turn

The tone for each active zone is appended to the faction turn prompt:

```python
zone_tones = []
for zone_id in active_zones:
    tone = get_zone_tone(zone_id)
    if tone:
        zone_tones.append(f"{zone_id}: {tone}")

prompt += f"\nNARRATIVE TONE PER ZONE:\n" + "\n".join(zone_tones)
```

### D.3.2 NPC Dialogue

In `npc_brain.py`, the zone's tone is injected into the NPC's system prompt:

```python
zone_tone = get_zone_tone(npc_zone)
if zone_tone:
    system_prompt += f"\n\nATMOSPHERE: {zone_tone}"
```

## D.4 Implementation

| File | Changes |
|---|---|
| `data/zones.yaml` or zone config | Add `narrative_tone` field |
| `engine/director.py` | Read and inject zone tones |
| `engine/npc_brain.py` | Read and inject zone tone |

**Estimated effort:** 1-2 hours.

---

# DESIGN E: Environmental Hazards

## E.1 Purpose

Rooms tagged with environmental hazards apply periodic mechanical effects
to characters present, creating resource pressure and making survival gear
relevant.

## E.2 Hazard Types

| Hazard | Planets | Effect | Mitigation |
|---|---|---|---|
| `extreme_heat` | Tatooine (outdoor) | Stamina drain: lose 1 wound level equivalent every 30 min without water | Carry water (consumable), cooling unit (craftable) |
| `toxic_atmosphere` | Kessel (mines) | Strength check (diff 12) every 15 min or take Stunned | Breath mask (purchasable/craftable) |
| `radiation` | Kessel (deep mines) | Technical check (diff 15) every 20 min or equipment degrades | Radiation suit (craftable) |
| `urban_danger` | Nar Shaddaa (lower) | Random pickpocket attempt every 20 min (NPC Sneak vs. PC Perception) | High Perception, secure housing |
| `low_gravity` | Space stations | Dexterity check (diff 8) on room entry or stumble (lose initiative next combat) | Mag boots (purchasable) |
| `wildlife` | Tatooine (Jundland), Kashyyyk | Random creature encounter every 30 min (scales with zone danger) | Travel in groups, Survival skill |

## E.3 Room Configuration

Hazards are stored in room properties JSON:

```json
{
  "environment_hazard": {
    "type": "extreme_heat",
    "severity": 2,
    "check_interval_seconds": 1800,
    "difficulty": 12,
    "skill": "stamina",
    "mitigation_item": "water_canteen"
  }
}
```

Builders set hazards via: `@hazard <type> [severity]` / `@hazard clear`

## E.4 Periodic Check

A new periodic task in `game_server.py` runs every 60 seconds:

```python
async def check_environmental_hazards():
    """Check all occupied rooms for hazard effects."""
    for room_id, occupants in get_occupied_rooms():
        room = await get_room(room_id)
        hazard = room.get("properties", {}).get("environment_hazard")
        if not hazard:
            continue
        
        for char_id in occupants:
            char = await get_character(char_id)
            last_check = char_hazard_timers.get((char_id, room_id), 0)
            
            if time.time() - last_check < hazard["check_interval_seconds"]:
                continue
            
            char_hazard_timers[(char_id, room_id)] = time.time()
            
            # Check for mitigation item in inventory
            if has_mitigation(char, hazard["mitigation_item"]):
                continue
            
            # Perform skill check
            result = await perform_skill_check(
                char, hazard["skill"], hazard["difficulty"]
            )
            
            if not result.success:
                await apply_hazard_effect(char, hazard)
                await send_hazard_warning(char, hazard)
```

## E.5 Hazard Warnings

Players receive atmospheric warning text before the mechanical check:

```
  The twin suns beat down mercilessly. Your mouth is parched,
  your skin burning. Without water, you won't last much longer.
  [Stamina check: difficulty 12]
```

On failure:

```
  The heat overwhelms you. Your vision swims and your legs
  buckle. [-1 wound level from dehydration]
```

On success:

```
  You push through the heat, drawing on your reserves. You're
  still standing — for now.
```

## E.6 Survival Crafting Lane

New schematics for environment-specific gear:

| Schematic | Mitigates | Skill | Components |
|---|---|---|---|
| `cooling_unit` | extreme_heat | droid_repair | 2 energy, 1 metal |
| `breath_mask` | toxic_atmosphere | first_aid | 1 chemical, 1 composite |
| `radiation_suit` | radiation | armor_repair | 3 composite, 1 rare |
| `anti_theft_alarm` | urban_danger | security | 2 energy, 1 chemical |
| `mag_boots` | low_gravity | space_transports_repair | 2 metal, 1 energy |

These items are consumable or durable depending on type. Cooling units
and breath masks are durable (don't degrade). Radiation suits degrade
with each check (10 uses). Anti-theft alarms are single-use per session.

## E.7 Files Affected

| File | Changes |
|---|---|
| `engine/environment.py` | NEW — hazard checking, effect application |
| `game_server.py` | Register periodic hazard check task |
| `parser/admin_commands.py` | `@hazard` builder command |
| `data/schematics.yaml` | 5 new survival schematics |
| `engine/crafting.py` | Handle `output_type: "survival_gear"` |
| Room properties schema | Add `environment_hazard` field |

**Estimated effort:** 6-8 hours.

---

# DESIGN F: Espionage Command Suite

## F.1 Purpose

Give the Intelligence/Espionage profession chain mechanical depth through
four new commands that create a gameplay loop around information gathering
and brokering.

## F.2 Commands

### F.2.1 `scan <player>`

Covertly assess another character's status.

**Skill check:** Perception vs. target's Con (opposed roll via
`perform_skill_check()` with `opposed=True`)

**On success (margin 0-4):**
```
  You discreetly size up Kael Voss.
  Condition: Wounded (favoring his left side)
  Armed: Yes (blaster pistol, holstered)
  Demeanor: Nervous
```

**On success (margin 5+):**
```
  You discreetly size up Kael Voss.
  Condition: Wounded (favoring his left side)
  Armed: Heavy Blaster Pistol (holstered), Vibroblade (concealed boot sheath)
  Credits: Roughly 2,000-5,000 (well-off for this district)
  Demeanor: Nervous, keeps checking the exit
  Faction: Likely Rebel sympathizer (Alliance insignia under collar)
```

**On failure:** Nothing happens. Target is not alerted.

**On fumble:** Target notices you staring.
```
  Kael Voss catches you sizing him up and narrows his eyes.
  "Something I can help you with?"
```

**Cooldown:** 2 minutes per target.

### F.2.2 `eavesdrop [direction]`

Listen to conversations in an adjacent room.

**Skill check:** Perception (difficulty based on room separation)

| Separation | Difficulty |
|---|---|
| Adjacent room (through door) | Moderate (15) |
| Two rooms away | Difficult (20) |
| Through sealed/locked door | Very Difficult (25) |

**On success:** You receive a "muffled" version of the next 5 minutes of
conversation in the target room. The muffling uses the same word-leak
algorithm as the Places `tt` (table-talk) system — 30% of words come
through clearly, quoted speech always leaks.

```
  You press your ear to the wall and listen...
  [Eavesdropping on: Docking Bay 94]
  
  You catch fragments:
  "... the shipment ... need to move it ... before the Imperials ..."
  "... how much ... credits ... Kessel ..."
```

**On failure:** You hear nothing useful.

**On fumble:** You make noise. Characters in the adjacent room see:
```
  You hear a faint shuffling sound from beyond the wall.
```

**Duration:** Active for 5 minutes or until you move rooms.

**Cooldown:** 10 minutes.

### F.2.3 `investigate`

Search the current room for hidden information.

**Skill check:** Search (difficulty based on room type)

| Room Type | Difficulty | Possible Findings |
|---|---|---|
| Residence/Housing | Moderate (15) | Hidden items, security vulnerabilities, personal effects |
| Public area | Difficult (20) | Hidden exits, concealed compartments, recent activity traces |
| Organization HQ | Very Difficult (25) | Faction documents, security codes, personnel records |

**On success:**
```
  You methodically search the area...
  
  FINDINGS:
  ● A concealed compartment behind the wall panel (Security diff 18 to open)
  ● Recent boot prints from at least 3 individuals — military-grade soles
  ● A discarded datacard wedged between crates (may contain data)
```

Findings are procedurally generated based on room properties, occupant
history (who has visited this room recently via the action log), and
organization ownership. The system checks for actual game state, not
random flavor.

**On failure:** "You search carefully but find nothing of note."

**Cooldown:** 30 minutes per room (you can investigate different rooms).

### F.2.4 `+intel`

Package gathered intelligence into a tradeable intel report.

```
+intel create <title>             — Start composing an intel report
+intel add <text>                 — Add a line to the current report
+intel seal                       — Seal the report (makes it tradeable)
+intel list                       — List your intel reports
+intel read <id>                  — Read a report you hold
+intel give <player> <id>         — Give a report to another player
```

Sealed intel reports are inventory items (stored in character attributes
JSON) that can be traded via `give` or the `trade` command. They have
an expiry date (7 days from creation — intel goes stale).

**Faction rewards:** Organizations can set a standing `+intel/bounty`
offering credits for intel reports about rival factions. Delivering an
intel report to a faction leader NPC grants credits and reputation:

| Intel Quality | Credits | Reputation |
|---|---|---|
| Basic (1-2 findings) | 200-500 cr | +5 rep |
| Detailed (3-5 findings) | 500-1,500 cr | +10 rep |
| Critical (security codes, fleet movements, etc.) | 1,500-5,000 cr | +25 rep |

Quality is assessed by the NPC (actually by checking what scan/eavesdrop/
investigate results are referenced in the report text — cross-referencing
against actual game events logged in the action log).

## F.3 Skill Integration

All commands route through `perform_skill_check()` per the architecture
invariant. The relevant WEG D6 R&E skills:

| Command | Primary Skill | Secondary Skill |
|---|---|---|
| `scan` | Perception (opposed by Con) | Investigation (specialization bonus) |
| `eavesdrop` | Perception | Sneak (to avoid detection on fumble) |
| `investigate` | Search | Investigation |
| `+intel` | No check (composition is freeform) | Forgery (for creating false intel — future feature) |

## F.4 Files Affected

| File | Changes |
|---|---|
| `parser/espionage_commands.py` | NEW — ScanCommand, EavesdropCommand, InvestigateCommand, IntelCommand |
| `engine/skill_checks.py` | Opposed roll support (may already exist) |
| `engine/espionage.py` | NEW — eavesdrop muffling, investigate findings generation, intel quality assessment |
| `parser/builtin_commands.py` | Wire `scan`, `eavesdrop`, `investigate` into command registry |

**Estimated effort:** 10-14 hours.

---

# DESIGN G: Achievement System

## G.1 Purpose

Track player milestones across all game systems, providing guided
progression for new players and long-term goals for veterans. Achievements
display on the web client and `+sheet`.

## G.2 Achievement Definition

Achievements are defined in `data/achievements.yaml`:

```yaml
achievements:
  # Combat
  - key: first_blood
    name: "First Blood"
    description: "Win your first combat encounter"
    category: combat
    icon: "⚔️"
    cp_reward: 2
    trigger: {event: "combat_victory", count: 1}
  
  - key: veteran_fighter
    name: "Veteran Fighter"
    description: "Win 50 combat encounters"
    category: combat
    icon: "🎖️"
    cp_reward: 5
    trigger: {event: "combat_victory", count: 50}
    requires: first_blood

  # Space
  - key: first_flight
    name: "First Flight"
    description: "Successfully launch a ship into orbit"
    category: space
    icon: "🚀"
    cp_reward: 2
    trigger: {event: "ship_launch", count: 1}

  - key: kessel_run
    name: "Kessel Run"
    description: "Complete a smuggling run to or from Kessel"
    category: space
    icon: "💨"
    cp_reward: 5
    trigger: {event: "smuggling_complete", zone: "kessel"}

  # Economy
  - key: first_paycheck
    name: "First Paycheck"
    description: "Earn your first 1,000 credits"
    category: economy
    icon: "💰"
    cp_reward: 1
    trigger: {event: "credits_earned_total", count: 1000}

  - key: master_crafter
    name: "Master Crafter"
    description: "Craft a Masterwork-tier item (quality 90+)"
    category: crafting
    icon: "🔧"
    cp_reward: 10
    trigger: {event: "craft_masterwork", count: 1}

  # Social
  - key: first_contact
    name: "First Contact"
    description: "Have a conversation with another player character"
    category: social
    icon: "🤝"
    cp_reward: 1
    trigger: {event: "pc_conversation", count: 1}

  - key: faction_loyalist
    name: "Faction Loyalist"
    description: "Reach rank 3 in any organization"
    category: social
    icon: "🏛️"
    cp_reward: 5
    trigger: {event: "org_rank_reached", count: 3}

  # Exploration
  - key: galaxy_traveler
    name: "Galaxy Traveler"
    description: "Visit all four planets"
    category: exploration
    icon: "🌍"
    cp_reward: 3
    trigger: {event: "planets_visited", count: 4}

  # Force
  - key: force_awakening
    name: "Force Awakening"
    description: "Successfully use a Force power for the first time"
    category: force
    icon: "✨"
    cp_reward: 3
    trigger: {event: "force_power_used", count: 1}

  # Territory
  - key: territory_baron
    name: "Territory Baron"
    description: "Your organization claims 5 rooms"
    category: territory
    icon: "🏰"
    cp_reward: 5
    trigger: {event: "territory_rooms_claimed", count: 5}

  # Espionage (if Design F is implemented)
  - key: information_broker
    name: "Information Broker"
    description: "Successfully sell 10 intel reports"
    category: espionage
    icon: "🕵️"
    cp_reward: 5
    trigger: {event: "intel_sold", count: 10}

  # Permadeath (if Design A is implemented)
  - key: cheated_death
    name: "Cheated Death"
    description: "Survive a Mortally Wounded result in combat"
    category: combat
    icon: "💀"
    cp_reward: 3
    trigger: {event: "survived_mortal_wound", count: 1}
```

## G.3 Schema

```sql
CREATE TABLE IF NOT EXISTS character_achievements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    progress        INTEGER DEFAULT 0,
    completed       INTEGER DEFAULT 0,
    completed_at    REAL,
    UNIQUE(char_id, achievement_key)
);

CREATE INDEX idx_achievements_char ON character_achievements(char_id);
```

## G.4 Achievement Engine

```python
# engine/achievements.py

async def check_achievement(char_id: int, event: str, 
                             count: int = 1, **kwargs):
    """
    Called from game systems when an achievement-relevant event occurs.
    
    Examples:
        await check_achievement(char_id, "combat_victory")
        await check_achievement(char_id, "smuggling_complete", zone="kessel")
        await check_achievement(char_id, "credits_earned_total", count=500)
    """
    relevant = get_achievements_for_event(event)
    for ach in relevant:
        # Check zone/kwargs filters
        if not matches_filters(ach, kwargs):
            continue
        
        # Update progress
        progress = await increment_progress(char_id, ach["key"], count)
        
        if progress >= ach["trigger"]["count"] and not already_completed:
            await complete_achievement(char_id, ach)

async def complete_achievement(char_id: int, achievement: dict):
    """Award the achievement and notify the player."""
    await db.mark_achievement_complete(char_id, achievement["key"])
    
    # Award CP
    if achievement.get("cp_reward"):
        await award_cp(char_id, achievement["cp_reward"], 
                       source=f"Achievement: {achievement['name']}")
    
    # Notify player
    await send_to_char(char_id, 
        f"\n  ★ ACHIEVEMENT UNLOCKED: {achievement['icon']} "
        f"{achievement['name']} ★\n"
        f"  {achievement['description']}\n"
        f"  Reward: {achievement.get('cp_reward', 0)} CP\n")
    
    # Broadcast to room (optional, celebratory)
    await broadcast_to_room(char_room_id,
        f"  {char_name} has earned the achievement: "
        f"{achievement['icon']} {achievement['name']}")
```

## G.5 Hook Points

Achievement checks are inserted into existing systems:

| Event | Hook Location |
|---|---|
| `combat_victory` | `engine/combat.py` → `_cleanup()` after combat ends |
| `ship_launch` | `parser/space_commands.py` → `LaunchCommand` |
| `smuggling_complete` | `parser/smuggling_commands.py` → delivery handler |
| `craft_masterwork` | `engine/crafting.py` → `resolve_craft()` when quality ≥ 90 |
| `force_power_used` | `engine/force_powers.py` → power resolution |
| `credits_earned_total` | `engine/economy_monitor.py` → credit_log insert (faucet events) |
| `planets_visited` | Room entry handler → check planet tracking |
| `pc_conversation` | `say` / `emote` commands when 2+ PCs present |

## G.6 Display

### G.6.1 Telnet: `+achievements`

```
═══════════════════════════════════════════════════════════
  ACHIEVEMENTS — Kael Voss                    12/30 Complete
═══════════════════════════════════════════════════════════
  COMBAT
    ⚔️ First Blood .......................... ★ Complete
    🎖️ Veteran Fighter ..................... 23/50
    💀 Cheated Death ........................ ★ Complete

  SPACE
    🚀 First Flight ........................ ★ Complete
    💨 Kessel Run ........................... ○ Locked

  ECONOMY
    💰 First Paycheck ....................... ★ Complete
    🔧 Master Crafter ....................... ○ Not started

  [... etc ...]
═══════════════════════════════════════════════════════════
```

### G.6.2 Web Client

New "Achievements" panel in the web sidebar. Category tabs. Progress
bars for incomplete achievements. Glow animation on completion.

## G.7 Files Affected

| File | Changes |
|---|---|
| `engine/achievements.py` | NEW — achievement engine, YAML loading, progress tracking |
| `data/achievements.yaml` | NEW — achievement definitions |
| `db/migrations/` | `character_achievements` table |
| `parser/builtin_commands.py` | `AchievementsCommand` |
| `static/client.html` | Achievement panel in web client |
| Various engine files | `check_achievement()` hook calls (see G.5) |

**Estimated effort:** 10-14 hours.

---

# DESIGN H: Buff/Debuff Handler

## H.1 Purpose

A centralized system for managing timed status effects on characters.
Replaces ad-hoc buff implementations across combat stims, Force powers,
environmental effects, food/drink, and hazard conditions.

## H.2 Core API

```python
# engine/buffs.py

class Buff:
    buff_type: str          # "combat_stim", "force_control_pain", "dehydration"
    source: str             # "item:stimpack", "force:control_pain", "env:extreme_heat"
    stat_modifiers: dict    # {"dexterity": 3, "strength": -2}  # pips, not dice
    duration_seconds: int   
    started_at: float
    stacks: int             # how many times this buff is stacked
    max_stacks: int
    display_name: str       # "Combat Stimulant"
    display_color: str      # ANSI color for telnet display

class BuffHandler:
    async def add(self, char_id: int, buff: Buff) -> bool:
        """Add or stack a buff. Returns True if newly applied."""
    
    async def remove(self, char_id: int, buff_type: str) -> bool:
        """Remove a buff by type. Returns True if found."""
    
    async def get_active(self, char_id: int) -> list[Buff]:
        """Return all active (non-expired) buffs."""
    
    async def get_modifier(self, char_id: int, stat: str) -> int:
        """Sum all active buff modifiers for a stat (in pips)."""
    
    async def tick(self):
        """Called every 60 seconds. Removes expired buffs, fires
        expiry notifications."""
    
    async def clear_all(self, char_id: int):
        """Remove all buffs (used on death/respawn)."""
```

## H.3 Storage

Buffs are stored in character attributes JSON under `"active_buffs"`:

```json
{
  "active_buffs": [
    {
      "buff_type": "combat_stim",
      "source": "item:stimpack",
      "stat_modifiers": {"dexterity": 3},
      "duration_seconds": 300,
      "started_at": 1713020000.0,
      "stacks": 1,
      "max_stacks": 1,
      "display_name": "Combat Stimulant",
      "display_color": "GREEN"
    }
  ]
}
```

## H.4 Integration with Skill Checks

`perform_skill_check()` in `engine/skill_checks.py` queries the buff
handler before rolling:

```python
# In perform_skill_check(), after computing base dice pool:
buff_modifier = await buff_handler.get_modifier(char_id, skill_attribute)
# Convert pips to dice adjustment
bonus_dice = buff_modifier // 3
bonus_pips = buff_modifier % 3
# Apply to dice pool
```

## H.5 Predefined Buff Types

| Buff Type | Source | Effect | Duration |
|---|---|---|---|
| `combat_stim` | Stimpack item | +1D Dexterity | 5 minutes |
| `bacta_healing` | Bacta treatment | +2D to healing checks | 1 hour |
| `force_control_pain` | Control Pain power | Ignore wound penalties | Scene duration |
| `force_enhance_attribute` | Enhance Attribute power | +1D to chosen attribute | Concentration |
| `dehydration` | Environmental hazard | -1 pip Stamina | Until water consumed |
| `toxic_exposure` | Environmental hazard | -1D Strength | Until breath mask equipped |
| `cantina_drink` | Cantina purchase | -1 pip Perception, +1 pip Con | 30 minutes |
| `inspired` | Kudos from another player | +1 pip to all social skills | 1 hour |
| `intimidated` | Failed Willpower check | -1D to all actions vs. intimidator | 10 minutes |

## H.6 Display

### H.6.1 `+buffs` Command

```
═══════════════════════════════════════════════════════════
  ACTIVE EFFECTS — Kael Voss
═══════════════════════════════════════════════════════════
  ▲ Combat Stimulant ............. +1D DEX ... 3:42 remaining
  ▼ Dehydration .................. -1 pip STA . until mitigated
  ▲ Inspired (by Renna Dox) ...... +1 pip SOC . 48:15 remaining
═══════════════════════════════════════════════════════════
```

### H.6.2 Web Client

Buff icons in the character status area. Green up-arrow for positive
effects, red down-arrow for negative. Hover tooltips with details.

## H.7 Files Affected

| File | Changes |
|---|---|
| `engine/buffs.py` | NEW — BuffHandler, Buff dataclass, tick loop |
| `engine/skill_checks.py` | Query buff modifiers before rolling |
| `engine/combat.py` | Clear buffs on death, apply combat-specific buffs |
| `engine/force_powers.py` | Refactor Control Pain / Enhance Attribute to use BuffHandler |
| `engine/environment.py` | Apply debuffs from hazards |
| `parser/builtin_commands.py` | `+buffs` command |
| `game_server.py` | Register buff tick task |

**Estimated effort:** 6-8 hours.

---

# DESIGN I: Safe Trade Command

## I.1 Purpose

A structured, atomic player-to-player trade system that prevents scams
and provides transaction logging for the economy monitor.

## I.2 Commands

```
trade <player>                    — Propose a trade with another player
trade/offer <item|credits N>      — Add to your side of the trade
trade/remove <item>               — Remove from your side
trade/accept                      — Lock in your offer
trade/confirm                     — Final confirmation (both must confirm)
trade/cancel                      — Cancel the trade
trade/view                        — View current trade state
```

## I.3 Flow

```
  Kael > trade Renna
  
  ═══════════════════════════════════════════════════════
    TRADE — Kael Voss ↔ Renna Dox
  ═══════════════════════════════════════════════════════
    YOUR OFFER:              THEIR OFFER:
    (empty)                  (empty)
  
    Commands: trade/offer, trade/remove, trade/accept,
              trade/cancel, trade/view
  ═══════════════════════════════════════════════════════

  Kael > trade/offer Heavy Blaster Pistol
  Kael > trade/offer credits 500

  Renna > trade/offer Vibroblade
  Renna > trade/offer credits 200

  ═══════════════════════════════════════════════════════
    TRADE — Kael Voss ↔ Renna Dox
  ═══════════════════════════════════════════════════════
    YOUR OFFER:              THEIR OFFER:
    Heavy Blaster Pistol     Vibroblade
    500 credits              200 credits
    
    Status: NEGOTIATING
  ═══════════════════════════════════════════════════════

  Kael > trade/accept      → "Kael Voss has accepted the trade."
  Renna > trade/accept     → "Renna Dox has accepted the trade."

  -- Both accepted. Final confirmation required. --

  Kael > trade/confirm     → "Kael Voss has confirmed."
  Renna > trade/confirm    → "Trade complete!"
```

## I.4 Atomicity

The trade executes in a single database transaction:
1. Remove items from Kael's inventory
2. Remove items from Renna's inventory
3. Transfer credits (both directions)
4. Add items to each player's inventory
5. Apply transaction tax (5% on credit portion, per economy audit)
6. Log to `credit_log` table

If any step fails, the entire trade rolls back.

## I.5 Constraints

- Both players must be in the same room
- Items must be in the player's inventory (not equipped)
- Credits offered must be available
- Only one active trade per player
- Trade times out after 10 minutes of inactivity
- Modifying the offer after accept resets both players' accept status

## I.6 Files Affected

| File | Changes |
|---|---|
| `parser/trade_commands.py` | NEW — all trade commands |
| `engine/trading.py` or new `engine/trade_handler.py` | Trade state machine, atomic execution |
| `parser/builtin_commands.py` | Wire trade commands |

**Estimated effort:** 3-4 hours.

---

# DESIGN J: RP Preferences

## J.1 Command

```
+rpprefs                          — View your RP preferences
+rpprefs/set <pref> = <yes|no|maybe|text>  — Set a preference
```

## J.2 Default Preferences

```yaml
rp_preferences:
  - key: adventure
    label: "Adventure & Action"
  - key: intrigue
    label: "Political Intrigue"
  - key: romance
    label: "Romance"
  - key: horror
    label: "Horror & Dark Themes"
  - key: comedy
    label: "Comedy & Humor"
  - key: permadeath
    label: "Open to Permadeath"
  - key: pvp
    label: "PvP Combat"
  - key: long_scenes
    label: "Long Scenes (2+ hours)"
  - key: scheduled_rp
    label: "Scheduled RP Sessions"
  - key: notes
    label: "Additional Notes"
    type: freeform
```

## J.3 Display on +finger

```
═══════════════════════════════════════════════════════════
  +FINGER — Kael Voss
  ─────────────────────────────────────────────────────────
  ...existing finger fields...
  ─────────────────────────────────────────────────────────
  RP PREFERENCES:
    Adventure ......... YES    Intrigue ........... YES
    Romance ........... MAYBE  Horror ............. NO
    PvP ............... YES    Permadeath ......... NO
    Long Scenes ....... YES    Scheduled RP ....... MAYBE
    Notes: "Prefer evenings PST. Always up for cantina RP."
═══════════════════════════════════════════════════════════
```

## J.4 Director Integration

When the Director generates personal quest hooks (PC Narrative Memory
doc §5), it checks the target PC's RP preferences and filters:
- Horror: NO → Don't generate horror-themed quests
- PvP: NO → Don't generate quests that lead to PvP confrontation
- Romance: YES → Can include NPC relationship hooks

## J.5 Files Affected

| File | Changes |
|---|---|
| `parser/mux_commands.py` | Add `+rpprefs` to `FingerCommand` display, new `RpPrefsCommand` |
| Character attributes JSON | New `rp_preferences` field |
| `engine/director.py` | Filter quest hooks by RP preferences |

**Estimated effort:** 2-3 hours.

---

# DESIGN K: Centralized Cooldown Handler

## K.1 Purpose

Replace scattered `time.time()` cooldown checks with a single handler.

## K.2 API

```python
# engine/cooldowns.py

class CooldownHandler:
    """Manages per-character cooldowns stored in attributes JSON."""
    
    def ready(self, char_id: int, cooldown_key: str) -> bool:
        """Returns True if the cooldown has expired."""
    
    def remaining(self, char_id: int, cooldown_key: str) -> float:
        """Returns seconds remaining, or 0 if ready."""
    
    async def set(self, char_id: int, cooldown_key: str, 
                   duration_seconds: int):
        """Start a cooldown."""
    
    async def clear(self, char_id: int, cooldown_key: str):
        """Force-clear a cooldown (admin use)."""
```

## K.3 Storage

```json
// In character attributes JSON
{
  "cooldowns": {
    "survey": 1713020300.0,
    "smuggling_run": 1713023600.0,
    "sabacc": 1713021800.0,
    "eavesdrop": 1713020900.0
  }
}
```

Values are Unix timestamps of when the cooldown expires.

## K.4 Migration

Existing cooldown checks in these files get refactored:
- `parser/crafting_commands.py` — `survey` (5-min cooldown)
- `parser/smuggling_commands.py` — smuggling runs
- `parser/builtin_commands.py` — sabacc
- Any other commands with `last_*` timestamp checks

## K.5 Files Affected

| File | Changes |
|---|---|
| `engine/cooldowns.py` | NEW — CooldownHandler |
| Multiple parser files | Refactor existing cooldown checks |

**Estimated effort:** 2-3 hours.

---

## Implementation Notes for Sonnet

### Reading Order
1. Start with Design K (Cooldown Handler) — smallest, foundational
2. Then Design B (Think Command) — smallest new feature
3. Then Design J (RP Preferences) — small addition to existing command
4. Then Design I (Safe Trade) — moderate, self-contained
5. Then Design D (Narrative Tone) — config-only, very small
6. Then Design H (Buff/Debuff Handler) — moderate, foundational for E
7. Then Design E (Environmental Hazards) — depends on H
8. Then Design C (World Lore) — moderate, Director integration
9. Then Design G (Achievements) — large but modular
10. Then Design F (Espionage Commands) — large, self-contained
11. Finally Design A (Permadeath) — largest, most complex

### Cross-Dependencies
- Design E (Hazards) depends on Design H (Buffs) for debuff application
- Design A (Permadeath) depends on Design A.7 (Scars) which is standalone
- Design F (Espionage) benefits from Design I (Trade) for intel item trading
- Design G (Achievements) has hooks across most other designs

### Architecture Invariants (from memories)
- All skill checks route through `perform_skill_check()` — no direct `roll_d6_pool`
- Every `except Exception` block must include `log.warning`
- Verify `import logging` and `log = logging.getLogger(__name__)` exist
- AST validation before every write
- CRLF line endings on Windows
- Read live source before writing any code

---

*End of Consolidated Design Documents — Version 1.0*
*Reference: competitive_analysis_feature_mining_v1.md,
sw_d6_mush_architecture_v23.md, economy_audit_v1.md,
director_ai_design_v1.md, pc_narrative_memory_design_v1.md*
