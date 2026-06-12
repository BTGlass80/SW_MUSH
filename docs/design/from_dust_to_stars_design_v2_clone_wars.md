# SW_MUSH — New Player Quest Chain: "From Dust to Stars" v2 (Clone Wars Era)
## Comprehensive Design Document for Sonnet Implementation
### April 25, 2026 · Opus Architecture Session
### Supersedes v1 (April 12, 2026, GCW era — archived as `from_dust_to_stars_design_v1_gcw_archive.md`)

---

## Executive Summary

This document designs a **30-step quest chain** that takes a brand-new player from the moment they complete the existing tutorial chain through earning their own beat-up light freighter with a hyperdrive. The chain runs entirely in the **live game world** — real rooms, real NPCs, real mission boards, real combat. No tutorial zones, no training wheels, no hint popups.

**v2 carries v1's structure forward unchanged.** The 5-phase arc, 30-step skeleton, NPC mentor pair (Kessa→Mak Torvin), the borrowed-ship-then-buy-with-debt arc, the Rusty Mynock ship, the Hutt loanshark — all era-agnostic and unchanged. The differences are surface-level era flavoring concentrated in roughly 8 of the 30 steps: faction names, planet destinations, two NPC backstory lines, and the smuggling-flavor patrol references. See `HANDOFF_FDTS_REWICKER_FOR_CLONE_WARS.md` for the change-set audit that produced this doc.

**Design targets (unchanged from v1):**
- **Duration:** 12–20 hours of active play spread over 2–3 weeks
- **Credits earned across the chain:** ~20,000–25,000 (not enough to buy a ship outright — the final reward IS the ship)
- **Systems introduced that tutorials DON'T cover:** Factions (deep interaction with 4+ of the CW factions), trade goods, sabacc, CP progression and the `train` command, `+background` narrative system, housing awareness, Director AI world events (experiencing one naturally), crafting in the field, NPC crew hiring, ship repair
- **Systems reinforced from tutorials:** Combat, missions, smuggling, bounties, space flight, hyperspace, skill checks
- **Final reward:** A decrepit Ghtroc 720 freighter (used, 23,000cr RAW value) with degraded systems, a balky hyperdrive, and a **10,000cr debt** to a Hutt loanshark — creating an ongoing credit sink and narrative hook
- **No new rooms required.** Every step uses existing CW rooms and existing or minimally-added NPCs
- **Faction reputation system:** Already shipped (per v32 architecture). Steps that award faction rep use `faction_rep` JSON in attributes against the CW faction roster.

**Relationship to existing systems (Clone Wars era):**
- **Core tutorial** (8 chains, 4–6 steps each, ~15–30 min): Per `clone_wars_era_design_v3.md` §10 — Republic Soldier, Republic Intelligence, Jedi Path (locked), Separatist Commando, Separatist Agent, Bounty Hunter, Smuggler, Shipwright/Trader. Runs in tutorial zone. *Prerequisite for this chain.*
- **Starter quest chain** (10 steps, ~30–60 min): Kessa's errands around Mos Eisley. Carries forward from v1 essentially unchanged — Kessa's character is era-agnostic. Runs in game world. *Prerequisite for this chain.*
- **THIS CHAIN** (30 steps, ~12–20 hours): "From Dust to Stars" v2. Runs in game world across the 4 active CW planets (Tatooine, Nar Shaddaa, Kuat, Coruscant — see §0 Era Coupling Notes). *Requires tutorial completion and starter chain complete. Replaces the need to grind credits for a first ship.*
- **Profession chains** (8 chains for CW, 5–8 steps each): Per `clone_wars_era_design_v3.md` §10. *Post-ship content. This chain feeds INTO those.*

---

## 0. Era Coupling Notes (NEW IN v2)

This section explicitly catalogs every Clone Wars-specific decision in v2 so future readers can audit era-coupling without reverse-engineering the whole doc.

**Active planet roster:** Tatooine, Nar Shaddaa, Kuat, Coruscant. (Kamino and Geonosis exist in `data/worlds/clone_wars/` but are too plot-coupled — Kamino is restricted, Geonosis is an active war zone — to be casual destinations for a brand-new spacer.) v1's roster was Tatooine + Nar Shaddaa + Kessel + Corellia; the change is Kessel → Kuat and Corellia → Coruscant.

**Faction roster used by this chain:**
- **Galactic Republic** (replaces GCW Empire as the "official authority" — but lighter footprint on Tatooine; "they have a war elsewhere")
- **Confederacy of Independent Systems / CIS sympathizers** (replaces GCW Rebellion — covert, recruiting quietly, "getting caught means trouble")
- **Hutt Cartel** (unchanged from v1 — Hutts are Hutts in any era)
- **Bounty Hunters' Guild** (unchanged from v1 — guild is era-agnostic)
- **Traders' Coalition** (unchanged from v1 — guild is era-agnostic)
- **Underworld** (unchanged from v1 — criminal underground is era-agnostic)

Faction codes match `data/worlds/clone_wars/organizations.yaml`: `republic`, `cis`, `hutt`, `bh_guild`, `traders`, `underworld`. The Imperial/Rebel/`empire`/`rebel` codes from v1 are NOT present in CW.

**Mak Torvin's backstory line.** v1 had "been running the Outer Rim since before the Clone Wars," which only works when CW is past tense. v2 swaps to "been running the Outer Rim since before the war started," placing Mak as a CW veteran whose career predates the conflict.

**Step 27 ship broker.** v1 had Lira Shan as a CEC (Corellian Engineering Corporation) broker on Corellia. CW manifest doesn't include Corellia, so Lira Shan moves to Kuat as a **Kuati Drive Yards (KDY) broker**. KDY is canonical CW shipbuilder; the secondhand-Ghtroc story works just as well there. CEC could still be referenced as the original manufacturer; KDY is the dealership.

**Smuggling flavor (Step 10).** "Imperial patrols" → "Republic patrols" or "Hutt enforcers" depending on context.

**Step 13 cargo passage.** Mechanic unchanged — passenger on a freighter to Nar Shaddaa. No customs gating in CW for this trip; freighter crews don't ask many questions.

**War-as-context flavor (NEW IN v2).** The Clone Wars are the dominant ambient context but aren't fought on Tatooine, Nar Shaddaa, Kuat, or Coruscant lower levels. Two flavor lines added (Steps 8 and 17) reference the war as background ambience without making it the plot. They're tone-setters, not quest beats.

**Force-sign hook (DEFERRED).** Per `clone_wars_era_design_v3.md` §10, every CW character has a 50% probability of being flagged as Force-sensitive during tutorial. The Jedi Village quest chain (Drop F.8 in v32 §19) consumes that flag for unlock. v2 includes a `# TODO(force_sensitive)` marker in the implementation but does NOT add a Force-sign hook step — the Village chain doesn't exist yet, so a hook would point at nothing. Revisit when Drop F.8 ships.

---

## 1. Architecture

### 1.1 Quest State Tracking

All state in character `attributes` JSON under `"spacer_quest"`:

```json
{
    "spacer_quest": {
        "phase": 2,
        "step": 12,
        "started_at": 1712700000,
        "completed_steps": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "flags": {
            "met_mak": true,
            "faction_sampler": "cis",
            "smuggling_caught_count": 0,
            "sabacc_played": true,
            "background_written": true,
            "debt_remaining": 10000,
            "ship_name": null,
            "borrowed_ship_id": null
        },
        "step_data": {
            "12": {"missions_done": 1, "target": 3}
        }
    }
}
```

(`faction_sampler` value updated from v1's `"rebel"` example to `"cis"` — the field is the same, the faction codes change.)

### 1.2 Quest Engine

New file: **`engine/spacer_quest.py`** (~1,000–1,200 lines)

```python
@dataclass
class QuestStep:
    step_id: int
    phase: int                          # 1-5
    title: str                          # "The Routine Run"
    description: str                    # Objective text shown in +quest
    objective_type: str                 # see table below
    objective_data: dict                # type-specific completion params
    briefing_text: str = ""             # NPC dialogue on step activation
    briefing_source: str = "kessa"      # which NPC gives the briefing
    briefing_delivery: str = "comlink"  # "comlink" or "talk" (in-person)
    reward_credits: int = 0
    reward_items: list = field(default_factory=list)
    reward_title: str = ""
    reward_faction_rep: dict = field(default_factory=dict)  # {"cis": 5, "republic": -2}
    reward_flags: dict = field(default_factory=dict)
    completion_text: str = ""           # NPC response on completion
    next_step: int = 0                  # 0 = chain complete
    prerequisite_flags: dict = field(default_factory=dict)
    fail_text: str = ""                 # on skill check failure
    hint_text: str = ""                 # shown in +quest as extra guidance
    phase_gate: bool = False            # triggers phase transition on complete
```

**Objective types** (unchanged from v1):

| Type | Completion Trigger | Example |
|------|-------------------|---------|
| `talk` | `TalkCommand` with matching NPC in matching room | "Talk to Vel Ansen in the Undercity" |
| `room` | Player enters target room_id | "Find the Warrens" |
| `mission` | `CompleteMissionCommand` with matching type (or any) | "Complete a combat mission" |
| `mission_count` | N missions completed (counter in step_data) | "Complete 3 missions of any type" |
| `combat_kill` | NPC killed in combat matching name/type | "Defeat Gorba's Enforcer" |
| `skill_check` | Auto-fires check on entering room or talking to NPC | "Persuade the merchant (Persuasion vs 10)" |
| `smuggling` | `SmugDeliverCommand` with min tier | "Complete a Tier 1 smuggling run" |
| `bounty` | `BountyCollectCommand` with min tier | "Collect a bounty" |
| `trade` | `TradeCommand` buy or sell action | "Buy trade goods on Kuat" |
| `craft` | `CraftCommand` completion | "Craft any item" |
| `space_action` | Space command: launch, land, hyperspace, course | "Launch from Mos Eisley" |
| `sabacc` | `SabaccCommand` played (win or lose) | "Play a hand of sabacc" |
| `use_command` | Player types a specific command | "Check your advancement: cpstatus" |
| `multi` | Multiple sub-objectives with AND/OR logic | "Complete 2 of: bounty, smuggle, mission" |
| `deliver_item` | Player has item X and talks to NPC Y | "Bring the part to Mak" |
| `faction_interact` | Player uses `factions` command or talks to faction NPC | "Learn about the factions" |

(Trade example updated to a CW-active planet.)

### 1.3 Hook Points

Single function call added to each handler: `await check_spacer_quest(ctx, trigger_type, trigger_data)`. Unchanged from v1.

| Hook Location | File | Trigger Type |
|---------------|------|-------------|
| `TalkCommand.execute()` | `parser/builtin_commands.py` | `talk` |
| Room entry | `server/session.py` move handler | `room` |
| `CompleteMissionCommand.execute()` | `parser/mission_commands.py` | `mission`, `mission_count` |
| Kill resolution | `engine/combat.py` | `combat_kill` |
| `SmugDeliverCommand.execute()` | `parser/smuggling_commands.py` | `smuggling` |
| `BountyCollectCommand.execute()` | `parser/bounty_commands.py` | `bounty` |
| `TradeCommand.execute()` | `parser/trade_commands.py` | `trade` |
| `CraftCommand.execute()` | `engine/crafting.py` | `craft` |
| `LaunchCommand` / `LandCommand` / `HyperspaceCommand` | `parser/space_commands.py` | `space_action` |
| `SabaccCommand.execute()` | `parser/sabacc_commands.py` | `sabacc` |
| Various commands (`cpstatus`, `factions`, `+background`) | respective files | `use_command` |

### 1.4 Player-Facing Command

**`+quest`** (aliases: `quest`, `+spacerquest`, `+dusttostars`)

```
+quest              — Show current objective, phase, progress
+quest log          — Show completed steps with timestamps
+quest abandon      — Abandon chain (confirmation prompt; can restart from Phase 1)
```

Display format (sample updated for CW):
```
═══════════════════════════════════════════════════════════════
  FROM DUST TO STARS — Phase 3: Off-World
  Step 16 of 30: "Your First Cargo Run"
═══════════════════════════════════════════════════════════════

  Mak wants you to prove you can make money with a ship.
  Buy trade goods cheap and sell them where they're wanted.

  Objective: Buy cargo on one planet, sell on another
  Hint:      Type 'trade list' to see what's available.
             Kuat sells Industrial Components cheap.
  Progress:  ████████████████░░░░░░░░  16/30 (Phase 3/5)
  Credits:   8,450 earned so far

═══════════════════════════════════════════════════════════════
```

### 1.5 Chain Activation

Triggers when ALL conditions are true:
- Tutorial chain complete (any of the 8 CW chains — see `clone_wars_era_design_v3.md` §10)
- `starter_quest.step >= 10` (starter chain complete)
- `spacer_quest` key does NOT exist in attributes
- Player is in Chalmun's Cantina (or any Mos Eisley room — comlink from Kessa)

On activation: Kessa sends a comlink message setting up the premise. `spacer_quest` created with `phase: 1, step: 1`.

**Backward-compat note:** The activation gate should check `attributes.tutorial_state == "complete"` regardless of which of the 8 CW tutorial chains the player took. If the tutorial rework drop (F.6) hasn't shipped when FDTS v2 lands, the gate falls back to the v1 activation rule (any tutorial completion flag).

### 1.6 New NPCs

| NPC | Room | Planet | Role |
|-----|------|--------|------|
| **Mak Torvin** | Docking Bay 94 | Tatooine | Retired freighter captain. Takes over as primary quest giver in Phase 3. Former owner of the Ghtroc the player eventually gets. |
| **Lira Shan** | Kuat City spaceport (KDY office) | **Kuat** | **Kuati Drive Yards** ship broker (changed from CEC/Corellia in v1). Handles the Ghtroc paperwork in Phase 5. Straight-dealing, no nonsense. |
| **Grek** | Nar Shaddaa Undercity | Nar Shaddaa | Hutt Cartel fixer. Drago the Hutt's representative. Handles the loanshark deal in Phase 5. Slimy but fair-ish. |

Place these in `data/worlds/clone_wars/npcs.yaml` (which the F.0 Drop 2 work needs to author). If F.0 Drop 2 hasn't landed when this chain ships, register them inline in the engine for now and migrate to the YAML file in a follow-up drop.

All other quest targets use existing NPCs already authored in the CW world data.

**"Drago the Hutt"** is never seen — only referenced in comlink messages and by Grek. This is intentional: the Hutt looming off-screen is more menacing than one sitting in a room. It also means no new NPC data entry for Drago.

---

## 2. Phase Overview

| Phase | Title | Steps | Location | Duration | Credits | Primary Systems Introduced |
|-------|-------|-------|----------|----------|---------|--------------------------|
| 1 | "Earning Your Keep" | 1–7 | Tatooine only | 2–3 hrs | ~3,800 | Missions (varied), combat, social skills, investigation, economy awareness |
| 2 | "The Wider Galaxy" | 8–14 | Tatooine + Nar Shaddaa (as passenger) | 3–4 hrs | ~5,200 | Factions (deep intro), bounties, smuggling, sabacc, CP/train, +background, Nar Shaddaa exploration |
| 3 | "Off-World" | 15–20 | All 4 CW planets (borrowed ship from Mak) | 3–4 hrs | ~4,500 | Space flight, hyperspace, landing, trade goods, ship repair, **Kuat + Coruscant** exploration |
| 4 | "A Spacer's Reputation" | 21–26 | All 4 CW planets (borrowed ship) | 3–4 hrs | ~5,500 | Crafting, advanced missions, NPC crew, housing awareness, multi-step ops, faction missions |
| 5 | "The Captain's Chair" | 27–30 | **Kuat** + Tatooine | 1–2 hrs | Ship + 10,000cr debt | Ship purchase, debt mechanic, naming your ship, first solo flight |

(Bolded items are CW-specific changes from v1; everything else is unchanged.)

**Total:** 30 steps, ~12–20 hours, ~19,000–22,000 credits earned across the chain (not counting mission/bounty/smuggling payouts the player earns independently).

---

## 3. Phase 1 — "Earning Your Keep" (Steps 1–7)

**Setting:** Player has ~1,000cr from the starter chain. They're in Mos Eisley, know the basics. Kessa continues as quest giver.

**Narrative:** Kessa is a fixer. She's been watching the player since the starter chain and thinks they have potential. She starts throwing real work their way — not tourist errands, but the kind of jobs that build a reputation in Mos Eisley.

**Era note:** Phase 1 has zero CW-specific content. Mos Eisley in CW is virtually identical to Mos Eisley in GCW — same Hutts, same scavengers, same dust. The Republic clone troopers occasionally pass through but don't linger; no one cares about the war here. All seven steps below are unchanged from v1.

---

### Step 1: "The Routine Run"
- **Objective:** `mission` — Complete any delivery mission from the mission board.
- **Briefing (Kessa, comlink):** *"You handled those errands well enough, but errands don't pay rent. Time to hit the mission board for real. Take a delivery job — they're the simplest, lowest risk. Walk the cargo from A to B, collect your credits, don't get shot. Simple as breathing... assuming you keep breathing."*
- **Reward:** 200cr bonus (on top of mission payout).
- **Completion (Kessa, comlink):** *"Clean delivery, no drama. That's how you build a reputation — one job at a time. I've got something more interesting for you next."*
- **Teaches:** Mission board as the primary income source. Reinforces starter chain lesson.

### Step 2: "Pest Control"
- **Objective:** `combat_kill` — Kill any hostile NPC. (Tusken Raiders in Jundland Wastes, or any hostile NPC on any active planet.)
- **Briefing (Kessa, comlink):** *"There's always someone out past the checkpoint causing trouble — Tusken Raiders, scavenger gangs, the odd Gamorrean who wandered off from Jabba's payroll. If you can handle yourself in a fight, people notice. And people who notice pay better than the mission board."*
- **Hint:** "Hostile NPCs can be found in the Jundland Wastes (east past the Checkpoint) or other Lawless zones."
- **Reward:** 300cr, quality-55 hold-out blaster.
- **Completion:** *"Word gets around fast in this town. 'New gun in Mos Eisley.' That's you, kid. Good — you'll need that rep."*
- **Teaches:** Combat in the wild (not the tutorial arena). Lawless zones. Real stakes.

### Step 3: "Smooth Operator"
- **Objective:** `skill_check` — Pass a Persuasion check (difficulty 10) by talking to a specific NPC.
- **Briefing (Kessa, comlink):** *"Not everything in this town gets solved with a blaster. Old Kayson at the weapon shop says a supplier is shortchanging him on power packs. I told him I knew someone who could have a... persuasive conversation. Head to the weapon shop, talk to Kayson, and he'll point you at the supplier. Make it right."*
- **Implementation:** Player talks to Kayson. Kayson gives a one-line setup. Quest engine fires Persuasion vs difficulty 10. On success: "The supplier backs down" flavor text. On failure: "He's not convinced. Try again in a minute." (60s cooldown, retry unlimited.)
- **Reward:** 250cr.
- **Completion:** *"Kayson says the power packs are flowing again. No blaster shots, no hospital bills. That's the smart way to do business."*
- **Teaches:** Social skill checks matter. Persuasion/Con/Bargain are real tools.

### Step 4: "The Investigation"
- **Objective:** `multi` (AND: enter Weapon Shop room + `skill_check` Search vs 12)
- **Briefing (Kessa, comlink):** *"Different job. A warehouse near the spaceport got broken into last night — cargo missing, door cut clean. The owner's offering 400 credits for whoever figures out who did it. Head over there, look around, see what you find. Use your eyes, not your blaster."*
- **Implementation:** Player enters the target room. Quest engine prompts: "[QUEST] You notice signs of forced entry. Examine the scene? Type `search` to investigate." When player uses `search` (or `look evidence` or similar), fires Search check vs difficulty 12. Success reveals clues and completes the step. Failure: "You don't notice anything useful. Try looking more carefully." (retry after 60s.)
- **Reward:** 400cr.
- **Completion:** *"Nice work, detective. Turns out it was Jawas — figures. The owner's happy, you're richer, and now people know you can find things. That's a useful reputation."*
- **Teaches:** Search/Perception as investigation tools. Skill checks outside combat.

### Step 5: "Diversify"
- **Objective:** `mission_count` — Complete 3 missions of any type.
- **Briefing (Kessa, comlink):** *"One-off jobs are fine, but I need to know you can handle volume. Hit the board, take three jobs — delivery, combat, investigation, whatever's up there. Finish all three and I'll introduce you to someone important."*
- **Tracking:** `step_data.5.missions_done` counter. Display in `+quest`: "Missions completed: 2/3"
- **Reward:** 800cr.
- **Completion:** *"Three for three. You're consistent — that's worth more than talent around here. Time you met someone who can open real doors for you."*
- **Teaches:** Grinding the mission board is the baseline income. Variety of mission types.

### Step 6: "The Sabacc Table"
- **Objective:** `sabacc` — Play a hand of sabacc in the cantina (win or lose).
- **Briefing (Kessa, comlink):** *"Before I introduce you to my contact, there's something you need to understand about how Mos Eisley really works. Half the deals in this town get made over sabacc cards. Head to the cantina, put some credits on the table, play a hand. I don't care if you win or lose — just learn the game. Type `sabacc` when you're in the cantina."*
- **Reward:** 100cr (win or lose — Kessa covers you).
- **Completion:** *"So? Win or lose? ...Doesn't matter. The point is you sat at the table. In this town, that means you're in the game. Now come to Docking Bay 94 — there's someone you need to meet."*
- **Teaches:** Sabacc exists, is cantina-only, uses Gambling skill. Social/economic minigame.

### Step 7: "The Old Captain" (Phase Gate → Phase 2) **[CW UPDATE]**
- **Objective:** `talk` — Talk to Mak Torvin at Docking Bay 94.
- **Briefing (Kessa, comlink):** *"His name is Mak Torvin. Old freighter captain — been running the Outer Rim since before the war started, and figures he'll still be running it after it ends, assuming the galaxy survives that long. His ship's in dry dock, his knees are shot, but he knows every spacer trick in the book. He's at Docking Bay 94. Tell him I sent you."*
- **Mak Torvin (on talk):** *"So Kessa's prodigy finally shows up. She tells me you're not completely useless — high praise from her. I've been flying freighters for forty years, kid. I've outrun Republic customs, survived pirate ambushes, and lost two ships — one to a Hutt and one to an asteroid. The war out there hasn't slowed business — if anything, it's made the lanes more interesting. I know what it takes to make it as a spacer, and I know it when I see it. Or when I don't. Let's find out which one you are. There's a whole galaxy out there past the atmosphere, and right now you've never even been off this dust ball. That changes soon — but first, you need to learn a few more things right here in Mos Eisley."*
- **Reward:** 250cr, flag `met_mak: true`.
- **Completion:** *Kessa: "Good. Mak's the real deal — if he decides to mentor you, you're set. Listen to what he says. He'll know when you're ready to go off-world."*
- **Phase gate:** Sets `phase: 2`.
- **CW changes from v1:** Kessa's "since before the Clone Wars" → "since before the war started." Mak's "Imperial customs" → "Republic customs." Added one war-as-context flavor sentence ("the war out there hasn't slowed business…") that establishes the war as ambient atmosphere without making it the plot.

**Phase 1 total credits:** ~2,300 bonus (plus mission payouts the player earned independently, probably another ~1,500).

---

## 4. Phase 2 — "The Wider Galaxy" (Steps 8–14)

**Setting:** Player has ~3,000–5,000cr total. They know Mos Eisley well. Mak Torvin is now the secondary quest giver (alternating with Kessa). This phase introduces factions, bounty hunting, smuggling, CP progression, the narrative system, and gets the player to Nar Shaddaa for the first time — as a passenger, not a pilot.

**Narrative:** Mak tells the player they need to see more of the galaxy before they're ready for a ship. He arranges passage on a freighter to Nar Shaddaa. But first, there are things to learn on Tatooine — the power players, the underground economy, and how to build a reputation that matters.

**CW note:** Phase 2's biggest changes are concentrated in Step 8 (faction roster swap) and Step 14 (the contact roster on Nar Shaddaa is unchanged — those NPCs are era-agnostic). Step 10's smuggling flavor needs the patrol-name swap.

---

### Step 8: "The Powers That Be" **[CW UPDATE]**
- **Objective:** `faction_interact` — Use the `factions` command, then talk to Kessa.
- **Briefing (Mak, comlink):** *"Before you go anywhere, you need to understand who runs this galaxy. It's not just the Republic — there are factions, guilds, cartels, all of them pulling strings. Type `factions` and read up. Then go talk to Kessa — she can tell you things about the local power structure that you won't find in any database."*
- **Implementation:** Two-part objective. First: player types `factions` (use_command trigger). Then: player talks to Kessa (talk trigger). Both must complete.
- **Kessa (on talk, extended dialogue):** *"So you've seen the list. Let me fill in the gaps. The Republic has a token presence on Tatooine — clone troopers passing through, a customs office that mostly takes bribes. They have a real war to fight elsewhere; they're not interested in this dustbowl. The Hutts run everything the Republic pretends doesn't exist, which is most of it. The CIS has sympathizers out here too — quiet ones, mostly traders and people who think the Republic's gone too far — but getting caught helping them means trouble nobody wants. Then there are the guilds — Bounty Hunters, Traders' Coalition — they're more about business than politics. Smart guilds, those. They'll work for either side and never pick. You don't have to pick a side right now either. Most smart spacers stay independent until they know the score. But pay attention to what you do — every job you run, every cargo you haul, someone's keeping track. When you're ready, the factions will come to you."*
- **Reward:** 150cr, +2 faction_rep to `traders` (just for asking — the Traders' Coalition likes informed operators).
- **Completion:** *Mak: "Good. Most rookies never bother learning the political landscape until they're already in trouble. You're smarter than most."*
- **Teaches:** `factions` command, all CW factions exist, rep is action-driven not menu-driven, factions are optional but rewarding.
- **CW changes from v1:** Empire→Republic, Rebellion→CIS sympathizers (with appropriately different framing — CIS is wider tent of "not-Republic" sympathy, not a single underground cell). Tone shift: Republic is *distant and disinterested* on Tatooine, not actively oppressive (that's a GCW Empire vibe). Added one war-as-context flavor: "the guilds will work for either side and never pick" — establishes the war's existence and the political neutrality of the trade guilds the player is most likely to engage with.

### Step 9: "Your First Bounty"
- **Objective:** `bounty` — Complete any bounty from the bounty board.
- **Briefing (Mak, comlink):** *"Time to try bounty hunting. Check the bounty board — `+bounties` — and pick a target you think you can handle. Start with the lower tiers. You'll need to track them down first — that's a Search or Streetwise check — and then take them down. Alive pays more than dead, but dead's a lot safer."*
- **Reward:** 500cr bonus, +3 faction_rep to `bh_guild`.
- **Completion:** *Mak: "Bounty Hunters' Guild noticed. They pay attention to first kills. Treat them well — they're a useful relationship for someone in your line of work."*
- **Teaches:** Bounty board, tier system, hunt-and-collect flow, BH Guild standing.
- (No CW changes — bounty hunting is era-agnostic.)

### Step 10: "The Underworld Economy" **[CW UPDATE — flavor only]**
- **Objective:** `smuggling` — Complete a Tier 1 smuggling run.
- **Briefing (Mak, comlink):** *"Now the other side of the same coin. Smuggling. There's a contact in the cantina who runs Tier 1 jobs for the Hutts — small stuff, low risk. Use `+smugjobs` to see available runs. `smugaccept <id>` to take one. Deliver the cargo to the destination. If Republic patrols stop you, you'll need a Con check to talk your way out. If a Hutt enforcer takes an interest in your delivery, that's a different conversation entirely."*
- **Reward:** 400cr, +2 faction_rep to `hutt`, +1 to `underworld`.
- **Completion:** *Mak: "Clean run. The Hutts noticed. They like a spacer who can deliver without drama. Just remember — every job for them is a string. Eventually they'll want you to do something you don't want to do, and you'll have to decide if the credits are worth it."*
- **Teaches:** Smuggling system, `+smugjobs`/`smugaccept`/delivery, Hutt and Underworld faction rep, the "every favor has a price" theme.
- **CW changes from v1:** "Imperial patrols" → "Republic patrols." Added a Hutt enforcer reference for ambient threat. Mechanic unchanged.

### Step 11: "Write Your Story"
- **Objective:** `use_command` — Use the `+background` command to write character backstory.
- **Briefing (Kessa, comlink):** *"Mak says you need to spend more time thinking about who you are, not just what you do. He's right, even if he's gruff about it. Type `+background` to write your story — where you came from, why you're here, what you want. The galaxy doesn't care about your past, but YOU should. And the AI will use what you write — NPCs will reference it in conversation, missions will hook into it. Make it real."*
- **Reward:** 200cr, flag `background_written: true`.
- **Completion:** *Mak: "Good. A spacer without a story is just cargo with legs. Now, about getting you off-world..."*
- **Teaches:** `+background` command, that NPC AI uses player backgrounds in dialogue, narrative identity matters.
- (No CW changes — narrative system is era-agnostic.)

### Step 12: "Check Your Progress"
- **Objective:** `use_command` — Use `cpstatus` command.
- **Briefing (Mak, comlink):** *"One more thing before we talk about Nar Shaddaa. You've been fighting, running jobs, talking your way through deals. All that experience adds up. Type `cpstatus` — it'll show you how close you are to earning a Character Point. When you get one, you can `train` a skill and improve it permanently. That's how you go from a kid with a blaster to someone worth hiring."*
- **Reward:** 100cr.
- **Completion:** *Mak: "See those ticks adding up? Every mission, every fight, every RP scene contributes. When you've got a CP saved up, pick a skill you want to improve and type `train <skill>`. Now — let's talk about getting you to Nar Shaddaa."*
- **Teaches:** CP progression system, `cpstatus` and `train` commands, long-term character advancement.
- (No CW changes.)

### Step 13: "Passage to Nar Shaddaa"
- **Objective:** `room` — Enter a Nar Shaddaa room.
- **Briefing (Mak, talk — player must visit him at Docking Bay 94):** *"I called in a favor with a freighter crew heading to Nar Shaddaa. They've got a spare bunk — you ride as a passenger, help with cargo loading, and they'll drop you at the Smuggler's Moon. Nar Shaddaa is nothing like Tatooine. It's bigger, dirtier, more dangerous, and there's ten times as much money moving through it. I want you to go there, look around, meet some people, and come back alive. That's the test. When you're ready to leave Tatooine, type `travel narshaddaa` at any docking bay."*
- **Implementation:** A special `travel` command variant (or a quest-specific shortcut) that teleports the player to the Nar Shaddaa Landing Platform when at a Tatooine docking bay. This simulates "booking passage" without requiring the player to own or fly a ship. The quest flag `borrowed_transport: true` is set. A return version (`travel tatooine`) works from Nar Shaddaa docking areas.
- **Reward:** 500cr (Mak pays you for helping load cargo on the freighter), +1 faction_rep to `traders`.
- **Completion:** *Mak (comlink): "You made it. Welcome to the Smuggler's Moon. Look around, don't trust anyone, and don't lose all your credits at a sabacc table. I want you to meet a few people while you're there."*
- **Teaches:** Interplanetary travel exists. Nar Shaddaa is a major destination. Sets up the desire for a personal ship.
- (No CW changes — passenger freight is era-agnostic, and CW Nar Shaddaa is the same Smuggler's Moon as GCW Nar Shaddaa.)

### Step 14: "Making Contacts" (Phase Gate → Phase 3) **[CW UPDATE — minor flavor]**
- **Objective:** `multi` (AND: talk to 3 specific NPCs on Nar Shaddaa)
- **Briefing (Mak, comlink):** *"Three people I want you to find on Nar Shaddaa. First: Zekka Thansen in the Corellian Sector — she runs a smuggler network and she's useful to know. Second: Renna Dox at the shipwright's — tell her I sent you, she owes me a hull patch. Third: Doc Myrra in the Undercity — she's the best medic on the moon and she doesn't ask questions. Find all three, introduce yourself, and report back."*
- **Targets:** Zekka Thansen, Renna Dox, Doc Myrra. All three exist in the Nar Shaddaa NPC roster.
- **Tracking:** `step_data.14.contacts_made: ["zekka"]` — list grows as player talks to each.
- **Reward:** 600cr, +2 faction_rep to `hutt`, +2 to `underworld`.
- **NPC dialogues on talk:**
  - *Zekka:* "Mak Torvin sent you? The old man still has contacts. Welcome to Nar Shaddaa, kid. If you ever need cargo moved quietly, you know where to find me."
  - *Renna Dox:* "Tell Mak his hull patch is ready — if he ever gets that wreck of his flying again. You're the apprentice? You've got the look. Come back when you have a ship of your own and I'll show you what a real overhaul looks like."
  - *Doc Myrra:* "Any friend of Mak's is a friend of mine. Remember where I am — when you take a blaster bolt in somewhere you shouldn't, I'm cheaper than the official medics and I won't report it."
- **Completion:** *Mak: "Good. You've got contacts on two planets now. That's the start of a real network. Head back to Tatooine — I think you're ready to learn how to fly."*
- **Phase gate:** Sets `phase: 3`. Player must `travel tatooine` to return.
- **Teaches:** Nar Shaddaa geography, key NPCs, the value of a contact network, cross-planet quest objectives.
- **CW changes from v1:** Doc Myrra's "I won't report it" line previously said "cheaper than the garrison medics" — kept the spirit, dropped the GCW-specific "garrison" word in favor of the more era-neutral "official medics." All three NPCs and dialogues are otherwise era-agnostic.

**Phase 2 total credits:** ~2,450 bonus (plus independent bounty/smuggling/mission income, probably another ~2,500–3,000).

---

## 5. Phase 3 — "Off-World" (Steps 15–20)

**Setting:** Player has ~6,000–9,000cr total. They've seen two planets. Now Mak lends them his old ship (a loaner — quest-flagged, can't be sold or permanently kept) to learn space flight, hyperspace, trading, and ship operations. This is the "learn to fly for real" phase.

**The Borrowed Ship:** Mak's old Ghtroc 720 (the same ship the player eventually buys in Phase 5 — they just don't know that yet). It's a quest item: assigned to the player via `borrowed_ship_id` in quest flags. The player can fly it, use all space commands, take damage, repair it. But they can't sell it, and it reverts to Mak if they abandon the quest. Ship template: `ghtroc_720` with cosmetic quirks (see §8.2 for the Ghtroc's personality).

**Narrative:** Mak lends the player his ship to "prove they can handle her." The player must fly to all four CW planets, run trade routes, handle ship operations, and bring the ship back in one piece.

**CW destination roster:** v1 had Tatooine + Nar Shaddaa + Kessel + Corellia. v2 has Tatooine + Nar Shaddaa + **Kuat** + **Coruscant**. Kuat replaces Kessel as the "industrial/shipyard" destination; Coruscant lower levels replace Corellia as the "big city/deal-broker" destination. Both substitutions are era-canonical and preserve the structural role each destination plays in the narrative arc.

---

### Step 15: "Your First Launch"
- **Objective:** `space_action` — Launch from Tatooine (`launch` command).
- **Briefing (Mak, talk at Docking Bay 94):** *"All right, kid, this is the moment. That's my ship over there — the Rusty Mynock. She's old, she's ugly, and the hyperdrive protests every jump. But she flies. I'm lending her to you — not giving, lending. You scratch her, you pay for repairs. You wreck her, you pay for a new ship. And you will pay, because I know where you sleep. Now get in the cockpit and take her up. Type `board` to get aboard, then `launch` when you're ready."*
- **Implementation:** On this step activation, system calls `db.create_ship()` or assigns a pre-built quest ship to the player. Ship is flagged `quest_ship: true` in its systems JSON (prevents sale). Standard Ghtroc 720 stats but with `condition` at 65% (cosmetically beat up).
- **Reward:** 200cr ("fuel money from Mak"), flag `borrowed_ship_id: <ship_id>`.
- **Completion:** *Mak (comlink): "She's up. Don't let the engine rattle scare you — that's just her way of saying hello. Now set a course for orbit and get a feel for the controls."*
- **Teaches:** `board`, `launch`, basic space commands. First time flying.
- (No CW changes.)

### Step 16: "Star Roads" **[CW UPDATE — destination list]**
- **Objective:** `space_action` — Make a hyperspace jump to any planet (`hyperspace <dest>`).
- **Briefing (Mak, comlink):** *"Orbit's nice, but it doesn't pay the bills. Time to see what's past the atmosphere. Pick a destination — Nar Shaddaa, Kuat, or Coruscant. Punch the hyperdrive when you've got coordinates. Type `hyperspace <destination>` when you're in orbit. The navicomputer handles the math, but keep an eye on your fuel. And maybe say a prayer to whatever you believe in — the Mynock's hyperdrive has... opinions about long jumps."*
- **Reward:** 300cr.
- **Completion:** *Mak: "Stars turned to lines, right? That feeling never gets old. Now land wherever you are and take a look around."*
- **Teaches:** Hyperspace travel, destination selection, fuel awareness.
- **CW changes from v1:** "Nar Shaddaa, Kessel, Corellia" → "Nar Shaddaa, Kuat, Coruscant."

### Step 17: "Touch Down" **[CW UPDATE — completion text per planet]**
- **Objective:** `space_action` — Land on any planet that isn't Tatooine.
- **Briefing (Mak, comlink):** *"Navigate to orbit around your destination, then type `land`. Each planet has its own docking bay, its own rules, its own prices. Notice the docking fee when you land — that's a cost of doing business."*
- **Reward:** 200cr.
- **Completion text varies by planet landed on:**
  - *Nar Shaddaa:* "Back to the Smuggler's Moon. You know some faces there already — good."
  - *Kuat:* "Kuat. The shipbuilding capital. Kuati Drive Yards built half the warships in the galaxy, and right now they're building more — the war's been good for KDY's bottom line. Worth a look around. Don't try to buy a ship here on a rookie's budget — they'd laugh you off the orbital."
  - *Coruscant:* "Coruscant. The galaxy's heart. Stay clear of the upper levels — too many badges, and the war makes everyone twitchy. The lower levels are full of work for someone who knows how to keep their mouth shut. Coco Town's where the freelance jobs are."
- **Teaches:** `land` command, docking fees as a credit sink, planet variety.
- **CW changes from v1:** Replaced Kessel and Corellia completion text with Kuat and Coruscant. Kuat text includes a war-as-context flavor sentence ("the war's been good for KDY's bottom line") — sets the tone without making the war the plot. Coruscant text emphasizes the lower-levels Coco Town district as the spacer-friendly part of the planet (per `data/worlds/clone_wars/planets/coruscant.yaml`).

### Step 18: "Your First Cargo Run" **[CW UPDATE — destination hint]**
- **Objective:** `trade` — Buy trade goods on one planet and sell them on another.
- **Briefing (Mak, comlink):** *"Here's where a ship starts paying for itself. Every planet produces goods that are cheap locally and expensive elsewhere. Type `trade list` to see what's available. Buy low, fly somewhere that wants it, sell high. That's the whole game. A word of advice: Kuat sells industrial components cheap, and the Hutts on Nar Shaddaa pay premium for them — they're rebuilding their fleets."*
- **Implementation:** Two-trigger objective. First: `trade buy` on any planet. Then: `trade sell` on a different planet (checked via quest flag tracking which planet they bought on). Both must complete.
- **Reward:** 500cr bonus (on top of trade profit).
- **Completion:** *Mak: "Now you understand why every spacer in the galaxy wants a freighter with cargo space. The bigger the hold, the bigger the profit. You're not just a gun for hire anymore — you're a trader."*
- **Teaches:** Trade goods system, buy-low-sell-high, cargo capacity, why freighters matter.
- **CW changes from v1:** "Corellia sells luxury goods cheap, and Tatooine can't get enough of them" → "Kuat sells industrial components cheap, and the Hutts on Nar Shaddaa pay premium for them." Hint matches the new active-planet roster and adds a small CW-flavored economic detail (Hutts rebuilding fleets in wartime).

### Step 19: "When Things Break"
- **Objective:** `skill_check` — Perform a ship repair (Space Transports Repair check, difficulty 10).
- **Briefing (Mak, comlink):** *"Here's a lesson every freighter captain learns: things break. The Mynock's sensor array has been acting up — probably a loose coupling. While you're docked, type `damcon` to run diagnostics, then `damcon sensors` to attempt a repair. You'll need Space Transports Repair skill — even a basic roll should handle it. If you can't fix it yourself, any shipwright NPC can, but that costs credits."*
- **Implementation:** Quest engine artificially sets `sensors` to damaged state on the borrowed ship when this step activates (or the ship already has degraded condition). Player must use `damcon sensors`. Fires Space Transports Repair vs difficulty 10. Success repairs and completes step. Failure: "The repair didn't hold. Try again." (Retry after 60s, or pay a shipwright NPC.)
- **Reward:** 300cr, flag `repaired_ship: true`.
- **Completion:** *Mak: "Every credit you save on repairs is a credit in your pocket. A captain who can't fix their own ship is just a passenger with a title."*
- **Teaches:** `damcon` command, ship repair skill, repair as an alternative to paying NPCs.
- (No CW changes.)

### Step 20: "The Grand Tour" (Phase Gate → Phase 4) **[CW UPDATE — planet list]**
- **Objective:** `multi` (AND: land on all 4 active CW planets — Tatooine, Nar Shaddaa, Kuat, Coruscant)
- **Briefing (Mak, comlink):** *"Almost there. I want you to visit every planet we've got routes to — Tatooine, Nar Shaddaa, Kuat, and Coruscant. Land on each one. While you're there, check the local mission board, talk to the locals, get a feel for the place. A good spacer knows every port in their territory."*
- **Tracking:** `step_data.20.planets_landed: ["tatooine", "nar_shaddaa"]` — list, must reach 4 with the CW roster.
- **Reward:** 500cr, title *"(Outer Rim Traveler)"*.
- **Completion:** *Mak: "Four planets. Four docking bays. You know the territory now, kid. You're starting to look like a real spacer. Head back to Tatooine — we need to talk about your future."*
- **Phase gate:** Sets `phase: 4`.
- **Teaches:** Full hyperspace navigation, all four planets, confidence in space operations.
- **CW changes from v1:** Planet roster updated.

**Phase 3 total credits:** ~2,000 bonus (plus trade profits and mission income, probably another ~2,500).

---

## 6. Phase 4 — "A Spacer's Reputation" (Steps 21–26)

**Setting:** Player has ~10,000–15,000cr. They can fly, trade, fight, and navigate. This phase deepens engagement: crafting, crew management, housing, advanced multi-step operations, and meaningful faction interaction. The borrowed ship remains available.

**Narrative:** Mak is impressed. He starts treating the player as a peer rather than a student. The jobs get harder, the stakes get higher, and the player starts building the kind of reputation that makes faction leaders take notice.

**CW note:** Phase 4 has surface-level faction dialogue swaps in Step 22, and the housing-mention in Step 23 keeps the same options. Step 24's shipwright reference points at Renna Dox on Nar Shaddaa (still there) — drop the Corellia reference (Venn Kator). Step 25's "three-jobs-in-a-day" challenge is fully era-agnostic. Step 26 sets up the Phase 5 Hutt-debt arrangement (unchanged).

---

### Step 21: "The Artisan's Edge"
- **Objective:** `craft` — Craft any item using the crafting system.
- **Briefing (Mak, comlink):** *"Every spacer I've ever admired could do more than just fly and shoot. The best ones can build things — weapons, components, tools. Head to wherever you've got resources stockpiled and try your hand at crafting. If you need materials, use `survey` to gather them. Check `schematics` to see what you can build. Even a simple blaster mod is worth knowing how to make."*
- **Hint:** "Use `survey` to gather resources, `resources` to check your stockpile, `schematics` to see available blueprints, and `craft <schematic>` to build."
- **Reward:** 400cr, +2 faction_rep to `traders`.
- **Completion:** *Mak: "Not bad for a first attempt. Crafted goods carry your name on them — that's your reputation in physical form. The Traders' Coalition notices people who can build as well as shoot."*
- **Teaches:** Full crafting pipeline (survey → resources → schematics → craft), crafter identity.
- (No CW changes.)

### Step 22: "Faction Flavors" **[CW UPDATE]**
- **Objective:** `multi` (OR — complete any 2 of the following 3 sub-objectives)
  - Sub-A: Complete a bounty of tier 2+ (`bounty`)
  - Sub-B: Complete a Tier 1+ smuggling run (`smuggling`)
  - Sub-C: Complete a combat or investigation mission (`mission`)
- **Briefing (Mak, comlink):** *"You've been doing a bit of everything. Good — that's smart early on. But the factions are watching. The Bounty Hunters' Guild tracks your kills. The Hutts track your deliveries. The Republic and the CIS sympathizer networks both track who's running which kinds of jobs — different files, same data. Do any two of these: a serious bounty hunt, a real smuggling run, or a quality mission. Show the galaxy you're not a one-trick spacer."*
- **Tracking:** `step_data.22.completed: ["bounty"]` list, needs 2 entries.
- **Reward:** 800cr, +3 faction_rep to whichever factions align with the chosen sub-objectives:
  - bounty → `bh_guild`
  - smuggling → `hutt` / `underworld`
  - mission → `republic` (if Republic-flavored) or `cis` (if CIS-flavored), determined by mission's faction tag in the mission data
- **Completion:** *Mak: "Two out of three. The factions are definitely watching now. When you've got your own ship, some of them will come to you with exclusive contracts. That's when the real money starts."*
- **Teaches:** Faction standing is driven by actions across multiple systems. Specialization begins to matter.
- **CW changes from v1:** "the Empire and the Rebellion track your mission history" → "the Republic and the CIS sympathizer networks both track who's running which kinds of jobs." Faction-rep awards updated to the CW codes (`republic` and `cis` instead of `empire` and `rebel`). Mission-tag mapping is identical structurally; just the codes change.

### Step 23: "Safe Harbor" **[CW UPDATE — completion text]**
- **Objective:** `room` — Enter any room that contains housing (i.e., a room in a zone that supports housing per player_housing_design_v1.md).
- **Briefing (Mak, comlink):** *"Here's something most new spacers don't think about: where do you sleep? Docking bays are fine for a night, but if you're going to be based somewhere, you need a home. Walk through the residential areas on whatever planet you're on and look at the housing options. Type `housing list` when you're in a residential zone to see what's available. You don't have to buy anything right now — just know it exists. A home means safe storage, a place to display trophies, and a permanent address in the galaxy."*
- **Implementation:** Player enters any room in a housing-eligible zone. Quest engine checks zone metadata for housing flag.
- **Reward:** 200cr.
- **Completion:** *Mak: "Good. When you've got credits to spare, a place of your own is worth the investment. The Mos Eisley residential zone is the cheapest; Coruscant Coco Town is the most networked. Your call."*
- **Teaches:** Housing system exists, `housing list`, zones have housing eligibility, storage/trophy/security implications.
- **CW changes from v1:** "Corellia is the nicest" → "Coruscant Coco Town is the most networked." Slight reframe — Coruscant lower levels aren't "nicer" than Mos Eisley, but they have the trade network access that Corellia did in v1.

### Step 24: "The Crew Question" **[CW UPDATE — NPC list]**
- **Objective:** `talk` — Talk to any shipwright or crew-related NPC (Renna Dox on Nar Shaddaa, or any equivalent NPC at the Kuat shipyards).
- **Briefing (Mak, comlink):** *"Something to think about as you fly more: crew. A ship can run solo, but it runs better with help. An NPC gunner on the turret while you pilot. An engineer who can handle repairs mid-fight. They cost wages — 30 to 1,000 credits every four hours depending on skill — but a good crew member can save your life. Talk to Renna Dox on Nar Shaddaa about hiring options, or stop by the Kuati Drive Yards crew office if you're up that way."*
- **Implementation:** Quest completes when player talks to either Renna Dox or a designated crew-broker NPC at the Kuat shipyards. (The Kuat NPC is part of F.0 Drop 2 NPCs.yaml authoring — if not yet shipped, this step accepts Renna Dox alone as the trigger.)
- **Reward:** 300cr.
- **Crew pitch dialogue (Renna):** *"Crew, eh? I know some people looking for berths. Type `hire` at any spaceport to see who's available. Check their skills before you hire — a 2D gunner isn't worth the wages. And remember, wages tick every four hours whether you're flying or not."*
- **Teaches:** `hire` command, crew wages as an ongoing expense, NPC crew as force multipliers.
- **CW changes from v1:** Removed Venn Kator (Corellia NPC, doesn't exist in CW manifest). Renna Dox carries the entire briefing if the Kuat alternative isn't yet authored. Mention of Kuat as the secondary option makes the new active-planet roster consistent.

### Step 25: "The Big Job"
- **Objective:** `multi` (AND: complete 1 mission + 1 smuggling run + 1 bounty — all in a single play session or within 24 real hours)
- **Briefing (Mak, talk at Docking Bay 94):** *"Here's the final test before we talk about your future. I want you to do three things in the next day: run a mission, deliver a smuggling cargo, and collect a bounty. Three different kinds of work, three different skill sets, all in a day's work. That's what life as a freighter captain looks like — you never know what's coming next, and you handle it all."*
- **Tracking:** `step_data.25.started_at` timestamp + sub-objective list. All three must complete within 86,400 seconds (24 real hours) of step activation. If time expires, step resets (no penalty, just try again).
- **Reward:** 1,000cr, title *"(Versatile Spacer)"*.
- **Completion:** *Mak: "Three jobs, three different flavors, one day. You handled it. Kid... you're ready. Come see me at the bay. There's something I've been wanting to talk to you about."*
- **Teaches:** Multi-tasking across systems. The spacer lifestyle in miniature.
- (No CW changes.)

### Step 26: "The Proposition" (Phase Gate → Phase 5) **[CW UPDATE — broker reference]**
- **Objective:** `talk` — Talk to Mak Torvin at Docking Bay 94.
- **Mak (extended dialogue):** *"Sit down. I'm going to tell you something I haven't told anyone. The Rusty Mynock — the ship you've been flying — she's mine, but I can't fly her anymore. My hands shake, my eyes aren't what they were, and the medics say one more hard landing might put me in a hover chair for good. I've been looking for someone to take her over. Not just anyone — someone who knows the lanes, knows the risks, and respects what a ship means to a spacer. I think that's you. But I can't give her away for free. I still owe money on her — there's a Hutt named Drago on Nar Shaddaa who holds the note. Here's what I'm proposing: I sell her to you at a price a retired captain can live on, and you take over the debt to Drago. Lira Shan at the Kuati Drive Yards office handles the paperwork — she's a KDY broker, everything above board. The ship is worth 23,000 credits. I'll sell her to you for 8,000 — that's my retirement fund. The other 10,000 goes to Drago's man Grek on Nar Shaddaa. You pay it off over time, 500 credits a week. Miss a payment and... well, Hutts aren't known for their patience. What do you say?"*
- **Reward:** Flag `proposition_accepted: true`. No credits — this is the setup for Phase 5.
- **Phase gate:** Sets `phase: 5`.
- **Teaches:** Nothing mechanically — this is pure narrative. The player now has a concrete goal and a reason to care about the ship.
- **CW changes from v1:** "Lira Shan on Corellia handles the paperwork — she's a CEC broker" → "Lira Shan at the Kuati Drive Yards office handles the paperwork — she's a KDY broker." Same character, same role, different employer.

**Phase 4 total credits:** ~2,700 bonus (plus independent earnings, probably another ~3,000).

---

## 7. Phase 5 — "The Captain's Chair" (Steps 27–30)

**Setting:** The player has ~15,000–20,000cr. They're a seasoned operator. Phase 5 is the payoff: buying the ship, paying Grek, naming the ship, and making the first solo jump as a captain.

**CW note:** Phase 5's only CW-coupled change is the location and broker affiliation (Lira Shan moves from Corellia/CEC to Kuat/KDY). The mechanics — purchase price, debt structure, ship transfer, naming, first solo jump — are all era-agnostic. Player must travel to Kuat in Step 27 (a meaningful detour, since most prior phases focused on Tatooine and Nar Shaddaa); this is a feature, not a bug — it gives Kuat a clear plot purpose and reinforces it as a destination worth knowing.

---

### Step 27: "The Down Payment" **[CW UPDATE — planet & broker]**
- **Objective:** `talk` + automatic credit check — Talk to Lira Shan at the Kuati Drive Yards office on Kuat with at least 8,000cr.
- **Briefing (Mak, comlink):** *"Head to Kuat. Find Lira Shan at the KDY office — Kuat City spaceport, she's got an office on the spaceport's commercial concourse. She's got the title and registration ready. You'll need 8,000 credits for the purchase price — that's my cut. If you don't have it yet, go earn it. I'll wait."*
- **Implementation:** When the player talks to Lira Shan, quest engine checks `credits >= 8000`. If yes: deducts 8,000cr, proceeds. If no: Lira says "You need 8,000 credits for the purchase. Come back when you've got it." Step stays active.
- **Lira Shan (on successful purchase):** *"Mak Torvin's Ghtroc 720. CEC built her thirty years back — KDY just handles the secondhand paperwork these days. Registration transferred. She's yours now — legally, anyway. The Hutt lien is separate; you'll need to talk to Grek on Nar Shaddaa about the debt. I've filed the ownership papers with the Kuati registry. Congratulations, Captain."*
- **Reward:** Ship ownership transfers to player (quest flag `quest_ship` removed, normal ownership set). −8,000cr (purchase price).
- **Completion:** *Mak (comlink): "Lira tells me it's done. She's yours now, kid. Take care of her — she took care of me for twenty years. Now go see Grek about the debt before Drago comes looking."*
- **Teaches:** Ship purchase mechanics, KDY as the ship registry authority for used Outer Rim freighters in CW era.
- **CW changes from v1:** Corellia/Coronet Starport → Kuat/KDY office. CEC is still acknowledged in Lira's dialogue ("CEC built her thirty years back") so the Ghtroc's actual manufacturer isn't lost — it's just that the dealership is KDY in CW. Registry filed with "Kuati registry" instead of "Corellian registry."

### Step 28: "Settling Accounts"
- **Objective:** `talk` — Talk to Grek on Nar Shaddaa.
- **Briefing (Mak, comlink):** *"The fun part. Grek is Drago's man on Nar Shaddaa — he handles the Hutt's lending operation. Find him in the Undercity. He'll set up the repayment terms. Don't try to negotiate — the terms are what they are. Just sign and start earning."*
- **Grek (on talk):** *"So you're the one taking over Mak's debt. Drago was wondering when this would happen. Here's the deal: 10,000 credits, payable at 500 credits per week. We deduct automatically from your account every seven days. Miss two payments in a row and Drago sends someone to... discuss your financial planning. Pay it off early if you want — type `debt` to check your balance and make extra payments. We're reasonable people, as long as the credits flow."*
- **Implementation:** Creates the debt mechanic in character attributes:
```json
{
    "hutt_debt": {
        "principal": 10000,
        "weekly_payment": 500,
        "next_payment_due": 1713304800,
        "payments_missed": 0,
        "total_paid": 0
    }
}
```
- **The debt system:** A weekly tick handler checks `hutt_debt.next_payment_due`. If current time >= due date and player has >= 500cr: auto-deducts 500cr, reduces principal, advances next_payment_due by 7 days. If player has < 500cr: `payments_missed += 1`. At 2 missed payments: Grek sends a threatening comlink. At 3 missed: a Hutt Enforcer NPC spawns near the player (hostile, but killable — killing one is a temporary fix, reduces missed to 0, but costs faction_rep with Hutts). The `debt` command shows balance, next payment, payments remaining.
- **Reward:** Flag `debt_active: true`, +5 faction_rep to `hutt` (Drago respects someone who faces their debts). The debt itself is a 20-week credit sink (10,000 / 500 = 20 weeks).
- **Completion:** *Mak: "Grek's set up? Good. 500 a week is manageable if you're flying steady. The debt is a leash, but it's a long one — and when it's paid off, you're truly free. No one owns you or your ship."*
- **Teaches:** Debt as a long-term credit sink, `debt` command, Hutt Cartel relationship, recurring financial obligations. This is the game's version of the WEG "Tramp Freighter Captain" template's 25,000cr loan shark debt.
- (No CW changes — Hutts and the debt mechanic are era-agnostic.)

### Step 29: "Name Her"
- **Objective:** `use_command` — Use the `shipname` command to name their ship.
- **Briefing (Mak, comlink):** *"One last thing before you fly off into the sunset. She needs a name. A real name — not 'Rusty Mynock,' that's what I called her when I was young and stupid. Type `shipname <name>` and give her something she deserves. A ship's name is her soul. Choose well."*
- **Implementation:** Hook on `shipname` command. Any valid name completes the step. Name stored in ship record.
- **Reward:** 500cr ("Mak's graduation gift"), title *"(Captain)"*.
- **Completion:** *Mak: "A good name. She'll wear it well. You're a captain now, [player name]. Not because I say so — because you earned it. Fair skies and following stars."*
- **Teaches:** `shipname` command, ship personalization.
- (No CW changes.)

### Step 30: "First Solo Jump" (Chain Complete) **[CW UPDATE — profession chain list]**
- **Objective:** `space_action` — Make a hyperspace jump from any planet to any other planet in your own ship (not the loaner).
- **Briefing (Mak, comlink):** *"There's nothing more I can teach you. The galaxy's out there — your galaxy, now. Take your ship, pick a direction, and go. Your first jump as captain. Make it count."*
- **Reward:** 1,000cr, title *"(Spacer)"*, +1 CP (direct Character Point award — first and only direct CP in the chain), flag `chain_complete: true`.
- **Grand completion broadcast (room message to player's current room):**
```
═══════════════════════════════════════════════════════════════
  ★  FROM DUST TO STARS — COMPLETE  ★

  You arrived on Tatooine with nothing but a blaster and
  a prayer. Now you've got a ship, a name, a network across
  four planets, and a Hutt who expects 500 credits a week.

  Welcome to the spacer's life, Captain.

  Rewards: "(Spacer)" title, "(Captain)" title, +1 CP
  Your ship: [ship_name] (Ghtroc 720 Light Freighter)
  Debt remaining: 10,000cr to Drago the Hutt

  The profession chains are now available:
    Smuggler's Run · Bounty Hunter's Mark · Shipwright's Forge
    Republic Service · Separatist Cell · Underworld

  Type '+quest' for more information.
═══════════════════════════════════════════════════════════════
```
- **CW changes from v1:** Profession chain list updated. v1 listed "Smuggler's Run · Hunter's Mark · Artisan's Forge / Rebel Cell · Imperial Service · Underworld." v2 maps these to the CW tutorial's 8-chain roster (per `clone_wars_era_design_v3.md` §10):
  - Smuggler's Run (unchanged)
  - Bounty Hunter's Mark (renamed from "Hunter's Mark" for clarity — same chain)
  - Shipwright's Forge (renamed from "Artisan's Forge" — same chain, more CW-accurate name)
  - **Republic Service** (replaces Imperial Service — same chain, faction renamed)
  - **Separatist Cell** (replaces Rebel Cell — same chain, faction renamed)
  - Underworld (unchanged)
  
  Note that this is 6 chains in the completion message, not all 8 from the tutorial roster. The Republic Soldier, Republic Intelligence, and Jedi Path chains are tutorial-only entry points; the post-FDTS profession chains are a different set targeting captain-level play. **Open question:** verify with `clone_wars_era_design_v3.md` §10 author whether the 6-chain post-FDTS list is correct or whether the profession chain roster needs its own design pass.

**Phase 5 total credits:** Net negative (−8,000cr purchase + 1,500cr rewards = −6,500). But the player gets a ship worth 23,000cr. The 10,000cr debt creates 20 weeks of ongoing credit demand.

---

## 8. The Ship — "The Rusty Mynock" (Default Name)

(All sections 8.1–8.3 unchanged from v1 — the Ghtroc 720 is era-agnostic, and the quirks are pure flavor.)

### 8.1 Stats

Standard Ghtroc 720 from `starships.yaml`, but with degraded starting condition:

| Stat | Standard Ghtroc | Player's Ghtroc |
|------|----------------|-----------------|
| Hull | 3D+2 | 3D+2 (but condition: 65%) |
| Shields | 1D | 1D (functional) |
| Speed | 3 | 3 |
| Hyperdrive | x2 | x2 (but see quirks) |
| Cargo | 135 tons | 135 tons |
| Weapons | 1 Double Laser Cannon | 1 Double Laser Cannon (condition: 50%) |
| Mod Slots | 4 | 4 (none used) |
| Sensors | Standard | Standard (repaired in Step 19) |

### 8.2 Ship Quirks

The Ghtroc has cosmetic personality — these don't affect mechanics but appear in flavor text from the ship's `quirks` JSON field:

```json
{
    "quirks": [
        "The port engine makes a grinding noise during acceleration.",
        "The cockpit lighting flickers when the shields activate.",
        "The cargo bay door sticks and requires a solid kick to close.",
        "The hyperdrive emits a high-pitched whine for the first 10 seconds of every jump.",
        "The previous owner painted a mynock on the starboard hull. Badly."
    ]
}
```

These are displayed randomly during launch, hyperspace, and landing sequences — one quirk per event, cycling through them. Pure flavor, zero mechanical impact. They make the ship feel lived-in and create attachment.

### 8.3 Upgrade Path

The ship has 4 mod slots and 65% condition hull. This naturally drives the player toward:
- **Repair:** Getting hull condition back to 100% via `damcon` or paying a shipwright
- **Weapon repair:** Laser cannon at 50% condition needs attention
- **Modifications:** Engine boosters, shield generators, sensor suites — all craftable via the existing ship component schematics in `data/schematics.yaml`
- **The eventual upgrade dream:** Saving for a YT-1300 (100,000cr new, 25,000 used) or YT-2400 (130,000cr)

---

## 9. The Debt System

(Unchanged from v1 — Hutt debt mechanics are era-agnostic.)

### 9.1 Implementation

New section in `engine/spacer_quest.py` (or a separate `engine/debt.py` if cleaner):

```python
DEBT_WEEKLY_PAYMENT = 500
DEBT_TICK_INTERVAL = 604800  # 7 days in seconds
DEBT_WARNING_THRESHOLD = 2   # missed payments before warning
DEBT_ENFORCER_THRESHOLD = 3  # missed payments before enforcer spawn

async def process_debt_payment(db, char_id):
    """Called by weekly tick handler."""
    char = await db.get_character(char_id)
    attrs = json.loads(char["attributes"])
    debt = attrs.get("hutt_debt")
    if not debt or debt["principal"] <= 0:
        return

    if char["credits"] >= DEBT_WEEKLY_PAYMENT:
        # Auto-deduct
        new_credits = char["credits"] - DEBT_WEEKLY_PAYMENT
        debt["principal"] -= DEBT_WEEKLY_PAYMENT
        debt["total_paid"] += DEBT_WEEKLY_PAYMENT
        debt["payments_missed"] = 0
        debt["next_payment_due"] += DEBT_TICK_INTERVAL
        await db.update_credits(char_id, new_credits)
        # Send comlink: "Grek: Payment received. Balance: X credits remaining."

        if debt["principal"] <= 0:
            # DEBT PAID OFF
            debt["principal"] = 0
            # Send celebration comlink from Grek
            # Award title "(Debt Free)" and +10 faction_rep to hutt
    else:
        debt["payments_missed"] += 1
        debt["next_payment_due"] += DEBT_TICK_INTERVAL
        if debt["payments_missed"] >= DEBT_ENFORCER_THRESHOLD:
            # Spawn hostile Hutt Enforcer NPC near player
            pass
        elif debt["payments_missed"] >= DEBT_WARNING_THRESHOLD:
            # Send threatening comlink from Grek
            pass

    attrs["hutt_debt"] = debt
    await db.save_character_attributes(char_id, attrs)
```

### 9.2 Player Commands

**`debt`** (alias: `+debt`)
```
═══════════════════════════════════════════════════════════════
  HUTT CARTEL DEBT — Drago the Hutt via Grek
═══════════════════════════════════════════════════════════════
  Principal remaining: 7,500 credits
  Weekly payment:      500 credits (auto-deducted)
  Next payment due:    3 days, 14 hours
  Payments made:       5 of 20
  Payments missed:     0
  ────────────────────────────────────────────────
  Pay extra: debt pay <amount>
  Pay off entirely: debt payoff
═══════════════════════════════════════════════════════════════
```

**`debt pay <amount>`** — Make an extra payment, reducing principal.
**`debt payoff`** — Pay off the entire remaining balance (if player has enough credits).

### 9.3 Economic Impact

The debt creates 10,000cr of guaranteed credit sink over ~20 weeks. At the economy's design target of 500–2,000cr/hr active income, the weekly 500cr payment represents 15–60 minutes of earnings — meaningful but not crushing. It ensures the player stays engaged with income-generating activities after the quest chain ends.

Early payoff is possible (and encouraged — Drago respects initiative). Paying off early awards the "(Debt Free)" title and +10 Hutt faction rep.

### 9.4 Debt Paid Off — Grek's Final Message

*Grek (comlink):* "Last payment received. Your account with Drago the Hutt is closed. Pleasure doing business, Captain. Drago says to tell you — if you ever need capital again, his door is open. Better terms for returning customers."

Awards: Title *"(Debt Free)"*, +10 faction_rep to `hutt`.

---

## 10. Systems Coverage Audit

(Unchanged from v1 — every major game system touched by this chain. Faction rows updated to CW codes.)

| System | Starter Chain | Tutorial | THIS CHAIN | How |
|--------|--------------|----------|------------|-----|
| Movement/Look | ✓ | ✓ | — | Already covered |
| Talk to NPCs | ✓ | ✓ | ✓ | Steps 7, 14, 24, 26, 27, 28 |
| Combat | — | ✓ | ✓ | Steps 2, 22, 25 |
| Missions | ✓ | ✓ | ✓ | Steps 1, 5, 22, 25 |
| Skill Checks | ✓ | — | ✓ | Steps 3, 4, 19 |
| **Factions (CW roster)** | — | Stub | **✓ DEEP** | Steps 8, 9, 10, 22, 28 |
| **Bounties** | — | ✓ | **✓** | Steps 9, 22, 25 |
| **Smuggling** | — | — | **✓** | Steps 10, 22, 25 |
| **Trade Goods** | — | — | **✓** | Step 18 |
| **Sabacc** | — | — | **✓** | Step 6 |
| **CP/Train** | — | — | **✓** | Step 12 |
| **+Background** | — | — | **✓** | Step 11 |
| **Space Flight** | — | ✓ | **✓** | Steps 15, 16, 17, 30 |
| **Hyperspace** | — | ✓ | **✓** | Steps 16, 30 |
| **Ship Repair** | — | ✓ | **✓** | Step 19 |
| **Trading Route** | — | — | **✓** | Step 18 |
| **Crafting** | — | ✓ | **✓** | Step 21 |
| **NPC Crew** | — | ✓ | **✓** | Step 24 |
| **Housing** | — | — | **✓** | Step 23 |
| **Ship Ownership** | — | — | **✓** | Steps 27, 29 |
| **Debt/Finance** | — | — | **✓** | Steps 28, ongoing |
| **Cross-Planet Travel** | — | — | **✓** | Steps 13, 14, 18, 20 |

Systems NOT covered (by design — they're too niche or too advanced for a new player chain):
- **Force Powers** (gated by Force sensitivity flag from tutorial; potentially unlocks via Jedi Village quest chain — Drop F.8)
- Capital Ships (endgame content)
- Territory Control (faction leader content)
- Player Shops/Vendor Droids (mid-game economic specialization)
- Party System (multiplayer — can't be quest-gated)

---

## 11. Reward Summary

(Unchanged from v1 — credit/title/rep totals are identical. Faction codes updated to CW.)

| Step | Credits | Items/Titles | Faction Rep |
|------|---------|-------------|-------------|
| 1 | +200 | — | — |
| 2 | +300 | quality-55 hold-out blaster | — |
| 3 | +250 | — | — |
| 4 | +400 | — | — |
| 5 | +800 | — | — |
| 6 | +100 | — | — |
| 7 | +250 | — | — |
| 8 | +150 | — | traders +2 |
| 9 | +500 | — | bh_guild +3 |
| 10 | +400 | — | hutt +2, underworld +1 |
| 11 | +200 | — | — |
| 12 | +100 | — | — |
| 13 | +500 | — | traders +1 |
| 14 | +600 | — | hutt +2, underworld +2 |
| 15 | +200 | Borrowed ship | — |
| 16 | +300 | — | — |
| 17 | +200 | — | — |
| 18 | +500 | — | — |
| 19 | +300 | — | — |
| 20 | +500 | "(Outer Rim Traveler)" title | — |
| 21 | +400 | — | traders +2 |
| 22 | +800 | — | varies (`bh_guild`, `hutt`/`underworld`, `republic`/`cis` per choice) |
| 23 | +200 | — | — |
| 24 | +300 | — | — |
| 25 | +1,000 | "(Versatile Spacer)" title | — |
| 26 | — | — | — |
| 27 | −8,000 | SHIP (Ghtroc 720) | — |
| 28 | — | — | hutt +5 |
| 29 | +500 | "(Captain)" title | — |
| 30 | +1,000 | "(Spacer)" title, +1 CP | — |
| **Debt payoff** | — | "(Debt Free)" title | hutt +10 |
| **TOTAL** | **~+2,150 net** | Ship + 4 titles + 1 CP + blaster | hutt +19, traders +5, bh_guild +3, underworld +3 |

The net credit gain is modest because the ship purchase absorbs most earnings. The player ends the chain with a ship, a debt, and motivation to keep playing. They're NOT rich — they're a new captain scrambling to make payments, exactly like the WEG "Tramp Freighter Captain" template.

---

## 12. Implementation Plan for Sonnet

(Drop structure unchanged from v1. NPC additions in Drop 7 updated for CW.)

### Drop 1: Quest Engine Core (~500 lines)
**File:** `engine/spacer_quest.py`

- `QuestStep` dataclass
- `QUEST_STEPS` — dict of all 30 steps (data, not logic)
- `check_spacer_quest(ctx, trigger_type, trigger_data)` — the universal hook function
- `get_current_step(char)` — reads attributes JSON, returns current QuestStep
- `complete_step(ctx, char, step)` — awards rewards, advances state, sends comlink
- `activate_step(ctx, char, step)` — sends briefing, sets up step_data
- Quest state read/write helpers

**Dependencies:** None. Pure data + logic, reads/writes attributes JSON.

### Drop 2: Hook Installation (~200 lines across many files)
Add `await check_spacer_quest(ctx, ...)` calls to:

- `parser/builtin_commands.py` — TalkCommand (1 line)
- `server/session.py` — room entry handler (1 line)
- `parser/mission_commands.py` — CompleteMissionCommand (1 line)
- `engine/combat.py` — kill resolution (1 line)
- `parser/smuggling_commands.py` — SmugDeliverCommand (1 line)
- `parser/bounty_commands.py` — BountyCollectCommand (1 line)
- `parser/trade_commands.py` — TradeCommand (1 line)
- `engine/crafting.py` — CraftCommand completion (1 line)
- `parser/space_commands.py` — LaunchCommand, LandCommand, HyperspaceCommand (3 lines)
- `parser/sabacc_commands.py` — SabaccCommand (1 line)
- Various: cpstatus, factions, +background, shipname (4 lines)

Each hook is: `from engine.spacer_quest import check_spacer_quest` + `await check_spacer_quest(ctx, "type", {data})`. Total: ~15 one-liners across 12 files.

### Drop 3: Player Command (~100 lines)
**File:** `parser/quest_commands.py` (or add to existing `narrative_commands.py`)

- `QuestCommand` — `+quest`, `+quest log`, `+quest abandon`
- ANSI-formatted display with progress bar

### Drop 4: Passenger Travel (~80 lines)
**File:** Addition to `parser/builtin_commands.py` or new `parser/travel_commands.py`

- `TravelCommand` — `travel <planet>` for quest passengers (Phase 2–3 only, before they have a ship)
- Checks quest state, validates player is at a docking bay, teleports with narrative wrapper
- Only active when `spacer_quest.phase in (2, 3)` and player doesn't own a ship

### Drop 5: Borrowed Ship System (~100 lines)
**Addition to:** `engine/spacer_quest.py`

- `create_borrowed_ship(ctx, char)` — creates the Ghtroc with quest flags
- `return_borrowed_ship(ctx, char)` — on quest abandon or Phase 5 completion
- `transfer_ship_ownership(ctx, char)` — converts loaner to owned ship (Step 27)
- Quest flag `quest_ship: true` in ship systems JSON prevents sale/transfer

### Drop 6: Debt System (~200 lines)
**File:** `engine/debt.py`

- `process_debt_payment(db, char_id)` — weekly tick handler
- `DebtCommand` — `debt`, `debt pay <amount>`, `debt payoff`
- Enforcer spawn logic on missed payments
- Integration with `tick_handlers_economy.py` (add debt tick to weekly cycle)

### Drop 7: NPC Additions (~30 lines) **[CW UPDATE]**
**Addition to:** `data/worlds/clone_wars/npcs.yaml` (preferred — pending F.0 Drop 2 NPC YAML authoring)
**Or:** inline in `engine/spacer_quest.py` if F.0 Drop 2 hasn't shipped yet

- **Mak Torvin** NPC entry (Docking Bay 94, Tatooine) — non-hostile, AI brain enabled with quest-specific context. CW-flavored backstory ("CW veteran who's been running freighters since before the war started").
- **Lira Shan** NPC entry (Kuati Drive Yards office at Kuat City spaceport, Kuat) — non-hostile, no AI brain (transactional NPC, scripted dialogue only). **Replaces v1's Corellia/CEC placement.**
- **Grek** NPC entry (Nar Shaddaa Undercity) — non-hostile but unsettling, AI brain enabled with Hutt-cartel context.

If F.0 Drop 2 has authored `npcs.yaml`, append the three FDTS NPCs in. If not, register them via `engine/npc_loader.py` augmentation pattern (the same way `data/npcs_gg7.yaml` is currently loaded) and migrate to YAML when F.0 Drop 2 lands.

### Drop 8: Quest Step Data (~400 lines)
**Addition to:** `engine/spacer_quest.py` or `data/spacer_quest.yaml`

- All 30 QuestStep definitions with full dialogue text, objective data, rewards
- This is pure data — the largest single chunk but also the simplest to write
- **CW dialogue applied per §3–§7 of this doc** (the [CW UPDATE] markers identify the steps that diverge from v1)

### Drop 9: Testing & Polish
- Walk through all 30 steps manually
- Verify hook triggers
- Test edge cases: abandon mid-chain, server restart mid-step, death during quest combat
- Verify debt tick handler
- Verify ship transfer
- **CW-specific verification:** confirm the four-planet tour completes (Tatooine + Nar Shaddaa + Kuat + Coruscant), confirm Step 27 lookup finds Lira Shan at Kuat (not Corellia), confirm faction rep awards land on the correct CW codes.

**Total estimated code:** ~1,600 lines of new code across 3–4 new files + ~20 lines of hooks across 12 existing files.

**Recommended implementation order:** Drop 1 → Drop 8 → Drop 3 → Drop 2 → Drop 7 → Drop 4 → Drop 5 → Drop 6 → Drop 9

(Engine first, then data, then display, then hooks, then NPCs, then travel/ship/debt, then test everything.)

---

## 13. Design Decisions & Rationale

(All v1 rationale carries forward. Two CW-specific additions.)

**Why 30 steps?** Short enough that each step feels achievable (average 30–45 minutes each), long enough that the chain represents genuine investment. 30 steps over 2–3 weeks matches the WEG assumption that "getting a ship takes weeks, not hours."

**Why a Ghtroc 720 and not a YT-1300?** The Ghtroc is 23,000cr used vs 25,000cr for a used YT-1300, but more importantly, it has 135 tons of cargo vs 100 — making it a better trader's ship. It's also less iconic, which means the player's eventual upgrade to a YT-1300 feels like genuine progression. The Ghtroc is the starter ship; the YT-1300 is the dream ship.

**Why a Hutt debt?** Three reasons. First, it's canon — the WEG Smuggler template starts with 25,000cr owed to a crime boss, and the Tramp Freighter Captain template from GG6 has a similar loanshark arrangement. Second, it creates a 20-week credit sink that solves the post-ship "now what?" problem. Third, it creates a narrative hook: the Hutt relationship can feed into the Underworld profession chain or the Smuggler's Run chain naturally.

**Why no new rooms?** Rooms are expensive (build script changes, DB rebuilds, exit wiring). The existing CW rooms across 4 active planets provide more than enough geography for 30 quest steps. Every location in the chain already exists.

**Why the passenger travel mechanic?** A new player can't fly to Nar Shaddaa before they have a ship, but the quest chain needs them to go there to learn about factions and the wider galaxy. "Booking passage" is the WEG-canon solution (R&E has a whole section on it). The `travel` command is a lightweight quest-gated teleport that simulates this without requiring ship ownership.

**Why introduce factions this deep?** The existing tutorial only briefly introduces factions. This chain goes much deeper: the player interacts with faction-aligned NPCs, runs faction-colored missions (bounties for the Guild, smuggling for the Hutts), sees their faction rep change, and ends the chain with meaningful rep in 3–4 factions. By the time they finish, they understand factions as a live system, not a menu.

**Why award +1 CP at the end?** A direct CP award is the most powerful reward in the game — it lets the player immediately improve a skill. It's appropriate here because the chain represents 2–3 weeks of active play, which is roughly the passive accrual time for 1 CP anyway. It also teaches the `train` command by giving the player something to spend.

**[v2] Why Kuat and Coruscant instead of Kessel and Corellia?** v1's planet roster was matched to GCW Mos Eisley galactic geography (Kessel as the "Imperial mining colony" destination, Corellia as the "shipbuilding capital and CEC home"). The CW manifest doesn't include those planets. **Kuat** preserves the structural role Kessel and Corellia played jointly: industrial/shipyard destination AND the location where Lira Shan brokers ship deals. **Coruscant lower levels** preserves the "big city, full of work for spacers who keep their mouths shut" role Corellia partly played, with the added narrative weight of the war-distant capital. Both are canonical CW destinations and both have rooms authored in `data/worlds/clone_wars/`.

**[v2] Why is Mak a CW veteran instead of a GCW-era pre-CW captain?** v1 placed Mak in GCW with the line "since before the Clone Wars" — implying he was active during CW and is now retired post-war. v2 places Mak in mid-CW (~20 BBY) with the line "since before the war started," meaning he was an Outer Rim freighter captain in the Republic-pre-war era and has continued through the war's onset. He's CW-current, not CW-veteran. This preserves the character's seasoned-old-spacer feel without anachronism. His health-driven retirement (shaky hands, bad knees) is era-agnostic — old spacers retire in any era.

---

## 14. Interaction with Existing Systems

(Updated for CW.)

### 14.1 Tutorial Chain (CW — 8 chains per `clone_wars_era_design_v3.md` §10)
The tutorial must be complete before this chain activates. The tutorial uses `tutorial_state` in attributes; this chain uses `spacer_quest`. No overlap. Activation gate accepts any of the 8 CW tutorial chains as completion.

### 14.2 Starter Quest Chain
The starter chain (Kessa's Mos Eisley errands) must be complete (step >= 10) before this chain activates. No overlap in step numbering — the starter chain uses `starter_quest` in attributes, this uses `spacer_quest`.

### 14.3 Planetary Discovery Quests
Discovery quests trigger on first planetary landing. The player will likely trigger Nar Shaddaa's discovery quest during Step 13, and Kuat/Coruscant during Steps 15–20. These run independently and concurrently — no conflict.

### 14.4 Profession Chains
Profession chains require: a ship (Smuggler's Run, Republic Service, Underworld), specific skill levels, or mission experience. This chain naturally satisfies those prerequisites. The chain completion message explicitly lists the available CW profession chains as "what's next." (See Step 30 for the canonical list, with the open question on whether the post-FDTS profession-chain set is six chains or eight.)

### 14.5 Economy
Chain credit rewards (~20,000cr gross, ~2,000 net after ship purchase) are calibrated against the economy design targets. At 500–2,000cr/hr active income, the chain's bonus credits represent roughly 10–40 hours of equivalent grinding — appropriate for 12–20 hours of quest content. The ship + debt creates long-term economic engagement.

### 14.6 [v2 NEW] Force Sensitivity & Jedi Village Path
Per `clone_wars_era_design_v3.md` §10.3, every CW character has a 50% chance of being flagged Force-sensitive at tutorial completion. FDTS does NOT currently include a Force-sign hook (deferred until Drop F.8 — the Jedi Village quest chain — is built). When F.8 ships, an optional Step 11.5 can be added between Steps 11 and 12, surfacing only for Force-sensitive players, where Mak hints at the Village. Until then: `# TODO(force_sensitive)` marker in `engine/spacer_quest.py`.

### 14.7 [v2 NEW] War as Background
The Clone Wars are the dominant ambient context but aren't *fought* on the four active FDTS planets. Two flavor lines added in v2 (Steps 7 and 17) reference the war as background ambience without making it the plot. Director-AI ambient generation can add more (clone troopers passing through Mos Eisley, Holonet news mentioning Jedi-led campaigns elsewhere, etc.) — that lives in `data/ambient_events.yaml`, not in the FDTS engine.

---

## 15. Open Questions for Implementation Session

These don't block the implementation but should be answered as the work proceeds:

1. **Profession chain roster.** Step 30's completion message lists six post-FDTS profession chains. Confirm with the `clone_wars_era_design_v3.md` §10 author whether this is correct or whether the post-FDTS profession set needs its own design pass (the tutorial roster is 8 chains — 3 are entry-only, leaving 5; v2 lists 6, so there's a one-chain mismatch to resolve).

2. **Kuat crew-broker NPC.** Step 24's "Kuati Drive Yards crew office" NPC isn't yet authored. Either:
   - (a) author a placeholder NPC in F.0 Drop 2's `npcs.yaml` work, or
   - (b) ship FDTS v2 with Renna Dox as the sole Step 24 trigger and add the Kuat alternative in a follow-up. Recommend (b) — small enough to defer.

3. **Tutorial-FDTS handoff dialogue.** When the player completes any of the 8 CW tutorial chains, what triggers Kessa's first FDTS-Step-1 comlink? v1 assumed a single starter-chain completion; v2 has 8 entry points. Probably a single shared completion event fires regardless of chain, but verify in the tutorial rework drop's design.

4. **Faction-rep tag mapping for missions.** Step 22's `mission` sub-objective awards `republic` or `cis` faction rep based on the mission's faction tag. Verify that mission generators in the live mission system actually tag missions with `republic`/`cis` codes (not generic mission types). If not, add the tagging in mission generation as a small follow-up.

5. **Should the war get a recurring narrative beat?** Currently v2 has two ambient flavor lines (Steps 7 and 17). Could expand to a third in Phase 4 (Mak commenting on a recent campaign in passing dialogue) for a stronger sense that the war is happening *somewhere*. Optional — recommend deferring until live testing reveals whether the war feels too absent.

---

## 16. v1 → v2 Change Summary (For Reviewers)

For quick reference, here's everything that changed from v1 to v2:

**Steps with [CW UPDATE] markers:** 7, 8, 10, 14, 16, 17, 18, 20, 22, 23, 24, 26, 27, 30. That's 14 of 30 steps with surface-level edits — mostly faction-name swaps, destination-list updates, and minor flavor tweaks.

**Steps unchanged from v1:** 1, 2, 3, 4, 5, 6, 9, 11, 12, 13, 15, 19, 21, 25, 28, 29. That's 16 of 30 steps fully unchanged.

**Structural changes:** none. The 5-phase arc, 30-step skeleton, NPC mentor pair, ship reward, debt mechanic, hook architecture, command interface, all data structures — all preserved verbatim.

**New section:** §0 Era Coupling Notes (this doc).

**Added war flavor:** two sentences total (Steps 7 and 17). Defers Force-sign hook to post-F.8.

**NPC roster changes:** Lira Shan moves from Corellia (CEC) to Kuat (KDY). Mak Torvin and Grek unchanged in placement and role.

**Faction-code swaps in JSON examples:** `empire`→`republic`, `rebel`→`cis`. Other codes (`hutt`, `bh_guild`, `traders`, `underworld`) unchanged.

---

*"She may not look like much, but she's got it where it counts, kid."*

*The best ship in the galaxy isn't the fastest or the toughest. It's the one that's yours.*

*End of design document — v2.*
