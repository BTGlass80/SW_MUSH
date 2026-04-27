# Wookieepedia Extract — Clone Force 99 ("The Bad Batch")

**Source:** Wookieepedia (Fandom CC-BY-SA), https://starwars.fandom.com/wiki/Clone_Force_99
**Synthesized:** April 26, 2026, from `raw_clone_force_99.md` (13 KB → 6 KB)
**Maps to:** `weight_of_war_design_v1.md`, `clone_wars_director_lore_pivot_design_v1.md`

## At a glance

Clone Force 99 — informally called **"the Bad Batch"** — is a special-forces clone squad composed of "defective" clones whose mutations grant them enhanced individual specializations. They are the canonical example of **clones-as-individuals** in the Republic military: each squad member has a distinct personality, role, and capability, in deliberate contrast to the standard clone trooper template. They serve as a Republic special-forces unit during the Clone Wars (one hundred percent mission success rate); after Order 66, they fracture, with most refusing to follow the order and going on the run, while one (Crosshair) accepts the Empire.

For SW_MUSH purposes, Clone Force 99 is **the canonical squad archetype** for clone-trooper player content. They map directly to the kind of named-individual squad composition the Director AI should support for player parties.

## Squad composition

The five canonical members:

| Member | Specialty | Mutation / Enhancement |
|---|---|---|
| **Hunter** | Squad leader; tracker | Heightened senses (sight, hearing, electromagnetic detection). Iconic skull-pattern face tattoo and bandana. |
| **Wrecker** | Heavy weapons; demolitions | Massive physical strength and size. Booming voice; childlike enthusiasm for explosions. Carries the squad's heavy gear; throws other troopers as a tactical move. |
| **Tech** | Communications; intelligence; technical | Genius-level intellect and analytical capability. Goggles and tools strapped across his armor; speaks rapidly with technical precision. |
| **Crosshair** | Sniper | Exceptional eyesight and stillness. Cold, taciturn, sardonic. Toothpick-chewing affectation. Eventually accepts the Empire after Order 66 — the squad's "fall" beat. |
| **Echo** | Communications; cyborg specialist | Joins the squad later (mid-CW). Originally an ARC trooper from the 501st (Fives's squadmate); captured at the Citadel; converted into a cyborg communications interface by the Techno Union; rescued by the Batch and Anakin during the Battle of Anaxes. Recovers; chooses to join the Bad Batch over returning to the 501st. Cybernetic right arm; bald, scarred, gaunt. |

The squad gains a sixth member after Order 66: **Omega**, an unaltered female clone (genetic donor template, not a soldier) who they recover from Kamino. Omega is canonically out of CW project scope (Imperial-era Bad Batch series content) but worth noting.

## Voice and personality (for Director AI rendering)

The squad voices itself collectively when together; each member also has a distinct individual register.

### Squad-collective register
- **Camaraderie under fire.** They mock each other constantly; the mockery is affection. The Director AI should let their dialogue carry sharp banter that other clone units don't have.
- **Suspicion of regs.** "Regs" = standard ("regular") clone troopers. The Bad Batch maintains a mild outsider stance toward standard clones; they are clones but not normal clones, and they know it.
- **Loyalty to each other above all.** The squad's defining trait. When asked to choose between the Empire and one another, the four (minus Crosshair) choose each other.

### Individual registers
- **Hunter:** Calm, weighted, leader-cadence. Speaks last in most exchanges. The Director should voice him with quiet authority — never showy, never theatrical.
- **Wrecker:** Loud, exuberant, simple but not stupid. The Director should let him cheer at explosions, complain about being scared (canonically afraid of small spaces), demand food.
- **Tech:** Rapid, technical, slightly socially-disconnected. Treats every conversation as a puzzle. The Director should let him explain things at length even when no one asked.
- **Crosshair:** Cold, sardonic, contemptuous. Few words; barbs when he speaks. Toothpick canon detail. The Director AI should let his late-CW slide toward authoritarianism be subtle — he is the squad member with the strongest natural inhibitor-chip response.
- **Echo:** Quieter than he was as Fives's squadmate; weight of his Citadel imprisonment shows. The Director should let him speak as a man who has died once and remembers it.

## Notable Clone Wars story arcs (for `cw_tutorial_chains_design`)

The Bad Batch's canonical CW arcs provide tutorial-chain templates:

1. **Battle of Anaxes (Echo recovery).** Squad infiltrates the Techno Union facility on Skako Minor to recover Echo, who has been wired into the CIS computer-decryption system. Pattern: deep infiltration mission with biological-rescue stakes; squad must extract a converted comrade alive.
2. **Yalbec Prime insurrection.** Squad puts down a Yalbec uprising. Pattern: small-scale planetary engagement where individual squad capabilities matter more than fleet strength.
3. **Coruscant Underworld covert mission.** Sent by Mace Windu to retrieve a stolen list of Republic Ghost Agents. Squad goes undercover in the underworld; tracks the thief (Asajj Ventress) across multiple worlds. Pattern: investigative mission through underworld settings — ties directly into `coruscant_underworld_landmarks_design`.
4. **Order 66 escape (Kaller).** Squad is present on Kaller when Order 66 is given. Padawan **Caleb Dume** (later Kanan Jarrus) is the assigned Jedi commander. Hunter chooses not to fire on the Padawan; lies to Crosshair about his death. Pattern: squad fractures at the Order 66 moment based on individual integrity vs. inhibitor-chip compliance.
5. **Post-Order 66 mercenary work** (early Imperial Era; out of project scope for CW pivot but worth noting).

## Clone biology — Bad Batch mutations

Canonical detail: the squad's mutations were the result of deliberate experiments in Nala Se's private research lab on Kamino, intended to produce enhanced clones. The mutations were "enhanced" by Nala Se, suggesting deliberate development rather than accidental defect. This is canonical lore — the Bad Batch are not random anomalies but engineered specialists.

## Equipment and ship

- **Ship:** ***Marauder*** — Omicron-class attack shuttle. The squad's mobile base. Armed and capable of independent operations.
- **Armor:** Distinctive non-standard clone armor with personalized markings. Originally red-and-dark-grey trim; post-Tipoca-City fall, gold-and-grey with light blue accents. Each member's armor reflects their role.
- **Weapons:** Hunter — vibroknife, blaster rifle. Wrecker — massive heavy weapons, thermal detonators. Tech — modified blaster, computer spike tools. Crosshair — long-range sniper rifle. Echo — adapted blaster with cybernetic targeting.

## Use in `weight_of_war_design_v1.md`

The Bad Batch is the **canonical model for player-party clone squads**. Pattern observations for the design:

- **Named individuals over numbered units.** Players who play clone troopers should have the option of distinct individual roles (tracker / heavy / tech / sniper / specialist) rather than interchangeable templates. The Bad Batch demonstrates this works in canon.
- **Specialization-based mutations or backgrounds.** Each member has a clear specialty rooted in physical or psychological trait. The system might support specialty trees that mirror these archetypes (Hunter-tracker, Wrecker-heavy, Tech-tech, Crosshair-sniper, Echo-cyborg-communications).
- **Squad cohesion as a mechanic.** The Bad Batch's "loyalty to each other above all" is canonically their strongest trait. The system should support party-cohesion mechanics that mirror this.
- **The fall member.** Crosshair's slide toward Imperial alignment is structural. The system might support a "squad member who falls" arc as a campaign-clock event.
- **Special-forces operations vs. line-trooper deployment.** The Bad Batch operates as a special-forces unit; standard 501st and 212th content is line-trooper deployment. The mass-combat ruleset (CWCG §2 additive content) handles line troopers; small-squad content like Bad Batch operations is **squad-scale** and uses standard combat resolution. The design should distinguish these two scales.

## Use in `clone_wars_director_lore_pivot_design_v1.md`

The Director AI must:

- **Voice each squad member with their distinct register.** Not interchangeable; not a generic clone voice.
- **Treat their loyalty-to-each-other as canonical and central.** Any scene that tests this should resolve in the squad choosing one another.
- **Treat Crosshair's late-CW arc as available pivot content.** Players may encounter the Bad Batch before or after Crosshair's break.
- **Treat the Order 66 / Kaller arc as a fixed campaign clock event.** After this point, the Bad Batch is on the run and out of standard Republic content.
- **Allow squad encounter content where players hire them or work alongside them.** The squad takes covert missions for the Republic during the war; players running parallel operations might cross paths.

## Cross-references

- `raw_anakin_skywalker.md` — worked alongside the squad during Anaxes campaign (Echo recovery).
- `raw_mace_windu.md` — assigned them the Coruscant underworld covert mission.
- `raw_501st_legion.md` — Echo's original unit; the Bad Batch is adjacent to but distinct from the 501st.
- `raw_clone_trooper.md`, `raw_advanced_recon_commando.md`, `raw_republic_commando.md` — broader clone-unit context.
- `raw_kamino.md` — their origin facility; site of multiple key arcs.
- `raw_asajj_ventress.md` — antagonist in the Coruscant Underworld covert mission arc.
- `raw_grand_army_of_the_republic.md` — the broader institutional context.

---

*End of extract. Synthesized from Wookieepedia per architecture v35 §32. Imperial-Era Bad Batch series content (Omega, Tantiss Base, Crosshair Imperial arc, post-CW mercenary work) noted but out of project's CW scope.*
