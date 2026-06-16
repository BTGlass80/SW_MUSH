---
key: +pcbounty
title: PCBounty — Player-to-Player Bounty System
category: "Commands: Economy"
summary: Post credit bounties against other players, view the Bounty Hunter Guild board, claim and fulfill PC bounties, and manage insurance debt from being hunted.
aliases: ["+pb"]
see_also: [+bounty, +pvp, economy, factions, combat, reputation]
tags: [economy, bounty, pvp, command]
access_level: 0
examples:
  - cmd: "+pcbounty post Dax Owes me 5,000 credits for the heist 5000"
    description: "Post a 5,000 cr bounty on Dax with a reason."
  - cmd: "+pcbounty status"
    description: "View your current outgoing and incoming bounties."
  - cmd: "+pcbounty board"
    description: "Browse active PC bounties (Bounty Hunter Guild members only)."
  - cmd: "+pcbounty claim bh-a3f2"
    description: "Claim bounty bh-a3f2 (BH Guild member only — 7 days to fulfill)."
  - cmd: "+pcbounty cancel"
    description: "Cancel your outgoing bounty (25% fee; rest refunded)."
  - cmd: "+pcbounty debt"
    description: "View your insurance debt if you were bountied and killed."
  - cmd: "+pcbounty pay 2000"
    description: "Pay 2,000 credits toward your insurance debt."
  - cmd: "+pb status"
    description: "Short alias for +pcbounty status."
---

The PC bounty system lets players post credit bounties against each
other through the Bounty Hunter Guild. This is separate from the NPC
bounty board (`+bounty`) — two different systems, two different
command roots.

SUBCOMMANDS

  +pcbounty post <player> <amount> <reason>
      Post a bounty. Minimum 1,000 cr; maximum 50,000 cr.
      Costs: amount posted + 10% posting fee (non-refundable).
      If the target already has an active bounty, your credit
      contribution stacks onto it (multiple posters allowed).

  +pcbounty cancel
      Cancel your active outgoing bounty. 25% of your contribution
      is forfeited as a cancellation fee; remaining 75% is refunded
      proportionally across all contributors.

  +pcbounty status  (also: +pcbounty mine)
      View your outgoing bounty (if any) and any active incoming
      bounty against your character.

  +pcbounty board  (also: +pcbounty list)
      View all active PC bounties on the Guild board. BH Guild
      members only — civilians can't see the hunting ledger.

  +pcbounty claim <id>   (BH Guild only)
      Claim an active bounty. You have 7 days to fulfill it.
      Only one active claim per hunter at a time.

  +pcbounty release <id>   (BH Guild only)
      Release a claimed bounty back to the board without penalty.
      Use this if you can't complete it before it expires.

  +pcbounty debt
      View your current insurance debt. Accrued when a Bounty
      Hunter successfully collects on a bounty against you.

  +pcbounty pay [amount]
      Pay down insurance debt. No argument = pay full balance.
      Partial payments reduce the total owed.

NOTE ON SYSTEMS

`+pcbounty` is the PC-vs-PC bounty system (player posts vs player
target). `+bounty` is the NPC contract board (posted by factions,
marks are NPCs). The two systems don't share boards, contracts,
or mechanics.

BOUNTY ECONOMICS

Posting fee (non-refundable): 10% of posted amount
  → Posting a 5,000 cr bounty costs 5,500 cr total

Cancellation fee: 25% of your contribution
  → Cancelling your 5,000 cr post refunds 3,750 cr

Insurance debt on kill: The bounty amount (minus a BH Guild cut)
  transfers as debt against you, payable via +pcbounty pay.

BOUNTY HUNTER GUILD

Only BH Guild members can see the board and claim contracts. Guild
membership requires completing the Hunter's Mark questline (see
`+quests` for available chains). Non-Guild players can only post
bounties and check their own status.

STACKING BOUNTIES

Multiple players can contribute to the same bounty:
  - First poster pays the 10% fee
  - Subsequent contributors add directly to the reward pool (no
    additional fee)
  - Cancellation refunds proportionally across all contributors

This lets a faction pool resources against a particularly troublesome
adversary.

PVP FLAG

Accepting a bounty claim puts you in a combat-eligible state with
the hunter (see `+pvp`). The full PvP consent rules apply — you
cannot be ambushed without some consent path.

EXAMPLES

  +pcbounty post Dax Unpaid debts from the Kessel job 8000
  → "Bounty posted on Dax: 8,000 cr. Posting fee: 800 cr.
     Balance deducted: 8,800 cr."

  +pcbounty status
  → "OUTGOING: Dax — 8,000 cr (1 contributor). Status: Open.
     INCOMING: None."

  (as a BH Guild member)
  +pcbounty board
  → Lists all active PC bounties with amounts and targets.

  +pcbounty claim bh-d3a1
  → "Bounty on Dax claimed. 7 days to fulfill."

CHEAT SHEET
  +pcbounty post <p> <amt> <reason>  = post bounty (+10% fee)
  +pcbounty cancel                   = cancel outgoing (25% fee)
  +pcbounty status                   = view in/out bounties
  +pcbounty board                    = BH Guild board (Guild only)
  +pcbounty claim/release <id>       = BH Guild only
  +pcbounty debt / pay               = insurance debt management
