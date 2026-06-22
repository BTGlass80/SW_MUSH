---
category: community
order: 1
summary: "Republic, CIS, Jedi Order, Hutts, Bounty Hunters Guild. Join a faction, climb the ranks, and shape the galaxy."
tags: ["faction", "organization", "republic", "cis", "jedi", "hutt", "bounty hunters", "guild", "rank"]
---

# Organizations & Factions

**Parsec — WEG D6 Revised & Expanded**

---

## How to Read This Guide

The Clone Wars are a galactic-scale conflict, but you experience them through one organization at a time. Joining a faction is the single biggest choice you make about your character's place in the war — bigger than your species, bigger than your starting profession, often bigger than your skills. The faction shapes which missions you see, which rooms you can enter, what equipment you carry, who shoots at you on sight, and what story arc your character lives.

This guide covers the six playable factions, the six era-agnostic professional guilds, the rank-and-equipment system that ties them all together, and the bigger-picture systems (Director AI, Faction Intent, reputation) that the factions plug into.

If you only have ten minutes, read **§1 The Faction Map** and **§2 The Six Playable Factions**. That's enough to make an informed first choice. The deeper sections cover ranks, equipment, the Bounty Hunters' Guild override, guilds, reputation, and the Director AI's role in keeping faction politics dynamic.

You should already understand the basics of the security model (see [Security Zones](#/guide/security-zones)) — factions matter most in the contested-zone gray space between Republic-secured and lawless territory.

---

## 1. The Faction Map

The Clone Wars galaxy has three large powers and a small handful of organizations that operate alongside them:

- **The Galactic Republic** — the thousand-year democratic state, fighting for its survival. Clone armies in the field, the Senate at home.
- **The Confederacy of Independent Systems (CIS)** — the Separatist alliance, drawing from systems that resent Republic taxation and Core World privilege. Battle droids in the field, the Separatist Council at home.
- **The Jedi Order** — ancient guardians of peace now drafted as generals. Aligned with the Republic, but as a way of life rather than a political affiliation.
- **The Hutt Cartel** — the criminal apparatus of the Outer Rim. Officially neutral. Profits from both sides.
- **The Bounty Hunters' Guild** — independent contractors. Both the Republic and the CIS post bounties through Guild cutouts when official channels would be embarrassing.
- **Independent** — the default. No faction obligations, no faction benefits. The galaxy is full of people who just want to survive the war without picking a side.

Beyond those six, there are two **NPC-only factions** that you'll encounter but can't join:

- **The Sith** — a covert dark-side cabal directing CIS strategy from off-stage. Players never see them as such; they see only Count Dooku publicly leading the CIS, and dark-side events the Director narrates.
- **The Separatist Council** — the CIS's oligarchic inner circle (Nute Gunray, Wat Tambor, San Hill, et al.). Their decisions surface as CIS faction policy; you don't interact with them directly as a player.

And six **professional guilds** that cut across faction lines — see §4.

You can be a member of one faction at a time. Switching factions later carries a **7-day cooldown** and a reputation hit with the cause you abandon, and no account may run two characters in the same faction at once — so the choice has weight, it isn't a hat you swap between sessions.

You can additionally hold membership in **up to three guilds**. So a Republic clone officer who's also in the Medics' Guild is fully valid; a CIS agent who's also in the Slicers' Collective is fully valid; a Hutt enforcer who's also in the Mechanics' Guild is fully valid. Guilds are neutral.

---

## 2. The Six Playable Factions

| Faction | Axis | HQ | Ranks | Joinable At |
|---|---|---|---|---|
| Galactic Republic | Republic / Order | Nar Shaddaa - Corellian Sector Promenade | 7 (Conscript → Commander) | Chargen or anytime |
| Confederacy of Independent Systems | Separatist | Nar Shaddaa - The Burning Deck Cantina | 6 (Sympathizer → Commander) | Chargen or anytime |
| Jedi Order | Jedi / Light | Coruscant - Jedi Temple Entrance Hall | 3 (Padawan → Master) | Village quest completion required |
| Hutt Cartel | Criminal | Nar Shaddaa - Hutt Emissary Tower - Audience Chamber | 6 (Associate → Vigo) | Chargen or anytime |
| Bounty Hunters' Guild | Independent / Contract | Nar Shaddaa - Bounty Hunters' Quarter | 6 (Novice → Guildmaster) | Anytime |
| Independent | None | (no HQ) | 1 (Freelancer) | Default starting affiliation |

Why so many faction HQs on Nar Shaddaa? Because Nar Shaddaa is the Smuggler's Moon — Hutt-controlled, neutral, where everyone has business and no one is officially supposed to. The Republic and CIS both maintain "trade missions" on Nar Shaddaa that function as recruitment offices. The Hutts let them coexist because it's good for business. Coruscant has Republic and Jedi presence but no CIS recruiting (you'd be arrested on sight). The Outer Rim has Hutt and bounty hunter presence but no Republic or CIS infrastructure.

### Galactic Republic

The thousand-year-old democratic Republic is fighting for its survival against the Separatist insurgency. Joining the Republic means clone trooper logistics, Senate politics, and the weight of an institution that believes it is fighting for civilization. You'll work alongside clone troopers (NPCs), report through a military chain of command, and access the best equipment in the game once you make rank.

The Republic recruits actively at the Nar Shaddaa Corellian Sector Promenade and on Coruscant. Joining is a `faction join republic` away — there's no audition, no test, the war needs warm bodies. Distinguishing yourself in service is where the work begins.

**Ranks** (each rank gates equipment, permissions, and certain mission types):

| Level | Title | Min Rep | Equipment Issued | Permissions |
|---:|---|---:|---|---|
| 0 | Conscript | 0 | Republic uniform, DC-17 pistol | — |
| 1 | Private | 10 | DC-15 blaster rifle, Republic light armor | faction_comms |
| 2 | Corporal | 25 | Improved armor | faction_comms |
| 3 | Sergeant | 40 | — | faction_comms, lead_npc_squad |
| 4 | Lieutenant | 60 | Officer's sidearm | + issue_orders, restricted_access |
| 5 | Captain | 75 | — | + create_missions, promote_sergeant |
| 6 | Commander | 90 | — | faction_admin |

Reputation is gained through completed Republic missions, donations to the faction treasury, killing CIS or Sith NPCs, and being present at Republic-aligned narrative events the Director runs. Reputation can be *lost* through faction infractions (smuggling Hutt contraband, fraternizing with CIS sympathizers, refusing direct orders from in-faction superiors).

### Confederacy of Independent Systems

The Separatist alliance draws its membership from systems that resent Republic taxation, corruption, and Core World privilege. Joining the CIS means working alongside battle droids (NPCs), Sith-aligned commanders, and a cause that might be justified or might be a power grab — it's genuinely hard to tell from the inside.

CIS recruitment is more covert than Republic. The HQ at the Burning Deck Cantina is a known Separatist front; walking in and saying you want to join is the equivalent of signing up at a recruiting station, but the cell-and-handler structure means you'll work in small groups, with limited visibility into the wider organization. The CIS cell structure is reflected in your starting equipment — civilian-looking gear instead of uniforms, encrypted comlinks instead of faction comms.

**Ranks:**

| Level | Title | Min Rep | Equipment Issued | Permissions |
|---:|---|---:|---|---|
| 0 | Sympathizer | 0 | Encrypted comlink | — |
| 1 | Operative | 15 | Blaster pistol, civilian gear | faction_comms, cell_missions |
| 2 | Agent | 30 | Heavy blaster pistol | faction_comms, cell_missions |
| 3 | Sergeant | 50 | — | + lead_npc_squad |
| 4 | Cell Leader | 70 | — | + create_missions, recruit |
| 5 | Commander | 90 | — | faction_admin |

CIS reputation tracks similarly to Republic — completed Separatist missions, donations, killing Republic or Jedi NPCs, narrative events. CIS members face a recurring tension: many missions push toward dark-side actions (sabotage, assassination, intimidation) that can attract Dark Side Points. The cause may be justified, but the methods are corrosive. See [Force Powers](#/guide/force-powers) for the dark-side mechanics.

### Jedi Order

The Jedi Order serves the Republic as generals while upholding their ancient mandate as guardians of peace. A Jedi's faction is not a political affiliation — it is a way of life. Joining the Order requires completing the **Jedi Village quest chain** (see [The Jedi Village](#/guide/jedi-village)). You cannot pick Jedi at chargen; you earn it through the longest narrative arc in the game.

**Ranks:**

| Level | Title | Min Rep | Equipment Issued | Permissions |
|---:|---|---:|---|---|
| 0 | Padawan | 0 | Padawan robes, Jedi utility belt | — |
| 1 | Jedi Knight | 50 | Jedi robes | faction_comms, take_padawan |
| 2 | Jedi Master | 90 | — | + sit_council, faction_admin |

Note that the **lightsaber** is granted via the Village quest's graduation step, not as standard rank equipment. The Order is a small faction — at any given time there are typically fewer than half a dozen PC Jedi on the entire game. This is by design. Jedi are meant to be rare and important.

A Jedi Knight can take a Padawan via the [Padawan-Master](#/guide/padawan-master) bond. Jedi Masters can sit on the Council and approve major decisions for the faction.

### The Hutt Cartel

The Hutts are neutral in the Clone Wars and intend to stay that way — neutrally profitable. Working for the Hutt Cartel means smuggling, enforcement, and the Outer Rim criminal apparatus. Dark side pays more. The Hutts know this and price accordingly.

The Cartel doesn't recruit publicly. You "join" by attracting the attention of a Hutt enforcer in the Nar Shaddaa underworld, on Tatooine, or anywhere Hutt interests run — usually by completing a job for them as a freelancer first. After enough freelance jobs, the local Vigo will offer you a Cartel position.

**Ranks:**

| Level | Title | Min Rep | Equipment Issued | Permissions |
|---:|---|---:|---|---|
| 0 | Associate | 0 | Blaster pistol | — |
| 1 | Runner | 10 | Heavy blaster pistol, smuggler vest | faction_comms, hutt_missions |
| 2 | Enforcer | 25 | — | faction_comms, hutt_missions |
| 3 | Operator | 45 | — | + hutt_black_market |
| 4 | Underboss | 65 | — | + recruit, territory_ops |
| 5 | Vigo | 85 | — | faction_admin |

The Hutts' `hutt_black_market` permission at Operator and above unlocks restricted gear sales — things the Republic and CIS would arrest you for owning. The Cartel is also the only faction with `territory_ops`, which lets Underbosses claim and contest territory rooms in lawless zones. See [Territory Control](#/guide/territory-control).

### Bounty Hunters' Guild

The Guild doesn't take sides in the war — it takes contracts. Both Republic and CIS put bounties on each other's agents. The Guild processes them all with professional neutrality. Anyone can enroll as a **Novice** (`faction join bounty_hunters_guild`), but enrollment is only the doorway: the contract board doesn't open to you until you make **Journeyman** (15 rep), and the right to post bounties on other players is gated higher still, at **Senior Hunter** (55 rep). Competence is proven on the ladder, not at the door. The Guild office in the Nar Shaddaa Bounty Hunters' Quarter (a few corridors away from the Hutt Emissary Tower) is the standard intake point; CT-7842 in Mos Eisley brokers offworld contracts; the Hutt Council on Nal Hutta posts the highest-value ones.

**Ranks:**

| Level | Title | Min Rep | Equipment Issued | Permissions |
|---:|---|---:|---|---|
| 0 | Novice | 0 | Binder cuffs, Guild license | — |
| 1 | Journeyman | 15 | Tracking fob | guild_bounty_board |
| 2 | Hunter | 35 | — | guild_bounty_board |
| 3 | Senior Hunter | 55 | — | + post_player_bounties |
| 4 | Veteran | 75 | — | + guild_vote |
| 5 | Guildmaster | 90 | — | faction_admin |

The most important Guild permission, available at Journeyman and above, is **bounty hunter PvP override** — see [Security Zones](#/guide/security-zones) §4. With an active claimed contract, you can attack your target in a contested zone without going through challenge/accept. The contract is the consent. This is what makes bounty hunting a playable profession rather than a roleplay aesthetic.

Senior Hunters and above can **post bounties on player characters** (not arbitrary characters — the system tracks criminal behavior, faction infractions, and contract failures; bounties are generated from real player actions, not griefing wishlists).

### Independent

The default starting affiliation. No allegiance. No faction benefits, no faction obligations. The galaxy is full of people who just want to survive the war without picking a side.

This is a real option, not a placeholder. An Independent character can join professional guilds, run missions through whatever broker pays today, smuggle for the Hutts on Tuesday and ferry Jedi diplomats on Wednesday, and never make a binding commitment to anyone. The price you pay is faction infrastructure: no comms net, no rank progression, no faction-only missions, no faction-issued equipment.

Many spacers run Independent for their entire career. The traders and freelancers around the Outer Rim mostly stay Independent because the alternatives all want something they aren't willing to give.

---

## 3. Equipment Issuance

When you reach a new faction rank, the faction's quartermaster **automatically issues** the equipment listed in the rank table — no command needed, it goes straight to your inventory. To request a replacement for lost or sold faction-issued gear, use `faction requisition <item description>`. The faction also reissues equipment on death (when you respawn), so promotion-tier gear is not lost permanently.

Some things to know:

- **Equipment is faction-marked.** A DC-15 blaster rifle issued by the Republic isn't ordinary military hardware — it's specifically Republic-issue. Walking around with it in a CIS zone gets you noticed. Most factions track lost or stolen equipment as a faction infraction.
- **You can sell or trade issued equipment**, but doing so repeatedly may flag you for fraud and cost reputation. The system tolerates occasional loss (battlefield reality) but punishes patterns.
- **Independents and guild-only members don't receive equipment** unless they pay for it through the standard economy. See [Economy](#/guide/economy).
- **Tutorial chains issue starter gear** before you've picked a faction. That gear is yours regardless of subsequent affiliation. See [Tutorial Chains](#/guide/tutorial-chains).

---

## 4. The Professional Guilds

Guilds are era-agnostic professional organizations. They don't take sides in the war; they take members. A guild membership signals competence in a craft and unlocks craft-specific tools, contracts, and discounts. Six guilds are available:

| Guild | Professional Domain | Weekly Dues |
|---|---|---|
| Mechanics' Guild | Vehicle & ship repair | 50 cr |
| Shipwrights' Guild | Starship construction & modification | 75 cr |
| Medics' Guild | First aid, bacta, combat medicine | 50 cr |
| Slicers' Collective | Computer intrusion & electronic warfare | 60 cr |
| Entertainers' Guild | Performance, music, gambling | 25 cr |
| Scouts' Guild | Survival, pathfinding, wilderness | 40 cr |

**The concrete benefit of guild membership is a flat 20% discount on the CP cost of skill training** (see [CP Progression](#/guide/cp-progression)). It applies the moment you're in *any* guild and does **not** stack — being in three guilds costs no less to train than being in one, so extra memberships are about identity and reach, not deeper discounts. Each guild posts a modest weekly due (the rate shown above, 25–75 credits) as the price of carrying its credentials.

You can hold **up to three guild memberships** at once. Joining is immediate — `guild join <code>` enrolls you on the spot; there's no audition or skill check at the door. Beyond the discount, a guild is the professional identity your character wears: the Mechanics' Guild marks you as a hands-on engineer, the Slicers' Collective as someone who lives inside other people's systems. It shapes how you roleplay and how other characters read you, even when it isn't changing a die roll.

Guild membership is **independent of faction**. A Jedi Knight in the Medics' Guild is fully canonical (some Jedi do specialize in healing). A Hutt Cartel Enforcer in the Slicers' Collective is fine — the slicers don't care who your patron is, only whether you can crack the encryption.

For the actual craft systems behind these guilds, see [Crafting](#/guide/crafting), [Sabacc & Entertainer](#/guide/sabacc-entertainer), and the relevant sourcebook-derived material.

---

## 5. Reputation, Promotion, and Demotion

Each faction tracks your **reputation** as an integer score from 0 to 100. The rank table for each faction lists a `min_rep` for each rank; when your reputation crosses a threshold, you become *eligible* for promotion. Promotion isn't automatic — a faction officer with the `promote_sergeant` (or `faction_admin`) permission has to approve it. For NPC-managed factions, the Director AI handles approvals; for PC-led factions, you'll need to be noticed by the brass.

**Gaining reputation:**

- Completing faction missions (~3–10 rep per mission, depending on difficulty)
- Donating credits to the faction treasury (1 rep per 100 credits, capped per week)
- Killing rival-faction NPCs (1–3 rep per kill)
- Being present at faction-relevant narrative events the Director runs (variable, sometimes substantial)
- Performing exemplary roleplay that the Roleplay Evaluator flags as faction-aligned (rare, but possible — see [Director AI](#/guide/director-ai))

**Losing reputation:**

- Failing missions (-1 to -5 rep)
- Faction infractions (smuggling rival gear, fraternizing with rivals, refusing orders, getting caught committing crimes against the faction)
- Long inactivity (-1 rep per week of game-time silence; this is mild attrition, not a punishment, but it adds up)

**Discipline escalates.** A first infraction is usually a warning. A second puts you on probation. A third can expel you from the faction entirely, which strips your rank and equipment and locks you out until you re-earn membership. The Director AI handles discipline for NPC-managed factions with this escalation pattern — see [Director AI](#/guide/director-ai) for the details.

---

## 6. Faction Intent and Tutorial Migration

If you completed a tutorial chain before joining a faction, the chain may have recorded your **faction intent** — a non-binding declaration of which faction you were leaning toward when you arrived. This is stored in your character data and surfaces when you actually join, sometimes giving you a small reputation head-start.

Faction intent is set during tutorial chains that include faction-relevant choices — the Mos Eisley spacer chain may flag you as leaning Independent or Hutt depending on whether you took a smuggling job; the Coruscant arrival chain may flag you as leaning Republic or CIS based on dialogue choices in the Senate sector tour.

Intent is **not** a commitment. You're free to join any faction your character qualifies for, regardless of what your intent says. The system just gives small alignment bonuses where your declared intent and actual joining match. Mostly this is invisible to you — a few extra reputation points at join time.

---

## 7. Director AI Integration

Factions don't exist as static rosters. They're embedded in the **Director AI's faction influence system**, which tracks each faction's strength in every zone and updates the world accordingly. See [Director AI](#/guide/director-ai) for the full system.

Practical effects for you as a faction member:

- **Your missions are pulled from a faction-specific pool** the Director generates based on the current state of the war. CIS gains influence in Sullust this week? Republic mission boards will offer counter-operations there. Hutts make a move on Nar Shaddaa? Republic enforcement missions appear at the spaceport.
- **Your reputation contributes to your faction's zone influence.** A high-rep Republic Captain doing missions in Mos Eisley nudges Republic influence upward in that zone. Multiply that across all active faction members and the world is shaped by player action.
- **Faction politics are visible.** The HoloNet News feed announces faction milestones — "Separatist offensive in Outer Rim Sector 4," "Jedi Master killed in action," "Hutt Council issues neutrality reaffirmation." You can read the war happening in real time.

---

## 8. Bounty Hunter Override (Cross-Reference)

Worth restating because it's the single most consequential faction mechanic for PvP players: **Bounty Hunters' Guild members with an active claimed contract bypass the PvP consent system in contested zones for their specific target.** The contract counts as consent. This is how bounty hunting is playable as a profession.

The guardrails:
- You need an active **claimed** contract, not just Guild membership
- The contract must name a specific target
- Targets have earned their bounties (criminal behavior, faction infractions, contract failures — not arbitrary)

For the full mechanics, see [Security Zones](#/guide/security-zones) §4.

---

## 9. Worked Example: A First Week as a Republic Conscript

To pull it together, here's what an early-career Republic Soldier might look like.

You roll a Human soldier at chargen and choose the Republic faction. You start as a **Conscript** (rank 0), 0 reputation, issued a Republic uniform and a DC-17 sidearm. You spawn at the Republic recruiting station at Nar Shaddaa Corellian Sector Promenade.

Your first mission, pulled from the Republic mission board: deliver a sealed dispatch to a Republic Intelligence officer in the Mos Eisley spaceport. Pays 200 credits and 4 reputation if successful. You hyperjump to Tatooine, walk the dispatch to the contact, complete the delivery. The dispatch is encrypted — you don't know what's in it. Mission completes, you have 4 rep and 200 cr.

Your second mission: escort a Republic Customs Liaison on a market sweep through Mos Eisley. You're armed (DC-17), in uniform (visible to anyone passing), and the Liaison is going to make herself unpopular by inspecting Hutt-aligned merchants. Three rounds of low-grade encounters: a Trandoshan stallholder gets aggressive (one dodge roll to defuse), a Hutt enforcer recognizes you and stares (Perception check to ignore it without losing face), a wounded Geonosian refugee tries to grab the Liaison's arm (Persuasion check to deflect without violence). Mission completes, you have 8 rep and 350 cr.

You hit 10 reputation. The system flags you eligible for **Private** rank. The faction NPC (or, if you're lucky, a high-rank PC officer) approves the promotion. You report to the Republic equipment officer, get issued a DC-15 blaster rifle and Republic light armor, and gain the `faction_comms` permission — you can now talk on the Republic faction channel and see what other Republic players are doing in real time.

Three Hutt missions you ran on the side as a freelancer (while still wearing the Republic uniform — sloppy, but you were broke) get noticed. The faction comms ping you: "Conscript, your association with criminal elements has been observed. This is a warning." Your reputation drops by 1. You decide to be more careful.

By the end of week 1, you're a Private with 14 reputation, a DC-15 rifle, light armor, 850 credits, and a working understanding that the Republic notices what you do.

That's the texture of faction life. Choices have weight, the world reacts, and progress is earned in small visible increments.

---

## 10. Commands Quick Reference

| Command | Effect |
|---|---|
| `faction list` | Show all factions and your standing in each |
| `faction info <code>` | Detailed faction info |
| `faction join <code>` | Apply to join a faction |
| `faction leave` | Resign from your current faction |
| `faction roster` | View other members of your faction (rank-gated detail) |
| `faction missions` | Show available faction missions |
| `faction channel <message>` | Speak on faction channel (requires `faction_comms` permission) |
| `faction requisition <item>` | Request replacement for lost faction-issued equipment |
| `faction invest <amount>` | Invest personal credits into zone influence |
| `faction influence` | Show your faction's territory influence across zones |
| `faction armory` | View shared faction armory (in claimed rooms) |
| `+reputation` | Show your reputation in all factions and guilds (alias: `+rep`) |
| `+reputation <code>` | Detailed reputation breakdown for a specific faction |
| `guild list` | Show all guilds and your membership status |
| `guild join <code>` | Apply to join a guild |
| `guild leave <code>` | Resign from a guild |
| `faction promote <character>` | Promote a subordinate (requires rank permission) |
| `faction warn <character>` | Issue a warning (requires rank permission) |
| `faction expel <character>` | Expel a member (requires rank permission) |
| `faction treasury` | View faction treasury balance (leader-only) |

---

*This guide is part of the Parsec Game Guides. See also: [Security Zones](#/guide/security-zones), [Territory Control](#/guide/territory-control), [The Jedi Village](#/guide/jedi-village), [Padawan-Master](#/guide/padawan-master), [The Director AI](#/guide/director-ai), [Tutorial Chains](#/guide/tutorial-chains).*
