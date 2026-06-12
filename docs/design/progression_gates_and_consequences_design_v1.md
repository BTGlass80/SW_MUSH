# Progression Gates & Consequences — Design v1

**Status:** Locked decisions, ready for implementation breakdown
**Author:** Brian + Claude (design session, May 2026)
**Supersedes:** `clone_wars_era_design_v3.md` Force Sensitivity sections, `jedi_village_quest_design_v1.md` chargen hooks, `web_chargen_design_v1.md` FS checkbox, `Guide_06_Economy.md` death-handling note, `launch_strategy_v1.md` Padawan-seeding rules (clarified, not replaced)

---

## 0. Why this doc exists

Three threads in the existing design corpus contradict or under-specify each other:

1. **Jedi gating.** Three docs answer "how does a player become Jedi" three different ways (50% chargen roll, player checkbox, tester-seeded contribution model). The Village quest is well-designed but bolted onto inconsistent foundations.
2. **Death penalty.** `Guide_06` declares "respawn at safe location, equipment preserved, no permadeath" — i.e., death is currently consequence-free. The Scar System is cosmetic; permadeath duels are opt-in.
3. **PC bounties.** The BH override and Guild infrastructure exist, but no mechanism lets one PC put a bounty on another. The system has output wiring but no input.

These three problems share a coupling: **the death penalty determines whether Jedi rarity matters, and the bounty system is the only thing that gives Jedi rarity teeth.** Solving them in isolation produces three inconsistent answers. This doc resolves them together.

---

## 1. Locked decisions (the short version)

### Jedi gating
- **No 50% chargen roll. No checkbox.** Force Sensitivity is earned through the Village, period.
- Predisposition stays as Director-AI flavor (some characters notice Force-signs sooner) but does not skip steps.
- **50-hour playtime gate** before Force-signs trigger at all.
- Real-time pacing: 7-day cooldown between Acts, 14-day spacing between trial clusters within Act 2, existing 6-hour Trial of Flesh timer preserved. Total path: ~3–4 weeks of engaged play after the 50-hour gate.
- `launch_strategy_v1.md`'s tester-seeded Master/Knight cohort applies at launch only — orthogonal to the long-term gating path.

### Death penalty
- **No CP loss, no XP loss.** Confirmed unsuitable for WEG D6's CP economy.
- **Wound recovery on respawn** — respawn Wounded (−1D), real-time clock to fully heal, bacta as accelerant credit sink.
- **Equipment recovery quest** — corpse stays where you fell with a recovery window, gear retrievable by self or party.
- **Insurance credit sink** for any PC who dies with an active bounty on them, killed by a Bounty Hunter.

### PC bounty system
- **PC-posted bounties only.** Faction-issued, Director-generated, and Dark-Side-fall bounties are explicitly out of scope for v1.
- Posting cost is meaningfully larger than insurance cost (anti-griefing).
- One open bounty per poster at a time (existing one-active-mission precedent).
- BH override unchanged — claimed contracts allow PvP override in contested zones (already designed).

---

## 2. Jedi gating — full design

### 2.1 What the Village currently is

Per `jedi_village_quest_design_v1.md`, the Village is a 3-Act quest chain on Tatooine:

- **Act 1 — Signs:** Player accumulates Force-signs through ambient play (precognitive flashes, lifting small objects under stress, hearing the Force during meditation). After ~5 signs, an NPC contact (the Hermit) appears and invites the character to the Village.
- **Act 2 — Village:** Three trials gating Padawan status — Trial of Insight (puzzle/dialogue), Trial of Flesh (6-hour real-time meditation/fast), Trial of Courage (combat trial against a Force-shadow construct, 24-hour cooldown on retry).
- **Act 3 — Choice:** Light or Dark path declaration. Successful candidates become Padawans and can be apprenticed to a PC Knight/Master.

The content is good. What was wrong was the gating.

### 2.2 The locked gate

```
[Character creation]
        ↓
[Standard play, no Force mechanics yet]
        ↓
[50 real-time hours of play accumulated] ─── HARD GATE
        ↓
[Director AI begins weighting Force-signs into ambient events for this character]
        ↓
[5 Force-signs accumulated through play]
        ↓
[Hermit NPC appears, invites to Village] ─── ACT 1 COMPLETE
        ↓
[7-day real-time cooldown before Act 2 entry]
        ↓
[Trial of Insight] ────┐
[14-day cooldown]      │
[Trial of Flesh]       ├── ACT 2 (sequential, real-time gated)
[14-day cooldown]      │
[Trial of Courage] ────┘
        ↓
[Act 3: Light/Dark choice + apprenticeship to PC Knight/Master]
        ↓
[Padawan status, lightsaber construction quest unlocks]
```

Minimum elapsed wall-clock from invitation to Padawan: **35 days** (7 + 14 + 14). With the 50-hour playtime gate beforehand, total path is **~5–8 weeks of active play** for a typical player.

### 2.3 Why these specific numbers

- **50 hours** filters alts and tourists. A player who's logged 50 hours has invested in the character, has relationships, has stuff to lose. The Force feels earned. Adjustable via config — start here, tune from observed conversion rates.
- **5 Force-signs** is unchanged from the existing Village design. It's the right narrative cadence.
- **7-day Act-1-to-Act-2 cooldown** gives the player time to roleplay the discovery. The Hermit's invitation should feel weighty, not like a quest accept dialog.
- **14-day inter-trial cooldown** is the biggest behavioral lever. It makes the Village feel like real spiritual training rather than a checklist. Each trial gets its own week of anticipation and reflection. SWG's village had ~7-day cooldowns between Phases; we're stretching slightly because our trials are deeper.
- **6-hour Trial of Flesh** unchanged. This is the meditation/fast trial; the 6-hour real-time wait is the trial.
- **24-hour Trial of Courage retry cooldown** unchanged. Failure is meaningful but recoverable.

### 2.4 Predisposition (flavor, not gating)

The Director AI maintains a per-character `force_predisposition` score (0.0–1.0) that affects:
- **Density of ambient Force-flavor events** during the 50-hour gate phase. Higher predisposition = more flavor (vivid dreams, déjà vu, animals reacting strangely) without any mechanical effect.
- **Force-sign trigger rate** post-gate. Higher predisposition = signs come faster (5 signs in ~10 hours of post-gate play vs. ~30 hours).

Predisposition is set at character creation by a hidden Director-AI weighted roll informed by:
- Species (some lore-relevant species weighted up)
- Backstory keywords parsed from the chargen narrative field
- Director RNG seed

It is **not visible to the player**, never queryable, and never affects whether someone can become Jedi — only how quickly the path opens. A player with 0.0 predisposition still becomes Jedi at the same total play-time as one with 1.0; the latter just experiences more atmospheric Force content along the way.

### 2.5 Chargen UI changes

`web_chargen_design_v1.md` is updated:
- Force Sensitivity checkbox **removed** from chargen.
- A backstory free-text field is preserved (it feeds predisposition scoring).
- No mechanical Force-related fields appear at chargen.

### 2.6 Launch-day cohort (clarification)

`launch_strategy_v1.md` specifies tester-seeded Padawans/Knights/Masters at launch (5–8 Masters, 10–15 Knights). This stands. Those characters are exempt from the 50-hour gate — they're authored as already-trained at launch as the foundational Jedi presence. They are the mentors who apprentice the first wave of organic Padawans.

After launch, all new Jedi go through the standard gate.

### 2.7 Apprenticeship requirement

Per `padawan_master_system_design_v1.md`, Act 3 requires apprenticeship to a PC Knight or Master. This is preserved. With the launch cohort + ~5–8 weeks ramp for the first organic Padawans, the apprenticeship pool grows organically.

If no eligible PC Master is online or available, the Hermit NPC can serve as a temporary "interim master" (NPC fallback) until a PC Master accepts the apprenticeship. This prevents the gate from becoming a deadlock when Master availability is low.

### 2.8 Schema additions

```sql
ALTER TABLE characters ADD COLUMN play_time_seconds INTEGER DEFAULT 0;
ALTER TABLE characters ADD COLUMN force_predisposition REAL DEFAULT 0.0;
ALTER TABLE characters ADD COLUMN force_signs_accumulated INTEGER DEFAULT 0;
ALTER TABLE characters ADD COLUMN village_act INTEGER DEFAULT 0;  -- 0=pre, 1=invited, 2=in trials, 3=passed
ALTER TABLE characters ADD COLUMN village_act_unlocked_at REAL DEFAULT 0;  -- timestamp of last act transition
ALTER TABLE characters ADD COLUMN village_trial_courage_done INTEGER DEFAULT 0;
ALTER TABLE characters ADD COLUMN village_trial_insight_done INTEGER DEFAULT 0;
ALTER TABLE characters ADD COLUMN village_trial_flesh_done INTEGER DEFAULT 0;
ALTER TABLE characters ADD COLUMN village_trial_last_attempt REAL DEFAULT 0;  -- for inter-trial cooldown
```

`play_time_seconds` ticks every minute of active play (heartbeat-driven, idle players don't accumulate). Existing session-tracking infrastructure already gives us this.

---

## 3. Death penalty — full design

### 3.1 Current state (to replace)

Per `Guide_06`: "When killed, your character respawns at a safe location. Equipment is preserved for recovery. This is a gameplay convenience; there's no permadeath."

This is functional but consequence-free. Players have no reason to fear combat outcomes, which trivializes the fiction the rest of the game tries to build.

### 3.2 New death flow

```
[PC reduced to Mortally Wounded or Killed]
        ↓
[Body remains in place, marked as a corpse object]
        ↓
[PC respawns at nearest safe location after 30-second blackout]
        ↓
    Respawn state:
    - Wounded condition (−1D to all actions)
    - Inventory empty (gear stays on corpse)
    - Credits and bank untouched
    - Skills and CP untouched
    - Active bounties: insurance triggered (see §4)
        ↓
    Two parallel recovery tracks:
    [A] Wound recovery — clears with time or bacta
    [B] Equipment recovery — corpse retrieval
```

### 3.3 Wound recovery

- Default real-time recovery: **1 hour** of active play to clear Wounded → Healthy.
- Bacta tank treatment at any med-droid: **500 cr** to clear immediately. Standard credit sink.
- Bacta packs (purchasable consumable): **150 cr** each, one-shot at any location, restores fully.
- Stims (medic buff, see future support-role-buffs design): can shorten recovery time; doesn't fully clear it.
- During Wounded: −1D to all dice pools. Survivable, noticeable, not crippling.

### 3.4 Equipment recovery

- Corpse persists at the death location for **2 real-time hours**.
- Anyone can `loot <corpse>` while it persists.
- Owner can retrieve all gear by returning to the corpse location.
- Party members can retrieve gear and deliver it to the owner (creates the "rescue your friend's body" gameplay).
- After 2 hours, corpse decays:
  - Equipment with `bound` flag (signature lightsabers, faction-issued gear) is auto-mailed to the owner.
  - Generic equipment is destroyed.
  - Credits on the corpse are dropped to the room (lootable until cleared).

This creates real choices: chase down your gear at the cost of returning to a dangerous area, or accept the loss. It also creates revenge-loop content (camp the corpse) that the BH override and security-zone design already accommodate.

### 3.5 Special cases

- **Death in a secured zone** (combat shouldn't happen there in the first place): full instant respawn with gear, no Wounded state. Edge case; only triggers from environmental hazards or admin actions.
- **Death in a contested zone:** standard flow as above.
- **Death in a lawless zone:** standard flow + corpse persists for 4 hours instead of 2 (more dangerous → longer recovery window for body recovery to be feasible).
- **Death by environmental hazard** (atmosphere, falling, etc.): standard flow but no corpse-decay rewards for any other player to claim (no "kill" credit).
- **Death during a permadeath duel:** governed by the existing duel system. This system does not modify those rules.

### 3.6 Schema additions

```sql
CREATE TABLE IF NOT EXISTS corpses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    room_id         INTEGER NOT NULL,
    died_at         REAL NOT NULL,
    decay_at        REAL NOT NULL,
    inventory       TEXT NOT NULL DEFAULT '[]',  -- JSON
    credits         INTEGER DEFAULT 0,
    killer_id       INTEGER DEFAULT NULL,        -- for bounty resolution
    killer_is_bh    INTEGER DEFAULT 0,           -- 0/1, was killer BH Guild member
    bounty_resolved INTEGER DEFAULT 0,           -- 0/1, has bounty insurance fired
    FOREIGN KEY (char_id) REFERENCES characters(id)
);

ALTER TABLE characters ADD COLUMN wound_state TEXT DEFAULT 'healthy';
ALTER TABLE characters ADD COLUMN wound_clear_at REAL DEFAULT 0;
```

---

## 4. PC bounty system — full design

### 4.1 Scope (locked)

**In scope:**
- Bounties posted by one PC against another PC.
- Insurance credit sink when a bountied PC is killed by a BH.
- Existing BH Guild infrastructure (override, claim, completion).

**Out of scope (explicitly):**
- Faction-issued bounties (deferred to a faction-systems future doc).
- Director-generated bounties (deferred indefinitely).
- Dark-Side-fall auto-bounty (deferred until Dark Side system gets its own redesign).
- NPC bounty board missions (already exist, untouched).

### 4.2 Posting a bounty

```
+bounty post <player> <amount> [reason]
```

- **Minimum amount:** 1,000 cr.
- **Maximum amount:** 50,000 cr (cap to prevent escalation wars).
- **Posting cost:** the full amount goes into bounty escrow + a 10% non-refundable posting fee.
- **One active outgoing bounty per poster.** Cannot post a second bounty until the first is resolved (claimed, expired, or canceled).
- **One active incoming bounty per target.** If a target already has a bounty on them, a new posting either fails or stacks (escrow merges, original poster remains "primary"); recommend **fail with message** for v1 simplicity. The second poster can wait or post on someone else.
- **Reason field is mandatory and visible** on the bounty board. Anti-griefing: posters must publicly state why. Bounties with reason-text matching obvious griefing patterns (admin moderation required) can be voided.
- **Posting cooldown:** after a bounty is canceled or expires unclaimed, the same poster cannot re-post on the same target for 30 days. Prevents harassment loops.

### 4.3 Bounty lifecycle

- **Posted → Active:** appears on Guild bounty board (`+bounty board`), claimable by any BH Guild member.
- **Active → Claimed:** a BH Guild PC takes the contract. They have 7 days to fulfill or contract reverts to Active.
- **Claimed → Fulfilled:** the BH kills the target. Insurance fires (see §4.4). Bounty escrow pays out: 80% to BH, 20% to Guild treasury (Guild upkeep sink).
- **Active → Expired:** if unclaimed for 30 days, expires. Escrow returns to poster minus the 10% posting fee.
- **Active → Canceled:** poster can `+bounty cancel` for a 25% cancellation fee (15% net loss vs. expiry). Refund discourages frivolous posts; cancel option prevents griefing-by-stalemate.
- **Claimed → Failed:** if the BH dies during pursuit, contract reverts to Active.

### 4.4 Insurance hit (the death-bounty bridge)

When a PC with an active bounty is killed by a BH Guild member:

1. **Insurance amount = 10% of the bounty value**, deducted from the target's credits at respawn.
2. If target lacks the credits, the difference becomes **debt** to the BH Guild. Until paid, target cannot:
   - Use Guild services (post bounties, etc.)
   - Receive faction stipends (intercepted by Guild claim)
   - Some BH-tier vendors refuse service
3. Debt clears as soon as it's paid off.

**Why insurance is bounty-scaled and asymmetric:**
- Posting a 5,000 cr bounty costs the poster 5,500 cr (5,000 escrow + 500 fee).
- Insurance hit on the target is 500 cr.
- Net cost ratio: poster pays **11×** what target pays per kill.
- Even if a poster bounty-posts repeatedly to bleed a target, the cost asymmetry burns the poster ~11× faster than the target. This is the core anti-griefing math.

### 4.5 Insurance only applies when killed by BH

If a bountied PC is killed by anyone *other* than a BH Guild member (random PvP, NPCs, environmental death), insurance does **not** fire. The bounty stays active. The kill doesn't claim the contract.

This is intentional:
- Prevents a poster from ganking the target themselves to extract insurance.
- Keeps the BH Guild as the single legitimate claim path.
- Gives bountied PCs a real reason to fear *registered hunters specifically*, which is the intended fiction.

### 4.6 Anti-griefing summary

| Mechanism | Effect |
|---|---|
| 10% posting fee, non-refundable | Discourages frivolous posts |
| Mandatory reason field (admin-reviewable) | Public accountability |
| One active outgoing bounty per poster | No bounty-spamming |
| 30-day cooldown after expiry/cancel on same target | No repeat harassment |
| Insurance is 10% of bounty (poster pays ~11× per kill) | Poster bleeds faster than target |
| Cancel fee 25% | Costly to weaponize, cheap enough to escape griefing yourself |
| Insurance only on BH kills | Poster can't gank for self-extraction |
| 50,000 cr cap | No nuclear-option bounties |

### 4.7 Schema additions

```sql
CREATE TABLE IF NOT EXISTS pc_bounties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    poster_id       INTEGER NOT NULL,
    target_id       INTEGER NOT NULL,
    amount          INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'active',  -- active|claimed|fulfilled|expired|canceled
    claimed_by      INTEGER DEFAULT NULL,            -- BH Guild member who claimed
    claimed_at      REAL DEFAULT 0,
    posted_at       REAL NOT NULL,
    expires_at      REAL NOT NULL,                   -- posted_at + 30 days
    resolved_at     REAL DEFAULT 0,
    FOREIGN KEY (poster_id) REFERENCES characters(id),
    FOREIGN KEY (target_id) REFERENCES characters(id),
    FOREIGN KEY (claimed_by) REFERENCES characters(id)
);

CREATE INDEX idx_bounties_target ON pc_bounties(target_id, state);
CREATE INDEX idx_bounties_poster ON pc_bounties(poster_id, state);

CREATE TABLE IF NOT EXISTS bounty_cooldowns (
    poster_id   INTEGER NOT NULL,
    target_id   INTEGER NOT NULL,
    until       REAL NOT NULL,
    PRIMARY KEY (poster_id, target_id)
);

CREATE TABLE IF NOT EXISTS bh_insurance_debt (
    char_id     INTEGER PRIMARY KEY,
    amount      INTEGER NOT NULL,
    incurred_at REAL NOT NULL,
    FOREIGN KEY (char_id) REFERENCES characters(id)
);
```

### 4.8 Commands

| Command | Aliases | Function |
|---|---|---|
| `+bounty post <player> <amount> <reason>` | — | Post a PC bounty (Active state) |
| `+bounty cancel` | — | Cancel your active bounty (25% fee) |
| `+bounty board` | `+bounty list` | View active PC bounties (BH Guild only) |
| `+bounty claim <id>` | — | Claim a bounty (BH Guild only) |
| `+bounty release <id>` | — | Release a claimed bounty back to Active (BH Guild only) |
| `+bounty status` | `+bounty mine` | View your outgoing/incoming bounties |
| `+bounty debt` | — | View your BH insurance debt |
| `+bounty pay` | — | Pay off insurance debt |
| `@bounty void <id> <reason>` | — | Admin: void a bounty (refunds escrow, no fee) |
| `@bounty review <id>` | — | Admin: review a flagged bounty |

---

## 5. Cross-system interactions

### 5.1 Jedi + bounty + insurance loop

Jedi PCs are, by design, the most-bountied target class:
- They're rare (5–8 weeks gated path).
- They have strong mechanics (Force powers, lightsabers).
- They're narratively hunt-worthy (Clone Wars era, Republic-aligned by default).

A Jedi with an active bounty killed by a BH triggers the standard insurance flow. The flavor outcome — "Jedi pay a tax to the Guild for being hunted" — emerges from the general rule, not from a Jedi-class special case. This is cleaner than singling out Jedi mechanically.

### 5.2 Dark Side and bounties (deferred)

When the Dark Side system is properly redesigned (separate doc, future), a fallen Jedi could automatically generate a Republic/Jedi-Order bounty. The schema already supports this — the `pc_bounties` table just needs a system-poster ID for "Jedi Order" or "Republic." Out of scope for v1; flagged for the Dark Side redesign doc.

### 5.3 Wound state and Force powers

A Wounded Jedi takes the standard −1D penalty. Force powers that have a strain or Control roll also incur the penalty. This is per-RAW WEG D6 — no special case needed.

### 5.4 BH Guild membership and the override

Existing BH override (per `Guide_10_Organizations_Factions.md`) is unchanged. A BH with an active claimed contract can engage the target in any zone where PvP is normally consent-gated, treating the encounter as if the target were flagged contested. This is the only way insurance fires correctly.

---

## 6. Phased delivery plan

### Phase 1: Schema + death penalty foundation
- Add all schema columns and tables (§2.8, §3.6, §4.7)
- Wound state mechanic (respawn Wounded, recovery clock, bacta sink)
- Corpse object + decay timer
- `loot <corpse>` command
- No bounty system yet, no Jedi gating yet
- **Effort:** Medium. ~1 session.

### Phase 2: PC bounty system
- All `+bounty` commands
- Posting flow with escrow + fee
- Lifecycle state machine (Active/Claimed/Fulfilled/Expired/Canceled)
- BH override resolution check on PC kill
- Insurance hit + debt mechanic
- `@bounty` admin commands
- **Effort:** Medium-Large. ~2 sessions.

### Phase 3: Jedi gating
- 50-hour playtime tracking (extend existing session heartbeat)
- Predisposition scoring at chargen
- Force-sign trigger refactor (gated by playtime + predisposition)
- Real-time Act/Trial cooldowns
- Update Village quest content to enforce cooldowns
- Remove FS checkbox from chargen
- **Effort:** Medium. ~1.5 sessions.

### Phase 4: Polish + integration
- Admin tooling for moderation
- Director AI digest extensions (bounty board state, Jedi cohort size)
- Web client UI for bounty board + insurance debt
- Help topic updates
- **Effort:** Small-Medium. ~1 session.

**Total:** ~5.5 sessions.

---

## 7. Open questions

1. **Corpse griefing.** What if hostile players camp a contested-zone corpse to prevent retrieval? Current mitigation: `bound` items auto-mail after decay. If this proves insufficient, add a 30-minute "ghost" window where the dead PC can mark items as retrievable-by-mail at a higher credit cost. **Defer until observed.**

2. **Bounty escrow on character deletion.** If a poster deletes their character with active bounties, what happens? Recommend escrow forfeits to BH Guild treasury. **Lock as a default.**

3. **Multi-killer bounty resolution.** If a BH and a faction NPC both contribute to a target's death within the same combat, who claims the bounty? Recommend last-hit attribution to the BH if they're claimed-on-target; otherwise no claim. **Lock as a default.**

4. **Bacta cost tuning.** 500 cr instant heal vs. 1 hour of active play recovery. Is this the right ratio? **Tune from observed behavior in first month.**

5. **Predisposition transparency.** Should players ever see their predisposition score? Current decision: never. Some playtesters may want a "have I been overlooked" mechanism. **Defer until launch feedback.**

6. **Jedi apprenticeship deadlock.** What if no PC Master is available for an extended period? Current mitigation: Hermit NPC interim. If `padawan_master_system_design_v1.md` evolves to require deeper PC-Master mentorship, revisit. **Defer.**

---

## 8. Architecture invariants

- All death state transitions go through a single `process_pc_death()` function. No shortcuts.
- All bounty state transitions go through `process_bounty_event()`. No shortcuts.
- Insurance debt is checked on every credit-spending command (bank withdraw, vendor purchase, etc.) and on every faction stipend tick.
- Playtime heartbeat is single-source-of-truth for the 50-hour gate. No alternative paths.
- Predisposition is set once at chargen and never modified. (If dialed, it's a schema migration, not gameplay.)
- The Village quest content is decoupled from this doc — content lives in `jedi_village_quest_design_v1.md` and `jedi_village_dialogue_authoring_design_v1.md`. This doc only changes when content unlocks.

---

## 9. Test plan

### 9.1 Unit / integration tests

- **Death flow:** Kill a test PC, verify Wounded state, corpse object, gear transfer.
- **Wound recovery:** Verify time-based recovery and bacta-based recovery both clear state.
- **Bounty lifecycle:** Post → Claim → Fulfill, with escrow accounting verified at each step.
- **Insurance trigger:** Kill bountied PC by BH, verify 10% deduction. Kill bountied PC by non-BH, verify no deduction.
- **Cooldown enforcement:** Attempt re-post on same target within 30 days, verify failure.
- **Playtime gate:** Force a Force-sign trigger before 50 hours, verify it's suppressed.
- **Real-time gates:** Attempt Trial of Insight before 7-day cooldown, verify rejection.

### 9.2 Manual / GM tests

- Full Village run-through with cooldowns mocked to 1 minute each.
- Posting a bounty, claiming it as a BH alt, killing the target, verifying full credit flow.
- Insurance debt blocking a faction stipend pickup.
- Corpse retrieval by party member (deliver to owner).

---

## 10. Documentation updates required

- `Guide_06_Economy.md` — replace death-handling note with new flow (§3).
- `Guide_08_Force_Powers.md` — add Village gating preamble.
- `clone_wars_era_design_v3.md` — strike 50% chargen roll, point to this doc.
- `jedi_village_quest_design_v1.md` — keep content, point to this doc for gating timing.
- `web_chargen_design_v1.md` — remove FS checkbox.
- `launch_strategy_v1.md` — clarify tester cohort vs. organic gating distinction.
- `Guide_09_CP_Progression.md` — note that death is no longer CP-impacting.
- `Guide_10_Organizations_Factions.md` — reference §4 for PC bounty mechanics.

---

*End of design v1.*
