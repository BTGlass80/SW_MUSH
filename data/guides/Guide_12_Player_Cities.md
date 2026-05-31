---
category: community
order: 2
summary: "Found a settlement, recruit citizens, build infrastructure, and govern."
tags: ["cities", "settlement", "governance", "build", "infrastructure", "town"]
---

# Player Cities

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Player cities are the largest persistent player-owned structures in the game. They aren't single rooms or single buildings — they're a *named place* on the map that your organization owns, with HQ at the center, expansion rooms branching out, citizens who get benefits inside the walls, and a treasury that fills from commerce happening on city soil.

A city is what an organization grows into once it has wealth, influence, territory, and a tier-5 HQ. Founding the first city on the server is a real moment. By the time you're reading this guide, the question is probably "do I want one?" or "how do I help build one?" rather than "what is it?"

If you only have time for one section, skim **§1 What is a Player City?** and **§4 Roles**. The role you'll hold in a city — citizen, guest, outsider, or in rare cases founder or mayor — is what determines how it feels to live in.

---

## 1. What is a Player City?

A player city is a named, persistent place owned by your organization. From the outside, it looks like a cluster of rooms in a single zone, all tagged with the city's name in the look output:

```
[Slave Quarter] [Mos Eisley Outskirts] Dust City
```

From the inside, it's a set of rooms your organization controls — your HQ at the center, plus up to 20 additional "expansion" rooms claimed outward in any direction, all of them in the same zone.

Cities do five things ordinary HQs don't:

1. **They aggregate identity.** All city rooms carry the city's banner tag in `look`. Players walking through know they're in your city. The name is a brand, and over time the city's name accrues reputation — players talk about Dust City, about Velvet District, about whichever city built itself into a known place.

2. **They collect tax.** Commerce happening in any city room — vendor sales, sabacc rake, bounty postings, dock cargo, NPC vendor trades — is taxed at the rate the Mayor sets, and the cut flows to the organization's treasury. The tax is invisible to the player paying it; their wallet sees the same price. The city's slice comes from the system's slice, not yours.

3. **They upgrade security for citizens.** Citizens (org members in good standing) get a security upgrade when standing in city rooms. Contested becomes Secured; Lawless becomes Contested. A city in Hutt Space is still rough for outsiders but safe for its own.

4. **They give citizens a teleport home.** `+city home` returns a citizen to the city's HQ entry from anywhere on the map, once an hour. Useful for getting back fast after a mission goes long.

5. **They let the Mayor govern.** Banishment, guest lists, citizen-only rooms, message of the day, tax rates — these are the levers of city life. A city has political content, not just spatial content.

You can found exactly one city per organization. Dissolving it returns half the founding cost. Cities are a long commitment, not a churn-and-rebuild structure. Most players, most of the time, are *citizens of* a city, not founders of one.

---

## 2. Founding a City

Founding a city is a high-bar action. You need, in order:

1. To be the **organization leader** (rank 5 — top of your org's rank ladder).
2. Your org must already have a **tier-5 HQ** placed somewhere on the map. Tier-5 is the top of the housing tree; getting there is its own project (see Guide #13 — Housing).
3. That HQ must be in a zone with **declared contested or lawless security**. Cities cannot be founded in Republic-secured zones — by design, the system is for frontier and underworld governance. Neither the Galactic Republic nor the CIS permits private cities inside their controlled territory.
4. Your org must have at least **50 influence** in that zone (the same threshold as a foothold territory claim — you've already established yourself there).
5. The org treasury must hold the **founding cost**.

The founding cost depends on which tier-5 HQ subtype you have:

| HQ Type | Storage | Founding Cost |
|---|---|---|
| Outpost | 100 | **25,000 credits** |
| Chapter House | 200 | **75,000 credits** |
| Fortress | 400 | **200,000 credits** |

This is *separate* from what you paid to build the HQ itself. The founding cost is the city declaration fee — a real and substantial credit sink that prevents cities from springing up casually.

Once those check out, you type:

```
+city found Dust City
```

The name must be 3–32 characters, mostly alphanumeric, and **not on the reserved list** — Mos Eisley, Theed, Coruscant, Tipoca City, Kachirho, Sundari, "Jedi Temple," "Senate Building," and roughly 30 other canonical Star Wars locations are off-limits. The list exists so player cities don't muddy the canon-faithful place names; you can't found "Coruscant Heights" and then have new players confused about where Coruscant is.

On success:
- The founding cost is debited from your org's treasury.
- A new city is born, in `active` state.
- All your HQ rooms become **City Center** rooms — permanent, never released, the anchor of the city.
- The city's name immediately appears in `look` output for those rooms.

You are now the **Founder.** Founders never lose their authority short of the city being dissolved. Even if you later step down as Mayor, hand the reins to another player, leave the org, or come back years later — the city's founder is still you.

---

## 3. Expanding the City

Once founded, a city has its HQ rooms locked as City Center. To grow, you **claim adjacent rooms** as expansion rooms. The claim is run by the org leader (same rank gate as founding), one room at a time, by walking to a position next to the city and pointing at the next room you want.

Each claim costs **5,000 credits** from the treasury. You also need:

- The target room shares an exit with an existing city room (contiguity — cities can't sprout disconnected islands).
- The target room is in the **same zone** as your city. Cities don't span zones.
- The target room isn't already in another city.
- Your org has at least **50 influence** in the city's zone (the influence requirement persists, not just at founding).
- The treasury has the 5,000.
- You haven't claimed any room in the last **24 hours** (real-time).

The 24-hour rate limit is the key constraint. You cannot zerg an entire sector; expansion is a project that plays out over real days, with other organizations watching to see where you're pushing. If you're rapidly expanding, your rivals know it.

The maximum total expansion is set by your HQ tier:

| HQ Tier | Max Expansion Rooms |
|---|---|
| Outpost | 5 |
| Chapter House | 10 |
| Fortress | 20 |

So an Outpost city tops out at HQ + 5 expansion = a small compound. A Fortress city at HQ + 20 expansion = a substantial neighborhood. If you want more rooms, you upgrade your HQ to the next tier (which has its own significant cost and requirements — Guide #13).

You claim by **direction from your current room**, or by room ID for scripted/admin work:

```
+city claim north
+city claim 1421
```

The direction form is the normal player experience. You stand in your HQ, type `+city claim north`, and the room to the north (assuming it qualifies) becomes part of the city. The room ID form is mostly for builders who already know the ID they want.

You can also **release** expansion rooms with `+city release [room_id]`. Release refunds **50%** of the claim cost (2,500 cr) and removes the room from the city. HQ City Center rooms cannot be released — they're permanent unless you dissolve the whole city. Releasing is useful for trimming back if you over-expanded, or if a neighborhood doesn't feel right and you want to move the city's footprint.

**Expansion is a tactical and political act.** A city growing east is sending a message about who they're encroaching on; a city growing toward a rival's territory is sending an even louder one. Cities in disputed zones often expand cautiously, room by room, with each room functioning as a small political statement. Talk to your org leadership before claiming; the room you grab is going to be visible to everyone in the zone.

---

## 4. Roles: Founder, Mayor, Citizen, Guest, Outsider, Banished

Every character has exactly one role with respect to any given city. The role determines what you can do.

**Founder.** The org leader at the moment of founding. Permanent unless the city dissolves. The Founder can:
- Reassign the Mayor.
- Set the **rate cap** (the ceiling on what the Mayor can set the tax rate to).
- Dissolve the city.
- Do everything a Mayor can do.

Founders are usually but not always the active Mayor too. A founder might step back into a ceremonial role and let a trusted lieutenant run things day-to-day.

**Mayor.** Assigned by the Founder. At founding, the Mayor defaults to the Founder. The Mayor runs day-to-day governance:
- Set the **tax rate** (bounded by the rate cap).
- Set the **MOTD** (Message of the Day, displayed on city-room entry).
- Add and remove **guests**.
- **Banish and unbanish** players from the city.
- Flag rooms as **citizen-only**.
- Set the city guards (a planned later feature — placeholder for now).

Mayor is the executive office of the city. The Founder is the sovereign; the Mayor is the prime minister.

**Citizen.** Any organization member in good standing is automatically a citizen of their org's city. Citizens get:
- The **security upgrade** in city rooms (Contested → Secured, Lawless → Contested).
- **Free movement** through citizen-only rooms.
- The **`+city home` teleport** (1-hour cooldown).
- The **rest bonus** in city rooms (a future-feature seam — the bonus mechanic itself is being designed).

Citizen is the most important role to understand because it's the one most players will hold. Citizens are the silent majority of city life; the city exists for them.

**Guest.** A non-member who has been explicitly added to the city's guest list by the Mayor. Guests get free movement — they can enter most city rooms without resistance — but **no security upgrade, no rest bonus, no home teleport, no citizen-only access.** Useful for trusted outsiders: a regular trading partner, a friendly rival's diplomatic emissary, a Jedi visiting a Falleen city for negotiations. Guest status is honorary — you're welcome here, but you're not one of us.

**Outsider.** Everyone else. Outsiders can enter most city rooms freely, but bounce off **citizen-only** rooms with a refusal. They get no benefits and they pay full taxes on commerce.

**Banished.** Explicitly banished by the Mayor. Banishment supersedes everything else. A banished player who is *also* a member is treated as a banished outsider: no security upgrade, no movement into citizen-only rooms, public banishment notice surfaces for citizens in look output (so everyone in the city knows). Default banishment is **30 days** real-time. The Mayor can `+city unbanish <player>` to clear it early.

Banishment is a real political tool. Mayors banish rivals, rule-breakers, defectors. It's also visible — when a Mayor banishes someone, citizens see it, and the banishment notice in look turns the cantina into political theater for as long as the banished player is around. Mayors who banish too readily look tyrannical; mayors who never banish look weak. The right cadence is part of the art of running a city.

---

## 5. Taxation — The Mayor's Lever

The Mayor sets a **tax rate** between 0% and the city's **rate cap**. The Founder sets the rate cap, with an absolute ceiling of 10%. The default rate cap at founding is 10% — the Founder can lower it for cities that want to advertise themselves as a low-tax haven, or leave it at the ceiling for cities that want maximum revenue.

Every commerce surface in the city pays the tax automatically:

- **Vendor droid sales** — buying from an NPC vendor in a city room.
- **Bounty postings** — when someone puts up a bounty contract in a city room.
- **Sabacc rake** — the house cut on every sabacc game played in a city room.
- **Selling to an NPC vendor** — selling a weapon, item, or salvage in a city room.
- **Buying from an NPC vendor at a dock or shop** — same logic.
- **Dock cargo sell at the planet market** — long-haul trade routes that terminate in a city.
- **Dock cargo buy at the planet market** — outbound trade routes.

The tax is **invisible to the player paying it.** When you buy a 1,000-cr rifle from a vendor in a 5% city, you still pay 1,000 cr. The vendor's escrow contributes 50 cr to the city; the system absorbs that out of its slice. From the player's perspective, prices haven't changed. From the city's perspective, every transaction quietly funds the treasury.

This is intentional: the tax shouldn't make players avoid your city. It should make organizations prefer to do business in cities that exist (the convenience, the security, the social density) over scattered roadside NPCs in the wild.

Customs fines — paid to a government NPC for smuggling violations — are **not** taxed. That's a state-imposed penalty, not commerce; the city doesn't get a slice of someone else's enforcement.

The Mayor's commands:

- **`+city tax view`** — shows the rate, the cap, this week's revenue, and the cumulative total.
- **`+city tax set 0.05`** — sets the rate to 5% (decimal form, valid range 0.0 to rate_cap).
- **`+city tax ratecap 0.10`** — Founder only; sets the rate cap.

Weekly revenue resets every 7 real-time days, so you can compare week-over-week. Cumulative revenue is forever — it's the running tally of every credit the city has ever earned.

**The political shape of tax.** A high tax rate (8-10%) makes commerce slightly less attractive; players might prefer to do their sabacc games or vendor shopping outside the city. A low rate (1-3%) keeps the city friendly to traffic but produces slower treasury growth. Most successful cities sit at 3-5%. Some specialized cities (smuggler havens advertising as "no taxes") sit at 0% and recoup the cost through other means — recruitment, services, prestige.

---

## 6. The Security Upgrade — Why Citizens Live Longer

This is the single biggest reason to be a citizen.

When you're inside a city room **as a citizen**, the security level of that room is upgraded:

- **Contested → Secured** — no combat allowed; PvP refused; you're untouchable.
- **Lawless → Contested** — combat with explicit consent only (challenge/accept, +pvp flag, bounty contracts, territory contests).

**Non-citizens get the base level.** A Hutt-controlled lawless zone is still lawless for everyone except the local Hutt syndicate's own members. An outsider walking through that lawless zone is in a lawless room; the citizen walking next to them is in a contested room. Same room, two different security tiers depending on who you ask.

The upgrade is the most permissive last word. Even if a hostile faction has temporarily downgraded the zone via a faction-override mechanic, the city upgrade lifts citizens back up. The principle is simple: a citizen inside their own city should be safer than any hostile downgrade can make them.

**Practical effect:** if your organization controls a city in a Hutt Space lawless zone, your members can walk through that city safely. Outsiders who follow your members in are still in a lawless zone and can be attacked. This is how a small disciplined faction holds a tough zone — the city itself is the citadel.

**Secured zones never downgrade.** A city founded in a contested zone never becomes a lawless zone for outsiders; the city upgrade only ever raises tier, never lowers. (And cities cannot be founded in secured zones to begin with, so that path is impossible by construction.)

**The citadel logic of cities.** This single feature changes the strategic shape of the game. A small organization with a city in a lawless zone is much more dangerous than the same organization with no city. They can attack outwards from a safe base. They can retreat to safety after a strike. They can rest in security while their enemies cannot. Cities aren't just real estate — they're force multipliers, and rival organizations should treat them as such.

---

## 7. Citizen-Only Rooms

The Mayor (or Founder) can flag any expansion room as **citizen-only**. Non-citizens who try to enter bounce off with a refusal.

```
+city citizenroom on      (flag current room as citizen-only)
+city citizenroom off     (clear the flag on current room)
```

**HQ rooms are citizen-only by default** — they don't count against the cap and don't need to be explicitly flagged. The inner sanctum of your tier-5 HQ is always private to your org.

**There's a cap.** At most 30% of non-HQ expansion rooms can be citizen-only. A 10-room Chapter House city can flag 3 expansion rooms; a 20-room Fortress city can flag 6. Going over the cap returns an error with the exact ceiling.

Why the cap? To prevent cities from sealing off everything and becoming gated communities that exclude all RP. A city that's 90% citizen-only is not really a city — it's a private compound with a public sign. The system wants cities to be *places* — places that outsiders walk through, do business in, fight near, and remember. The 30% cap means the majority of your city remains open ground, available for chance encounters and ordinary traffic. Use the citizen-only flag for the things that genuinely need privacy: the treasure vault, the strategy room, the meeting chamber where leadership talks shop. Not for "the whole upper floor."

**The role separation in practice.** Citizens move through citizen-only rooms freely. Guests bounce off them even with their guest status. Outsiders bounce off them. Banished players bounce off them. This is the only mechanic that genuinely separates citizens from guests — guests get most benefits, but they cannot access the city's private spaces.

---

## 8. The `+city home` Teleport

Citizens get a teleport home to the city's HQ entry room. From anywhere on the map. Once per hour.

```
+city home
```

Conditions:
- You're a citizen (founder, mayor, or member; not guest, not outsider, not banished).
- You're not in combat.
- You're not in space.
- You're not in a wilderness sentinel (those have their own travel mechanics).
- At least 60 minutes have passed since your last `+city home`.

The cooldown is per-character and persists across logouts. You don't get to home twice in a session by reconnecting. The teleport works **across zones** — you can `+city home` from Mos Eisley to your city on Nar Shaddaa.

The destination is always the **city's HQ entry room**. Not your personal housing, not your favorite room — the city's front door. From there you can walk inward to your own house, your guildhall, whatever.

This is the citizen's emergency button. Used a missing CP for a mission and you're stuck two planets away from your party? `+city home`. Going to log off and want to make sure you start tomorrow somewhere safe? `+city home` first. Down to Wounded Twice in a dangerous zone with a slow respawn? `+city home` if you haven't used it in the last hour.

It's also a quiet recruitment tool. Players considering joining an organization sometimes ask "what's it actually like to be in this org?" and one of the answers is "I can be home in two commands no matter where I am on the map." That convenience matters.

---

## 9. Mayor Actions in Detail

The Mayor's day-to-day toolkit:

**`+city motd <text>`** — sets the Message of the Day, max 240 characters. Displayed on city-room entry. Keep it terse. Good MOTDs are short and specific:

> Welcome to Dust City. Smugglers Council meets Sundown. Visitors welcome at the Atrium.

Bad MOTDs are long manifestos. Players reading "welcome" lines don't want to be lectured; they want to know what's happening *right now* in the city.

**`+city mayor <player>`** — Founder only. Reassign the Mayor to any member of the org. Useful when the leader wants to delegate, or when leadership formally changes hands.

**`+city guest add <player>`** / **`+city guest remove <player>`** — manage the guest list. Adding a citizen is a no-op (they're already in). Re-adding an existing guest is idempotent. Removing a guest who was never a guest is an error.

Use guests deliberately. A guest is "this person is welcome to walk through our city without being treated as an outsider." Good candidates: trade partners, NPCs you've befriended (no, you can't add NPCs — only PCs), allied faction emissaries, occasional friendly contacts. Don't guest someone you'd be annoyed to see in the cantina; the whole point of guest status is comfort.

**`+city banish <player> [reason]`** — banish a player from the city. Default 30 days; the reason (if given) shows up in the public banishment notice. Banishments stack to the longest expiry, so re-banishing extends rather than overwriting.

**`+city unbanish <player>`** — clear the banishment early. Sometimes the right call after a cooling-off period. Sometimes you just leave it.

**`+city citizenroom on/off`** — flag the current room as citizen-only. Capped at 30% of non-HQ expansion rooms. Use sparingly.

**`+city guards`** — placeholder for a future feature. The Mayor will eventually be able to station NPC guards at specific city rooms. Not live yet.

---

## 10. Dissolution

The Founder can dissolve the city:

```
+city dissolve Dust City
```

Effects:
- City state becomes `dissolved`.
- All expansion rooms are released — they revert to ordinary zone rooms.
- HQ rooms revert to plain HQ rooms (no longer City Center).
- The treasury gets **half the founding cost** back (12,500 / 37,500 / 100,000 cr, depending on tier).
- Active banishments and guest entries are cleared.
- All city-room tags drop off in look output.

This is **final**. You cannot un-dissolve. Founding again means starting over from scratch: pay the full founding cost again, requalify on influence and HQ, pick a new name (the old name is now free for anyone, including you, to claim).

Dissolving is a serious decision. Most cities never dissolve; they're built to outlast the founding generation. The reasons that genuinely justify dissolution: the org has split or imploded, the city's zone has become uninhabitable (an event drove out commerce), or the leadership wants to consolidate two cities into one (rare — see "you can only have one per org"). If you're considering it because the city "isn't fun anymore," try changing the tax rate, banishing some troublemakers, or relocating expansion before you nuke the whole thing.

---

## 11. The Look Output and What People See

City rooms show the city's name as a tag in `look`:

```
[Slave Quarter] [Mos Eisley Outskirts] Dust City
```

First bracket is the room name, second is the zone, third is the city. For citizens, the city tag colors brighter — you're home. For outsiders, the tag is dimmer — it's somewhere, but it's not yours.

If you're **banished**, the city tag is replaced with a warning line:

```
*** You are banished from Dust City. ***
```

That line is visible to other citizens too — they see "Outsider Trill, banished, present." This is the public-shame layer; the Mayor's banishment becomes part of the social fabric of the city. Banished players walking around are politically visible.

The MOTD shows on first entry per session. If you walk into a city room for the first time tonight, you get the MOTD. If you walk between rooms within the city, you don't get it again — once per session is enough.

---

## 12. `+city info` and `+city list`

**`+city info`** with no argument shows the city you're currently standing in (or your org's city if you're a member of one). **`+city info <name>`** shows any city by name. Output includes:

- Name, Founder, Mayor
- HQ tier (outpost/chapter_house/fortress)
- Zone
- Founded date
- Citizen count, expansion room count, banishment count
- Tax rate, rate cap
- This week's revenue and lifetime total (Mayors/Founders see this; outsiders see only the rate)
- MOTD

**`+city list`** lists all active cities on the server, paged 25 per page. Useful for getting a feel for the political map: who's where, who has what tier, who's been around longest. New players sometimes browse the list as a quiet survey of "which factions actually exist and have momentum."

**`+city map`** shows an ASCII grid of the city's rooms and exits — your own city only, by design. Other cities are private business.

**`+city citizens`** lists the city's citizens (paged). Mayors use this to keep track of who's in.

---

## 13. A Founding Walkthrough

A concrete worked example, start to finish.

You're the leader of **Vask's Vigil**, a Falleen Syndicate splinter, rank 5. Your org has been running together for a couple months; you've built up to a tier-3 HQ on Nar Shaddaa.

**Step 1 — Tier up the HQ.** You need a tier-5. Spend a few real-time weeks accumulating credits, completing influence-building missions, and upgrade the HQ to tier-5 — a **Chapter House** in your case (storage 200). The HQ purchase cost is its own thing, separate from the city founding cost; that's already paid by the time you start thinking about a city.

**Step 2 — Check influence.** The HQ is in **The Vertical Bazaar**, a lawless zone on Nar Shaddaa. You check `+reputation falleen` and see 47 influence in The Vertical Bazaar. You need 50. Run two or three more missions in the zone; reach 52.

**Step 3 — Check treasury.** Look at your org treasury via `faction info` or your treasury surface. It says 80,000 cr. Founding a Chapter House city costs 75,000. Good — you've got headroom.

**Step 4 — Pick a name.** "Velvet District" — three words, 14 characters, no canonical conflict, alphanumeric. Sounds like a Falleen-organized commerce hub. Approve.

**Step 5 — Found.** Run `+city found Velvet District`. The treasury debits 75,000. The city is born. The HQ rooms get the new tag in `look`. You're the Founder and (by default) the Mayor.

**Step 6 — Set the MOTD.** `+city motd Velvet District. House rules: no shooting in the Atrium. All faiths welcome.` The MOTD now greets visitors.

**Step 7 — Set the tax rate.** `+city tax set 0.04`. Four percent. Modest; you want the city to be friendly to traffic.

**Step 8 — Start expanding.** Stand in your HQ. Type `+city claim northwest`. 5,000 cr debits; the room becomes part of the city. 24 hours later, `+city claim east`. Another 5,000 cr. Over the next two real-time weeks, you grow the city to 10 expansion rooms — the cap for your Chapter House tier.

**Step 9 — Citizen-only flags.** You flag your inner vault (one room) as citizen-only: `+city citizenroom on` while standing in it. The vault is now private to your org.

**Step 10 — Watch the revenue.** Over the next several real-time weeks, the treasury fills from tax revenue. Sabacc games being played in the Atrium contribute. Vendor droids selling repair parts to passing freighter crews contribute. Bounty postings on the cantina board contribute. The city is generating its own income.

**Step 11 — Govern.** A rival cell from a competing Falleen splinter starts hanging around the cantina, making trouble. After two warnings, the Mayor (you, in this case) banishes their leader for 30 days. The banishment notice appears in `look`; the rival is publicly shamed. Two weeks later, a guest membership negotiation with a neutral trading consortium goes well; you add their two emissaries as guests.

That's the arc. It takes real time. It's meant to. Cities are slow-burn structures that pay off when you let them.

---

## 14. Living in Someone Else's City

Most players will spend more time as **citizens of** a city than as the Founder/Mayor of one. Here's what that experience looks like.

You're a member of a small Republic-aligned recon faction on Coruscant. Your org has a city — let's call it Lighthawk — in the Senate District. You walk into the cantina there and see the MOTD: "Welcome back. Squad briefing Sundown in Conference 3."

You glance at `look`. The city tag is bright — you're home. Half the players in the room are also citizens; one or two are guests. Combat in this room is not possible (Senate District is contested, your citizenship upgrades it to secured for you). You can RP, drink, shop, post bounties, play sabacc, plan missions — all in safety.

You walk to the inner sanctum, a citizen-only conference room. The exit is flagged; you pass through cleanly because you're a citizen. Inside, the squad lead is going over a Hutt-Space mission. You spend an hour planning, then split for the spaceport.

Mission goes long; you're on Nar Shaddaa, you're at Wounded, and you don't want to fight the bacta-soak timer on top of debt to the smuggler captain. You burn your `+city home`: instant teleport back to the Senate District HQ entry. From there you walk to the medbay, bacta-tank yourself, and you're back to full ahead of next session.

A week later, the Mayor announces a rate change: tax going from 3% to 5% to fund a planned expansion north. You and the rest of the citizens see the announcement on the org channel. Nobody loves a tax hike, but the case is reasonable. You shrug; commerce in the city still goes through. The Mayor knows what they're doing.

That's the daily texture of citizenship: small conveniences, public benefits, a sense of belonging to a place that's been deliberately built. Most players never found a city. Most players belong to one.

---

## 15. Numbers At A Glance

| Quantity | Value |
|---|---|
| Min rank to found / claim / release | 5 (org leader) |
| Min influence to found | 50 |
| Min influence to claim | 50 |
| Founding cost — Outpost | 25,000 cr |
| Founding cost — Chapter House | 75,000 cr |
| Founding cost — Fortress | 200,000 cr |
| Expansion cost per room | 5,000 cr |
| Expansion rate limit | one per 24 real-time hours |
| Max expansion rooms — Outpost | 5 |
| Max expansion rooms — Chapter House | 10 |
| Max expansion rooms — Fortress | 20 |
| Dissolution refund | 50% of founding cost |
| Release refund | 50% of claim cost |
| Max tax rate (absolute ceiling) | 10% |
| Default rate cap at founding | 10% |
| Min tax rate | 0% |
| Revenue rollover | every 7 real-time days |
| Banishment default duration | 30 real-time days |
| MOTD max length | 240 characters |
| `+city home` cooldown | 60 minutes |
| Citizen-only room cap | 30% of non-HQ expansion |
| Eligible founding zones | contested or lawless only |

---

## 16. Player Commands Quick Reference

| Command | Syntax | Who |
|---|---|---|
| `+city found` | `+city found <name>` | Org leader (rank 5) |
| `+city dissolve` | `+city dissolve <name>` | Founder |
| `+city claim` | `+city claim <direction\|room_id>` | Org leader (rank 5) |
| `+city release` | `+city release [room_id]` | Mayor or Founder |
| `+city info` | `+city info [name]` | Anyone |
| `+city list` | `+city list` | Anyone |
| `+city map` | `+city map` | Citizens (own city) |
| `+city citizens` | `+city citizens` | Mayor or Founder |
| `+city motd` | `+city motd <text>` | Mayor or Founder |
| `+city mayor` | `+city mayor <player>` | Founder |
| `+city guest add` | `+city guest add <player>` | Mayor or Founder |
| `+city guest remove` | `+city guest remove <player>` | Mayor or Founder |
| `+city banish` | `+city banish <player> [reason]` | Mayor or Founder |
| `+city unbanish` | `+city unbanish <player>` | Mayor or Founder |
| `+city citizenroom` | `+city citizenroom on\|off` | Mayor or Founder |
| `+city tax view` | `+city tax view` | Citizens |
| `+city tax set` | `+city tax set <decimal>` | Mayor or Founder |
| `+city tax ratecap` | `+city tax ratecap <decimal>` | Founder |
| `+city home` | `+city home` | Citizens |
| `+city guards` | `+city guards` | Mayor or Founder (planned feature) |

---

## 17. A Final Word — Why Cities

The player city system exists because organizations needed something to grow into.

A small faction has missions, kudos, RP, a couple of HQ rooms. That's the early game. A medium faction has a tier-3 or 4 HQ, some influence, regular operations. That's the mid-game. The late-game, before cities existed, was: keep doing the mid-game with more credits. Boring.

A city changes that. Now the late-game has a real artifact — a *place* that exists because you built it, that other players can see on the map, that has your name attached, that generates passive income, that gives your members public benefits, that requires governance, that produces political theater (the banishments, the guest lists, the tax rate debates).

It's also the system that makes contested and lawless zones playable as serious territory. Without cities, those zones are just dangerous areas where short-term scrums happen. With cities, they're places where small disciplined factions can build a citadel and project power outward. The Falleen Syndicate splinter in the Vertical Bazaar isn't just running missions out of a hideout — they're running missions out of *Velvet District*, the place everyone in Nar Shaddaa knows.

The system is **deliberately slow.** Founding is expensive. Expansion is rate-limited. The 24-hour cooldown means cities can't just spring up overnight; they have to be planned and committed-to. This is the right shape. Cities are the kind of structure that should take real time and real organizational discipline to bring into being, because once they exist, they exist as features of the world — visible to everyone, persistent across sessions, and worth fighting over.

If you're an org leader thinking about founding one: you're probably not ready yet. Almost nobody is. The orgs that succeed are the ones who built up to it, then waited a little longer, then founded once everything was clearly in place. The hardest part isn't the rules; it's the patience.

---

*End of Guide #12 — Player Cities*
