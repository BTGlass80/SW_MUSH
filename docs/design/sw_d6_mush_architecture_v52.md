# SW_MUSH — Architecture (v52)
## Star Wars D6 MUSH on Python/aiohttp/aiosqlite — 2026-06-12 consolidation

> **v52 supersedes v51.** It is grounded in HEAD as of the 2026-06-12
> session. It does two jobs at once:
>
> 1. **Reconciles the invariant block.** The on-disk
>    `sw_d6_mush_architecture_v51.md` carries a known numbering collision —
>    it runs §4.29 → §4.31 with **no §4.30**, and its §4.31 is the
>    *communal-objective* invariant, colliding with the *creature-spoils*
>    invariant that the CHANGELOG records as §4.31. The collision was
>    flagged 2026-06-06 (TODO `version_history`), which **pulled the arch
>    doc out of the per-drop drop-zip** and made it known-stale: *"do NOT
>    trust its invariant numbering."* A dedicated v52 reconciliation was
>    owed. This is it. §4.30–§4.33 are re-established from CHANGELOG truth,
>    each verified at HEAD (§4.x below).
> 2. **Folds in everything since the v51 May-30 cut.** The June economy /
>    creature / Force waves (point-updated into v51's §1.4-G..K on a
>    *chat-uploaded* copy that never reached disk), the 2026-06-06 communal
>    objective + hunter-consequence, and the **headline June 11–12 wave:
>    the Gundark crafting lane (drops 1–11)** — ~40 recipes, 3 NPCs, 6
>    engine mechanics, every faucet shipped with its sink — plus the web
>    onclick-export fix, market segmentation, and the vendor-presence buy
>    gate.
>
> **Fold-forward by reference.** v52 does NOT re-type the durable layer
> detail. v51's §2 (architecture by layer narrative), §5 (process
> disciplines), §6.1–§6.3/§6.6 (audit discipline), and §10.1–§10.5
> (retirement notes) **carry forward unchanged** — read them in v51, which
> stays on disk as the detailed reference. v52 restates only what moved:
> current-state counts (§1), the June waves (§1.4), the roadmap (§3), the
> **full reconciled invariant block** (§4), the design-doc-map delta (§7),
> outstanding decisions (§8), and version history (§9).
>
> If you have v51 or earlier in hand and need a single number: **current
> `SCHEMA_VERSION = 43`.** v51's header still says 35; that header was
> never reconciled. Trust this doc and the CHANGELOG over it.

---

## §0. Reading guide

- **§1 Current state** — what SW_MUSH is; HEAD-grounded code counts; the
  June waves (audit-remediation tail, creature/Force waves, communal
  objective, and the Gundark crafting lane); what's still open.
- **§3 Roadmap** — lanes (engine + web-client closed for launch; content
  + crafting follow-ups remain), priority ranking, forward plan.
- **§4 Invariants** — **the reconciled block.** §4.1–§4.29 fold forward
  from v51 (read there); §4.30–§4.33 are re-established here from CHANGELOG
  truth with corrected numbering; §4.34–§4.37 are new (the Gundark lane).
- **§7 Design doc map** — delta only (crafting/sourcebook + vendor rows).
- **§8 Outstanding decisions** — the resolved CRAFT letters and what's
  genuinely still open.
- **§9 Version history** — what each consolidation closed.

Everything not restated here is **as v51 records it.**

---

## §1. Current state

### §1.1 What SW_MUSH is

A Star Wars MUSH built solo by Brian (GitHub: BTGlass80) in Python 3.14,
using aiohttp + aiosqlite + asyncio with a vanilla-JS web client. Active
era is **Clone Wars** (~20 BBY); GCW is deprecated reference content. WEG
D6 R&E ruleset, fidelity is a hard constraint. Local Mistral 7B for NPC
dialogue (RTX 3070, 8GB VRAM); Claude Haiku for the Director AI when
enabled (~$20/mo circuit breaker). Web-first design directive (§4.1).

Windows desktop is the ground-truth dev box (`run_all_tests.bat`,
~7,700+ tests). The chat sandbox runs targeted regression sweeps against
HEAD; the full suite is the gate on apply.

### §1.2 What this document is

The architecture-of-record. v52 is a **reconciliation + delta**
consolidation, not a from-scratch re-type: it fixes the v51 invariant
numbering and folds in the June waves, while explicitly folding v51's
durable sections forward by reference (see the header). `TODO.json
architecture_of_record` should now read `sw_d6_mush_architecture_v52.md`.

### §1.3 Code-state baseline (grounded in HEAD, 2026-06-13 — drops 34–43)

| Surface | v52 (Jun 12) | drops 24–33 | HEAD (drops 34–43) | Note |
|---|---:|---:|---:|---|
| Engine modules (`engine/*.py`) | 139 | 140 | **141** | +1: `engine/breaching.py` (drop 40). |
| Parser modules (`parser/*.py`) | 67 | 68 | **69** | +1: `parser/demolitions_commands.py` (drop 40, `breach` verb). |
| Server modules (`server/*.py`) | 16 | 16 | **16** | 0. |
| Schema version | 43 | 43 | **43** | Still 43 — **all of drops 34–43 are schema-neutral.** The additive-on-43 fields (chain `kind`, multi-slot questline keys, zone `threat_band`, encounter `min_band`/`max_band`) remain a **T3.20 state-preservation/backfill obligation** for pre-existing saves (see §1.5). |
| Test files (`tests/test_*.py`) | 319 | 335 | **342** | +7: T5-questline content/gating suites (drops 34–35), world-event flag-consumer suites (36–37), breaching suites (40/42). |
| SPA test files (`tests/spa/test_*.py`) | 49 | 49 | **49** | 0. |

**Schema-neutrality of the June 11–12 wave is load-bearing.** The entire
Gundark crafting lane (drops 1–11) added recipes, NPCs, and six engine
mechanics, but no migration — every credit movement it introduced routes
through `adjust_credits` (tuition sink, contraband-confiscation sink), and
every data row is read by an existing consumer. It applies on top of
schema 43 with no DB change.

### §1.4 What landed since the v51 May-30 cut

v51's May-30 body (the SYN tail + the web/map wave) is unchanged — read it
in v51 §1.4-A..F. The waves below landed after, in chronological order.
The first three were point-updated into a *chat-uploaded* v51 copy
(§1.4-G..K there) that never reached the on-disk file; v52 makes them
durable. The Gundark lane and web fixes are new here.

**G. Audit-remediation + economy-hardening tail (2026-06-04..05).**
Ledger chokepoint (drops 1.a–1.c), the audit-v2 9-item remediation
(market-state pool persistence, the spacedock yard-repair sink `F2`, NPC
craft-buyback refusal, the Tier-2 tuning batch), Drop-3 willing sinks
(gear insurance, home prestige, vanity titles, commissary, sabacc dens at
**schema 39 → 40**), CW era-compliance Drop 0a, death/respawn Drop 2, and
the **world-event narrative-layer pass — E1** (B3 era-cleanness: GCW
event/room-state strings + clean enum rename, plus repair of the inert CW
era-milestone feature) and **E2** (dormant *passive* world-event effects
wired at their faucets + repair of the `patrol_spawn_mult`
shadowed-duplicate phantom). New invariants: **§4.29** (world-event
mechanical-effect consumption — folds forward) and **§4.32** (credit
ledger chokepoint — restated below). Phantom catalog grows to eight
(#8 shadowed-duplicate-definition). Open decision **§8.19** (the six
world-event FLAG effects, `T2.E3`).

**H. Creature lane — Lane A Phase C (2026-06-05).** Creature natural-attack
faithfulness (§4.30) and the **creature-spoils harvest sink**
(`engine/creature_spoils.py`): a **no-credit, quality-capped** faucet —
`_SPOILS_QUALITY_CEILING = 65.0`, deliberately **below**
`crafting.T5_MIN_QUALITY = 75` so creature spoils can never feed the
top crafting tier — gated by a per-region cooldown. New invariant
**§4.31** (restated below). `composite_chitin` confirmed wired (maze
anomaly named-loot, T2 + T3).

**J. Force social-mechanics wave (2026-06-04..05).** The
`affect_mind`/`dominate_mind` mind-trick split, telekinesis disarm,
`life_sense`/`sense_force`, telepathy/`sense_lie`/farseeing/danger_sense.
Mechanics-only; no new invariant.

**K. Vendor sell V1 — Part A (2026-06-05).** `sell <item name>` liquidates
a *carried* inventory item to an NPC vendor (closing the gap that
looted/quest/org-issued/crafted gear had no casual NPC liquidation path).
Reuses the §4.32 chokepoint (`item_sale` tag), the §1.3 craft-buyback
refusal guard, bargain haggle, and city tax. Value is weapons-registry-key
or stored-value only (quest tokens / crafting inputs refused, not
floored). Deferred: `sell armor` (blocked on the equipment dual-format
debt, `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES`-adjacent) and
per-unit stack selling. Part B (web vendor panel) is post-launch.

**L. Communal objective + hunter consequence (2026-06-06).** The
dark-side cult **communal objective** — a Director-posted, world-scale
threat the whole playerbase rallies against, the counterpart to the
per-PC DSP hunter: `engine/communal_objective.py` (pure menace state
machine) + `engine/communal_objective_runtime.py` (IO) +
`parser/communal_commands.py` (`rally`) + `communal_objective_tick` +
`@director cult`. Schema **42 → 43** (`MIGRATIONS[43] communal_objective`).
New invariant **§4.33** (restated below — this is the invariant the
on-disk v51 mis-numbered as §4.31). Same session, CHANGELOG-only: the
hunter's PC-death collect-consequence (closing `T1.3.4`) and wiring the
dormant `contraband_scan` checkpoint effect.

**M. The Gundark crafting lane — drops 1–11 (2026-06-11..12). The
headline wave.** A complete equipment-crafting economy, A→G, shipped as
eleven drops over two days; the recent handoffs in `docs/handoffs/` are
its record. Net: **~40 recipes, 3 new NPCs, 6 engine mechanics — every
faucet landed with its sink (§4.35).** Schema-neutral throughout.

| Drop | What shipped | Watch / mechanic |
|---|---|---|
| **1 — skill-key P0** | `engine.character.canonical_skill_key()` (§4.34): a single canonicalizer (underscore→space + sanctioned aliases) routed through **both** resolution surfaces. Fixed a HEAD-wide latent: two key dialects (space-form registry vs underscore-form schematics/NPC yaml) resolved cross-dialect lookups as *untrained* and fell `_skill_to_attr` to its `"perception"` default. **Crafter training had never counted; every `melee_combat`-keyed NPC attacked/parried at raw attribute.** | ⚑ Trained pools now **jump** — suite tests pinning the old untrained rolls were pinning the bug; expect flips in combat-balance / mission-outcome pins. |
| **2 — Drop B: lawful weapons** | 14 schematics + 14 `weapons.yaml` rows (Avail 1–3), §5 rubric mass-applied, difficulties recomputed in-test. New use-skills `missile weapons` / `firearms` registered + combat-routed. | The whole-catalog gate test (every `skill_required` resolves) is what makes rubric mass-application safe from here on. |
| **3 — web onclick fix** | `client.html` is a strict-mode IIFE, so inline `onclick` resolves in **global** scope — 12 dead handlers (tour trio + every Webify modal's ✕/backdrop). All exported via `window.NAME`. `tests/spa/test_client_onclick_exports.py` (4) — a whole-file sweep + a jsdom real-click test. | "It renders ≠ it's wired": the Webify render contracts were tested; not one inline-handler click was. |
| **4 — Drop C: armor + Sela Tarn** | 10 non-powered armor schematics + 10 `type: armor` rows (in `weapons.yaml`, the registry the sheet reads — `armor.yaml` superseded by extend-don't-add). Trainer Sela Tarn at Kayson's. | ⚑ **The v22 dex-penalty latent:** armor Dex penalties stored signed (`"-1D"`), `DicePool.parse` silently returned (0,0), so penalties **never applied since v22** (BH armor included). Producer now returns magnitude — penalty-armor pools correctly **drop**. |
| **5 — P2P cap removed** | Both S51 enforcement blocks gone; the 5% tax + ledger tags + alt-account `[TRADE BLOCKED]` kept; the rolling window now feeds a **fail-open velocity alert** (`@economy`, caution 1,500 / critical 7,500). All three old-policy pin sites rewritten **with** the drop, guarded against restore. | Decision `ECON.p2p_cap_review = a`. Under market segmentation, one quality rifle legitimately trades above 1,500 — the cap fought the core loop. |
| **6 — Drop D: ordnance** | Pre-flight found `blast_radius` has **no combat consumer** (blast stays data + notes) and **ammo is wholly unmodeled** (every grenade was infinite-use). Ships a small **`single_use` consumption** mechanic (§4.35): single-use rows clear from the slot at attack **declaration**. Roster: Incendiary + frag schematics; Merr-Sonn Stun Grenade (the sanctioned `single_use: false` rechargeable exception, pinned). Thermal stays uncraftable. | ⚑ frag/thermal retro-flagged `single_use` — grenades stop being infinite (vetoable). |
| **7 — Drop E: field gear** | Three broken joints fixed: **Vek Nurren was a dangling trainer** (5 schematics named him, seeded nowhere) — now a Sullustan ex-scout at Lup's; **`uses` never decremented** (radiation suit / alarm were decorative) — mitigation gear with `max_uses` now spends a use when it averts a hazard, mutating **both** db + the live session dict; anti-theft alarm wired into `urban_danger`'s mitigation list. New items: Luma Flare (thrown burn) + Animal Excluder (new `roll_encounter` aversion seam). | ⚑ Consumable mitigation gear now **depletes**. |
| **8 — Drop F: espionage kit** | §5's dominant pattern — **skill-bonus gear — had no consumer anywhere.** `perform_skill_check` now applies the single best carried tool (`skill_bonus`, never stacks, dialect-canonical, fail-open) at the SRB.3 lead-bonus chokepoint, so every out-of-combat caller benefits. **Combat is structurally immune** (it never calls the chokepoint — pinned). Roster (zero new NPCs): Code Slicer, UniTech Patch, Medscanner. Also fixed two pre-existing reds with attribution. | Found en route: a missing `json` import the fail-open was masking. |
| **9 — Drop G: the finale (A–G complete)** | **Tuition** (§4.37): trainer recipes cost half base (floor 50 cr) under `schematic_tuition`; first lesson free once/char; new **`learn <name>`** command buys one at a time. PC↔PC teaching stays free (pinned). **Contraband** shipped WITH its enforcer: `contraband: true` flags the landed item; patrol boardings sweep carried inventory (Con-15-to-hide, confiscate + Class-4 infraction on fail). **The black market:** Disruptor Pistol / Predator Rifle (the 7D Heroic cap) / Anti-Vehicle Grenade — all q70, all contraband, all taught by **Gundark** (Whiphid dealer, Nar Shaddaa Undercity). Drops A/B/C "no contraband yet" guards all flipped into scope pins. | ⚑ Trainers no longer hand over whole catalogs free. Decision `CRAFT.schematic_tuition = a`. |
| **10 — market segmentation** | The audit found the hole in the **bare `buy` verb**: its fallthrough resolved the *entire weapon registry* by name, no stock/vendor/room gate, under a `ship_weapon_purchase` tag — so the Drop-G contraband band was credit-purchasable anywhere. Fix: **`vendor_stocked` on `WeaponData`, default closed** (§4.36); exactly 11 Avail-1 commons sell at book cost; everything else refuses with a craft/shop/"know the right people" redirect. The consistency test ("no band-40+ craft output on the open market") rejected two of the author's own first-cut picks. Grandfather: nothing stocked needed withdrawing. | ⚑ `buy <anything unstocked>` now refuses. Decision `CRAFT.market_segmentation = a`. |
| **11 — vendor-presence gate** | Buying now requires an in-room NPC with **`ai_config.vendor: true`** (§4.36) — the `trainer: true` precedent applied to commerce, disentangling vendors from mere hagglers (Lup the grocer was an implicit arms dealer; an empty room sold via a phantom "generic 3D vendor"). The haggle now reads **the vendor's own** Bargain (fixing the first-Bargain-NPC-in-room bug). 8 curated vendors across the settlements; **Kamino none** (commissary world); **Gundark NOT a vendor** (teaches, never retails — pinned). An uncurated-vendor sweep test makes future vendor adds deliberate. | ⚑ `buy` refuses outside vendor rooms. Decision `OBS.buy_verb_followups (a)`. |

Verification (sandbox, cumulative): the Gundark lane ran **602/602 green**
at drop 9; drops 10–11 added segmentation 9 + adjacent net 174 + the
vendor sweep. **Seven Windows watch items** carry into the next
`run_all_tests.bat` (the real gate): (1) trained pools jump · (2) armor
Dex penalties live · (3) grenades consume · (4) mitigation gear depletes ·
(5) tuition charges · (6) buy gates on stock · (7) buy gates on vendor
presence. Each is a *deliberate* behavior change; any suite test that
flips is pinning a now-fixed bug (the "pinning the bug" class — flag the
flip direction so triage is five minutes).

**N. Onboarding + difficulty-tiers + mid-game questline wave (drops
24–33, 2026-06-12..13).** The post-v52 wave; the arch doc body above was
cut at drop 23, so this is the catch-up block. Four threads:

- **Onboarding playability (drops 24–26).** All 7 chargen tutorial chains
  were non-completable pre-launch (inter-step teleport gap + a `+factions`
  registry miss); fixed with `engine/chain_graduation.py::apply_step_teleport`
  and a reachability coverage net (`test_chain_corpus_reachability_invariant.py`)
  that catches the stranding class statically. The `give` command shipped
  here. See the CW-tutorial-chains record.
- **B3 era sweep of the help corpus (drop 27).** Player-facing help/Codex
  strings de-Imperialized; SPA DOM tests unblocked. (Companion to the
  separate guide-cleanup effort in `help_guides_rework_plan_v1.md`.)
- **Difficulty-tiers / threat-band axis (drops 28–31, DIFF.1–4).** A NEW
  orthogonal world axis — see the new §3.5 below. `engine/threat_band.py`
  (`ThreatBand` FRONTIER/SETTLED/CONTESTED_MARCHES/WILDS), zone labeling,
  encounter-pool band gating, and bounty-reward scaling. Design:
  `difficulty_tiers_design_v1.md`.
- **Mid-game questline / multi-slot chain engine (drops 32–33).** The
  chargen-only tutorial-chain engine generalized to dual-slot to carry
  mid-game questlines — see the new §3.6 below. Drop 32's get/take/drop
  redirect stubs (`parser/builtin_commands.py`) are a pure-additive
  newbie-friendliness fix.

In flight (uncommitted at the time of this update): the **T5 master-trainer
questline** (`T2.DEF.t5_trainer_storyline`) — `kind: questline` chains
gating a master's T5 recipe behind a completed quest + faction rep ≥ 50,
riding the drop-33 multi-slot engine. First vertical slice (Jedi /
lightsaber master, `npcs_drop_b_t5_trainers.yaml`); 4 masters to follow.

### §1.5 What's still open

**Web client** (unchanged from v51 §1.5): mission-**giver** POI pins
(blocked on a non-existent giver→room field); the browser smoke-test of
the substrate map lane (Windows-only verification); Phases 2/4/5 mostly
post-launch. The Drop-3 onclick fix closed the interaction-wiring gap that
blocked the onboarding browser walk.

**Crafting follow-ups** (logged, post-lane — the Gundark queue):

- **`CRAFT.market_segmentation_impl`** — now the natural immediate
  follow-up: the ~40-recipe catalog vs vendor stock is segmented (drops
  10–11), but the broader vendor-family stock audit across Lane C is the
  remaining piece.
- **Powered-suit design pass** — Drop C deferred §3.2 powered/space suits
  wholesale (no `powersuit operation` skill, no mount consumer); pinned by
  test so nothing rosters piecemeal.
- **Mines/breaching design pass** — placement-mechanic ordnance deferred
  out of Drop D.
- **`OBS.quality_and_boosts_not_combat_read`** — combat reads damage AND
  protection from the registry **by key**, so crafted quality and
  experiment boosts never reach combat math (decay/value-side only today).
  Wants a deliberate quality→combat-stats pass.
- **CRAFT.HOOK passes** — restraints; the force-detector + suppression-cage
  anti-Jedi quest pair (kept HOOK-gated out of the lane as quest artifacts,
  never recipes; parsed-data pinned).
- **Buy-verb tail** (`OBS.buy_verb_followups` b/c): rename the
  `ship_weapon_purchase` tag for ground buys → **T3.19** (ledger-continuity
  caveat); the commissary `tracking_fob` "+1D Search" advert has no
  consumer — one `skill_bonus` field would put it on the Drop-F tool seam,
  pending an issued-item landing-shape check.
- **`WEBIFY.commissary_vendor_mode`** · Lane C remainder + Lane F · Kamino ·
  Drop-5 farming controls.

**Carried forward from v51** (unchanged): Coruscant Underworld full 40×40×3
region build (§8.13); intel-handler NPC seeding (§8.18); the engine Tier-2
launch-flexible items (PG.2.bounty follow-ups, PG.3 Act 3, F.7.n
Force-attribute seeding); the eavesdrop `target_char` design call. Vendor
V1 Part B (web vendor panel) is post-launch.

**RESOLVED since v52 (no longer open — see v52.2):** the world-event FLAG
effects (`T2.E3`) shipped in drops 36–37 (all **5**, not 6 — the "6" was a
miscount); the Director CW faction-model mapping (`TD.DIRECTOR_FACTION_MODEL_GCW`)
shipped drop 39 (a boundary mapping layer; the deeper internal re-key is still
correctly deferred, and the Director-scope review found the digest still uses the
`imperial`/`rebel` axis — a separate larger item).

**Correction (verified HEAD 2026-06-13):** **Weight of War is SHIPPED**, not
a pending follow-up — `engine/weight_of_war.py` (19 functions) +
`engine/wow_combat_hooks.py`, wired into `parser/combat_commands.py` (retreat
refusal + WoW hooks at three sites). Earlier doc copy listed "Weight of War
full impl" as a launch-flexible item; that is stale. (If a specific WoW
sub-feature remains, name it against HEAD — the base system and combat
integration are live.)

**State-preservation obligation (NEW, drops 28–33):** the additive
persisted fields shipped without a schema bump — chain-record `kind`,
multi-slot questline state keys, zone `threat_band`, encounter
`min_band`/`max_band` — MUST be covered by **T3.20** migration/backfill on
pre-existing characters and saves. The "launch = whole backlog to avoid
post-launch state surgery" rationale is breached at launch if these
new-on-43 fields aren't backfilled.

### §1.6 What's been steady

WEG D6 R&E core (stable since v40), dual WebSocket/Telnet networking, the
web-first directive, the `replaces:` protocol, the phantom-catalog
discipline (eight patterns), the `_FakeDB`-with-mutation-log fixture
pattern (§4.20). The SYN sequence (SYN.0→10) and the web-client SPA
visual port + hybrid raster substrate map lane remain shipped and closed.

---

## §3. Roadmap

### §3.1 Lanes (status at v52)

- **Engine lane — substantially closed; the difficulty + questline axes
  reopened it briefly.** SYN.0→10 shipped (v51); the June economy-hardening,
  creature, Force, and communal-objective waves shipped; the Gundark
  crafting lane (A→G) shipped; Weight of War is shipped (§1.5 correction);
  the difficulty-tiers axis (§3.5) and the mid-game questline engine (§3.6)
  shipped post-v52 (drops 28–33). Remaining engine work is the in-flight T5
  master-trainer questline content (§1.4-N), PG.2/PG.3, F.7.n, and the
  crafting design passes in §1.5.
- **Web-client lane — substantially shipped** (v51). The Drop-3 onclick
  fix closed the last known interaction-wiring gap. Remaining: the
  Windows-only substrate browser smoke-test, mission-giver POI pins
  (blocked), Phases 2/4/5 (post-launch).
- **Content lane — Coruscant Underworld** (full 40×40×3 region, §8.13) is
  the main pre-launch content task; intel-handler seeding is a small
  follow-up.
- **Crafting lane — the Gundark lane is COMPLETE (A→G).** What remains is
  the post-lane design passes and the stock-audit impl (§1.5).

### §3.2 Priority ranking (v52)

**Tier 1 — top priority**

| # | Item | Lane | Effort | Why |
|---|---|---|---|---|
| 1 | Brian: `run_all_tests.bat` on the Gundark lane (drops 1–11) | gate | — | Seven deliberate behavior changes (§1.4-M); the 7,700-test Windows run is the real gate. Expected flips are bug-pins. |
| 2 | Browser smoke-test the substrate map lane | web-client | Small (Windows) | The only launch-gating map verification the sandbox can't do (v51 carry). |
| 3 | Eavesdrop `target_char` design call | design | Small | Open since v45. |

**Tier 2 — important, queued**

| # | Item | Lane | Why deferred |
|---|---|---|---|
| 4 | `CRAFT.market_segmentation_impl` (vendor-family stock audit) | data + design | The craft economy it segments is now whole; the natural immediate follow-up. |
| 5 | Coruscant Underworld full 40×40×3 build | content | Main pre-launch content task (§8.13). |
| 6 | Powered-suit / mines-breaching / quality→combat design passes | engine + design | Deferred out of the Gundark lane, each pinned. |
| 7 | Intel-handler NPC seeding | content | Resolve live `hq_room_id` (§8.18 / v51 §10.6). |
| 8 | World-event FLAG effects (`T2.E3`) | design + engine | The six interactions (§8.19); reuse existing systems. |
| 9 | CRAFT.HOOK passes (restraints; anti-Jedi quest pair) | design + engine | Quest artifacts, not recipes. |
| 10 | PG.2.bounty / SRB / PG.3 Act 3 / F.7.n follow-ups | engine | Post-launch per-drops. |

**Tier 3 — polish / post-launch:** Padawan-Master expansion; cities
multi-city + legacy surface removal + 520 legacy tests retargeted; Director
AI CW tuning (T3.15); Space Wildspace; web-client Phases 2/4/5; Vendor V1
Part B (web vendor panel); `WEBIFY.commissary_vendor_mode`; buy-verb tag
rename (T3.19).

### §3.3 Closed since v51

The June economy-hardening tail (§1.4-G), the creature lane Phase C
(§1.4-H), the Force social-mechanics wave (§1.4-J), vendor-sell V1 Part A
(§1.4-K), the communal objective + hunter consequence (§1.4-L), and — the
headline — **the entire Gundark crafting lane, drops 1–11 (§1.4-M)**, plus
the web onclick-export fix, market segmentation, and the vendor-presence
buy gate. Three CRAFT design letters resolved (`market_segmentation = a`,
`schematic_tuition = a`, `p2p_cap_review = a`) and one OBS call
(`buy_verb_followups = a`). **Post-v52 (drops 24–33, §1.4-N):** onboarding
playability, the help-corpus era sweep, the difficulty-tiers axis (§3.5),
and the mid-game questline engine (§3.6).

### §3.5 Difficulty-tiers / threat-band axis (NEW, drops 28–31)

A NEW world axis orthogonal to security. `engine/threat_band.py`:
`ThreatBand` enum (1–4: FRONTIER / SETTLED / CONTESTED_MARCHES / WILDS),
`get_effective_threat()` (zone-inheritance resolver, same pattern as
security), `reward_multiplier()` (0.6× / 1.0× / 1.4× / 2.0×), and the
`frontier_lawless_conflict` validator (world_loader load-time check #7).
Wiring: `zones.yaml` `properties.threat_band` (default SETTLED if absent);
`wilderness_encounters.py` `min_band`/`max_band` pool filtering (now
**behavior-affecting**, drop 30); `bounty_commands.py` reward scaling at
the existing bounty faucet (drop 31); `builtin_commands.py` look-header
band tags + the read-only `+threat` command. **Invariant — orthogonal
axes:** threat (difficulty) is independent of security (combat-allowance);
the ONLY coupling is `frontier_lawless_conflict` (a tile cannot be both
FRONTIER-threat and lawless-security). Design:
`difficulty_tiers_design_v1.md`.

### §3.6 Mid-game questline / multi-slot chain engine (NEW, drop 33)

`engine/tutorial_chains.py` generalized from single-slot (chargen
onboarding only) to **dual-slot**: the legacy `_TUTORIAL_CHAIN_KEY` plus a
new `_QUESTLINE_KEY`, tracked in `CHAIN_STATE_KEYS`. Chain records gain a
`kind` field (default `"tutorial"`, validated against
`ALLOWED_CHAIN_KINDS`); every public chain hook gains an optional
`state_key` param defaulting to the tutorial slot (back-compat for all
legacy callers). `chain_events.py` walks all slots per event
(`_try_advance_all_slots`); `has_completed_chain` is a durable check used
for downstream gating. Player surface: `parser/questline_commands.py`
`mastery` verb (start/status/abandon/list) + an NPC-offer talk hook.
**Engine is behavior-neutral for onboarding** — the dual-slot machine
reduces to the old single-slot behavior when only the tutorial slot is
populated. This is the substrate the in-flight T5 master-trainer questline
(§1.4-N) rides on.

---

## §4. Architecture invariants — the reconciled block

**§4.1–§4.29 carry forward from v51 unchanged** — read them there. They
are: §4.1 web-first · §4.2 WEG-fidelity · §4.3 audit discipline · §4.4
boot/era flag · §4.5 seam vs. integration · §4.6 `replaces:` protocol ·
§4.7 smoke-test · §4.8 test ground-truth split · §4.9 chunked delivery ·
§4.10 single-source state transitions · §4.11 security model · §4.12
support-role buffs · §4.13 player cities · §4.14 wilderness co-location ·
§4.15 map renderer · §4.16 Q1 canonical-character policy · §4.17 +pvp
opt-in · §4.18 PG.1 death · §4.19 PG.2 bounty · §4.20 test-fixture
patterns · §4.21 cities web-UI safety · §4.22 combat-trigger state · §4.23
engine-canonical command discipline · §4.24 web wire-protocol discipline ·
§4.25 wilderness-only influence · §4.26 region-anchored cities · §4.27
parallel-ship discipline · §4.28 hybrid raster substrate render contract ·
§4.29 world-event mechanical-effect consumption.

**§4.30–§4.33 are re-established below from CHANGELOG truth.** The on-disk
v51 lost §4.30 entirely and mis-numbered the communal-objective invariant
as §4.31, colliding with creature-spoils. The correct numbering, verified
at HEAD:

### §4.30 Creature natural-attack faithfulness (re-established; Lane A Phase C, 2026-06-05)

A creature's combat output is its WEG-statted **natural attack**, not an
improvised attribute roll. Each creature template declares its
natural-weapon dice (claw/bite/venom DC, etc.); the combat resolver reads
that declared attack rather than falling back to a raw STR/Dexterity roll.
This is the creature-side counterpart to the equipment registry: a
creature with no declared natural attack is a data gap to fix, not a
silent attribute roll. (v51 "reserved" this slot but never wrote it — the
reservation note at its §4.31 confirms the intent.)

### §4.31 Creature-spoils faucet — no-credit, quality-capped (re-established; 2026-06-05)

Harvesting a downed creature is a **resource faucet that mints no
credits** and is **quality-capped below the top crafting tier.**
`engine/creature_spoils.py`:

- **No credits.** Spoils yield crafting materials / components only; the
  harvest path never calls `adjust_credits`. (Contrast the region-harvest
  faucet, which is rate-limited *and* mints credits.)
- **Quality ceiling `_SPOILS_QUALITY_CEILING = 65.0`**, deliberately
  **below `crafting.T5_MIN_QUALITY = 75`** — so creature spoils can *never*
  feed the top (T5) crafting tier. Verified at HEAD: both constants are
  present and the inequality holds.
- **Rate-limited** by a per-region cooldown, so spoils can't be farmed for
  unbounded material.

**Why an invariant:** an uncapped or credit-minting spoils faucet would
bypass the harvest economy's sinks and let the top tier be fed for free.

### §4.32 Credit-ledger chokepoint (re-established; 2026-06-04, drops 1.a–1.c)

**Every credit movement routes through the single funnel**
`adjust_credits(char_id, delta, "tag")`. No code path mints, debits, or
transfers credits by writing the balance directly. This is AST-guarded —
`tests/test_ledger_chokepoint_complete.py` walks the tree and fails on any
out-of-band balance write. Each new sink/faucet ships with a distinct
ledger tag (e.g. `schematic_tuition`, `item_sale`, `ship_repair`,
`p2p_tax`) so `@economy` can account for it automatically. This invariant
is the load-bearing precondition for every faucet/sink discipline below
and for the §4.35 faucet-with-sink rule.

### §4.33 Communal-objective discipline (re-established; was v51's mis-numbered §4.31; 2026-06-06)

*(Content unchanged from v51's §4.31 text — only the number is corrected
from §4.31 to §4.33, resolving the collision with §4.31 creature-spoils.)*

The dark-side cult **communal objective** is a Director-posted,
world-scale threat the whole playerbase rallies against — the counterpart
to the per-PC DSP hunter. Its discipline:

- **Pure / runtime / tick split.** `engine/communal_objective.py` owns the
  cult roster, the menace model (`advance_menace` / `apply_strike`),
  win/lose resolution (`resolve_state`), the cross-playstyle strike pool
  (`best_strike_pool_pips` — best of combat / investigation / persuasion /
  Force, so any archetype qualifies), and every player-facing string. No
  DB, no asyncio. `engine/communal_objective_runtime.py` owns all I/O; the
  cadence lives in `server/tick_handlers_progression.py::
  communal_objective_tick`. Escalation **never un-wins a routed cult**
  (`advance_and_resolve` resolves a terminal menace before applying any
  time-based rise).
- **Opportunities, never penalties.** A community win confers status; a
  loss confers nothing and the cult merely entrenches as flavor. No player
  is debited or penalised for a communal loss.
- **Prestige-domain, faucet-disciplined (extends §4.32).** Rewards are
  Republic faction-rep (`organizations.adjust_rep`, share-scaled) + a
  commemorative status flag (`attributes.communal_objective_wins`). **No
  credits are minted**; any future credit reward MUST route through
  `db.adjust_credits`. Payout is single-writer/idempotent under an
  `UPDATE ... WHERE state='active'` rowcount guard.
- **Era/Q1-clean.** All five cults are invented (no canonical figures, no
  GCW-faction strings); guarded by
  `test_drop4b_communal_cult.py::test_roster_is_era_and_canon_clean`.
- **Deterministic + idle-Ollama flavor only (NEVER Haiku).**

**Persistence:** one `communal_objective` row per uprising
(`MIGRATIONS[43]`); the active one is the latest row with `state='active'`;
per-contributor points + per-character strike cooldown live in
`contributions_json`.

---

**§4.34–§4.37 are NEW (the Gundark crafting lane, 2026-06-11..12).**

### §4.34 Skill-key canonicalization (NEW v52, Gundark Drop 1)

There is **one canonical skill-key dialect** (space-form: `melee combat`,
`blaster repair`), and **all** cross-surface skill lookups pass through
`engine.character.canonical_skill_key()` (underscore→space + the sanctioned
alias set: `computer_prog`, plural-transport, `pickpocket`,
`craft lightsaber`→technical) before resolution. The canonicalizer is
routed through **both** resolution surfaces — `SkillRegistry.get` and
`Character.get_skill_pool` (+ the miss-path canonical scan for NPC dicts) —
plus `advance_skill`, `perform_skill_check` ingress, `_get_skill_pool`,
`_skill_to_attr`, and the `train` write-site.

- **Data may use either dialect; the engine canonicalizes at the
  boundary.** Schematic `skill_required`, NPC `melee_combat:`/`first_aid:`
  yaml blocks (underscore-form) and the registry/chargen/combat literals
  (space-form) all resolve to the same skill.
- **The whole-catalog gate is mandatory.** `test_skill_key_resolution.py`
  asserts every `skill_required` resolves to a registered skill or the
  sanctioned set. This gate is what makes rubric mass-application of new
  schematics safe — a typo'd or unregistered key fails the suite, it does
  not silently roll the wrong dice.

**Why an invariant:** the pre-Gundark state had two dialects with **zero
translation** — cross-dialect lookups resolved as *untrained* and
`_skill_to_attr` fell to its `"perception"` default. The failure was
silent (untrained fallback never crashes) and survived eight green drops:
crafter training never counted, and every `melee_combat`-keyed NPC fought
at raw attribute. A lookup that can't fail loudly degrading to a
legal-looking no-op is the recurring bug class this invariant closes.

### §4.35 Craftable faucets ship with a consumption sink (NEW v52, Gundark Drops D/E)

A craftable item that the player can *produce* must not be an infinite
free resource where its real-world analogue is consumable. **Every
craftable consumable ships its consumption sink in the same drop**
(the faucets-and-sinks invariant, applied to crafting):

- **Single-use ordnance** (`single_use: true`) clears from the equipment
  slot at attack **declaration**, not resolution — because the resolver
  rolls the action's *captured* strings, the early clear is safe, and an
  explicit `with … damage …` override never eats the item. The sanctioned
  exception is book-rechargeable ordnance (`single_use: false`, e.g. the
  Merr-Sonn Stun Grenade), which is pinned.
- **Limited-use mitigation gear** (`max_uses`) spends a use when it
  *actually averts a hazard* and is removed at zero, mutating **both
  stores** — the DB and the live session dict the hazard tick re-reads
  (stale-sync would re-mitigate forever).
- **Consume at commitment, not resolution.** When an engine resolves
  declared actions from captured strings, the declaration point is the
  safe place to mutate equipment.

**Why an invariant:** at HEAD pre-Gundark, `blast_radius` had no combat
consumer and ammo was wholly unmodeled — every grenade was an infinite-use
weapon, and `uses`/`max_uses` were decorative. Craftable explosives on top
of that would have been a permanent-weapon printer. A craft faucet without
its sink is an economy hole.

### §4.36 Vendor buy-gate: stock + presence (NEW v52, Gundark Drops 10/11)

The open-market **`buy`** verb is gated on **two** independent checks, both
default-closed:

- **Stock gate (`vendor_stocked`).** `WeaponData.vendor_stocked` defaults
  **`False`** — a row is off-market until *deliberately* opened. `buy`
  prices and sells only stocked rows; everything else refuses with a
  craft/player-shop/"know the right people" redirect, and the `weapons`
  reference list reads "craft" for unbuyables. A consistency test enforces
  **no band-40+ craft output on the open market.**
- **Presence gate (`ai_config.vendor: true`).** Buying requires an in-room
  NPC flagged `vendor: true` — the `trainer: true` precedent applied to
  commerce. No flagged vendor → refusal; the haggle reads **the flagged
  vendor's own** Bargain (a generic 3D vendor only when the flagged vendor
  lacks the skill). Vendors are a **curated set** (an uncurated-vendor
  sweep test fails any unlisted `vendor: true`), so new vendors are
  deliberate decisions. A trainer (e.g. Gundark) is **not** automatically a
  vendor — teaching and retailing are separate flags.

**Why an invariant:** the bare `buy` fallthrough resolved the *entire*
weapon registry by name with no stock/vendor/room gate, so each Gundark
drop silently widened an unintended store — the contraband band was
credit-purchasable anywhere, and an empty desert room sold blasters via a
phantom "generic 3D vendor." Economy audits must walk every path credits
exit through, including command fallthroughs nobody thinks of as a store.

### §4.37 Trainer tuition is a credit sink; one free path stays open (NEW v52, Gundark Drop G)

Trainer-taught recipes are a **metered credit sink**, not a free
all-at-once grant:

- Each recipe costs `engine.crafting.schematic_tuition(schematic)` —
  **half base cost, floor 50 cr** — charged via `adjust_credits(...,
  "schematic_tuition")` (a real §4.32-routed sink that scales with recipe
  desirability). Bought one at a time via the **`learn <name>`** command;
  trainer must be in the room; broke students are refused cleanly.
- **Exactly one free path stays open:** the trainer's cheapest recipe is
  granted free, once per character ("first lesson's on the house"),
  through both the `talk` chat and `learn`. This keeps the paywall feeling
  like worldbuilding rather than a gate, and preserves any tutorial chain
  that does "talk trainer → craft" (verified: the KDY chain uses its own
  `+craft fetch` flow, not trainer grants).
- **PC-to-PC teaching stays free** (pinned) — payment there is RP + the
  trade verb, making crafter→apprentice a social loop.

**Why an invariant:** trainer learning was free and all-at-once (one
`talk` granted a 16+ schematic catalog), so `base_cost` fed only
repair/salvage with no tuition consumer. Replacing a free flow with a paid
one by keeping exactly one free path open is the pattern; the sink scales
with desirability automatically because tuition tracks base cost.

---

## §7. Design doc map — delta from v51

v51 §7 carries forward. Changed/added rows:

| Surface | Design doc | Status |
|---|---|---|
| Crafting equipment lane (Gundark A→G) | `sourcebook_enrichment_roadmap_v1.md` (Lanes) + the WEG40120 mechanics authority (CLAUDE.md "Sourcebook PDFs") | **A–G SHIPPED 2026-06-11..12** (drops 1–11); follow-up passes in §1.5 |
| Market segmentation / vendor gate | `CRAFT.market_segmentation` + `OBS.buy_verb_followups` (TODO design calls) | **SHIPPED** (drops 10–11); `market_segmentation_impl` stock audit pending |
| Creature lane (Phase C spoils) | `sourcebook_enrichment_roadmap_v1.md` Lane A | **Phase C SHIPPED** (`engine/creature_spoils.py`); §4.30/§4.31 |
| Vendor sell surface | `vendor_system_design_v1.md` | **V1 Part A SHIPPED** (`sell <item>`); Part B (web panel) post-launch |
| World events (effects) | `sw_mush_remediation_and_fun_additions_design_v1.md` + §4.29 | E1/E2 SHIPPED; 6 FLAG effects open → `T2.E3` (§8.19) |
| Communal objective | design III.3 | **SHIPPED**; §4.33 |

---

## §8. Outstanding decisions — delta from v51

v51 §8 carries forward. **Resolved since v51:**

- **`CRAFT.market_segmentation = a`** (2026-06-11): Avail-1 vendor-stocked
  at book cost + craftable; Avail-2/3 craft/loot/player-shop supply;
  Avail-4/X = the Drop-G black market. Implemented drops 10–11; the
  vendor-family stock audit (`_impl`) remains.
- **`CRAFT.schematic_tuition = a`** (2026-06-12): graduated tuition at 50%
  base (floor 50 cr), first-lesson-free, PC teach free. Implemented Drop G
  (§4.37).
- **`ECON.p2p_cap_review = a`** (2026-06-11): hard cap removed; 5% tax +
  ledger tag kept; threshold → fail-open `@economy` velocity alert.
  Implemented Drop 5.
- **`OBS.buy_verb_followups = a`** (2026-06-12): vendor-presence gate via
  `ai_config.vendor: true`. Implemented Drop 11. Tail (b) tag rename →
  T3.19, (c) tracking_fob `skill_bonus` candidate — both still open, small.
- **`CRAFT.avail_cutoff_and_demolitions`** (b/a): Kayson teaches the full
  lawful Avail 1–3 set; `demolitions` is ordnance's `skill_required`.

**Still open** (genuine, non-blocking): the world-event FLAG-effect
interactions (§8.19, `T2.E3`); the powered-suit, mines/breaching, and
quality→combat (`OBS.quality_and_boosts_not_combat_read`) design passes;
the CRAFT.HOOK passes (restraints, anti-Jedi quest pair); Coruscant zone
naming (§8.5); eavesdrop `target_char` (carried since v45).

**Update (v52.3, Jun 14):** most of the above is now resolved — FLAG consumers
wired (v52.2, resolves `T2.E3`), restraints + powered-suit + breaching all BUILT
(v52.3 §9), only **quality→combat** remains of that cluster (still open, balance-gated).
**NEW pending design call: `ERA.tutorial_v2_gcw_profession_chains`** (the one item in
`design_calls_pending_brian`) — the now-dormant GCW REBEL_CELL/IMPERIAL_SERVICE chains
need a permanent disposition: **(A)** delete, **(B)** keep dormant, or **(C)** CW-rewrite;
recommendation B-now / C-or-A depending on whether the legacy `tutorial_v2` profession-chain
system is kept vs deprecated for the `chains.yaml` questline engine. **NEW candidate (method):**
a broad allow-listed AST era scan over `engine/*.py` player-facing string constants, to close
the *partial-coverage test blind spot* that let the `tutorial_v2` era blocker (and the
wilderness/chain phantom refs) slip past the surgical curated-list tests.

---

## §9. Version history

- **v52.3 (Jun 14 2026)** — Jun 13–14 hardening + Director-scope wave (≈30 drops, multi-session
  parallel). Five themes, all schema-additive (`SCHEMA_VERSION 43→44`, migration-gated):
  **(1) Director scope expansion — COMPLETE, resolves the v52.2 finding.** The "Director runs
  only 6 Mos Eisley zones + dead `_apply_influence_delta`" item is closed: native CW faction axis
  over 34 zones (`director-living-galaxy`), live API path (SSL fix + 2 real bugs, drop 51),
  adaptive-spend governor (skip-empty-turns + auto cadence + `@director fidelity` toggle),
  **economy perception** (`_compile_economy_digest` — a pure read of the `credit_log` funnel, no
  new write seam), soft **economic NUDGES** (decision A — opportunity seeds only, never
  price/yield levers), and economy prompt-tuning. Per `director_scope_and_adaptive_spend_v1.md`.
  **(2) Runtime era-guard layer (NEW cross-cutting hardening theme).** `engine/era_validator.py`
  is now the single source of truth for the banned-GCW-token + canonical-figure canon, and EVERY
  LLM→player surface validates against it at runtime: the Ollama idle queue (`ollama-era-guard`),
  the ambient dynamic pool (`ambient-dynamic-pool-era-guard`), the primary `talk <npc>` dialogue
  path (`npc-dialogue-era-guard`), and the new idle-GPU ambient-flavor feeder. The static side
  closed a **live era BLOCKER**: `tutorial_v2.py`'s GCW REBEL_CELL/IMPERIAL_SERVICE profession
  chains were reachable in CW and are now gated dormant (`tutorial-v2-era-remediation`). This
  closes the LLM-era-leak class — era invariant B3 now holds at the *generation* boundary, not
  just over static strings. **(3) Equipment/combat forks BUILT** (the v52.2 "3 pending"): per-slot
  equipment-instance accessor stage 1 (drop 47), restraints/handcuffs engine + verb layer (drops
  48–49, consent/defeat-gated), powered armor + the Powersuit Operation skill (drop 50).
  **(4) State-preservation / migration safety (T3.20 underway).** Safe character-load (guarded
  attrs/force parse + force-sensitivity fail-safe, Ruling 5) + a migration-framework integrity
  harness (`SCHEMA_VERSION == max(MIGRATIONS)` + reboot data-preservation, schema 43→44).
  **(5) Defect-hunt remediation wave** (adversarial workflow → verify → fix): encounter spawn-count
  range honored (bias-low, `TD.ENCOUNTER_COUNT_RANGE_IGNORED` resolved), 4 phantom wilderness
  creatures + global resolution guard, chain combat-fallback reachability Class 5, questline
  graduation re-fire, idle-queue broadcast/persist coupling, breaching honest-failure, and the
  **space-encounter skill-check funnel bypass** (all 5 `encounter_*.py` `_skill_check` helpers
  always fell back to skill-ignoring raw 3D → now call the sync `perform_skill_check` correctly).
  Plus lore ingestion (sourcebooks → ~1,978-entry grounded lorebook), 2 achievement hooks wired
  (`on_scene_completed`/`on_org_rank_reached` — others remain defined-but-unwired, see
  `HANDOFF_defect_hunt_findings_2026-06-14.md`), and `stat-d6`/`world-yaml` agent skills. Counts:
  engine 143, parser 70, tests 370, spa 49, schema 44. **1 NEW design call pending Brian**
  (`ERA.tutorial_v2_gcw_profession_chains` — delete vs keep-dormant vs CW-rewrite the now-dormant
  GCW chains). NEW method finding (see §8): the **partial-coverage test blind spot** — surgical
  curated-list tests (era-cleanness, per-biome reachability) miss whole files/objects; the era
  blocker + the wilderness/chain phantom refs all slipped through that gap.

- **v52.2 (Jun 13 2026)** — drops 34–43 catch-up. Folds in the post-v52.1 wave:
  **T5 master-trainer questline COMPLETE** (drops 34–35 — 5 trainers in
  `npcs_drop_b_t5_trainers.yaml`, 5 questlines, all T5 schematic gates, per-step
  reward consumer in `engine/chain_rewards.py`) — this **supersedes the v52.1
  "in-flight T5 questline" note**; **all 5 world-event FLAG consumers wired**
  (drops 36–37 — rare_vendor, krayt_bounty, distress, hutt_auction, brawl in
  `engine/world_events.py`) — **resolves T2.E3 / the "6 FLAG effects open" item,
  which was always 5 not 6**; commissary sellback (38), Director CW faction-order
  mapping `normalize_faction_order_code` (39), **breaching CHARGES + obstacle
  placement** (`engine/breaching.py` + `world_writer.py::_write_breachables`,
  drops 40/42 — only placed proximity MINES remain deferred), per-region harvest
  override (41), T5 ship-part effects verified (43). Counts: engine 141, parser
  69, tests 342; server 16, spa 49, schema 43 (all drops schema-neutral). NO new
  §4 invariants. **8 design calls resolved** (flag_consumers, commissary,
  faction_mapping, breaching split + placement, harvest_skill, rare_no_vendor,
  force_detector-DEFER — moved to `design_calls_resolved_recent`); **3 forks
  remain pending Brian** (quality_combat_armor/consumables, powered_suit,
  restraints — all balance/equipment-migration-gated). NEW finding folded into
  the roadmap: the **Director AI runs only 6 Mos Eisley zones** and its primary
  influence lever is a dead call (`director.py:896` → undefined
  `_apply_influence_delta`); see `director_scope_and_adaptive_spend_v1.md` — a
  pre-launch scope-expansion candidate, not a tuning item.

- **v52.1 (Jun 13 2026)** — post-v52 catch-up pass (drops 24–33). The
  v52 body was cut at drop 23; this pass folds in the onboarding-playability
  + difficulty-tiers + mid-game-questline wave (§1.4-N). NEW subsystem
  descriptions: **§3.5 difficulty-tiers / threat-band axis** (`engine/threat_band.py`,
  drops 28–31) and **§3.6 mid-game questline / multi-slot chain engine**
  (drop 33). Corrected §1.3 HEAD counts (engine 140, parser 68, tests 335);
  corrected the stale "Weight of War pending" claim (it is shipped). Flagged
  the **T3.20 state-preservation obligation** for the additive-on-schema-43
  fields (chain `kind`, questline slots, `threat_band`, encounter bands).
  `SCHEMA_VERSION` still 43. The in-flight T5 master-trainer questline noted
  as building on §3.6. (Sequencing/readiness analysis lives in the session
  handoff, not the arch doc.)

- **v52 (Jun 12 2026)** — reconciliation + delta. (1) **Fixes the v51
  invariant-numbering collision** the 2026-06-06 audit flagged: restores
  §4.30 (creature natural-attack), §4.31 (creature-spoils no-credit faucet),
  §4.32 (credit-ledger chokepoint), and **renumbers the communal-objective
  invariant from the mis-numbered §4.31 to §4.33** — each re-established
  from CHANGELOG truth and verified at HEAD. (2) **Folds in the June
  waves** that the on-disk v51 never carried: the economy-hardening tail
  (§1.4-G), creature Phase C (§1.4-H), Force social mechanics (§1.4-J),
  vendor-sell V1 (§1.4-K), the communal objective + hunter consequence
  (§1.4-L). (3) **Documents the headline June 11–12 Gundark crafting lane,
  drops 1–11** (§1.4-M) — ~40 recipes, 3 NPCs, 6 engine mechanics, four
  new invariants §4.34–§4.37 (skill-key canonicalization, craftable
  faucet-with-sink, vendor buy-gate, tuition sink) — plus the web
  onclick-export fix, market segmentation, and the vendor-presence gate.
  Five design letters resolved. HEAD counts: engine 139, parser 67,
  server 16, tests 319, spa-tests 49. **`SCHEMA_VERSION = 43`** (Gundark
  lane schema-neutral). Folds v51's durable §2/§5/§6/§10 forward by
  reference. Seven Windows watch items pending `run_all_tests.bat`.
- **v51 point-update (Jun 6 2026)** — communal objective subsystem
  (mis-numbered §4.31 on disk; corrected to §4.33 here), schema 42 → 43.
- **v51 point-update (Jun 4 2026)** — audit-remediation tail (§1.4-G),
  world-event consumption invariant §4.29, phantom catalog → eight,
  schema 39 → 40.
- **v51 (May 30 2026)** — full consolidation: SYN tail (SYN.6–10), SPA
  visual port, hybrid raster substrate map lane (§4.28), map A/D/B +
  environment + bearing + POI feeds. Web-client lane moved from paused to
  live. Header schema-of-record was left at 35 (never reconciled — see
  this doc).
- **v50 (May 25 2026)** — SYN wave consolidation; invariants §4.25–§4.27;
  §5.9 roll-up discipline.
- **v49 (May 24 2026)** — web-client lane opened as first-class.
- **v48 (May 23 2026)** — post-Player-Cities v1.2; invariants §4.21/§4.22;
  phantom pattern 7.
- *(v40–v47 history as v51 §9 records it.)*

---

## §10. Closing notes

v52's reason for existing is the lesson it encodes: **a doc carried inside
the per-drop drop-zip will round-trip lossily.** The on-disk v51 lost three
invariants and gained a numbering collision precisely because point-updates
were applied to a chat-uploaded copy that diverged from the file on disk.
The 2026-06-06 decision — pull the arch doc out of the drop-zip; let
CHANGELOG + TODO be the authoritative per-drop record; owe a dedicated
reconciliation — is now discharged. **The CHANGELOG was correct and
complete throughout; this doc is rebuilt from it, verified at HEAD.**

v51's §10.1–§10.5 retirement notes carry forward. v52 adds: the Gundark
crafting lane closed on its own fiction (the catalog's in-world compiler
selling the catalog's contraband), and every faucet in ~40 recipes landed
with its sink — the faucets-and-sinks invariant scaled to a whole content
lane without a single schema change.

**The path to launch is short:** the Windows full-suite gate on the
Gundark lane (seven expected bug-pin flips), the substrate browser
smoke-test, the Coruscant Underworld content build, and a handful of
resolved-but-unbuilt design passes. The two largest historical surfaces —
the SYN sequence and the web-client port — remain behind us.

---

*v52 reconciles the v51 invariant block (§4.30–§4.33 restored from
CHANGELOG truth, verified at HEAD) and folds in the June 2026 waves,
headlined by the Gundark crafting lane (drops 1–11): a complete
equipment-crafting economy delivered A→G, schema-neutral, with four new
invariants and every faucet shipped beside its sink. Current
`SCHEMA_VERSION = 44` (the v52.1–v52.3 §9 catch-up entries fold the Jun 13–14
waves forward — Director scope, the runtime era-guard layer, equipment forks,
and the defect-hunt remediation). v51 stays on disk as the detailed reference
for the sections v52 folds forward.*
