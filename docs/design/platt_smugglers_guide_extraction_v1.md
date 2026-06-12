# SW_MUSH — Platt's Smugglers Guide Extraction
## Version 1.0 — June 2, 2026 · Opus session
### Source: WEG40141 — *Platt's Smugglers Guide* (Peter Schweighofer, West End Games, 1996, 106 pages, scanned with an OCR text layer)

---

## Table of Contents

1. Book Identity & Mining Assessment
2. Deliverable A: Smuggler-Concealment Gear Catalog (Ch. 4) — the centerpiece vein
3. Deliverable B: Cargo-Handling & Survival Gear (Ch. 4) — era-agnostic, feeds Crafting (G07) / Encounters (G24)
4. Deliverable C: Spacer Documentation & the Forged-Document Economy (Ch. 3)
5. Deliverable D: The Contact Network System (Ch. 5) — design stub
6. Deliverable E: Grudge / Nemesis Generation (Ch. 6) — design stub
7. Deliverable F: Smuggler Origins & Employer Taxonomy (Ch. 1–2) — chargen / tutorial
8. Deliverable G: Character Templates & the Crewing Model (Ch. 7)
9. Era-Translation Notes — what carries, Q1 handling
10. Integration — New vs. Already-Built (with one reconciliation flag)
11. Remaining Unmined / Prune Note

---

## 1. Book Identity & Mining Assessment

**Source confirmed.** WEG40141, *Platt's Smugglers Guide*, by Peter Schweighofer, West End Games, 1996. 106 pages. Image-based scan with an Adobe Paper-Capture OCR text layer — legible but error-prone; gear-stat sidebars are heavily mangled (numeric fields transcribed by eye where possible, flagged where not). Framed as the in-character handbook of **Platt Okeefe**, a WEG-original smuggler PC.

**Roadmap status.** Tier 1, sequencing item under "Economy/space depth" (#2: *Platt's Smugglers Guide → Stock Ships → Pirates and Privateers*) in `sourcebook_extraction_roadmap_v1.md`. It feeds Economy (G06), the smuggling loop, and Space (G05). Guide 05 already *names* this book as a rules source for transponder countermeasures, so the extraction closes the citation.

**The honest assessment: the live smuggling system is already mature, so this is a depth/refinement mine, not a foundation mine.** The 06-01 era drop and the GG6/GG11 extractions already shipped route tiers, customs-by-authority, contraband checks, transponder countermeasures, drop-point delivery, and the fence/black-market role. What Platt's adds that *isn't* in HEAD: a **concealment-gear layer**, a **forged-document credit sink**, a **starport-class tier model**, a **contact-relationship system**, a **grudge/nemesis model**, and a clean **smuggler-origin/employer taxonomy** for chargen and the spacer tutorial. Everything below is scoped to *extend*, not restate, the live system (see §10).

**Era note — unusually light.** This is a how-to-smuggle toolkit, not an Imperial-period setting book, so it's overwhelmingly era-flexible/agnostic. The only systematic translation is authority labels (Imperial → Republic/sector/Hutt), which the codebase already performs. **BoSS stays** — it's a clan-administered agency that predates the Empire, era-correct for 20 BBY.

**Q1 canon-character policy.** No film-canon figures appear anywhere in this book. Every named NPC (Platt Okeefe, Alec Aroval, Voos, Tulagn, Captain Seprine, Grumme Vinn, Zo'Tannath, Vowluss) is WEG-original and survives as a named archetype after era-label translation — none require reduction beyond that. Platt herself is treated as the *narrator/voice* of the doc, usable as a "veteran-smuggler mentor" archetype but not instantiated as a named open-world NPC.

**Chapters mined:** Ch. 1 (Character Development — backgrounds, worksheet), Ch. 2 (Smuggler Origins — origin + employer taxonomy), Ch. 3 (Your Ship — registration, documents, starport procedure), Ch. 4 (Tools of the Trade — the gear catalog), Ch. 5 (Contacts — the relationship system), Ch. 6 (Rivals and Adversaries — the grudge model), Ch. 7 (Character Templates).

---

## 2. Deliverable A: Smuggler-Concealment Gear Catalog (Ch. 4)

The richest new vein. These are **gear modifiers to the existing customs check** — today contraband evasion is a flat Con/Sneak roll against an authority-scaled difficulty; this gear gives the player something to *buy/craft* that bends that roll, plus counter-mechanics (energy sensors) so it isn't a free pass. Stat lines use WEG sidebar fields; OCR-uncertain numbers are flagged.

**Sleight Box** *(the centerpiece — a concealment cargo crate)*
- Model: Edo Industries "Stress-Steel" Crate · Type: sleight box · Cost: ≈35,000 cr *(OCR-ambiguous — verify against scan)* · Availability: 3, R (custom-made in smuggler shadowports; not from standard outfitters)
- **Mechanics:** Looks like an ordinary cargo container, but a low-powered repulsorlift coil matrix + power supply is concealed in the bottom casing, with a compensation board that neutralizes the weight of anything inside — **the box feels empty when lifted.** Fools most customs officials *as long as they don't open it.* Best practice: never put holoseals or tag markers on it (a sealed-but-cargoless box reads as suspicious). Energy sensors can sometimes catch the power signature, so smugglers store sleight boxes among other energized components (shield-generator capacitors, power converters, life support, reserve cells) to mask it. A successful sensor scan raises the difficulty to detect the box; a sleight box nested inside another sleight box is harder still.
- **Integration:** the marquee item. Carrying contraband in a sleight box should grant a die bonus (or raise the inspector's difficulty) on the launch/arrival patrol check — with an **energy-sensor counter-roll** available to high-authority customs (Core/Capital and Republic-Navy zones), so it's a strong but defeatable tool, not an exploit.

**Cold Crate** *(cryogenic cargo crate)*
- Cost: ≈2,500 cr *(OCR-uncertain)* · Availability: 2
- Insulated case + cryo unit; sets temperature from cool to well below freezing; holds ≈50 standard hours, indefinitely by recharging off the ship's generator. **Not** suspended-animation (not carbonite). **Smuggling use:** hide contraband at the bottom under a layer of frozen preserved cargo — the cold + insulation block sensors, and few inspectors will chip through frozen fish to reach the bottom.

**Hot Box** *(heated cargo crate)*
- Insulated crate + base heater; warm to near-boiling; pressure valves vent steam (hoseable elsewhere); ≈50 hours on power cells. **Weaker for smuggling than the cold crate** — heat/humidity damage most goods over long hauls and venting can betray contents — but the steam/humidity can shorten an inspector's patience and cut a search short. Overheat risk; check every couple of hours.

**Containment Unit / Irradiator Box**
- Broad-spectrum radiation + ultrasonics kill bacteria/viruses/microorganisms on tools and gear. Small "containment box" ≈ a spacer's chest (self-powered); larger booths need a ship power hookup. **Can** conceal contraband but is a *poor* hiding spot — powered (energy signature) and anyone opening it finds the cargo. Primarily a legit sterilization tool.

**Marker Placards**
- Model: SoroSuub Marker Signs · Type: starship signage · Cost: 10 cr · Availability: 2
- Metallic/plastic signs, magnetic or adhesive backing. Warning variants: "Danger: Charged Capacitors," "Steam Vent Zone — Keep Away," "Beware: Hot Ion Coils," "Blow-out Panel Zone," "Caution: Super-Heated Elements," "Do Not Step Here." **Smuggling use:** stick one over the access panel hiding contraband to wave nosy inspectors off. Doesn't always work (especially against inspectors willing to send subordinates into "danger"), but cheap insurance — a minor situational modifier + a roleplay prop.

**Tox Detector** *(toxic-gas detector)*
- Cost: 12 cr · Availability: 2 (cheap enough to put one in every vital compartment)
- ~1-meter-square patch with a central pad; center dot turns from deep blue to fluorescent orange when poisonous fumes are present (most react to any gas harmful to human atmospheres; some tailored to non-human biology). Legit safety device. **Smuggling use:** a *tripped* (orange) detector marks a compartment "contaminated," giving a pretext to wave inspectors off the space actually hiding contraband — good for staging a hazard/maintenance scene.

**Thermal Credit Belt**
- Fabric waist belt; four pockets absorb body heat inside and radiate it outside, masking high-denomination currency from a thermal/sensor scan. **Drawbacks:** wear loose clothing (obvious under a tight outfit); makes a blast vest/armor uncomfortable; no scent-masking (won't hide spice/spike — customs animals still detect odor).

**Crate Tag Imprinter** *(the cargo-manifest forging tool)*
- Type: cargo imprinter · Cost: 1,500 cr · Availability: 1
- Handheld freight-label printer; prints scancode/lettering tags (often Aurebesh Basic) recording cargo type, count, sender, receiver, authorized agent, ship date, hazards, routing. **It only marks what you enter — no validation**, so a smuggler labels a crate of blaster pistols as "nerf links." A copy function duplicates data across many crates (sequential tracking numbers). The contraband-manifest counterpart to forged ship papers.

**Tag Scanner / Tag Scanner Octapod**
- Reads cargo-label coding (removable comlink-sized scanner; docking to the datapad uploads to inventory). Customs checkpoints use scanners to interpret coding and cross-check against sensor data. The **Octapod** model can be modified to interpret the coding *cipher* — a slicer tool.

**Sector Customs Holoseal** *(era-translated; "Imperial" → sector authority)*
- Plastic seals applied to cargo that has passed inspection; one side a holographic authority symbol, the other adhesive, run along the body/lid seam (special variants for liquid-tank valves, access hatches, living-cargo collars). Each carries a register code readable by a customs datapad and traceable to where/when issued; tamper-evident (peeling corrodes the hologram to a blackened smear).
- **Infraction scale (era-flexible — maps to the Class-One-to-Five spacer-crime table):** tampering with a customs holoseal = **Class Four** (fine 1,000–5,000 cr, up to ~1 month imprisonment, cargo confiscation); cocky behavior bumps it to **Class Three** (transporting restricted goods) or even **Class Two** (transporting stolen goods). Lower-grade agencies use weaker seals. → A ready penalty ladder for the customs system.

---

## 3. Deliverable B: Cargo-Handling & Survival Gear (Ch. 4)

Era-agnostic; feeds Crafting (G07) and Encounters/Wilderness (G24). Several have dual-use mechanics worth wiring as item abilities.

- **Crate Hooks** (Vlasth Cargo Grippers) — Cost: 50 cr/pair. Handles with curved, blunt blades for gripping crate frames. **Dual use:** improvised melee weapon (the curved blades; STR-based), cracking cargo seals / prying stuck lids, climbing claws on soft surfaces. Vlasth makes species-specific grip variants.
- **Loader's Gloves** (Vlanth) — Heavy gloves + forearm guards with a metal-strut exoskeleton and armor plates; leverage + hand protection for moving crates; lockable for grip endurance. **Unwieldy for fine manipulation** (firing blasters, pressing controls); a few rounds to don/doff.
- **Repulsorlift Cart** — A repulsor coil keeps it hovering but doesn't propel it; a push-bar steers; straps/webbing/railings hold the payload; hard to control without feet on the ground. Premium (Falkenhausen Mark V14 Baggage Handler) adds maneuver thrusters.
- **Servo-lifter** (powered exoskeleton) — Cost: ≈10,000 cr (loaded) / ~7,000 cr (bare). Hydraulic limbs/graspers; lift and haul heavy cargo short distances. A luxury item.
- **Cargo Netting** (SoroSuub) — Cost: 100 cr / 10-meter-square section. Synthetic webbing, metal grommets, adjustable hooks; ties down and partitions crates. **Improvised:** a weighted-edge net as a pitfall/capture trap (otherwise poor at capturing); cut by a blade or destroyed by blaster fire.
- **Portable Emergency Beacon** (Chedak) — Cost: 1,000 cr. Size of two medpacs; burst beacon on an emergency frequency (≈4 ly range — summons rescue on settled worlds, draws patrols/pirates/mercs/rival smugglers on wild ones); search strobe; glow-rod lantern; mini-fusion generator (≈250 hr; recharges glow rods/blaster packs/low-power gear, ~1 hr drain per charge); heat-vent fan. Irreversible rip-switch activation (can't shut off until the generator dies; a **Moderate Technical** task rigs a toggle, risking blown components). **Unconventional use:** plant it in a rival's crate rigged so opening the lid trips the beacon — broadcasts through the crate to track a package or betray a competitor's position. A clean quest/PvE-tracking hook.
- **Personal Strobe Locator** — Comlink-sized; pocket clip + retractable spike; flashes every ~2 s for ~20 hr, visible ~3 km, rechargeable, switchable on/off. **Dual use:** a reusable flash-bang — with sleight of hand + misdirection, get a target to look toward it and flick it on to temporarily blind them (especially in the dark).
- **Survival Pack / "Crash Pack"** — Two weeks' rations (often stale), 3 medpacs, glow rod, 2 thermal flares, a dichrome shelter, a breath mask, ~18 m synthrope, a knife, a portable fusion generator. Smugglers swap cheap parts for their own gear (emergency beacon in place of the generator, a holdout blaster, a flamer for fire-starting). The standard wilderness-crash kit.
- **Aqua Survival Shelter** — Cost: 1,500 cr · Availability: 1. Pack ≈ a spacer's chest; pull-and-toss inflates a two-person dichrome life-raft/shelter; flotation resists reasonable acidity/alkalinity (moderately corrosive liquid eats through); reflective skin keeps it cool; vent flap for air. Built-in homing beacon (civilian/military channels, ≈4 ly) on deployment; ≈250-hr fusion generator + heat vent; detachable bundle (2 weeks' rations, glow rod, ~6 m synthrope, 2 medpacs, large water tank, bailing bucket, repair kit, mini inflator); paddle/sail-riggable, no propulsion. A water-world variant of the crash pack.
- **Entry Hatch & Console Locks** — Three lock types (electronic combination, key card, coded key), cockpit-controllable; devices burn out with deadbolts in place if overly stressed (struck, shot). Disassembling the bolts is a difficult task (a fusion cutter helps). Console locks secure the cockpit controls. Pairs with the shipjacking/boarding system.
- **Comm Scrambler** *(partial in scan)* — Switches comm channels + adjusts volume; jacks into the ship's intercom (which then blocks normal comlink transmission to outside sources). A countermeasure item alongside the existing comm jammer.

---

## 4. Deliverable C: Spacer Documentation & the Forged-Document Economy (Ch. 3)

A net-new **credit sink + customs-check modifier**, plus a docking-zone tier model. Authority labels era-translated; **BoSS retained as era-correct.**

**The registration layer.**
- **BoSS (Bureau of Ships and Services)** — clan-administered record-keeper of ship registrations, transponder codes, captain's flight certifications, and weapon/shield load-outs. Era-flexible; keep as-is.
- **Space Ministry** (era-translate → **Republic Space Ministry / sector authority**) — publishes the Spacer's Information Manual for 25 cr; astrogation/nav updates for 150 cr.

**The three required documents (carried aboard at all times):**
1. **Ship's Operating License** — specs, port of origin, manufacturer, registration code, transponder-code sample. Legit cost **1,000 cr** + background check + brief ship inspection + transponder verification.
2. **Captain's Accredited License** — license to pilot a specific starship *class*; written + flight tests, ~2 years documented flight time, a background check, a **300 cr** fee. BoSS will overlook the time/testing for a **200 cr** "expediter" fee — total ~**500 cr**.
3. **Arms Load-Out Permit** — for non-military ships with weapons or unusually high shields; **each weapon/shield system needs a separate permit**; brief inspection + background check + a minimum **250 cr** fee (scaling with the hardware). Upgraded weapons need new permits. Emplacements/boosted shields with no permit → impounded (assumed pirate/insurgent). *This is a natural sink on the existing ship-mod system — boosted weapons aren't free to fly legally.*

**Getting Around BoSS — the forging economy (the new sink + risk):**
- A data-document **forger** charges ≈ *half the ship's value* for the secure datapad, then half again to imprint the papers — commonly **6,000–10,000 cr** total (scales with quality and your Bargain).
- Forged paper that doesn't match BoSS records gets you busted — you also need a **slicer** to access the BoSS network and implant matching records: ≈**3,000–5,000 cr**.
- A **forger/slicer team** sells a full package (operating + captain's + arms permits, all "legitimately" updated in BoSS) for **6,000–10,000 cr**.
- Crime-lord employers often bundle proper documentation into a ship purchase — and can yank it from BoSS to punish a disloyal worker. (Platt's advice: own your own papers even if you fly for a crime lord — a built-in betrayal hook.)
- **Integration:** carrying *good, matched* forged docs lowers the difficulty / grants a bonus on transponder-verification and the customs ID check; carrying *bad, unmatched* forgery raises the bust risk on a data-mismatch. Feeds the live transponder / false-transponder countermeasure and the slicer/data-forger contact (§5) + GG11's data-fixer.

**Starport procedure & classes.**
- **METOSP ("Message to Spacers")** — a one-way, daily-updated comm channel carrying traffic patterns, customs-checkpoint notices, patrol activity, piracy threats, astrogation hazards; no reply. A flavor/info feed concept that pairs cleanly with `+news` and the Director-AI lockdown heat broadcast.
- **Arrival procedure** — tune starport control, verbally ID ship + captain, answer questions on last port of call / cargo / passenger count (an interrogation the inspector may cross-check against sensors).
- **Five starport classes** (era-translate "Imperial Class" → **Core/Capital Class**): **Landing Field** (cleared dirt/ferrocrete, no tower/beacon, no guaranteed services) → **Limited Services** (small command center + signal beacon, rentable maintenance sheds) → **Standard Class** (full flight command, restocking, small shipyard, minor repairs at up-to-double price/time) → **Stellar Class** (docks nearly any vessel, multiple shipyards, advanced repairs/customization, on-site customs + navy) → **Core/Capital Class** (best: extensive docking, merchant offices on-site, rapid high-quality repairs, expert customs, formidable military, thorough ID checks). → A **docking-zone tier** model: a `port_class` field can drive per-port repair cost/quality, customs-scrutiny level, and patrol presence — slotting beside the existing `PLANET_PATROL_FREQUENCY` / customs-by-authority.

---

## 5. Deliverable D: The Contact Network System (Ch. 5)

A design stub for a **tracked-relationship** model — the part GG6/GG11 didn't build. (The drop-point-agent and fence *mechanics* already ship; what's new is contacts as persistent relationships with loyalty that degrades on betrayal.) Feeds PC narrative memory, NPC relationships, faction reputation, and the Director AI.

**Contacts pegged to a chargen stat.** At creation a smuggler gets **one contact per die** of a designated background/social value (the book ties it to a chargen stat; in our schema, peg it to a chosen attribute or a fixed budget). e.g., 5D → five starting contacts. The GM may adjust for how richly the background is written.

**Each contact carries a relationship-origin that sets baseline loyalty** (the hinge into §6 — betray one and it becomes an adversary):

| Origin | Baseline loyalty behavior |
|---|---|
| **Life Debt** | One saved the other; becomes a friendly competitive life-saving rivalry; loyal to the end. Breaking it marks you a despicable villain. |
| **Common Experience** | Survived a crisis together (prison break, dangerous job, firefight, shared scam, same tyrannical boss). Strong, durable. |
| **Family Friend** | Tied to your family; forgives slip-ups on your family's standing, but disappoint too often and it gets back to your family. |
| **Romantic Interest** | Once involved; strong if it ended well, crumbles if it ended badly. |
| **Former Colleague** | Worked together, now in different lines; can be strong but decays with time — you only have their word on the gap. |
| **Favors** | Transactional ("you fix my ship, I'll run your cargo"); falls apart if one side perceives the other isn't pulling weight. |
| **Old Acquaintance** | Casual (old Academy, same circle, weekly sabacc); superficial, leisure-based; prone to becoming a fair-weather friend. |
| **Reference** | Referred by another contact (initiated by informants/starport workers); grants access but **not** loyalty — only as reliable as the credits you pay. |

**Loyalty degrades on betrayal.** Treat a contact well → stays reliable; cheat/betray → likely to do the same. *"Nothing is more dangerous than a good friend turned vindictive adversary."*

**Contact-type taxonomy** (the roles a network is built from):
- **Drop-Point Agent** — cargo middleman. *Already live (GG6).*
- **Fence / Black Marketeer** — offload hot cargo or source specific stolen items; hides behind a legit business, stash in a guarded location, passwords + contact times required; merchandise from a fence is hot and traceable to you. *Already live (GG11).*
- **Data Forger** — §4 forging.
- **Slicer** — BoSS-record implant; cipher-cracking.
- **Docking-Bay Owner** — *fresh archetype:* a friendly owner who gives safe landing/hiding for favors. Secure bays have blast doors, automated surveillance, comm gear, concealed hides, and secret escape routes; the more solid the relationship, the more they'll risk — but the greater the favor owed later. Pairs with the security-zone and housing systems (a safe-haven landing spot tied to a relationship).
- **Broker / Informant / Technician** — supporting roles.

---

## 6. Deliverable E: Grudge / Nemesis Generation (Ch. 6)

A design stub for a **nemesis ledger** that converts player actions into named adversaries with motives — feeds the Director AI (which complication to inject, and against whom), the bounty system (debt → bounty), and faction reputation. The betrayed-contact → adversary path links §5 directly into this.

**Rivals vs. Adversaries.** A **rival** is a same-trade competitor (other smugglers, free-traders, corporate transport pilots, drop-point agents) who wants to out-bid you and might sic an inspector on you or swap your contraband with empty crates — but rarely wants you dead; *"as long as they get something out of the deal, they can be your friend."* An **adversary** wants you dead, captured, or gone and doesn't care how (slavery, the spice mines, a carbonite block, an interrogator droid).

**The eight grudge generators** — actions that turn an NPC (or a betrayed contact) into a persistent adversary with a motive:
1. **Breaking the law** → the official who enforces it makes tormenting you a mission.
2. **Owing debts** → unpaid services/goods → bounty hunters hired to collect; owing your *employer* is worst.
3. **Destroyed property** → fine, forced work-off, forced replacement, or a bounty.
4. **Embarrassment** → humiliating someone before their subordinates/superiors → disproportionate revenge.
5. **Romantic trouble** → meddling in a romance → a bitter, emotionally-driven enemy.
6. **Foiling plans** → blocking someone's goal (a lost job, prison) → they aim to do the same to you.
7. **Harming a close friend** → hurting their friend/crew/contact → they seek to inflict the same.
8. **Physical harm** → lasting reminders (scars, a limp, one eye, cybernetics) → enduring revenge.

**Rival archetypes (NPC templates):**
- **Corporate Transport Pilot** — condescending, jealous of smuggler freedom; reports contraband to inspectors; manipulative (the Captain-Seprine type).
- **Honest Free-Trader** — a noble *legal* captain who won't fight or sabotage you, but **will** report any illegal activity to the authorities (the Grumme-Vinn type).
- **Other Smugglers** — competitors and sometimes allies; rivalries escalate from bar brawls and pranks to ratting you out, traffic-lane dogfights, and docking-bay shootouts.
- **Bounty Hunter / Collection Agent** — the debt-collection adversary (the Zo'Tannath type).

---

## 7. Deliverable F: Smuggler Origins & Employer Taxonomy (Ch. 1–2)

Feeds chargen origins (G02) and the **spacer tutorial track (G25)**. The book's worksheet structure is itself a clean chargen prompt: *Name · Background · Past Occupation · How You Got Into Smuggling · Who You Work For · How You Got Your Ship · Contacts · Rivals/Enemies.*

**"How Did You Get Into Smuggling?" — origin table** (most are dragged in by circumstance, not choice; era-translated):
- **Employer Encouragement** — a legit captain asked to slip contraband for a bonus; smuggling under cover of legal cargo.
- **Illegal Cargo Proved Profitable** — discovered smuggling pays far better; abandoned the day job.
- **Escaped Slave** — fled bondage, possibly still pursued; smuggling to survive (or to fund revenge / free others).
- **Exiled** — fled a homeworld/clan/government; wanders the lanes until the name is cleared.
- **Family Business** — inherited the ship *and* the family's debt, bad reputation, and unsavory contacts.
- **Leaving a Dead-End Job** — bought an old freighter chasing adventure; got more than bargained for.
- **Indentured to Power** — a powerful patron saved you and demands a lifetime of favors; provided a ship + a ~1,000 cr/month stipend that only sinks you deeper in debt; go rogue and the patron hunts you. *A strong recurring quest/debt hook.*
- **On the Run** — wanted by a crime lord / sector government / corporation / the Hutts; mobile, untethered, blast-and-flee when enemies arrive.
- **Out for Revenge** — a past injustice; smuggling provides the mobility, contacts, and credits to pursue it (but you won't kill for money — not a bounty hunter).
- **Pirate's Loot** — a disbanded pirate group; took your share, bought a ship, went legit-ish using shadowport contacts.
- **Smuggling as a Hobby** — already rich and bored; the wealth avoids the usual debt pitfalls but has soured your peers and family on you.
- **Stowaway** — stowed away; the captain put you to work and taught you the trade.
- **Wanderlust** — always wanted to roam the lanes, meet cultures, see strange ports.
- *(Off-era hook recast:)* **Working for a Cause** — the book's "working for the Rebellion" → translate to running supplies/operatives/data for a faction or cause without joining outright.

**"Who Do You Work For?" — employer/patron taxonomy:**
- **Drop-Point Agent** — the freelance backbone; cargo from A to B for a pre-set fee. **Pay formula:** ~10 cr/ton/day at a ×2 hyperdrive, up to ~20 cr/ton/day at ×1; bonuses for quick delivery / hazard navigation; **half up front + a voucher** for the balance (paid by the receiver, or signed and redeemed with the agent). Influential backers hire bounty hunters if their cargo goes missing. *(See the reconciliation flag in §10.)*
- **Crime Lords / Hutts / Klatooinan Trade Guild / Loan Sharks** — indenture for life; even a legitimate exit means being hounded for your career.
- **Shipping Corporations** — dabble in contraband via legit freighters; corporate benefits + steady work as the lure.
- **Swoop Gangs** — odd hauls (e.g., custom repulsor parts).
- **Sector Official / Governor** (era-translate the "Imperial Moff" hook → a corrupt sector official) — runs in exchange for favors.

**Design principle for the starter quest:** the templates deliberately omit freighters — *whether a character starts with a ship depends on background and group composition* (a just-out-of-prison spacer is less likely than a fresh Trade-Guild signee). Directly supports the **earn-the-ship quest** model (G25) and seeds intra-crew tension as a feature, not a bug.

---

## 8. Deliverable G: Character Templates & the Crewing Model (Ch. 7)

**Seven book-original templates** as PC/NPC archetype seeds (era-translatable; none are canon figures): **Bacta Pirate, Bacta Smuggler, Disguise Artist, Freeworlds Trader, Mrlssi Roving Entertainer, Mrlssi Swindler, Professional Thief.** (Bacta is era-agnostic; *Mrlss/Mrlssi* is a species — keep.) Stat sidebars are OCR-mangled — re-stat by eye from the scan if any are instantiated.

**Crewing model** for a light-freighter smuggling crew: **pilot + copilot + one gunner per weapon**, plus a **technician** and a **"fast-talker,"** plus **heavy hitters** to move cargo and fight in port. Reinforces the multi-crew design (`space_overhaul_v3`) and the spacer NPC-crew loop — each station is a role a player or NPC crew member fills.

---

## 9. Era-Translation Notes

- **Carries unchanged (era-agnostic/flexible):** the entire gear catalog (§2–§3), the contact system (§5), the grudge model (§6), the origin/employer taxonomy (§7), the crewing model and templates (§8). This book is a toolkit, not a period piece.
- **Authority-label translation only:** *Imperial Space Ministry → Republic Space Ministry / sector authority*; *Imperial Navy → Republic Judicial/Navy*; *Imperial Customs → customs-by-authority (Republic / CIS / Hutt)* — **all already done in HEAD** by the 06-01 era drop. *"Imperial Class" starport → Core/Capital Class.* The "New Order" line and the Rebel-Alliance origin/employer hooks recast to faction/cause.
- **BoSS is retained** — a clan-administered agency predating the Empire; era-correct for 20 BBY.
- **Q1:** no film-canon figures appear; all named NPCs are WEG-original and survive as archetypes after era labels. **Platt Okeefe** is the doc's narrator-voice — usable as a "veteran-smuggler mentor" archetype, not instantiated as a named open-world NPC.

---

## 10. Integration — New vs. Already-Built

**Already shipped — do NOT duplicate:**
- The four-tier smuggling route board + pay bands; launch + arrival customs/patrol checks; contraband carry + Con/Sneak evasion; customs-by-authority (Republic/CIS/Hutt); transponder + false-transponder / sensor-mask / comm-jammer countermeasures; drop-point delivery + fence/black-market contact mechanics (GG6); the fence role + black-market protocol (GG11); the Director-AI lockdown heat.

**Net-new from Platt's (the extraction's actual value):**
1. **Concealment-gear layer** (§2) — sleight box + cold/hot crate + marker placards + tox detector + thermal credit belt + crate-tag imprinter + customs holoseal, as **gear modifiers to the existing customs check** with an energy-sensor counter so they aren't free passes.
2. **Forged-document economy** (§4) — BoSS docs + forger/slicer/package price bands, as a **credit sink + customs-check modifier** (good-matched docs help; bad-unmatched docs raise bust risk).
3. **Starport-class tier model** (§4) — a `port_class` field driving repair cost/quality + scrutiny + patrol presence.
4. **Contact-relationship system** (§5) — origin → baseline loyalty → degradation on betrayal; the tracked-relationship layer GG6/GG11 didn't build.
5. **Grudge / nemesis model** (§6) — eight grudge generators → persistent adversaries with motives; feeds the Director AI + bounties + reputation.
6. **Smuggler-origin + employer taxonomy** (§7) — chargen origins + the spacer tutorial track.
7. **Conditional-ship design principle** (§7) — supports the earn-the-ship starter quest.

**One reconciliation flag — your call.** The book's drop-point pay formula (**~10 cr/ton/day at ×2 hyperdrive, up to ~20 at ×1, half up front + voucher**) is more granular than the live fixed route-tier bands. My recommendation: **keep the live bands** and treat this formula as optional flavor / an alternative "freelance drop" pay model — *not* a replacement — unless you specifically want per-ton economy granularity. Flagging rather than assuming.

---

## 11. Remaining Unmined / Prune Note

- **Light-skim only (low ROI):** the first-person fiction interludes; the detailed sample-employer write-ups in Ch. 2 (XTS, the Trade-Guild patron, "Governor McClain" — McClain is framed as secretly exempt from *Imperial* harassment, an off-era hook → recast as a corrupt sector official if used); and the cross-references to other WEG books (Galladinium's *Fantastic Technology*, Cracken's *Rebel Field Guide*, *Platt's Starport Guide*, GG6/GG11).
- **OCR caveat:** the NPC and gear stat sidebars are mangled — transcribe by eye from the rendered pages during implementation; the prose mechanics above are reliable, the exact numeric fields flagged with "≈" or "verify" are not.
- **Per the roadmap loop:** once §2–§7 land in design/data, **WEG40141 can be deleted** — its value is captured here.
