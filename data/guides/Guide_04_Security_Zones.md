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

The four things that can change a zone's effective security:

1. **Director AI events.** When the Director runs a "criminal surge" arc — usually triggered by player actions (a series of successful Hutt missions, a CIS infiltration plot landing, the bounty board filling with claimable contracts) — contested zones in the affected area downgrade one tier. Contested becomes Lawless, Secured becomes Contested. When the Director runs a "Republic crackdown" arc, it goes the other way. The shifts are temporary and revert when the underlying influence changes.
2. **Faction influence thresholds.** Sustained Republic dominance in a zone (75+ influence) upgrades it one tier. Sustained criminal dominance (80+ Hutt or syndicate influence) downgrades it. At 90+ Republic, the zone goes to martial law — forced SECURED regardless of base level, clone garrisons deploy, you'll see Republic banners everywhere. Both rules apply in sequence, so a zone in crisis can have a criminal surge AND a crackdown partially canceling each other out.
3. **Builder-set baseline.** Every zone has a default security set when it was built. The Mos Eisley Cantina is Contested by default; the Senate District is Secured; Jundland is Lawless. These defaults represent the zone's character in normal Clone Wars conditions.
4. **Territory claims.** If your organization claims a room in a lawless zone, that room is treated as Contested **for your org's members** — you get PvP consent protection on your own turf. Non-members still see Lawless. See §7.

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

**Economy.** Rare crafting resources only spawn in lawless zones — phrik ore in the Jundland Wastes, biological reagents in the Coruscant Underworld's chemical sumps, salvageable wreckage on Geonosis. The mission board offers higher-paying jobs that require lawless travel — Hutt contracts, CIS espionage runs, Republic black-ops insertions through Separatist territory. Smuggling routes pass through lawless territory for the biggest payouts; spice runs from Kessel and the Outer Rim into the Inner Worlds are the classic case. Black market vendors selling restricted gear without markup are found in lawless underworlds — Cad Bane's old contacts in the Nar Shaddaa Warrens, the back rooms of cantinas in Mos Eisley, the Twi'lek fences in the Coruscant Underworld.

**Progression.** Certain advanced NPC trainers only operate in lawless zones. The Mos Eisley cantina has a half-dozen specialists who'll train you for credits — sharpshooting, slicing, demolitions — without asking what you intend to do with the skills. A few Force-sensitive hermits in the Jundland Wastes will teach you Force basics if you can find them and survive the trip out. Ruins, crash sites, and hidden caches — the discovery content — only spawn in lawless zones. Your CP tick rate (the slow drip of advancement currency) gets a **+25% bonus** while you're actively in a lawless zone, on top of whatever you earn from missions and combat.

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

When a player organization claims a room in a **lawless** zone (the only zone where claims are permitted), that room is treated as **contested for the organization's members**. You get PvP consent protection on your own turf. Enemies still have to challenge you to start a fight; they can't just walk in and shoot.

Non-members entering the same claimed room see the room as Lawless, because for them it is — they have no claim, and no protection. So you can defend your claimed territory aggressively while still benefiting from the consent rule against rival player organizations trying to take it.

This is the first benefit of the territory control system. It means a Hutt syndicate's claimed warehouse in the Nar Shaddaa Warrens is dangerous for rival players but safe for its own members — the same room, viewed by different characters, with different consequences. There are more benefits as the territory system fills out — guard NPCs, resource nodes, vendor stalls, passive income — see [Territory Control](#/guide/territory-control) for the full picture.

A worked example: the **Falleen Syndicate** (player-run, Coruscant Underworld-based) claims a warehouse room in the Nar Shaddaa Warrens. A Falleen Syndicate member walks in and sees **[CONTESTED]**. A Black Sun rival walks in and sees **[LAWLESS]**. Both can attack the Falleen member, but the Black Sun has to challenge first if they want a fair fight — meanwhile a non-aligned Trandoshan thug in the same room could just open fire on the Falleen member because, to the thug, the room is still lawless and PvP needs no consent. Territory protects you from rivals who care about appearances; it doesn't protect you from sociopaths who don't.

---

## 8. Admin Commands (Staff Only)

These commands let staff inspect or override security levels for testing, narrative events, or emergency fixes:

```
@security <zone>                  — Show effective security level
@security <zone> = <level>        — Set zone security (secured/contested/lawless)
@security override <room> = none  — Clear any override on a room
```

Changes take effect immediately — there's no restart needed, and the next `attack` attempt in the affected zone reads the new value from the database. The override flow is intentionally non-persistent across server restarts when set via the Director (since those are narrative effects), but admin sets via `@security` are persistent.

If you're staff running an event and need a normally-Secured zone to allow PvP for the duration of a scene — say, a duel arc set in the Senate District plaza, or a CIS infiltration that compromises the Jedi Temple lobby — `@security` is the tool. Don't forget to reset it after the scene ends; lingering overrides have caused player confusion.

---

## 9. Worked Example: A Night on Nar Shaddaa

To pull it all together, here's how the system feels in actual play.

You step off the landing pad at the Nar Shaddaa Promenade. The room reads **[CONTESTED]**. You can buy and sell freely. If another player wants to fight you, they have to challenge you and you have to accept. Hutt enforcers in matching beskar are openly visible — they're the actual authority here, not the Republic. The casino-tower neon makes night and day feel the same.

You walk a few rooms toward the Undercity entrance. The tag changes to **[LAWLESS]**. The one-time warning fires:

```
  *** WARNING: You are entering LAWLESS territory. ***
  *** Players can attack you freely here. ***
```

From here on, anyone in the room can shoot at you without warning. The mission board entry that paid 4,000 credits to deliver this package made sense now — the danger is real. You're earning the +25% CP bonus just by being here.

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
