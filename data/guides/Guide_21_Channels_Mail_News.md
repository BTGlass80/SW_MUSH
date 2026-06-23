---
category: community
order: 3
summary: "Public channels, private mail, in-game news. How players talk to each other and stay informed."
tags: ["channels", "mail", "news", "communication", "chat", "message"]
---

# Channels, Mail & News

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.1**

---

## How to Read This Guide

This guide covers the **communication infrastructure** of the game — how players talk to each other across rooms, planets, and factions; how they send persistent messages that survive logout; and how they read the galaxy's news. Three subsystems: channels (real-time chat), mail (persistent messages), and news (world-event bulletins).

These are the social plumbing. You'll touch all three regularly. If you only have ten minutes, read **§1 The Communication Layers** and **§3 Channels in Practice**. Channels are how most cross-room communication happens; the rest is structural depth.

*Version 1.1 — every command, syntax, and number reconciled against the live engine: `page` requires `=`, custom frequencies are whole numbers 1–9999, `comlink` reaches all online characters, mail recipients are space-separated, and the world-event effects are stated as the engine actually applies them.*

---

## 1. The Communication Layers

Nine communication layers, from intimate to galactic:

| Layer | Scope | Latency | Lifespan |
|---|---|---|---|
| **`say`** | Same room | Instant | Scene log only |
| **`tt`** (table-talk) | Same place within room (Guide #20) | Instant | Scene log only |
| **`page`** | Specific player | Instant | None (ephemeral) |
| **`comlink`** | Galaxy-wide IC | Instant | None |
| **`fcomm`** | Faction-wide IC | Instant | None |
| **`commfreq`** | Custom frequency | Instant | None |
| **`ooc`** | Server-wide OOC | Instant | None |
| **`@mail`** | One or more players | Asynchronous | Persistent |
| **`+news`** | World bulletin | Asynchronous | Persistent |

Each has its purpose. **`say`** is in-person conversation. **`page`** is one-on-one whisper (always private). **`comlink`** is in-character comlink voice — your character speaking into their comlink for *every online character* to hear; treat it as an open galaxy-wide frequency (it is not planet-scoped). **`fcomm`** is your faction's internal channel. **`ooc`** is server-wide chitchat between players (not characters). **`@mail`** is asynchronous letters that persist until the recipient reads them. **`+news`** is the world bulletin showing recent Director-driven events.

The right choice depends on **who you want to reach** and **whether it should be IC or OOC**.

---

## 2. Saying Things

### `say` — Same-room speech (IC)

```
say <message>            (alias: ")
" <message>
```

Heard by everyone in your current room. The most basic form of in-character speech. Use this for in-person conversation; the scene log captures it.

### `tt` — Table-talk (place-only speech, IC)

```
tt <message>
```

If you're sitting at a place (Guide #20), `tt` is heard only by others at the same place. Lets you have private conversation at a booth or table while the rest of the room hums along.

### `page` — Private whisper (IC or OOC)

```
page <player> = <message>                (alias: p)
page <player1> <player2> = <message>     — multiple recipients
page <message>                           — re-page your last target
page <player> = :waves                   — pose form (": " / "; ")
```

A direct, private message — note the **`=`** between the target(s) and the text. It reaches the named player(s) wherever they are in the world. List several recipients **space-separated** before the `=`. After your first page, a bare `page <message>` re-pages whoever you last paged. Begin the message with `:` or `;` to pose it ("From afar, Trill waves."). If a target is idle, you're told how long.

Often used IC for comlink-style "your character whispers to mine"; often used OOC for "OOC: hey, let me know when you're back."

Pages are **ephemeral** — they go to the screen and disappear; there's no persistent log. If you want a message to stick, use `@mail`.

---

## 3. Channels in Practice

The channel system handles **real-time IC and OOC chat across distance**. Five named channels exist, plus custom-tunable frequencies.

### Named channels

| Channel | Mode | Scope | Use |
|---|---|---|---|
| **`ooc`** | OOC | Server-wide | All player chitchat |
| **`newbie`** | OOC | Server-wide | New-player help (alias for ooc) |
| **`comlink`** (`cl`) | IC | Galaxy-wide (all online) | Cross-room comlink conversation |
| **`fcomm`** (`fc`) | IC | Faction-wide | Faction internal channel |
| **`commfreq`** (`cf`) | IC | Custom frequency | Tuned-frequency comm |

### `ooc` — Server-wide OOC

```
ooc <message>          (aliases: newbie, oocsay)
```

Heard by every online player. Use for:
- Asking for help with commands.
- Coordinating schedules ("anyone want to RP at 8 PM tonight?").
- General community chitchat.
- Welcoming new arrivals.

**`newbie`** is the same channel — designated as the new-player help channel. Some servers culturally split: routine OOC on `ooc`, help questions on `newbie`. They show up the same way regardless.

OOC speech is bracketed clearly in display:

```
[OOC] Trill: Anyone know how to start a scene?
```

The brackets and prefix make OOC unambiguous from in-character speech.

### `comlink` — Galaxy-wide IC

```
comlink <message>      (alias: cl)
```

Your character speaks into their comlink. **Every online character** hears the transmission — comlink is the in-character broadcast channel. Cross-room (and currently cross-planet): you don't have to be anywhere near your conversation partner.

Common uses:
- Coordinating with allies in different rooms.
- Asking around the galaxy for someone.
- IC "broadcast" announcements that aren't faction-secret.

```
[Comlink] Trill: Anyone seen Mara recently? I need to talk to her about the convoy.
```

The comlink transmission is **public** — Republic, CIS, Hutt, neutral, everyone online hears it, and an enemy slicer running an intercept (Guide #22) can catch fragments. Treat it as the IC equivalent of an open radio frequency. Sensitive operational chatter shouldn't go here.

### `fcomm` — Faction-internal IC

```
fcomm <message>        (alias: fc)
```

Heard only by other members of your faction. The faction's internal communication channel. Useful for:
- Coordinating faction operations.
- Discussing faction-internal matters.
- Operational chatter that shouldn't go on the comlink.

```
[Republic] Trill: All units, status report.
```

The channel announces your faction prefix so members know which faction's channel is being used. Players outside the faction don't see the message at all.

**The intercept system** (Guide #22) can catch fragments of faction-channel speech. A skilled enemy spy can eavesdrop on `fcomm`. Sensitive operations should use private rooms or trusted couriers, not just `fcomm`.

### `commfreq` — Custom frequencies

```
commfreq <freq> <message>     (alias: cf)
tune <freq>                   — Tune into a frequency
untune <freq>                 — Untune
freqs                         — List your tuned frequencies
```

For private groups that aren't aligned to a faction, custom frequencies let you create your own channel on **any whole number from 1 to 9999**. Anyone can tune into a frequency by knowing its number; communication on that frequency goes only to tuned listeners. (You must `tune` a frequency before you can transmit on it.)

Frequencies are **shared knowledge among tuned players** — there's no ownership. If you tell someone "tune frequency 1138," they can listen. If they tell their friend "tune frequency 1138," that friend can also listen.

Common uses:
- A small group of allies coordinating across factions.
- Private business channels for traders or smugglers.
- One-shot operational channels for a specific mission.

```
cf 1138 Position is secured. Holding for instructions.
```

### `channels` — Channel overview

```
channels (or +channels)
```

Shows the channels available to you, your current faction, any custom frequencies you're tuned to, and the online player count.

### `+who` — Online players

```
+who
```

Lists currently online players with their locations and statuses. Useful for finding who's around to interact with. (It carries the `+` prefix because it's an out-of-character meta command — the same convention as `+channels`, `+news`, and `+freqs`.)

---

## 4. The Mail System

Mail is **persistent player-to-player messaging**. Messages survive logout, accumulate in the recipient's inbox, and are flagged as read/unread.

### Composing and sending mail

The standard compose flow:

```
@mail <player> = <subject>          — Start a compose session
                                      (then enter the body line by line)
- (dash on a blank line)            — Send it
@mail/send                          — Alternative send command
~q (on its own line)                — Cancel the draft
@mail/quick <player>/<subj> = <body>  — Quick one-line send
```

A typical compose session:

```
@mail Mara = Convoy investigation update
You: After last night's eavesdrop, I have more.
You: Three names came up: Captain Voss, a Twi'lek
You: smuggler called Renn, and someone they called
You: "the broker."
You: Need to meet in person. Cantina booth, your call.
You: -

[Mail sent to Mara.]
```

The blank-dash line ends the compose; the message is sent. (A very long letter is truncated at 8,000 characters when it sends — generous, but not unlimited.)

**Multiple recipients** are listed **space-separated** before the `=`:

```
@mail Mara Garth = Convoy investigation update
```

All listed recipients get the message. Their replies go back to the sender alone.

### Reading mail

```
@mail                       — List your inbox
@mail/read <#>              — Read message #N
@mail/unread                — Show unread count
@mail/sent                  — Show messages you've sent
```

Your inbox shows unread messages first, then read ones. Each message shows sender, subject, and timestamp. You read by number.

### Replying and forwarding

```
@mail/reply <#> [= <text>]            — Reply to message #N
@mail/forward <#> = <player>          — Forward to another player
```

Reply starts a new compose with the original subject prefixed `RE:`. Forward sends the original message to a new recipient.

### Cleaning up

```
@mail/delete <#|all>          — Mark message(s) for deletion
@mail/purge                   — Permanently delete marked messages
```

Two-stage deletion: first mark, then purge. Lets you recover from "oops, I meant to keep that" before final commitment.

### Login notifications

When you log in, the system tells you how many unread messages you have:

```
[MAIL] You have 3 unread messages.
```

This is your cue to `@mail` and check the inbox.

### Mail use cases

- **Asynchronous coordination.** "Will you be online tomorrow at 8?"
- **Intel reports.** Composing a multi-paragraph report and sending it to a faction handler.
- **Long-distance RP.** A letter between distant characters.
- **Business proposals.** "I'd like to discuss an exclusive cargo arrangement."
- **Records keeping.** A character keeps important correspondence in their archived mail.

For active players who play 3-5 hours per week in scattered sessions, mail is the glue that keeps multi-session arcs coordinated.

---

## 5. The News System

```
+news (or news)
```

Shows the **galactic news bulletin** — the 10 most recent world events as recorded in the Director's event log. Updates dynamically as the world changes.

A typical `+news` display:

```
=== Mos Eisley Galactic News Network ===

  • 2 minutes ago:    Republic checkpoint set up at Mos Eisley spaceport.
                      All travelers subject to inspection.

  • 15 minutes ago:   Pirate surge reported across the Outer Rim.
                      Smugglers urged to take precautions.

  • 1 hour ago:       Cantina brawl breaks out at Mos Eisley.
                      Local security responding.

  • 3 hours ago:      Distress signal detected from Kessel system.
                      Source unconfirmed.

  • yesterday:        Trade boom hits Coruscant trade hub.
                      Demand for moisture-farming equipment spikes.

  • 2 days ago:       Hutt auction announced — rare relics on offer.
                      Bidding opens at Mos Eisley cantina.
```

Each entry shows a relative-time stamp ("just now," "X minutes ago," "X hours ago," "yesterday," "X days ago"), a headline, and a brief description.

### Why news matters

The news bulletin is your window into **what's happening in the world**. Events listed in `+news` typically have real mechanical effects:

- **Republic checkpoint**: customs scans intensify at the affected spaceport (see [Security Zones](#/guide/security-zones) — patrol risk on transit increases).
- **Pirate surge**: pirate encounters spawn ~3× as often in deep space (Guide #24).
- **Cantina brawl**: hostile brawl encounters spike in that cantina (Guide #24).
- **Distress signal**: the mission board pays a distress bonus while the signal is live (Guide #6).
- **Trade boom**: vendor sell prices rise 25% in the affected zone for an hour — sell goods there for more (Guide #6).
- **Sandstorm**: a −3 penalty to Perception and ranged attacks in the affected zone (−2D in a gravel storm, −3D in a sandwhirl; Guide #24).

Reading the news before you act on a plan is **smart spacing**. If there's a Republic crackdown on Mos Eisley spaceport, maybe defer your contraband run. If there's a trade boom on Coruscant, maybe go sell your stockpile there before the convoy departs.

### How the news populates

The Director AI generates news entries when:
- **Faction influence crosses thresholds** (e.g., Republic dominance reaching lockdown level).
- **World events activate** (17 standard event types: security crackdown, security checkpoint, bounty surge, merchant arrival, sandstorm, gravel storm, sandwhirl, cantina brawl, distress signal, pirate surge, Hutt auction, krayt sighting, separatist agitation, trade boom, intelligence thaw, spice demand, flood).
- **Story events fire** (the era milestone system).
- **Player actions** with global narrative significance (rare — usually faction-driven).

The Director writes the headlines and descriptions. They reflect actual current state of the game world; they're not just flavor text.

---

## 6. The Galactic News Network in Practice

A worked example. You log in for an evening session. The news bulletin shows:

```
+news
=== Mos Eisley Galactic News Network ===

  • just now:         Sandstorm sweeping the Outer Rim Tatooine.
                      Travel difficult in deep desert.

  • 12 minutes ago:   Hutt Auction begins at Mos Eisley cantina.
                      Rare goods on the block.

  • 1 hour ago:       Republic crackdown declared.
                      Patrols on Tatooine doubled.
```

Three current world events. You parse:

- **Sandstorm** in the Outer Rim Tatooine: your planned hunt in the Dune Sea (lawless wilderness) just got harder. Move it to tomorrow or push through the −3 Perception and ranged-attack penalties.
- **Hutt Auction** at the cantina: there are rare goods being sold for credits. You can bid if you have the wallet. Worth checking out.
- **Republic crackdown** on Tatooine: patrols are doubled. Your contraband run to Mos Eisley has heightened patrol risk. Defer or accept the risk.

You decide: skip the contraband run tonight. Visit the Hutt auction. Save the Dune Sea hunt for next session.

The news shaped your evening. That's the system at its best.

---

## 7. Channel Etiquette

Some norms that emerge across active servers.

### OOC etiquette

- Keep OOC conversation respectful — `ooc` reaches everyone, including new players who may be sensitive.
- Don't out-spoiler in OOC ("Trill and Mara are romantically involved" before they reveal it).
- Don't dump OOC arguments into the channel. Take them to private pages.
- Welcome new arrivals on `ooc` or `newbie`. The community grows when newcomers feel seen.
- Avoid all-caps. Avoid emoji floods.

### Comlink etiquette

- Comlink is **galaxy-wide and IC**. Treat it like an open broadcast channel.
- Don't use comlink to RP intimate scenes — comlink is public.
- Don't spam comlink. The channel has limited attention.
- Sensitive operational coordination should go to `fcomm` or `commfreq`, not `comlink`.

### Faction comm etiquette

- Faction comms are **internal-only**. Don't relay them to non-members.
- Be aware that intercept can catch fragments. Sensitive intel should still go through private channels.
- Respect the faction's culture. Republic fcomm is more formal than Hutt fcomm.

### Page etiquette

- Pages are private but appear in scenes/logs sometimes. Assume they're discoverable.
- Don't page during active scenes unless it's directly relevant ("OOC: are you free after this?").
- Long OOC conversations should move to a dedicated room or off-platform.

---

## 8. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — The newbie OOC ask.** You're a new player. You type `ooc How do I start a scene?` Within a few minutes, three veteran players respond: "Use +scene/start [title] — try it now in your current room!" You try it, it works, you thank them in `ooc`. The community welcomed you.

**Scenario 2 — The cross-room comlink coordination.** Your character, a Republic field agent, needs to coordinate with a friend across town. You `comlink` your location and intent: "Trill: At the spaceport hangars. Standing by for instructions." Your friend, in a separate room, responds: "Mara: Acknowledged. ETA five minutes." The two-room coordination happens fluidly without either of you having to walk to the other.

**Scenario 3 — The faction operations channel.** You're a Hutt Cartel Vigo coordinating a smuggling run. Six members are involved across two rooms. You use `fcomm` for the operation-wide coordination ("Lift in five minutes; we move on Mara's signal"). The conversation is invisible to non-Hutt characters; the operation flows.

**Scenario 4 — The asynchronous letter.** You finished a great cantina scene with a player who plays at very different hours. You compose `@mail` to them: "Last night's scene was excellent. I have a follow-up arc in mind — happy to brainstorm by mail if you're game." They read it the next morning; they reply with their thoughts; the arc starts to take shape across multiple mail exchanges before you ever play another scene together.

**Scenario 5 — The news-driven decision.** You log in. `+news` shows: "Trade boom hits Coruscant trade hub." You realize the stockpile of goods you've been meaning to offload, normally worth about 8,000 cr to sell, now fetches roughly 10,000 cr while the convoy is in (vendor sell prices are up 25% for the hour). You drop everything to make the sale before prices normalize. The news shaped your evening's play; you bank a 2,000-cr bonus you wouldn't have made otherwise.

---

## 9. Player Commands Quick Reference

### Channels (real-time)

| Command | What it does |
|---|---|
| `say <msg>` (or `" <msg>` / `' <msg>`) | Same-room IC speech |
| `tt <msg>` | Place-only IC speech; room hears a muffled version (Guide #20) |
| `page <player> = <msg>` (alias: p) | Private whisper; use `=`, space-separate multiple targets |
| `ooc <msg>` (aliases: newbie, oocsay) | Server-wide OOC |
| `comlink <msg>` (alias: cl) | Galaxy-wide IC (all online) |
| `fcomm <msg>` (alias: fc) | Faction-wide IC |
| `commfreq <freq> <msg>` (alias: cf) | Custom frequency IC |
| `tune <freq>` | Tune into a custom frequency |
| `untune <freq>` | Untune from a frequency |
| `freqs` (or `+freqs`) | List your tuned frequencies |
| `channels` (or `+channels`) | Show channel overview |
| `+who` | List online players |

### Mail (persistent)

| Command | What it does |
|---|---|
| `@mail` | List inbox |
| `@mail <player> = <subject>` | Start composing |
| `@mail/send` (or `-` on blank line) | Send composed message |
| `@mail/read <#>` | Read message |
| `@mail/reply <#> [= <text>]` | Reply to message |
| `@mail/forward <#> = <player>` | Forward message |
| `@mail/delete <#\|all>` | Mark for deletion |
| `@mail/purge` | Permanently delete marked |
| `@mail/unread` | Show unread count |
| `@mail/sent` | Show sent messages |
| `@mail/quick <player>/<subj> = <body>` | Quick one-line send |

### News

| Command | What it does |
|---|---|
| `+news` (or `news`) | Show galactic news bulletin |

---

## 10. Numbers At A Glance

| Quantity | Value |
|---|---|
| Communication layers | 9 (`say`, `tt`, `page`, `comlink`, `fcomm`, `commfreq`, `ooc`, `@mail`, `+news`) |
| Channel scope — `say` | Same room |
| Channel scope — `tt` | Same place within room |
| Channel scope — `comlink` | All online characters (galaxy-wide IC) |
| Channel scope — `fcomm` | Faction-wide |
| Channel scope — `commfreq` | Tuned-frequency listeners |
| Channel scope — `ooc` | Server-wide |
| Custom frequency range | 1–9999 (whole numbers) |
| Mail persistence | Permanent (until the recipient deletes, then purges, it) |
| Mail body cap | 8,000 characters (truncated on send, not rejected) |
| Inbox display | Up to 30 messages, unread first |
| Sent display | Up to 20 messages |
| News bulletin | 10 most recent events |
| Time-ago formatting | "just now" / "X minutes ago" / "1 hour ago" / "X hours ago" / "yesterday" / "X days ago" |
| World event types | 17 (security crackdown/checkpoint, bounty surge, merchant arrival, sandstorm, gravel storm, sandwhirl, cantina brawl, distress signal, pirate surge, Hutt auction, krayt sighting, separatist agitation, trade boom, intelligence thaw, spice demand, flood) |
| Faction prefixes in fcomm | Republic / Separatist / Hutt / Bounty Hunter / Jedi / etc. |
| `+who` displays | Name, species, location, status, worn title |

---

## 11. Common Pitfalls

**1. Using `comlink` for sensitive operational chatter.** Everyone online hears it — and enemy spies can intercept it. Sensitive coordination belongs on `fcomm` (faction-only) or `commfreq` (tuned-only).

**2. Treating `page` as persistent.** Pages disappear from the screen. If you need a message to stick, use `@mail`. If you need it logged, RP it in a scene.

**3. Forgetting to check mail at login.** The "[MAIL] You have N unread messages" notification is your reminder. Acknowledge it.

**4. Spamming `ooc`.** All players see every OOC message. Don't dump long conversations into the channel. Take them to private pages.

**5. Ignoring `+news`.** The news shows what's happening in the world right now. Players who never check it miss the dynamic context that shapes opportunities and risks.

---

## 12. A Final Word

The communication infrastructure of Parsec is what turns the room-graph into a **social network**. Without it, two characters in different rooms couldn't easily interact; the spacer running cargo at Kessel couldn't know what's happening at Mos Eisley; the faction couldn't coordinate operations across planets. With it, the galaxy becomes a connected place where information flows, plans are made, and stories form.

For most players, the communication layers become **invisible infrastructure** — you use `ooc` to chat, `comlink` to coordinate, `@mail` to follow up, `+news` to check the world. The commands are second nature within a few sessions.

For social roleplayers, comms become **the medium of relationship** — long-distance RP through mail, galaxy-wide presence through comlink, faction belonging through fcomm. Characters whose lives play out partly across distance use these systems heavily.

For plotrunners and faction leaders, comms are **the organizational layer** — the fcomm channel where you coordinate, the mail you send to assemble teams, the news bulletin that shapes the world your plot operates in.

If you're starting out: send your first `ooc` greeting. Try `+who` to see who's online. Read `+news`. Send `@mail` to someone interesting. Within a few sessions, the comms layer is just part of how you play. The system rewards engagement — the more you use it, the more connected your character becomes to the wider game world.

---

*End of Guide #21 — Channels, Mail & News*
