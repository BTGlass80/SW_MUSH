# SW_MUSH — Padawan / Master System Design
## Version 1.0 — April 18, 2026 · Opus parallel session (Clone Wars track)
### Mechanical spec for the Jedi apprenticeship system.

---

## 1. Purpose

This document defines the mechanical bond between Padawan and Master PCs in SW_MUSH. It specifies: how the relationship is established, what it enables mechanically, how it is dissolved, how falls are handled, and how Knight promotion works.

This is an implementation spec. It is the source of truth for Drop 2 authoring of the Padawan/Master commands, database schema, and Director AI integration.

**Prerequisites:** `launch_strategy_v1.md` (tier allocation, launch-day caps), `clone_wars_era_design_v4.md` (faction structure, Jedi Order context), `jas_extraction_v1.md` (Jedi pedagogy lore, Force powers).

---

## 2. Core Principle

**Players train players.** No NPC Masters. No NPC Padawans. Every Master-Padawan pair is two PCs with a real OOC relationship. The Director AI supports and amplifies the bond with narrative memory, Force-vision prompts, and Council dialogue — but it never replaces a human in the relationship.

This choice is load-bearing. It makes the system socially real, it eliminates an entire category of Director AI integration complexity, and it makes the scarcity of Masters (per `launch_strategy_v1.md`) meaningful rather than artificial.

---

## 3. Tier Definitions

The Jedi hierarchy in SW_MUSH has four tiers. Only the first three are available as PCs at launch.

### 3.1 Initiate (Youngling)

**Not a PC tier at launch.** Reserved for future expansion (potential chargen path for younger character concepts, Temple-raised characters).

### 3.2 Padawan

**Starting Jedi PC tier** (per `clone_wars_era_design_v4.md` §3.4).

- Force Sensitive: Yes (required)
- Force Skills at creation: Control 2D, Sense 2D, Alter 1D
- Known Powers at creation: concentration, sense Force, life detection, lightsaber combat
- Force Points at creation: 2
- Dark Side Points at creation: 0
- Equipment: Padawan robes (beige/brown/earth tones), Padawan braid, lightsaber (constructed under Master's guidance during chargen narrative, color selected by player), Jedi utility belt, datapad
- Starting location: Jedi Temple on Coruscant, or on assignment with their Master
- Special constraint: **must have a linked Master PC** (or be on the Padawan waitlist per `launch_strategy_v1.md` §5.4)

### 3.3 Knight

**Earned tier** (in-game advancement) or **launch-day seeded tier** (per `launch_strategy_v1.md`).

- Force Skills (typical): Control 4D-6D, Sense 4D-6D, Alter 3D-5D
- Knight-tier Known Powers: expanded set — typical Knight knows 8-12 powers across all three disciplines
- Force Points (typical): 3
- Dark Side Points: variable (Knights with combat experience may have 1-2)
- Equipment: Knight robes (varied, personalized), lightsaber (self-constructed at end of Padawan training), Jedi utility belt, datapad, mission-variable gear
- Can take a Padawan: **No, not automatically.** Knight becomes eligible to take a Padawan after being explicitly authorized by the Council (staff adjudication post-launch; launch-day Knights are not automatically Master-eligible).
- Rank title: "Jedi Knight"

### 3.4 Master

**Earned tier** (post-launch advancement) or **launch-day seeded tier** (per `launch_strategy_v1.md`).

- Force Skills (typical): Control 7D-10D+, Sense 7D-10D+, Alter 5D-8D+
- Master-tier Known Powers: broad — typical Master knows 15-20+ powers across all three disciplines
- Force Points (typical): 5+
- Dark Side Points: variable
- Equipment: Master robes (often with distinctive personal variation), lightsaber (often reworked/upgraded), full Jedi gear, Council-dispatched mission equipment
- Can take a Padawan: **Yes.** Master tier is defined by Padawan-taking authority.
- Rank title: "Jedi Master"

### 3.5 Tier Progression

Progression path: Padawan → (Trials) → Knight → (take Padawan to Knight) → Master.

Each transition is adjudicated. Not every Knight becomes a Master. Some Knights prefer solo missions, diplomatic roles, or specialist paths (Sentinels, Consulars) that do not require taking apprentices.

---

## 4. The Bond: Establishing a Padawan/Master Pair

### 4.1 Launch-Day Assignment (Tester-Seeded Cohort)

Handled per `launch_strategy_v1.md` §5. Tester-Masters and tester-Knights are assigned tier pre-launch; launch-day Padawan PCs are paired with available Masters at chargen time based on:

1. Player preference (Padawan indicates 1-3 preferred Masters by PC name if any)
2. Master consent (Master PC must opt in; Masters can cap at 0 Padawans if they wish)
3. Staff mediation if the matching is contentious

Padawan PCs whose preferences cannot be satisfied go to the **Padawan waitlist** (canon: Initiates-awaiting-assignment at Temple), per `launch_strategy_v1.md` §5.4.

### 4.2 Post-Launch Assignment

Post-launch, new Padawan PCs and newly-Master-eligible Knights are paired through one of:

**Path A: Mutual selection.** Master PC announces they are taking a Padawan; interested Padawan-tier PCs apply in-character; Master selects; Council (staff/Director AI) ratifies.

**Path B: Council assignment.** Padawan-tier PC requests a Master; Council reviews available Masters and assigns based on compatibility (teaching style, mission roles, availability). Staff-mediated.

**Path C: Narrative-driven.** Organic pairing through gameplay — a Knight saves a young Force-sensitive during a mission, a Master takes an interest in a wandering initiate, etc. Staff approves the narrative and formalizes the bond.

All three paths converge on the same mechanical state: a `master_padawan_bond` record in the database.

### 4.3 Database Schema

```sql
CREATE TABLE master_padawan_bond (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_char_id INTEGER NOT NULL,
    padawan_char_id INTEGER NOT NULL,
    bond_established_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bond_status TEXT NOT NULL CHECK(bond_status IN ('active', 'dissolved', 'knighted', 'fallen')),
    dissolved_at TIMESTAMP,
    dissolved_reason TEXT,
    knight_promotion_at TIMESTAMP,
    trials_passed_json TEXT,  -- JSON array of passed Trial names
    FOREIGN KEY (master_char_id) REFERENCES characters(char_id),
    FOREIGN KEY (padawan_char_id) REFERENCES characters(char_id)
);

CREATE INDEX idx_bond_master ON master_padawan_bond(master_char_id, bond_status);
CREATE INDEX idx_bond_padawan ON master_padawan_bond(padawan_char_id, bond_status);
```

**Constraint:** At any time, a Padawan-tier PC has at most one `bond_status='active'` bond. A Master-tier PC has at most one `bond_status='active'` bond at launch; post-launch, this cap may be raised to 2 via Council authorization (staff adjudication).

**Schema migration note:** This is an additive schema change. Apply via the existing boot-time migration pattern in `engine/db_migrations.py`.

---

## 5. What the Bond Enables

Mechanical effects of an active Master-Padawan bond:

### 5.1 Shared Awareness

- `who` output highlights your bonded partner with a visual marker (web client: avatar halo; telnet: asterisk prefix on their name).
- A new command `+master` (for Padawans) and `+padawan` (for Masters) reports the partner's current zone, general status (safe / in combat / wounded / unknown), and last-seen timestamp. This is narrative awareness, not GPS — it models the Force-bond between the pair.
- A `+forcebond` command activates a deeper sense: for 1 Force Point, either side can roll `sense` (Moderate) to locate their partner's general location and sense their emotional state. This uses the existing Force Point economy per `engine/force_powers.py`.

### 5.2 Training Commands

- `+teach <power>` — Master command. Formally teaches the Padawan a Force power the Master knows. Padawan gains the power at 1D if they meet prerequisites; Master marks the teaching in `training_log`. Uses CP from Padawan; uses nothing from Master.
- `+learn <power> from <master>` — Padawan command. Requests instruction. Master must accept (`+teach` command) for the teaching to register.
- `+spar` — initiates a training lightsaber duel (non-lethal combat mode per `engine/combat.py`) between bonded pair. Grants CP to both on completion regardless of outcome. Cap: 1 CP-granting spar per in-game day per pair.

### 5.3 Master Approval Weight

Several gameplay actions are gated by Master approval for Padawan PCs:

- Leaving Coruscant for a non-Council-sanctioned mission (Master can approve or deny; denial + defiance = dark side narrative trigger, see §7)
- Using a Force power the Master has not authorized for field use (per training discipline)
- Initiating a formal Trial attempt (Master must endorse; without endorsement, the attempt fails automatically)

Implementation: commands that require Master approval check for an active bond; if present, issue an OOC notification to the Master PC and block the action pending `+approve <padawan> <action>` or `+deny <padawan> <action>`. A Master can pre-authorize categories via `+authorize <padawan> <category>` to avoid needing per-action approval for routine activities.

**Master absence handling:** if Master PC has been offline >7 days, approval-gated actions default to Council-adjudication (auto-approve after 24 hours with a notification to staff). This prevents a missing Master from bricking a Padawan's gameplay.

### 5.4 Shared Narrative Memory

The PC narrative memory system (per `pc_narrative_memory_design_v1.md`) already stores per-character memory arcs. For bonded pairs, **shared memories** are automatically cross-written: a significant event involving both PCs generates one memory entry linked to both character IDs. The Director AI surfaces these shared memories in both PCs' contexts when generating NPC dialogue, Force visions, or scene suggestions.

This is the technical substrate for "the Master remembers the mission where the Padawan first defied orders" — both PCs have the memory, the Director AI can invoke it for either of them, and the relationship feels continuous across sessions.

---

## 6. The Trials: Padawan → Knight Promotion

### 6.1 Overview

Per the canon traditions captured in `jas_extraction_v1.md` §2 (Jedi Trials lore entry), a Padawan becomes a Knight by passing the Jedi Trials. SW_MUSH implements five Trials, each a separate gameplay event.

### 6.2 The Five Trials

| Trial | Gameplay Mechanic | Pass Condition |
|---|---|---|
| **Trial of Skill** | Combat/Force-power demonstration before Council | Moderate+ success on lightsaber combat + one Force power of Padawan's choosing |
| **Trial of Courage** | Solo mission into contested or lawless zone | Complete objective without Master assistance; Very Difficult threat tier |
| **Trial of Flesh** | Endurance/injury event | Survive a prolonged hostile situation (prolonged combat, capture, environmental hardship) — no Master rescue |
| **Trial of Spirit** | Confronting inner darkness | Director AI-narrated vision event that tempts the Padawan with dark side advancement; pass = refuse |
| **Trial of Insight** | Perception/puzzle event | Solve a mystery, detect a deception, or identify a hidden truth (Difficult+ Perception/investigation challenge) |

### 6.3 Trial Mechanics

- **Endorsement:** Master must endorse Trial attempt via `+endorse trials <padawan>`. Without endorsement, attempts auto-fail. This is the Master's approval-weight showing up concretely.
- **Sequencing:** Trials can be attempted in any order, but all five must be passed. No time limit.
- **Failure:** A failed Trial is not permanent. Padawan returns to training and attempts again later. Repeated failures (>3 on the same Trial) flag for staff review — often indicates the Padawan needs mechanical help (more CP, different approach) or the Trial was improperly scoped.
- **Trial Record:** `master_padawan_bond.trials_passed_json` stores the list of passed Trials. Queried via `+trials <padawan>` command.
- **The Fifth Trial (Spirit):** Because this is a Director AI-narrated event, it requires a real prompt session. Brian may choose to make this a scheduled event (staff-facilitated) rather than on-demand, to ensure quality narrative. Alternatively, it is a fully AI-adjudicated event with Director AI taking the role of the dark-side tempter.

### 6.4 Knight Promotion Ceremony

When all five Trials are passed:

1. Master invokes `+knight <padawan>` (requires all five Trials recorded).
2. Command triggers a ceremonial event at the Jedi Temple (Council Chamber room; Director AI narrates the ceremony; other online Jedi PCs are auto-notified and can attend).
3. Padawan's character data updates: tier shifts from "padawan" to "knight"; braid item removed (narrative: cut during ceremony); Force skills adjust per Knight norms (typically +1D-2D across skills, funded by stored CP); Force Points grant +1.
4. Bond status updates to `knighted`; `knight_promotion_at` timestamp recorded.
5. New Knight is now eligible (but not automatically authorized) to take a Padawan in the future.

**Narrative convention:** The new Knight typically constructs a new lightsaber at or around promotion, reflecting their matured identity. This is a chargen-like mini-event, not a hard requirement — some Knights keep their Padawan saber for sentimental reasons.

---

## 7. Falls: When a Padawan Turns Dark

### 7.1 The DSP Threshold

Per `engine/force_powers.py` existing mechanics, a character with Dark Side Points exceeding their Force Points accumulates to the dark side. For a Padawan with starting Force Points of 2, this threshold is quickly reached.

### 7.2 Fall Triggers

A Padawan's bond is at risk when:

- DSP exceeds Force Points (standard WEG rule)
- Padawan uses a Sith power (auto-DSP per `jas_extraction_v1.md` §4)
- Padawan defies a direct Master order in a way that causes harm
- Padawan's "weight of war" state reaches critical (per `weight_of_war_design_v1.md`, pending)

### 7.3 Fall Consequences

**Stage 1: Concern.** Master receives OOC notification ("Your Padawan's connection to the Force is troubling you"). Director AI begins surfacing darker Force visions in Padawan's dreams. No mechanical penalty yet.

**Stage 2: Warning.** Master-Padawan bond stress increases. Some bond commands (`+spar`, `+forcebond`) have reduced effectiveness (narrative: the bond itself resists being used for good while the Padawan is turning). Council receives automated flag. Staff may intervene narratively.

**Stage 3: Fall.** DSP exceeds FP + 3, or Padawan takes a fall-commitment action (kills surrendered enemy, attacks Master, uses Sith power repeatedly). Bond status automatically shifts to `fallen`. Padawan character is locked for 24 hours OOC for a narrative-restart event (staff-facilitated or Director AI-narrated). Padawan emerges as:
  - **Fallen Padawan PC** (dark side, no longer Jedi; faction shift to independent or Separatist sympathizer; retains lightsaber but may reconstruct to alternate form including double-bladed per JAS lore)
  - OR narrative-death (player opts to retire the character)

**Stage 4: Master Accountability.** When a Padawan falls, the Master's standing with the Council reduces (mechanically: Jedi faction reputation -20). Master receives a Director AI-narrated Council summons. This is narrative, not punitive — the Master is not stripped of tier — but it creates RP fuel and models the canon reality that every Jedi fall is a lineage wound.

### 7.4 Reversal / Redemption

A Fallen Padawan can return to the light through gameplay. This is a long arc, not a flip of a flag: DSP reduction through Force Point expenditure on light-side acts, reconciliation with Master (if Master will accept), Council trial. Implementation deferred to post-launch — at launch, fallen Padawans remain fallen.

### 7.5 When the Master Falls

Mirrored. If a Master PC accumulates DSP to the fall threshold, the Padawan receives narrative notification ("Your Master's presence in the Force has grown cold"). The Padawan can:

- **Stand with their Master** (accept the fall, follow them into darkness — Padawan gains DSP, eventually falls themselves)
- **Stand against their Master** (attempt to stop them — triggers a dramatic encounter, Council backing, eventual bond dissolution with status `dissolved` and reason `master_fallen_padawan_loyal`)
- **Flee** (break the bond without direct confrontation — bond dissolved, Padawan becomes a free agent, Council offers reassignment)

This is the Dooku/Qui-Gon situation in reverse — if your Master turns, you have choices. This is a design intent, not a mechanically-locked path: staff adjudicates the specifics.

---

## 8. Bond Dissolution (Non-Fall Cases)

Outside of falls, bonds can dissolve for several reasons:

| Dissolution Reason | Trigger | Handling |
|---|---|---|
| `knighted` | Padawan passes Trials | Automatic; bond status = knighted |
| `master_inactive` | Master PC offline >2 weeks without notice | Staff-mediated; Padawan offered reassignment or waitlist |
| `master_voluntary` | Master invokes `+release <padawan>` | Requires reason; Council review; Padawan goes to reassignment |
| `padawan_voluntary` | Padawan invokes `+leave-master` | Requires reason; staff review (discourages impulsive breaks); if approved, Padawan to reassignment or retired |
| `ooc_conflict` | Players cannot continue together | Staff-mediated; no in-character narrative penalty to either |
| `master_killed` | Master PC permadeath | Automatic on PC death event; Padawan receives shared-memory trauma event; reassignment offered after grief period |
| `master_fallen_padawan_loyal` | Master falls, Padawan stands against | See §7.5 |
| `fallen` | Padawan falls | See §7.3 |

All dissolutions record `dissolved_at` and `dissolved_reason`. The pair's shared narrative memory is preserved (not deleted) — past events remain in both characters' histories.

---

## 9. Director AI Integration

The Director AI (per `director_ai_design_v1.md`) gains the following bond-aware prompts:

- **Bond-aware NPC dialogue:** When an NPC addresses a Padawan or Master PC, the Director AI is told "this character has a bonded [Master/Padawan] named [X]" and can weave references naturally.
- **Council dialogue:** Council NPC dialogue (Master Yoda, Master Windu, etc.) acknowledges the bond explicitly — praise, concern, or summoning — based on bond status and recent events.
- **Force visions:** Shared-memory events generate Force-vision prompts for both pair members that reference the other. Director AI can produce "You dream of your Master standing alone on a battlefield" or "You sense your Padawan in danger" prompts.
- **Trial of Spirit narration:** The Director AI's most complex bond integration — it composes the dark-side temptation scenario using the Padawan's specific history, weaknesses, and recent actions. This is prompt-engineering work and should be developed iteratively against the tester cohort during beta.

---

## 10. Commands Summary

New commands introduced by this system:

| Command | Who Uses It | Purpose |
|---|---|---|
| `+master` | Padawan | Check bonded Master's status |
| `+padawan` | Master | Check bonded Padawan's status |
| `+forcebond` | Either | Force Point expenditure for deeper bond sense |
| `+teach <power>` | Master | Teach Padawan a Force power |
| `+learn <power> from <master>` | Padawan | Request instruction |
| `+spar` | Either | Training lightsaber duel |
| `+approve <padawan> <action>` | Master | Approve a gated action |
| `+deny <padawan> <action>` | Master | Deny a gated action |
| `+authorize <padawan> <category>` | Master | Pre-authorize category of actions |
| `+endorse trials <padawan>` | Master | Endorse Trial attempt |
| `+trials <padawan>` | Either | View Trial progress |
| `+knight <padawan>` | Master | Invoke Knight promotion ceremony (requires all Trials) |
| `+release <padawan>` | Master | Voluntarily dissolve bond |
| `+leave-master` | Padawan | Voluntarily dissolve bond (staff-reviewed) |

All commands follow the existing `execute(ctx)` pattern with switch dispatch per `engineering_standards_v1.md` conventions.

---

## 11. MVP Scope for Launch

**Everything in §4, §5, §6.4 (Knight ceremony), §8 (dissolution), and §10 (commands) must work at launch.**

**Deferred to post-launch:**

- The Five Trials adjudication automation (§6.2, §6.3). At launch, Trials are staff-adjudicated per-event. Automation comes in Drop 3.
- The Trial of Spirit Director AI-narrated event (§6.2 Trial #5). At launch, this is a scheduled staff-facilitated event.
- Redemption arc for fallen Padawans (§7.4).
- Multiple Padawans per Master (post-launch, by Council authorization).
- The full Weight of War integration (§7.2 reference; depends on `weight_of_war_design_v1.md` which is pending).

This MVP is substantially smaller than the full design. The launch version provides the bond, the training commands, the approval mechanics, and the Knight promotion path. The Trials are narrative-and-staff at launch; they become mechanical in Drop 3.

---

## 12. Open Questions for Brian

1. **Lightsaber color selection at chargen.** Players typically want to pick. Default: allow blue, green, yellow (Sentinel tradition), purple (unusual but canon per Mace Windu). Not allowed at chargen: red (Sith), orange/white/black (rare/unique). Brian-decision.

2. **The Fifth Trial implementation at launch.** Staff-run event or Director AI-run event? Staff-run is safer (quality control) but is a staff load. Director AI-run is scalable but risks producing uneven narratives. Recommend: staff-run for the first six months, Director AI-authored scenario draft that staff reviews and runs.

3. **Master soft cap for launch.** Document says 5-8 (per `launch_strategy_v1.md`). Depends on beta cohort size. Revisit 30 days before launch when beta size is known.

4. **Does a Master's fall propagate to already-Knighted former Padawans?** Canon says no (Obi-Wan was not stained by Qui-Gon's death, Luke was not stained by Ben's actions). Recommend: no mechanical propagation, but surfaced as shared narrative memory for RP fuel.

5. **Padawan waitlist playability.** What can a waitlisted Padawan actually do while waiting? Recommend: Temple training commands, practice sparring with other waitlisted Padawans, library research, observation missions with Knights (not as their apprentice, just as a shadow-observer). This is enough to keep them engaged for days-to-weeks until a Master becomes available.

---

*End of Padawan/Master System Design v1.0 — April 18, 2026.*
*Paired with: launch_strategy_v1.md (anchor), clone_wars_era_design_v4.md (world context), jas_extraction_v1.md (lore and Force powers), weight_of_war_design_v1.md (pending).*
*Ready to drive Drop 2 implementation.*
