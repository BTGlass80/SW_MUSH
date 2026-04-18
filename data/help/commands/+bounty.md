---
key: +bounty
title: Bounty — Hunting Contracts & The Bounty Board
category: "Commands: Economy"
summary: All bounty-board verbs live under +bounty/<switch>. Browse the board, claim a contract, track your mark, collect the reward — every verb is a switch here.
aliases: [bounty, mybounty, activebounty, myhunt, +myhunt, +mybounty, bounties, bboard, bountyboard, +bboard, +bounties, bountyclaim, claimbounty, acceptbounty, bountytrack, tracktarget, hunttrack, bountycollect, collectbounty, claimreward]
see_also: [bounty, +mission, +smuggle, economy, combat, streetwise, search]
tags: [economy, bounty, hunting, command]
access_level: 0
examples:
  - cmd: "+bounty"
    description: "Show your active contract (target, tier, reward, last known location)."
  - cmd: "+bounty/board"
    description: "Browse posted bounties. Typically 2–4 contracts at any time."
  - cmd: "bounties"
    description: "Same as +bounty/board (bare alias preserved)."
  - cmd: "bountyboard"
    description: "Board alias."
  - cmd: "+bounty/claim b-7e1f"
    description: "Claim contract b-7e1f. You are now hunting the target."
  - cmd: "bountyclaim b-7e1f"
    description: "Same as +bounty/claim (bare alias preserved)."
  - cmd: "claimbounty b-7e1f"
    description: "Another bare alias for /claim."
  - cmd: "+bounty/view"
    description: "Show active contract. Same as bare +bounty."
  - cmd: "mybounty"
    description: "Active-contract alias (muscle memory preserved)."
  - cmd: "myhunt"
    description: "Another active-contract alias."
  - cmd: "+bounty/track"
    description: "Investigate the target's location. Rolls Search / Streetwise / Tracking (best)."
  - cmd: "bountytrack"
    description: "Same as +bounty/track (bare alias preserved)."
  - cmd: "tracktarget"
    description: "Another bare alias for /track."
  - cmd: "+bounty/collect"
    description: "Turn in after defeating the target. Skill check determines pay quality (50–120%)."
  - cmd: "bountycollect"
    description: "Same as +bounty/collect (bare alias preserved)."
  - cmd: "claimreward"
    description: "Another bare alias for /collect."
---

All bounty-board verbs are switches under +bounty. Bare forms
(bounties, bountyclaim, bountytrack, bountycollect) still work as
aliases — typing `bountytrack` and `+bounty/track` reach the same
code. The canonical form is +bounty/<switch>; the rest of this
page uses it everywhere.

See `+help bounty` for the conceptual overview of bounty hunting
in the setting. This page is the command reference.

SWITCH REFERENCE
  /board    Browse posted contracts (2–4 available)
  /claim    Take a contract by its id (prefix match works)
  /view     Show your active contract (also: bare '+bounty', mybounty)
  /track    Investigate target location — Search / Streetwise / Tracking
  /collect  Turn in after defeating the target

ONE ACTIVE CONTRACT AT A TIME. Collect or wait for expiration
before claiming another.

THE CONTRACT LIFECYCLE

  POSTED → CLAIMED → COLLECTED
                  ↘ EXPIRED (4 hours after claim)
                  ↘ FAILED (target was killed by someone else)

The board holds 2–4 posted contracts. Refreshes every 45 minutes
(REFRESH_SECONDS = 2700). Unclaimed posts expire after 3 hours
(BOUNTY_TTL = 10800). Claimed contracts expire after 4 hours
(CLAIMED_TTL = 14400).

TIER SYSTEM (Galaxy Guide 10: Bounty Hunters)

Tier        Pay Range         Target        Track Diff.
  Extra     100–300 cr        Easy NPC      6
  Average   300–800 cr        Moderate      10
  Novice    800–1,500 cr      Competent     13
  Veteran   1,500–3,000 cr    Dangerous     17
  Superior  3,000–10,000 cr   Elite         21

Extras are the most common postings (weight 5 in the spawn table);
Superiors are rare (weight 1) — they represent significant criminal
figures and are priced accordingly. GG10 p.11–20 outlines the tier
archetypes: petty thieves up to high-profile smugglers and Rebel
agents.

TARGETS ARE REAL NPCS

Unlike mission targets (abstract), bounty marks are actual NPCs
spawned into the world by engine/npc_generator.py. They live in
rooms, move occasionally, carry appropriate gear for their tier,
and will defend themselves. Archetypes include:

  - Thugs (most commonly)
  - Smugglers
  - Bounty hunters (PvP-like challenge)
  - Scouts
  - Stormtroopers (rare — Alliance-posted)
  - Imperial officers (rare — underworld-posted)

They are placed in non-obvious rooms (never in docking bays where
patrols would arrest them). The only way to find them is /track.

/board

Lists posted contracts with:
  - ID (4-character prefix, e.g. 'b-7e1f')
  - Target name + race/description
  - Tier (Extra → Superior)
  - Reward
  - Posting org (Alliance, Empire, Hutt, Black Sun, Civilian)

/claim <id>

Prefix matching works. You take the contract; board removes it from
public display. You'll see the full detail, including the target's
last-known room (empty on first claim — use /track to locate).

/view

Your active contract:
  - Target name + racial description
  - Tier + skill difficulty
  - Reward
  - Last tracked location (if /track has succeeded)
  - Expires-at timestamp

/track — THE INVESTIGATION PHASE

The game uses the BEST of your Search, Streetwise, and Tracking
pools — you roll whichever is highest. Rolls vs. the tier difficulty
above.

  Success: Target's current room is revealed.
           "Lead found! Fenn Shysa was last seen at: The Lucky
            Despot's back corridor. Make your way there and engage."

  Close (miss by ≤5): Cold trail. Flavor text mentions a nearby
           spot (cantina / market / docking bays / outskirts).
           Try again.

  Fail: "No leads. The target has covered their tracks well. Try
         again later." (Targets DO move — /track may work next time.)

You can /track repeatedly; each roll is independent. Your skill dice
don't deplete.

/collect — AFTER YOU'VE PUT THEM DOWN

Requirements:
  1. Active contract.
  2. Target NPC is dead/incapacitated (wound_level ≥ 5 = Mortally
     Wounded) OR the NPC was already cleaned up from the database
     (combat handles this automatically on kill).
  3. You're in the same room as them OR they're already despawned
     (in which case you can collect from anywhere).

/collect then runs a claim-quality skill check:
  - Uses Streetwise if you have it, else Search
  - Difficulty scales with reward: 8 / 11 / 14 (small / med / large)
  - Critical success: +20% bonus [EXCEPTIONAL]
  - Success: full reward (100%)
  - Partial (miss by ≤4): 75% [PARTIAL]
  - Failure: 50% [POOR PAPERWORK]

This system models the difference between a clean Imperial-style
capture and a messy bounty — the corpse is the same but the
paperwork and the story are what you're selling.

FACTION REPUTATION

Every successful /collect grants +reputation with your primary
faction (complete_bounty action). Alliance-posted bounties grant
bonus rep to the Rebellion; Empire-posted to the Imperials. See
'+help reputation'.

POST-COLLECTION HOOKS

A successful /collect also fires:
  - Narrative log (PC record updates)
  - Faction reputation (above)
  - Ships-log tick (profession chains)
  - Spacer quest check (bounty tier is passed for quest progress)
  - Territory influence in the collect room
  - NPC cleanup (delete_npc if not already handled)

THE HUNTER'S MARK QUEST LINE

Collecting 3 bounties unlocks the Bounty Hunter profession chain
(Hunter's Mark). See the tutorial system for details.

"DARK SIDE PAYS MORE" HOOKS

Some bounties are posted by factions whose agenda tilts dark —
taking an Imperial contract against a Rebel agent may grant DSP on
collection. Similarly, an Alliance contract against an Imperial
officer may grant light-side rep. The mission data flags determine
this. See '+help darkside'.

EXAMPLES

  +bounty/board
  → Shows 3 posted contracts.

  +bounty/claim b-7e
  → Claims b-7e1f via prefix match. "Contract accepted. Find
    Fenn Shysa and bring him to justice."

  +bounty/track
  → "Streetwise roll: 16  vs Difficulty 17. Close, but not enough.
    You pick up a cold trail near the docking bays."

  (try again)
  +bounty/track
  → "Streetwise roll: 23  vs Difficulty 17. Lead found! Fenn Shysa
    was last seen at: The Lucky Despot's back corridor."

  move the_lucky_despot
  attack fenn_shysa
  (combat ensues — when Fenn is Mortally Wounded or dead:)

  +bounty/collect
  → "Bounty collected: Fenn Shysa. Reward: +2,400 credits
    (Balance: 8,540 cr). Claim quality: Streetwise [4D]
    Roll 23 vs 11. Posted by: Alliance Intelligence."

CHEAT SHEET
  +bounty/board    = browse
  +bounty/claim    = take a contract (prefix id matching)
  +bounty         = view active (also: /view, mybounty, myhunt)
  +bounty/track    = investigate (also: bountytrack, tracktarget)
  +bounty/collect  = turn in (also: bountycollect, claimreward)

Sources: Galaxy Guide 10: Bounty Hunters for tier archetypes;
R&E p.75 (Difficulty ladder), p.93 (Streetwise/Search).
