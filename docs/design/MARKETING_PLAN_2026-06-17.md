# SW_MUSH — Low-Key Community-First Launch Marketing Plan

**Date:** 2026-06-17
**Author:** Marketing strategist synthesis (from 4 research dossiers: MU* launch landscape, WEG-D6 community, SW fan-game IP risk, text-game retention)
**Posture (Brian's standing decision):** LOW-KEY / community-first / organic-only. No mainstream press, no Hacker News, no Product Hunt, no Steam, no "Show HN," no crowdfunding, no monetization. Visibility + money are the two C&D accelerants — we trade the one-day viral spike for slow, durable niche growth.

> **How to use this doc:** Sections 1–6 are the strategy + an execute-in-order checklist. Section 7 is copy-paste-ready draft text. You (Brian) are the producer for everything unless noted. This is a checklist, not theory — work top to bottom.

---

## 0. The two non-negotiables (read first)

These two rules override every tactic below. Every casualty in the research (Apeiron, Galaxy in Turmoil, Lightsaber Academy) broke one of them; every survivor (SWGEmu, Star Wars Combine, the 1990s Star Wars MUSHes) kept both.

1. **Zero monetization, ever.** No sales, no Patreon, no donations, no "support the dev," no ads, no merch, no paid early access. (If hosting ever forces it: cap donations transparently at *documented server cost only*, SWGEmu-style — never personal profit. Default to none.)
2. **Stay inside the niche.** Promote ONLY in MU*/MUD/MUSH venues and WEG-D6 fan venues. Never a mainstream surface. Enforcement tracks visibility — so staying small *is* the legal strategy, not a constraint on it.

---

## 1. POSITIONING

### One-line positioning statement
> A free, browser-playable roleplaying galaxy that brings the authentic West End Games D6 ruleset to the Clone Wars era — the era WEG was never licensed to publish — with a living, AI-driven galaxy that reacts to what players do.

### 3 tagline options
1. **"The Clone Wars, in authentic WEG D6 — playable in your browser, free."** *(lead with the gap + the barrier-remover; this is the workhorse)*
2. **"A living Star Wars galaxy, run on real D6 dice. No download. No cost."** *(leads with the Director-AI "living galaxy" + free/browser)*
3. **"Roll the Wild Die in the Clone Wars."** *(insider tagline for the D6 crowd — the Wild Die signals fidelity to people who know the system)*

> Use tagline #1 on the landing-page hero and MUD-directory listings. Use #2 in the Discord/Grapevine one-liner. Use #3 only inside the WEG-D6 community (Rancor Pit, the D6 Discord), where "Wild Die" lands as a credibility signal.

### 30-second elevator pitch
> SW_MUSH is a free, browser-playable text roleplaying game set in the Star Wars galaxy during the Clone Wars. It runs on the authentic West End Games D6 *Revised & Expanded* rules — real dice codes, the Wild Die, control/sense/alter Force skills — not a loose homage. It fills a genuine gap: WEG was never licensed to publish the Clone Wars era, so this is content that never officially existed. You play in your browser with no download (telnet's there for purists), and a "living galaxy" Director AI drives macro-storytelling and NPC dialogue that reacts to player actions. It's a non-commercial solo passion project — free, no catch.

**Three stacked messages, in priority order (use this order everywhere):**
1. **Fidelity** — real WEG R&E mechanics (dice codes, Wild Die, control/sense/alter). This is what earns credibility with the D6 crowd.
2. **The Clone Wars gap** — the era WEG couldn't publish; a specific, recognized hole this fills.
3. **Free + browser-playable** — barrier-remover vs. classic MUDs, and the free/non-commercial framing *doubles as the IP-safety signal*.

---

## 2. AUDIENCE BEACHHEADS (ranked, most-likely-to-convert first)

The single biggest strategic call from the research: **the WEG-D6 *tabletop* community converts better than the generic MUD crowd**, because they already (a) love the exact ruleset you built on, (b) recognize the Clone Wars gap as novel, and (c) are themselves quietly IP-cautious, so your posture matches theirs. Lead there.

| # | Beachhead | Why it's ranked here | Where exactly |
|---|-----------|----------------------|---------------|
| **1** | **The Rancor Pit forum** (rancorpit.com/forums) | THE flagship WEG-D6 venue — ~2,350 members, ~200k posts, posting *today*. Has a *sanctioned* home for "come play this online game": the **Community Resources → Gaming Groups** and **Play-by-Post / Online Games** sections. Highest authenticity + highest intent. A prior "D6 Online" game wound down → there's an open seat. | Gaming Groups + Play-by-Post subforums (NOT the rules forums) |
| **2** | **Star Wars D6 Discord** (~1,284 members) | The live, modern-tooling D6 crowd — the real-time complement to the older forum demographic. Welcoming, growing. | Invite `discord.com/invite/Y6MraUJ` — share in the appropriate channel after participating |
| **3** | **r/MUD** (Reddit) | The single primary *MUD-side* announcement venue, and it welcomes RP/MUSH games. Feeds the main "Multi User Dungeon" Discord. | One `Promotion`-flaired post; obey 1-self-promo-per-7-days |
| **4** | **MU Soapbox** (musoapbox.net) | The MUSH/RP community's forum, socially distinct from the hack-and-slash MUD crowd — your *actual* peer group. Has a New-Games announcement board. | The game-announcement / Current Games board |
| **5** | **WEG-D6 Facebook groups** | The older / Facebook-native slice of the same fanbase. "D6 Holocron", "WEG SW D6 RPG Discussion", "West End Games SW RPG Books". | Post in-group after reading each group's rules |
| **6** | **The main "Multi User Dungeon" Discord** | Real-time center of gravity for MUDs now that IRC is dead; overlaps heavily with r/MUD. | `#advertising` / promo channel only — be a person first |

**Deliberately low priority / skip:** RPGGeek's WEG family (dormant — catalog, not a community; ~29 fans, no threads), OpenD6 community (adjacent generic-D6, not core WEG), Mudlet default-game inclusion (high-effort integration, web-first gains little — defer until you have a telnet base), the $10/mo MudVerse banner (skip entirely for organic).

**r/swrpg caveat (verify before posting):** it skews Fantasy Flight Games, not D6; a dedicated r/swd6 may or may not be active. Do a 15-minute visit-in-person check of scope/rules and member counts before relying on either. Lead with D6-authenticity to find your people if you do post.

---

## 3. CHANNEL PLAN (named venues + how to list on each)

Two buckets: **directories** (set-and-forget, SEO/discoverability, mostly automated once MSSP ships) and **community posts** (hand-crafted, one-time, cadence-gated). Do the directories first so your links resolve before you announce.

### A. Technical / directory listings (do these FIRST)

| Venue | How to list | Priority |
|-------|-------------|----------|
| **Grapevine** (grapevine.haus) | **Highest-leverage.** Register an account → create a game → get Client ID/Secret → connect over WebSocket (`wss://grapevine.haus/socket`). You get a *free hosted web client* with GMCP gauges, cross-game chat, an online-player count, and an **Events board** that surfaces your live events on their homepage. Requires UTF-8 at the server level (you already encode UTF-8 in the telnet handler — verify end-to-end). | **1** |
| **MudVerse** (mudverse.com) | Free. Email `brendan@withmorehope.org` (or "Add Your Game"). You get a detailed page — pick features, set RP-enforcement level, upload a banner. It has a **"Star Wars" theme filter** and RP-level filters, and supports MSSP auto-stats. Skip the optional $10/mo banner. | **2** |
| **The Mud Connector / TMC** (mudconnect.com) | Free web form (`mud_entry.html`), admin-approved, appears in ~a week. Legacy SEO/credibility. Treat as set-and-forget — slow throughput, not a traffic driver. | **3** |
| **Top Mud Sites** (topmudsites.com) | Live (verified 2025). Vote-ranked directory + a vote widget you can embed. Forum activity is low; value is the ranked listing + votes, not discussion. | **4** |
| **MUSHcode.com MUSH/MUX list** | Submit via the `/SubmitMush` form. ~250+ games, telnet-linked, monitors UP/DOWN. | **5** |
| **Amberyl's Automated MUSH List** (clock.org/muds/auto.html) | Auto-pings games every ~120 min — getting listed is mostly automatic once reachable. | **5** |
| **MSSP auto-indexers** (MUDStats, BestMUDs/mudlistings, GameScry, MUDHalla) | **No manual submission** — implement the **MSSP** protocol and these index you automatically. | auto |

> **Single highest-leverage technical task:** implement **MSSP** on the telnet server. The codebase currently negotiates only NAWS + TTYPE (verified in `server/telnet_handler.py`) — **MSSP is NOT yet implemented.** Shipping it auto-discovers you across MudVerse, MUDStats, and several others with zero per-site effort. Optionally add GMCP to unlock Grapevine's web-client gauges. (This is an engineering pre-req, flagged here so it lands before launch — log it in TODO.json if not already tracked.)

### B. Community announcement posts (after directories + Discord are live)

- **r/MUD** — one post, `Promotion` flair, max once / 7 days. Tailor the copy; don't copy-paste.
- **MU Soapbox** — game-announcement board, emphasize RP depth (D6 mechanics, factions, Director AI, web client).
- **The "Multi User Dungeon" Discord** — intro yourself as a person in the promo channel, then the link.
- **Rancor Pit** + **Star Wars D6 Discord** — see Section 2; these are *earn-then-mention* (Section 6), not drive-by drops.

### C. EXPLICITLY EXCLUDED channels (and why)

| Excluded channel | Why it's out |
|------------------|--------------|
| **Hacker News / "Show HN"** | Front-page virality = exactly the mainstream visibility that summons a C&D. Also an etiquette mismatch for the niche. |
| **Product Hunt** | Same — a launch-spike surface built for visibility. The generic waitlist playbooks recommend it; we explicitly skip it. |
| **Mainstream gaming press** (Kotaku, PC Gamer, Polygon, Destructoid, etc.) | High-profile coverage is a documented C&D trigger (Galaxy in Turmoil's strike followed press + a Steam deal). |
| **Steam / itch.io / app stores / any distribution platform** | A commercial-platform move is the brightest tripwire in the data. We are browser/telnet only. |
| **Large general subreddits** (r/gaming, r/StarWars, r/pcgaming) | Front-page-scale reach = the visibility risk, plus a self-promo etiquette mismatch. |
| **Crowdfunding** (Kickstarter, GoFundMe, Patreon) | Money = the #1 C&D accelerant. Non-negotiable: zero. |
| **Twitter/X virality, TikTok, influencer pushes** | Any high-virality channel courts the spike we're avoiding. Word-of-mouth inside the niche only. |

---

## 4. IP-RISK GUARDRAILS (concrete dos / don'ts)

Grounded in the enforcement pattern: **visibility + monetization + trademark-in-the-name** are the three sharp edges. Disclaimers are good-faith *framing*, not legal armor (Lightsaber Academy had a disclaimer and was still sued) — but they reduce escalation odds, so we ship one anyway.

### Naming & branding
- **DO** use an original, evocative public-facing name + domain + logo (clone-era / galaxy flavor *without* the trademarked marks). "SW_MUSH" is fine as an internal/repo name; **pick a non-trademarked public title before the landing page goes live.**
- **DON'T** put **"Star Wars", "Jedi", "The Force", "Lightsaber", "Droids", "X-Wing"**, character names, or any official logo in the project **name, domain, or logo**. These are live trademarks — the cheapest thing for Lucasfilm to enforce (false designation of origin / dilution).
- **DO** describe the setting *in prose* ("a fan game set in the Star Wars galaxy during the Clone Wars"). Prose description ≠ branding with the mark.

### Money
- **DON'T** monetize in any form (repeat of §0: no sales, Patreon, donations, ads, merch, paid tiers, crowdfunding).
- **DO**, if hosting ever forces it, cap donations transparently at *documented server cost only*, never "support the dev."

### Assets
- **DO** keep 100% original assets — your custom code, original art/audio, and WEG-D6-derived text re-stat-from-scratch (the era-cleanness invariant already enforces this: no Imperial/Empire/Rebel/TIE in production strings; canonical Clone Wars figures never appear as open-world NPCs).
- **DON'T** ship any ripped sprite, model, music, voice line, or official logo. Recognizable copied assets were common to every struck-down project.

### Disclaimer (ship on landing, about, AND login)
- **DO** display the fan disclaimer prominently on the **landing page, About page, and the login/connect screen.** Draft text in §7. (Verified: **no disclaimer currently exists in `server/web_client.py`** — this is a real pre-launch task.)
- **DON'T** treat the disclaimer as protection — it's framing only.
- **DON'T** claim or imply any license, endorsement, partnership, or affiliation with Lucasfilm / Disney / EA anywhere.

### Where NOT to post
- **DON'T** post anywhere in Section 3C. Visibility is the trigger.
- **DON'T** link copyrighted PDFs / bootleg material anywhere (Rancor Pit explicitly bans this — and it's a needless flag).

### The fallback (architect now, hope never to use)
- **DO** keep the setting data-driven (era.yaml, world YAML, dice content) so a single "de-Star-Wars" pass could reskin to a generic clone-era space setting. Galaxy in Turmoil survived by stripping all SW references and continuing as original sci-fi.
- **DO** comply fast and quietly if ever contacted: take it down / rename, don't publicize a fight, **never file anything against them.** The one party that got *sued* (not just C&D'd) had escalated by filing his own trademark.

---

## 5. ASSETS NEEDED (production checklist)

| # | Asset | What it is / spec | Producer |
|---|-------|-------------------|----------|
| 1 | **Public project name + domain + logo** | Original, non-trademarked. Blocks the landing page — do this first. | Brian (decision) |
| 2 | **Landing page — hero** | Passes the 5-second test above the fold: ~7-word benefit headline + one subheadline answering *what / who / next*. Headline draft in §7. | Brian (+ existing web stack) |
| 3 | **Hero GIF/clip** | 5–10s loop of the *actual web client mid-play*: a room description → one combat round → the area map. **Single highest-leverage asset for a text game** — refutes "text = boring" instantly. | Brian (screen-capture) |
| 4 | **Primary CTA** | One button: **"Play in browser."** Above the fold AND repeated after the value sections / at page end. Thumb-friendly on mobile. | Brian |
| 5 | **Secondary CTA** | A *smaller* Discord-invite link/button — NOT co-equal with Play. Don't split attention between two equal buttons. | Brian |
| 6 | **Fan disclaimer block** | Ships on landing + about + login. Text in §7. | Brian |
| 7 | **Game Discord server** | Channels: `#announcements`, `#newbie-help` (bridged to the in-game help channel), `#general`, `#feedback`, `#events`, `#insiders` (private). Stand it up BEFORE announcing anywhere. **Only open channels you can keep alive** — a neglected Discord signals a dead project. | Brian |
| 8 | **FAQ / "What is this" blurb** | Short site blurb (§7) + an FAQ covering: is it free? (yes) do I need to install? (no) is it official? (no — fan project) what ruleset? (WEG D6 R&E) what era? (Clone Wars) telnet host:port for purists. | Brian |
| 9 | **Community-post kit** | Tailored variants of the announcement (§7) for r/MUD, MU Soapbox, Rancor Pit, the two Discords — NOT copy-paste-identical. Each names the venue's own norms. | Brian (from §7 templates) |
| 10 | **In-game onboarding** | Tutorial **< 5 min, skippable, contextual** (movement → one interaction → primary goal). A guaranteed **early win in the first ~5 min** (win the first skill check / combat round) with a visible reward + celebratory line. A **"Quick Start" preset archetype** path alongside the full WEG-D6 builder (verify presets are real producers — no phantom archetypes). Searchable, current help files. | Brian (engine work) |
| 11 | **MSSP (+ optional GMCP)** | Telnet protocol support — auto-discoverability + Grapevine gauges. Pre-req for §3A. Currently unimplemented. | Brian (engine work) |
| 12 | **Grapevine + MudVerse listing pages** | Banner image for MudVerse; game registration on both. | Brian |

---

## 6. PRE-LAUNCH → LAUNCH → POST-LAUNCH PLAYBOOK

> Realistic pace for organic, niche-only growth: ~1,000 signups over 4–8 weeks of focused effort is a *good* outcome here. Don't chase a spike. The highest-leverage work is **first-session quality** — re-acquiring a churned player costs ~5–10x more than not losing them.

### PHASE 0 — Foundation (engine + assets; before any outreach)
- [ ] Pick the original public name + domain + logo (§5.1).
- [ ] Implement **MSSP** on the telnet server (§3A); verify UTF-8 end-to-end for Grapevine.
- [ ] Cap the tutorial at < 5 min, skippable + contextual; engineer the early win; ship the Quick Start preset path (§5.10).
- [ ] Make help files searchable + current.
- [ ] Build the landing page (hero, GIF, single CTA, secondary Discord link) + ship the disclaimer on landing/about/login.
- [ ] Stand up the game Discord with the channel set; bridge `#newbie-help` to the in-game help channel.

### PHASE 1 — Pre-launch community (start EARLY; 6 months is "too late" for real momentum)
- [ ] **Become a participating member first, promoter second.** On Rancor Pit + the D6 Discord: register, post genuinely useful D6 content (your Clone Wars-era D6 stat conversions, a mechanics writeup) — the community already hand-converts Clone Wars content, so yours is welcome and showcases fidelity. Earn ~9 value-adding posts per 1 promo.
- [ ] **Build in public, ~weekly, inside niche venues only.** Post the *messy middle* — failed prototypes, design reversals, Director-AI experiments. Visibly **close the loop**: "You asked about X; here's what changed." (Keep this in niche Discords/forums — NOT high-visibility channels.)
- [ ] **Recruit ~8–12 insider testers** across diverse player types: special Discord role, private `#insiders` channel, early access. Frame as "one of the first to play" — insider framing drives launch-day advocacy.
- [ ] Wire up the directories that don't require launch: Grapevine game registration, MudVerse listing.
- [ ] (Optional) light referral loop: reward only *confirmed* signups, public leaderboard.

### PHASE 2 — Soft launch (closed alpha/beta — prove the loop before scaling)
- [ ] Run closed tests with the insiders in **short, bounded windows** (a weekend, or up to a week) to avoid solo-dev burnout, with a dedicated feedback channel.
- [ ] **Instrument first-session signals:** tutorial (FTUE) completion rate, Day-0 playtime, repeat sessions, the **D1→D7 retention curve** (its shape predicts long-term retention — you don't need 60-day tests).
- [ ] **Fix the single biggest first-session drop-off**, then re-test. Repeat (Build-Measure-Learn).
- [ ] Surface "you shaped this" moments — testers who feel heard become unpaid marketers.

### PHASE 3 — Community announcement wave (only after the loop is proven fun)
Stagger over ~1–2 weeks; tailor each post; obey each venue's cadence:
- [ ] Submit TMC + Top Mud Sites + MUSHcode + Amberyl directory forms (set-and-forget).
- [ ] **Rancor Pit** — post in Gaming Groups / Play-by-Post (you've already earned standing). Lead with the Clone Wars gap + fidelity.
- [ ] **Star Wars D6 Discord** — share in the appropriate channel.
- [ ] **MU Soapbox** game board — emphasize RP depth.
- [ ] **r/MUD** — one `Promotion`-flaired post (problem/value-led, not "I'm launching").
- [ ] **"Multi User Dungeon" Discord** — promo channel, person-first.
- [ ] **WEG-D6 Facebook groups** — after reading each group's rules.
- [ ] Use Grapevine's **Events board** to surface live in-game events to the wider MU* network.
- [ ] **Cross-promote** with other game admins (shout out each other's events) — the welcomed norm that compounds reach without spamming.

### PHASE 4 — Post-launch retention (the real game)
- [ ] **Live content cadence is itself a Day-7 retention lever** — repetitiveness is the main ~Day-7 churn driver. Keep shipping.
- [ ] Keep `#newbie-help` warm — staff/owner models a welcoming tone (cold/toxic first contact is a named churn driver).
- [ ] Continue close-the-loop devlogs weekly.
- [ ] Judge the landing page against benchmark: 5–15% visitor→signup is healthy; **below 5%** = fix the headline/hero/social-proof; above 20% = very warm traffic.

---

## 7. DRAFT ASSETS (copy-paste-ready)

> Tailor each before posting — identical copy-paste across venues is the fastest way to get ignored or flagged. These are starting points. **Replace `[GAME NAME]` and `[gamename.example]` with the original non-trademarked name + domain once chosen, and fill in the real web-client URL, telnet host:port, and Discord invite.**

### 7a. Respectful r/MUD-style launch announcement post

> **Title:** `[Promotion] [GAME NAME] — a free, browser-playable WEG D6 roleplaying galaxy set in the Clone Wars`
>
> Hi r/MUD — I'm Brian, the solo developer, and after a long build I've opened **[GAME NAME]** for players. It's a free, browser-playable text RP game set in the Star Wars galaxy during the Clone Wars era (~20 BBY), built on the authentic **West End Games D6 Revised & Expanded** ruleset.
>
> The hook, if you know the system: WEG was never licensed to publish the Clone Wars era, so this is a setting that never officially existed in D6 — re-stat from scratch against the original rules (real dice codes, the Wild Die, control/sense/alter Force skills). And it's **web-first**: you play in your browser with no client install (telnet's there for purists who want it).
>
> What's in it:
> - **Authentic WEG R&E mechanics** — dice codes, Wild Die, the real Force-skill tree, out-of-combat skill checks and ground/space combat
> - **Clone Wars era setting** — the gap WEG couldn't publish
> - **A "living galaxy" Director AI** — macro-storytelling + NPC dialogue that reacts to player actions
> - **Deep systems** — crafting, factions, territory control, smuggling, player shops/cities, Jedi/Force progression
> - **Browser-playable, no download** — and **completely free / non-commercial** (it's an unlicensed fan project)
> - Actively developed by one person who's a fellow D6 fan — feedback genuinely shapes it
>
> **Play in browser:** `https://[gamename.example]`
> **Telnet (purists):** `[host]:[port]`
> **Discord (newbie help + events):** `[invite]`
> **Listing:** `[Grapevine / MudVerse link]`
>
> It's live and playable right now, not vaporware. It's an unofficial, non-commercial fan project — not affiliated with or endorsed by Lucasfilm/Disney. Happy to answer anything in the comments.

*(For Rancor Pit / the D6 Discord, re-lead with the Clone Wars gap + the Wild Die and drop the MUD-jargon; for MU Soapbox, lead with RP depth, consent/PvP norms, and staff responsiveness.)*

### 7b. Short site "what is this" blurb

> **[GAME NAME]** is a free, browser-playable roleplaying galaxy set in the Star Wars galaxy during the Clone Wars. It runs on the authentic West End Games D6 *Revised & Expanded* tabletop rules — real dice, real Force skills — in a living world where an AI Director drives stories that react to what players do. No download, no cost. Telnet for purists. Roll up a character and play in your browser in a couple of minutes.

### 7c. Fan-project IP disclaimer line (landing + about + login)

> *Unofficial, non-commercial fan project. Not affiliated with, endorsed, sponsored, or approved by Lucasfilm Ltd. or The Walt Disney Company. Star Wars and all related properties are trademarks of Lucasfilm Ltd. No copyright or trademark infringement is intended. This game is free and will never be monetized.*

### 7d. Discord welcome / onboarding outline

> **`#welcome` (pinned message):**
> - One-line "what is this" (reuse 7b) + the **Play in browser** link.
> - "We're a free, non-commercial fan project — be welcome, be kind, and the `#newbie-help` channel is staffed."
> - The fan disclaimer line (7c).
> - 3 quick links: How to make your first character · The < 5-min tutorial · Where to ask for help.
>
> **Channel map:**
> - `#announcements` — devlog + new content (post the weekly "here's what changed from your feedback")
> - `#newbie-help` — bridged to the in-game help channel; owner/staff model a welcoming tone (first-contact warmth is a retention driver)
> - `#general` — community chat
> - `#feedback` — where "you shaped this" loops get closed publicly
> - `#events` — mirrors the Grapevine Events board; live in-game happenings
> - `#insiders` (private) — the ~8–12 early testers with a special role
>
> **New-member auto-DM / first-channel nudge:**
> - "Welcome! Two things get you playing fast: (1) hit **Play in browser** → pick a **Quick Start** archetype (you can build a full custom character later), (2) the tutorial takes under 5 minutes and you'll win your first roll early. Stuck? Drop a line in `#newbie-help` — a real person answers."

---

## Appendix — verified-against-HEAD notes for Brian

- **MSSP is not yet implemented.** `server/telnet_handler.py` negotiates only NAWS + TTYPE. MSSP is the highest-leverage discoverability task — log it in TODO.json if it isn't tracked.
- **No fan disclaimer exists in the web client** (`server/web_client.py`) — ship one on landing/about/login per §4 and §7c before any outreach.
- **UTF-8** is set on the telnet stream encoding (`server/telnet_handler.py`) — verify end-to-end for Grapevine's UTF-8 requirement.
- **Public name is still "SW_MUSH"** internally — choose an original, non-trademarked public-facing name + domain + logo before the landing page goes live (§4 naming guardrail). Keep "SW_MUSH" as the repo/internal name only.
- Era-cleanness invariant (CLAUDE.md B3) already enforces "no Imperial/Empire/Rebel/TIE in production strings" and "canonical Clone Wars figures never appear as open-world NPCs" — this is your original-assets guardrail already in code.
