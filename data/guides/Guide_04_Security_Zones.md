---
category: galaxy
order: 1
summary: "EVE-style security tiers. Where PvP is legal, where Republic patrols respond, and where you're on your own."
tags: ["security", "pvp", "zones", "republic", "lawless", "safe", "wildspace", "hutts"]
---

# Security Zones

**Parsec — WEG D6 Revised & Expanded**

---

## How to Read This Guide

The galaxy is not one undifferentiated combat sandbox. Every zone in the game carries a **security level** — a risk tier inspired by EVE Online's high-sec / low-sec / null-sec gradient — and that level controls whether you can shoot people, whether NPCs will attack you, and whether other players can hunt you down. This is the layer that makes the Senate District feel different from the Coruscant Underworld, and it's the layer most likely to surprise you in your first week of play if you don't read it.

The Clone Wars era makes this system particularly meaningful. The Republic doesn't have the reach the Empire will eventually claim — clone patrols garrison the core worlds and important military assets, but the Outer Rim is largely on its own. The Hutts run Hutt Space. Independent spacers run their own affairs. The CIS operates openly in Separatist-aligned systems. As a player, knowing where Republic authority actually extends — and where it doesn't — is one of the most important pieces of map literacy you can develop. <!-- lint-era-ok: deliberate CW-vantage foreshadowing of the Empire, not a stale GCW string -->

If you only have five minutes, read **§1 The Three Tiers** and **§3 PvP Consent**. The rest covers the moving parts — Republic crackdowns, bounty contracts, the space equivalent, organizational territory upgrades, and why anyone bothers going to lawless zones in the first place.

This system runs alongside, not separate from, the [Ground Combat](#/guide/ground-combat) and [Space Systems](#/guide/space-systems) layers. Combat is *gated* by security — knowing how the gate behaves matters as much as knowing the combat mechanics themselves.

---

## 1. The Three Tiers

Every zone in the game is classified as **Secured**, **Contested**, or **Lawless**. The label appears next to the room name when you `look` or move in:

```
Senate District Plaza [SECURED]
  Republic banners snap in the recycled breeze...

Mos Eisley Cantina [CONTESTED]
  Smoke and conversation in a dozen languages...

Jundland Wastes - Canyon Floor [LAWLESS]
  Wind-carved sandstone walls rise on either side...
```

Each tier behaves very differently:

| Tier | PvE | PvP | Where you'll see it |
|---|---|---|---|
| **Secured** | Blocked | Blocked | Senate District, Jedi Temple, Kuat Drive Yards, Tipoca City clone facility |
| **Contested** | Allowed | Consent required | Mos Eisley Cantina, Nar Shaddaa Promenade, Coruscant CoCo Town, most urban zones |
| **Lawless** | Allowed | Unrestricted | Jundland Wastes, Coruscant Underworld below Level 50, Nar Shaddaa Warrens, Geonosis war zone, deep space |

**Secured.** Combat is shut off. You cannot attack a player, you cannot attack an NPC, and NPCs will not attack you. The local authority is too thick to allow it — on Coruscant that's the Coruscant Security Force and Senate Guard, on Kuat it's the shipyards' private security plus clone garrisons, in the Jedi Temple it's the Temple Guards themselves. Think of secured zones as the social and economic hubs: shops, banks, the cantina entrance, official buildings, government chambers, anywhere a serious authority has eyes everywhere. If you try to attack in one, you'll see something like:

```
  Senate Guard patrols this district.
  They'd be on you before you could draw.
```

Your `attack` command does nothing. This isn't a difficulty penalty — it's a hard refusal. The flavor text changes based on who's actually doing the policing in that zone. Coruscant gets Senate Guard or Coruscant Security Force flavor; Kamino gets clone garrison flavor; Mos Eisley's spaceport core (when crackdown-elevated) gets clone patrol flavor.

**Contested.** PvE combat works normally — you can fight Hutt enforcers, criminal NPCs, the occasional CIS infiltrator, anyone the world has marked as hostile. PvP, on the other hand, requires the consent flow described in §3. You can't just walk up to another player and gun them down; you have to challenge them and they have to accept. Most of the inhabited galaxy is contested — the cantinas of Mos Eisley, the Promenade levels of Nar Shaddaa, the markets and street levels of Coruscant outside the Senate sector. It's the workaday tier where most play happens.

**Lawless.** No rules. No clone response. NPCs are fully aggressive and any player can attack any other player at any time. When you step into a lawless zone for the first time, you get a one-time warning:

```
  *** WARNING: You are entering LAWLESS territory. ***
  *** Players can attack you freely here. ***
```

After that first warning, you're on your own. Lawless zones are where the highest rewards and worst surprises live — see §9. They are also where most of the Outer Rim actually exists. Tatooine outside the cities, the open dunes of the Jundland Wastes, the lower levels of Nar Shaddaa, the warrens beneath Mos Eisley, anywhere on Geonosis that isn't an active Republic position, the Coruscant Underworld below the Senate Guard's patrol depth — all lawless. The galaxy is a large and dangerous place once you step off the well-trodden routes.

---

## 2. How a Zone's Security Is Decided

The security tag you see on a room isn't always its baseline value. The effective level can shift based on a few things working in sequence — admin overrides, Director AI events, faction influence, and your own organization's territorial claims. As a player you don't need to think about the resolution chain; you just see the result. But knowing it exists explains why the Mos Eisley spaceport sometimes flips from contested to lawless overnight, or why the Coruscant Senate District stays SECURED even when criminal activity spikes everywhere else.

The things that can change a zone's effective security:

1. **Director AI events.** When the Director runs a "criminal surge" arc — usually triggered by player actions (a series of successful Hutt missions, a CIS infiltration plot landing, the bounty board filling with claimable contracts) — contested zones in the affected area downgrade one tier. Contested becomes Lawless, Secured becomes Contested. When the Director runs a "Republic crackdown" arc, it goes the other way. The shifts are temporary and revert when the underlying influence changes.
2. **Faction influence thresholds.** Sustained Republic dominance in a zone (authority influence 75+) upgrades it one tier. Sustained criminal dominance (underworld influence 80+) downgrades it. At authority 90+, the zone goes to martial law — forced SECURED regardless of base level, clone garrisons deploy, you'll see Republic banners everywhere. The surge and the crackdown apply in sequence, so a zone in crisis can have a criminal surge AND a crackdown partially canceling each other out.
3. **Builder-set baseline.** Every zone has a default security set when it was built. The Mos Eisley Cantina is Contested by default; the Senate District is Secured; Jundland is Lawless. These defaults represent the zone's character in normal Clone Wars conditions.
4. **Territory claims.** If your organization holds the wilderness region you're standing in, its lawless rooms are treated as Contested **for your org's members** — you get PvP consent protection on your own turf. Non-members still see Lawless. See §7.
5. **Faction strongholds.** A room can be tagged as belonging to a faction. If you're *hostile or unfriendly* to that faction, a normally-Secured stronghold room reads as **Lawless** to you specifically — walking into your enemy's headquarters means walking somewhere they can cut you down with no consent rule to protect you. Everyone else sees the room's normal tier. (Staff set these tags with `@security override`; see §8.)
6. **Your own city.** If you're a citizen of a player-run city, that city's rooms are safer *for you*: a contested city room reads as Secured, and a lawless one reads as Contested. Non-citizens — including guests and the banished — get no such upgrade. This is the most generous modifier in the chain; a citizen at home is as safe as the system can make them, even if a hostile-faction tag (#5) would otherwise have downgraded the room. See [Player Cities](#/guide/player-cities).

You can monitor current influence in any zone via the Director's zone reports on the web client. When a zone is mid-shift, the HoloNet News feed will usually call it out: "Republic crackdown announced for Mos Eisley spaceport — clone patrols deploying" or "Hutt unrest spreads through Nar Shaddaa lower levels." The world tells you what's happening; you don't have to dig.

A worked example of resolution in practice: you walk into the Mos Eisley spaceport docking bay. The room's builder-set baseline is Contested. Right now there's a low-level Republic crackdown active (Republic influence at 78), bumping the effective level up one tier — so you see **[SECURED]**. Two days later (game time), the crackdown lapses and the underlying baseline reasserts: **[CONTESTED]**. Two days after that, a player-driven Hutt smuggling arc raises criminal influence to 82 — back down one tier to **[LAWLESS]**. The same physical room, three different security tags inside a week, all driven by what the players and the Director are doing.

---

## 3. PvP Consent in Contested Zones

This is the rule that comes up most often. In any contested zone, you cannot attack another player without their consent. The flow is:

```
> challenge Vex
  You challenge Vex to a fight!

  (Vex sees: "Tundra challenges Vex to a fight!
   Type 'accept' to accept or 'decline' to refuse.")

> accept                  (Vex types this)
  Vex accepts the challenge! PvP is active for 10 minutes.
```

Once accepted, both players can attack each other freely for the next ten minutes. After the window expires, or if either player leaves the zone, the consent lapses and either side has to re-challenge to start again.

You can also `decline` a challenge. Declining is silent to the rest of the room — only the challenger sees the refusal. There is no etiquette penalty for declining; PvP consent exists precisely so players can opt out of fights they don't want.

A few things worth knowing:

- **Challenges expire** if not accepted within ten minutes. You can't sit on a challenge indefinitely.
- **Consent is per-pair, not per-room.** If you and Vex agree to fight, that doesn't mean Tarn can join in. Tarn would need their own challenge accepted. A bar brawl with four people involves six separate challenge/accept pairs.
- **The challenge is visible to the room.** The whole point is that PvP is a public, opt-in event in contested space. Bystanders can see "Tundra challenges Vex" and react however they want — flee, call for help, take cover, place bets.
- **In secured zones, the challenge command itself is blocked.** No PvP, period, in those zones. Asking the Senate Guard to politely look the other way is not on the menu.
- **In lawless zones, no challenge is needed.** If you're somewhere lawless, anyone can shoot you with no preamble. The Coruscant Underworld's lower levels are full of Twi'lek pickpockets and Trandoshan muggers who will skip the formality.

### Flagging for open PvP

If you'd rather skip the challenge/accept dance entirely — say you're a duelist who wants all comers, or you're running an open-brawl scene — you can flag yourself:

```
> +pvp on        — open yourself to PvP in contested zones
> +pvp off       — close yourself again
> +pvp status    — show your flag and any cooldown
> +pvp           — same as +pvp status
```

While your flag is on, anyone in a **contested** zone can attack you without a challenge, and you can attack any other flagged player the same way. If *either* the attacker or the target is flagged, the fight starts with no challenge needed. The flag is your standing consent.

Two limits keep it honest:

- **It never overrides a SECURED zone.** Flagging yourself in the Jedi Temple or the Senate District does nothing — those zones stay absolute. The flag only matters in contested space (in lawless space everyone is effectively flagged already).
- **You can't flag-and-flee.** Once your flag has actually been used in a fight, you can't switch it off for five minutes. This stops griefers from flagging, ambushing someone, and immediately un-flagging to dodge the consequences. `+pvp status` shows how much of the cooldown remains.

### Common questions

**Can I challenge someone in a secured zone, then move to a contested zone to fight?** No. The challenge has to be issued in the contested zone where the fight will happen. The system tracks zone-of-issue and the consent only activates in the same zone.

**What if my target logs out mid-challenge?** The challenge stays open until its ten-minute timer expires. If they come back inside the window, they can still accept or decline. Most players just let it expire.

**Can I challenge a Force-using PC into a duel?** Yes. The challenge system is fully Force-neutral. A Padawan can challenge a smuggler, and vice versa. Force powers used in the resulting fight follow the normal rules; see [Force Powers](#/guide/force-powers) for the dark-side consequence model on using offensive Force powers against another player.

**Does declining hurt my reputation?** No. There's no system tracking declines, no badge of cowardice, no NPC who thinks less of you. Decline whenever you want.

For the underlying combat mechanics (initiative, damage, soak, all of it), see [Ground Combat](#/guide/ground-combat).

---

## 4. Bounty Hunter Override

There's one carve-out to the consent rule. If you're a member of the **Bounty Hunters' Guild** with an active claimed bounty contract, you can attack your contracted target in a contested zone without going through challenge/accept. The contract is the consent.

The target gets a clear warning when you draw:

```
  Vex draws on you! [BOUNTY HUNTER — Contract #4421]
  You've been marked. Defend yourself!
```

This exists specifically to make bounty hunting playable as a profession. Without the override, every bounty would require the target's cooperation, which obviously defeats the purpose. With it, the game can support genuine hunter-vs-hunted scenarios in civilized space — Cad Bane stalking a witness in the Coruscant Senate plaza, Aurra Sing collecting a Hutt contract on Nar Shaddaa, a player bounty hunter following a wanted CIS sympathizer through Mos Eisley.

The system has two important guardrails:

- **You need an active claimed contract.** You can't just declare yourself a hunter and start shooting. The contract has to exist on the bounty board, you have to have claimed it through `+bounty/claim`, and it has to name your target specifically. The Bounty Hunters' Guild headquarters in Nar Shaddaa Promenade is where contracts post; CT-7842's office on Tatooine handles offworld contracts; the Hutt Council on Nal Hutta posts the highest-value ones.
- **Targets have earned their bounties.** Bounties don't get posted on innocent players. The bounty board tracks criminal behavior — successful PvP killings, smuggling caught and reported, faction infractions, contract failures with witnesses. Bounties appear because of player choices, not because someone with credits paid to grief.

This means bounty hunting is meaningful PvP content without being a griefer's playground. If you're getting hunted, you did something to attract a contract. If you're a hunter, you're working off real player-generated targets. The Hutts and the Republic both post contracts; the Guild brokers neutrally between them.

### A note on Republic vs. criminal bounties

Republic bounties (issued through Guild cutouts when official channels would be politically awkward) tend to target players who've conducted CIS-aligned actions or who've been caught smuggling military-grade contraband. Criminal bounties (issued through Hutt or syndicate channels) tend to target players who've crossed cartel interests — failed to deliver, refused a job, witnessed something they shouldn't have. Both types are legitimate and both unlock the contested-zone override.

What you can't do: post a bounty on a player you simply don't like. Bounties have to originate from in-world events the game's narrative system records as bounty-worthy. The boards are not a wishlist.

---

## 5. Space Has Its Own Security Tiers

Ships in space follow a parallel security model. Instead of zones labeled Secured/Contested/Lawless, space sectors are labeled by their type, and each type maps to a security tier:

| Space type | Effective security | Why |
|---|---|---|
| **Dock** | Secured | Landing approach, port control, customs — combat shut off |
| **Orbit** | Contested | Patrols are present but thin — PvP needs consent |
| **Hyperspace Lane** | Contested | Major shipping routes get some patrol presence |
| **Deep Space** | Lawless | Open void, no authority, anything goes |

The `fire` command in space hits the same gate as the `attack` command on the ground. You can't fire on another ship in a dock zone. You can't fire on another player's ship in orbit without consent. In deep space, anyone can engage anyone.

The mapping shows up in concrete ways during play. **Pirate ambushes** happen almost exclusively in deep space — Black Sun raiders, Trandoshan slavers, freelance corsairs, whatever the Director has spawned this week. **Republic patrol encounters** happen in orbit and along the major lanes between the Core Worlds and the Inner Rim — clone-piloted Z-95s or ARC-170s investigating suspicious traffic. **CIS infiltrators** sometimes appear in orbit around Separatist-aligned worlds. **Customs scans** happen at dock — your cargo is sniffed and you may be charged duty.

Specific examples from the active game world:

- **Coruscant orbit** is heavily patrolled — Republic Navy presence is dense, contested-level by rule but de facto closer to secured for non-military traffic. Don't smuggle through here.
- **Kuat orbit** is even tighter — the shipyards are a strategic asset. Expect Republic Navy challenges.
- **Tatooine orbit** is technically contested but patrols are rare. Mostly safe for smugglers.
- **Hyperspace lane from Coruscant to the Outer Rim** is patrolled at both ends; the long middle is contested but quiet.
- **Deep space beyond Geonosis** is the actual war zone — CIS pickets, Republic counter-pickets, opportunistic pirates. Don't fly through unless you have business there.

For the full ship combat mechanics, see [Space Systems](#/guide/space-systems).

---

## 6. Lawless Zone Incentives

Why would anyone willingly go to a lawless zone if any player can murder them there? Because the rewards are dramatically higher. The game deliberately concentrates valuable content in dangerous space — risk and reward run together.

**Economy.** The harvest yield tables run richest in lawless zones. The same node type that drops one unit of metal in a contested zone can drop several units plus chemicals and a tier-5 rare in a lawless zone under a dominant org — phrik ore in the Jundland Wastes, biological reagents in the Coruscant Underworld's chemical sumps, salvageable wreckage on Geonosis. (Contested zones aren't dry — a contested zone held under tight organizational control still carries a chance at a T5 rare — but the biggest, most reliable hauls are out in the wilds.) The mission board offers higher-paying jobs that require lawless travel — Hutt contracts, CIS espionage runs, Republic black-ops insertions through Separatist territory. Smuggling routes pass through lawless territory for the biggest payouts; spice runs from Kessel and the Outer Rim into the Inner Worlds are the classic case. Black-market dealing concentrates in the lawless underworlds — the Nar Shaddaa Warrens, the back rooms of Mos Eisley cantinas, the Twi'lek fences in the Coruscant Underworld.

**Progression.** Much of the world's reward density lives where the Republic can't reach. The higher-paying contracts route you through lawless space; the richest crafting hauls come off lawless nodes; the discovery content — ruins, crash sites, hidden caches — clusters out past the patrols. Advancement (CP) doesn't come from *standing* in a lawless zone — there's no idle bonus for loitering somewhere dangerous — it comes from the play that dangerous zones make possible: the missions you complete, the scenes you run, the kudos you earn for memorable play. (See [CP Progression](#/guide/cp-progression) for exactly how CP accrues.) Lawless zones don't pay you to be there; they're where the better-paying work *is*.

**Faction work.** Most criminal-faction missions require lawless travel. Most CIS sympathizer missions, by definition, take place in territory the Republic doesn't control. If you're aligned with anyone other than the Republic, your job's going to take you somewhere dangerous sooner rather than later. Even Republic missions sometimes require lawless travel — a clone intelligence officer doesn't ask a player to extract a witness from the Senate District; they ask you to go pull someone out of the Nar Shaddaa Undercity.

The math works out to: if you spend all your time in secured zones, you'll level slowly, you'll never see the best loot, and you'll feel like the world is small. The game is designed to be larger and richer the farther out you push. The Outer Rim is where the actual game happens; the Core Worlds are the staging area.

### Tactical advice for first lawless trips

If you're new to a lawless zone, a few practices reduce your odds of dying ignominiously:

- **Travel light.** Don't carry cargo you can't afford to lose. The death loop (see [Medical & Death](#/guide/medical-death)) preserves your equipped gear but lets attackers loot anything you were carrying separately.
- **Travel paired.** Lawless zones are where the [Padawan-Master](#/guide/padawan-master) bond shines — two characters in a lawless zone are exponentially safer than one. Same for any player-organized pair.
- **Watch the news.** If HoloNet News is flagging unrest in the area you're heading to, the Director has likely seeded extra hostile NPCs. Reconsider.
- **Scout first.** Step into a new lawless room, `look`, and immediately leave if the contact roster shows more PvP-flagged players than you can handle. There's no shame in scouting and turning back.
- **Use cover.** The cover system (see [Ground Combat](#/guide/ground-combat) §7) is your friend in lawless zones where you might be ambushed. A character behind half-cover is a much harder target.

---

## 7. Territory Claims and Security Upgrades

Territory is claimed at the **region** level, not room by room. When a player organization claims a contestable **wilderness region** (via `faction claim`, once the org holds a foothold there), every lawless room inside that region is treated as **contested for the organization's members** — the "citadel upgrade." You get PvP consent protection across your whole holding, not just one spot. Enemies still have to challenge you to start a fight; they can't just walk in and shoot.

Non-members entering the same region see its rooms as Lawless, because for them they are — they have no claim, and no protection. So you can defend your claimed territory aggressively while still benefiting from the consent rule against rival player organizations trying to take it. (One caveat: only an org member who is *not* independent gets the upgrade. A factionless PC traveling with the org gets the base lawless tier — the protection follows organization membership, not company.)

This is the first benefit of the territory control system. It means a syndicate's held stretch of frontier is dangerous for rival players but safe for its own members — the same ground, viewed by different characters, with different consequences. There are more benefits as the territory system fills out — guard NPCs, resource nodes, passive income — see [Territory Control](#/guide/territory-control) for the full picture.

A worked example: the **Falleen Syndicate** (player-run) holds a contestable wilderness region. A Falleen Syndicate member crosses into it and sees its rooms as **[CONTESTED]**. A Black Sun rival sees the same rooms as **[LAWLESS]**. Both can attack the Falleen member, but the Black Sun has to challenge first if they want a fair fight — meanwhile a non-aligned Trandoshan thug in the same room could just open fire, because to the thug the region is still lawless and PvP needs no consent. Territory protects you from rivals who care about appearances; it doesn't protect you from sociopaths who don't. (Note the ceiling: the citadel upgrade only lifts LAWLESS to CONTESTED — wilderness never becomes fully SECURED, so there is no zero-risk turf out in the wilds.)

---

## 8. Admin Commands (Staff Only)

The `@security` command (ADMIN-only) has four forms, split between *zone-level* security and *per-room faction* overrides:

```
@security <zone>                        — Show a zone's base security level
@security <zone> = <level>              — Set zone security (secured/contested/lawless)
@security override <room> = <faction>   — Set a room's faction override
@security override <room> = none        — Clear a room's faction override
```

The first two forms work on whole zones. `@security <zone> = lawless` writes the zone's baseline tier to the database, so it **persists across restarts**; the read form shows that stored base value (not the dynamic, per-character effective level a player actually sees, since that depends on Director arcs and faction influence). `<level>` is one of secured / contested / lawless and is case-insensitive; `<zone>` is matched by exact name.

The `override` form is a different tool. It doesn't set a security tier — it tags a single room (by id or slug) with a **faction override**: hostile or unfriendly PCs of the named faction then see that room as **LAWLESS instead of SECURED** (the §2 rule that lets a faction stronghold turn dangerous for its enemies). `@security override <room> = none` clears the tag. The faction code must be a real organization (`faction list` shows valid codes).

Changes take effect immediately — no restart needed; the resolver re-reads the database on every effective-security check. (Note: transient *Director-driven* security shifts — criminal surges, crackdowns — are held in memory and reset on restart by design, because they're narrative effects; only the admin `@security` writes above are durable.)

If you're staff running an event and need a normally-Secured zone to allow combat for the duration of a scene — say, a duel arc in the Senate District plaza, or a CIS infiltration that compromises the Jedi Temple lobby — set the zone with `@security <zone> = contested` (or `lawless`) and reset it after. Don't forget to reset it; lingering overrides have caused player confusion.

---

## 9. Worked Example: A Night on Nar Shaddaa

To pull it all together, here's how the system feels in actual play.

You step off the landing pad at the Nar Shaddaa Promenade. The room reads **[CONTESTED]**. You can buy and sell freely. If another player wants to fight you, they have to challenge you and you have to accept. Hutt enforcers in matching beskar are openly visible — they're the actual authority here, not the Republic. The casino-tower neon makes night and day feel the same.

You walk a few rooms toward the Undercity entrance. The tag changes to **[LAWLESS]**. The one-time warning fires:

```
  *** WARNING: You are entering LAWLESS territory. ***
  *** Players can attack you freely here. ***
```

From here on, anyone in the room can shoot at you without warning. The mission board entry that paid 4,000 credits to deliver this package makes sense now — the danger is real, and the pay tracks the danger.

You take the contract. Halfway through the run, the news ticker on the web client flashes: "Republic strike team deploys to Nar Shaddaa Levels 89-91 — Hutt cartel asset suspected." Your zone's effective security upgrades one tier — the rooms you're moving through go from Lawless to Contested. A pair of clone troopers in dark recon armor materialize from the next room. The deployment isn't your friend (Republic clones in the area will challenge any obviously criminal player), but it means random PvP gankers can no longer touch you mid-run.

A rival player — let's call her Vex — sees you in the contact roster, recognizes the contract you're carrying (HoloNet rumored it was a juicy one), and tries to intercept. Because the zone is now Contested, she has to challenge you:

```
  Vex challenges you to a fight!
  Type 'accept' to accept or 'decline' to refuse.
```

You're alone, you're carrying valuable cargo, you decline. Vex sees the decline; the rest of the room doesn't. She has to find another way to get the package — maybe tail you to your delivery point and try again somewhere lawless.

You complete the delivery in the Warrens (lawless throughout — the entire bottom of Nar Shaddaa is). The contract pays. You head back to the Promenade, the tag flips through **[LAWLESS]** in the Warrens, **[CONTESTED]** on the way back up through the levels, and ultimately **[SECURED]** at the docking bay where your ship waits — the bay is privately operated and the operator pays Hutt enforcers enough to keep it actually safe. Combat shuts off the moment you cross into secured space.

That's the security system in motion. Three tiers, dynamic shifts driven by Director arcs and faction influence, real player choices in the form of accepts and declines, and a clear line between social space, contested space, and the wilds. The Clone Wars galaxy isn't simple — the Republic doesn't have the reach to make it simple — and the security system is the layer that makes that texture playable.

---

*This guide is part of the Parsec Game Guides. See also: [Ground Combat](#/guide/ground-combat), [Space Systems](#/guide/space-systems), [Territory Control](#/guide/territory-control), [Organizations & Factions](#/guide/organizations-factions), [Medical & Death](#/guide/medical-death).*
