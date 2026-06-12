# Security Model — Design v1

**Status:** Locked decisions, ready for implementation breakdown
**Author:** Brian + Claude (design session, May 2026)
**Builds on:** `security_zones_design_v1.md` (existing 3-tier model), `wilderness_system_design_v1.md`, `security_drop6_territory_control_design_v1.md`, `player_cities_design_v1_2.md`, `clone_wars_era_design_v3.md`
**Era:** Clone Wars (~20 BBY). Republic vs. CIS. No Rebel/Imperial framing.

---

## 0. Why this doc exists

The existing `security_zones_design_v1.md` was written under GCW assumptions (Imperial Garrison, criminal vs. Imperial influence overlays, stormtroopers in martial-law upgrades) and predates the Clone Wars pivot. The mechanical 3-tier model (secured / contested / lawless) is sound and shipped through Drops 1–5 + 6A–6B, but two questions are unsettled:

1. **Where should the boundary between contested and lawless actually fall** in the live CW world? The original doc's per-zone catalog mapped GCW zones; the CW-era zone catalog in `data/worlds/clone_wars/zones.yaml` was authored to fit the new content but the *security assignments* haven't been deliberately re-decided.

2. **What's the right scope for hand-built lawless content?** The tension surfaced through the player cities discussion: if cities and territory PvP are the endgame, where does that play happen? Three candidate models exist (current hybrid, hand-built-secured-only, Cantina Sanctuary).

This doc resolves both. It is the canonical assignment of security tiers for the CW-era world and the policy that future zone authors should follow.

---

## 1. Locked decisions (the short version)

- **Cantina Sanctuary model.** Hand-built rooms default to **secured**. A hand-curated set of zones gets **contested**. Wilderness owns lawless and the bulk of contested.
- **No GCW security assignments are inherited.** All CW zone security is decided fresh in this doc.
- **Wilderness regions get per-zone influence** (per `player_cities_design_v1_2.md` §21.5).
- **The `Director AI dynamic overlay` mechanism is preserved** but its triggers are re-tuned for CW factions.
- **Settled cities can exist in the curated contested zones** but are rare; **frontier (wilderness) cities are the default** for territorial play.
- **Per-tile PvP in wilderness works as it does today.** No change. What's new is per-region influence accumulation feeding the Drop 6D contest mechanic.

---

## 2. The three tiers — what they mean in CW

The mechanical rules from `security_zones_design_v1.md` §2 stand unchanged:

| Tier | PvE | PvP | Display |
|---|---|---|---|
| **Secured** | Blocked | Blocked | `[SECURED]` blue |
| **Contested** | Allowed | Consent required | `[CONTESTED]` yellow |
| **Lawless** | Unrestricted | Unrestricted | `[LAWLESS]` red |

What changes is the *flavor text* and which zones live where.

### 2.1 Secured — under authority

The Republic, planetary government, or Hutt enforcers (depending on planet) maintain order. Combat is suppressed by ambient enforcement — clone troopers, CSF officers, Hutt muscle, monastery custodians.

CW-flavored refusal text examples (replace any Imperial-flavored text in the engine):

- Coruscant: *"Coruscant Security Force patrols this area. Drawing a weapon here would summon a full response squad in seconds."*
- Tatooine: *"Even in Mos Eisley, Jabba's enforcers maintain order in his territory. Starting trouble here ends badly."*
- Nar Shaddaa: *"This level of the Smuggler's Moon is Hutt-claimed. Their enforcers don't tolerate freelance violence."*
- Kuat: *"Kuat Drive Yards security is everywhere. The corporate response would be immediate."*
- Kamino: *"Kaminoan oversight is total. Violence here is a violation of Kaminoan custom AND clone training protocol."*

### 2.2 Contested — fringe authority

Authority exists but is thin or partial. Combat is technically illegal but enforcement is unreliable. PvP requires the standard challenge/accept consent flow.

CW flavor: smuggler hangouts, fringe districts, the edges of legal commerce, neutral-but-tense crossroads, shadowport approaches, pirate-adjacent cantinas.

### 2.3 Lawless — no authority

No effective enforcement. Anything goes. Players can attack other players freely (with the existing one-time entry warning per session).

CW flavor: deep wilderness, criminal strongholds, war-active surface zones, contested space far from Republic patrol routes.

---

## 3. Per-planet zone security catalog (CW canonical)

This is the canonical security assignment for all CW zones. When zone files are next touched (the Apr 30 loader audit identified zone naming drift that requires a YAML pass anyway), these values should be applied.

### 3.1 Coruscant (7 zones, ~55 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `jedi_temple` | Secured | Jedi Order's own house. No combat. Period. |
| `senate_district` | Secured | Senate Guard, Republic intelligence, official functions. |
| `commercial_district` | Secured | CSF heavy patrols, civilian commerce. |
| `monumental_district` | Secured | Tourist/cultural heart. CSF presence high. |
| `entertainment_district` | Secured | Outlander Club tier — security is real even if patrons are not. |
| `southern_underground` | **Contested** | Approach to the Underworld. Authority thins. CSF withdrawn after dusk. |
| `coruscant_underworld` (wilderness) | Lawless | Wilderness region — see §4. Includes `vent` exit from `southern_underground`. |

The single contested hand-built zone (`southern_underground`) is the Cantina Sanctuary archetype: it's in the city, it's hand-built, and it's where canon-flavored danger lives. Players who want PvP on Coruscant find it here, or they go down into the Underworld wilderness.

### 3.2 Tatooine (7 zones, 54 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `market` | Secured | Jabba's tacit protection. Daylight commerce. |
| `cantina` | Secured | Chalmun runs a tight house. Bouncers, no draws. |
| `residential` | Secured | Homes, monastery, hotel. Quiet. |
| `civic` | Secured | Bank, clinic, prefect's office. Republic-coded. |
| `spaceport` | Secured | Republic customs presence (CW-era — small but real). |
| `outskirts` | **Contested** | City edges, back alleys, between-zones. Patrols thin. |
| `wastes` (Jundland) | Lawless | Open desert. No law. Tuskens. |
| `dune_sea` (wilderness) | Lawless | Wilderness region (Drop 9, the Village). See §4. |

Tatooine's `outskirts` is the second Cantina-Sanctuary archetype — a small contested handbuilt zone that gives the planet some PvP texture without making the cantina itself dangerous.

### 3.3 Nar Shaddaa (4 zones, 30 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `ns_landing_pad` | Secured | Hutt-controlled commerce port. Even thieves need somewhere to land. |
| `ns_promenade` | **Contested** | Hutt commercial level. Tense, watched, but PvP via consent. |
| `ns_undercity` | Lawless | Lower levels. Authority gone. |
| `ns_warrens` | Lawless | Deepest level. Worst of the worst. |

Nar Shaddaa is the only planet where the bulk of the hand-built content is contested+lawless. This is intentional — Nar Shaddaa is the canonical "lawless port" planet, and forcing it into mostly-secured would undercut its identity.

### 3.4 Kuat (3 zones, 30 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `kuat_main_spaceport` | Secured | KDY corporate security. Total surveillance. |
| `kuat_city_embassy` | Secured | Embassy district. Polite, watched. |
| `kdy_orbital_ring` | Secured | Shipyard work zones. Workplace-strict. |

Kuat is fully secured. This is a deliberate choice — it's the Republic-industrial anchor, and contested/lawless content there would betray its lore identity. Players who want PvP go elsewhere.

### 3.5 Kamino (3 zones, 25 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `kamino_tipoca_city` | Secured | Kaminoan custom + clone training oversight. |
| `kamino_cloning_halls` | Secured | Restricted access. Sensitive. |
| `kamino_ocean_platform` | Secured | Outdoor work platforms. Regulated. |

Kamino is fully secured for the same reason as Kuat — its lore identity is tightly controlled. The "danger" on Kamino is narrative (Sith infiltration plotline material for the Director) not mechanical PvP.

### 3.6 Geonosis (4 zones, 35 rooms)

| Zone | Security | Rationale |
|---|---|---|
| `geonosis_petranaki` | **Contested** | Trade arena entrance. CIS-tolerated, neutral-tense. |
| `geonosis_surface` | Lawless | War-active surface. B1 droid patrols, active combat. |
| `geonosis_deep_hive` | Lawless | Geonosian territory. CIS-allied but unpredictable. |
| `geonosis_arena` | **Contested** | Historical arena. Tourist-trap with edges. |

Geonosis is the **inverse-faction** planet (per `clone_wars_era_design_v3.md`). Republic-aligned PCs encounter active hostility from B1 droid patrols in the lawless zones; CIS-aligned PCs move freely. The `faction_override` mechanism from `security_zones_design_v1.md` §3.2 handles this — Republic PCs in Geonosis surface zones experience effective security as Lawless even if a CIS-aligned org has claimed contested-tier upgrades there.

---

## 4. Wilderness — owns null-sec entirely

Wilderness regions are **lawless by default**, with three exceptions:

- **Landmark rooms with explicit `security_override`** (per `wilderness_system_design_v1.md` §6.1). Used sparingly: a Republic outpost might be contested-for-citizens, or a peaceful enclave might be secured.
- **Citizen rooms inside frontier cities** (per `player_cities_design_v1_2.md` §6.2): contested for citizens, lawless for outsiders.
- **Regional Director events** (per `wilderness_system_design_v1.md` §6.6): a "Republic Operation" event could temporarily upgrade a region to contested for the duration.

Currently planned wilderness regions:

| Region | Planet | Security | Notes |
|---|---|---|---|
| `coruscant_underworld` | Coruscant | Lawless | Drop 5; 40×40×3 grid |
| `dune_sea` | Tatooine | Lawless | Drop 9; hosts the Village quest content |
| Future regions | Various | Lawless | Default for any new region |

Per `player_cities_design_v1_2.md` §21.5, **wilderness regions get per-zone influence** in the Drop 6 framework. This means:
- Influence accrues per-region the same way it accrues per-zone in hand-built space.
- Org orgs can establish "regional dominance" through presence + activity.
- The Drop 6D contest mechanic fires on wilderness regions identically to zones.
- Frontier cities are fully contestable.

What is **NOT** added: per-tile claims (already explicitly rejected in wilderness design — invites tedious micro-management), per-tile contests (same reason), or per-tile influence accumulation (the region is the unit).

---

## 5. The Cantina Sanctuary policy

This is the policy that future zone authors should follow.

### 5.1 The default is secured

When authoring a new hand-built zone, **default it to secured** unless there's a deliberate canonical reason to do otherwise. This is the inverse of the `security_zones_design_v1.md` original default (`'contested'`), which was correct for an MMO design pre-pivot but is wrong for the world we're building.

### 5.2 Deliberate exceptions

A hand-built zone gets **contested** status only if all of the following are true:

1. **Canon supports it.** The location is canonically a fringe/dangerous space (Mos Eisley outskirts, Nar Shaddaa promenade, Coruscant southern underground).
2. **It's authority-thin, not authority-absent.** Some enforcement exists; PvP requires consent.
3. **It anchors a narrative role** that the secured/lawless tiers can't fill (smuggler hangout, fringe market, faction-edge).

A hand-built zone gets **lawless** status only if all of the following are true:

1. **Canon supports it strongly.** The location is canonically dangerous, lawless, or active warfront.
2. **It's adjacent to wilderness** (or is itself the transition layer to wilderness).
3. **It's not a primary social/commerce hub.** Lawless cantinas would betray most planet identities; lawless mining tunnels are fine.

### 5.3 The CW catalog (as decided in §3)

| Tier | Hand-built zones |
|---|---|
| **Secured** | 21 zones (the bulk of every planet) |
| **Contested** | 5 zones — Coruscant `southern_underground`, Tatooine `outskirts`, Nar Shaddaa `ns_promenade`, Geonosis `geonosis_petranaki` + `geonosis_arena` |
| **Lawless** | 5 zones — Tatooine `wastes`, Nar Shaddaa `ns_undercity` + `ns_warrens`, Geonosis `geonosis_surface` + `geonosis_deep_hive` |

That's **31 hand-built zones total**: 21 secured (68%), 5 contested (16%), 5 lawless (16%). Plus 2 wilderness regions (Coruscant Underworld, Dune Sea) carrying the full lawless load.

This ratio is the design intent: secured space dominates hand-built content; PvP/territorial content lives primarily in wilderness; a small curated set of hand-built zones provides the canon-flavored fringe content that wilderness can't supply.

### 5.4 Future planet authoring

Any new planet added post-launch follows this policy:
- Start with all zones secured.
- Add 1–2 contested zones for canonical fringe content.
- Add lawless zones only if the planet's identity demands it (deep mines, war zones, criminal-controlled surface).
- If you need lawless coverage but the planet doesn't support hand-built lawless, **add a wilderness region** instead. That's what wilderness is for.

---

## 6. Director AI overlay — CW-flavored re-tuning

The dynamic security shift mechanism from `security_zones_design_v1.md` §6 is preserved. What changes is the trigger conditions, since GCW factions (Imperial / Rebel / criminal) don't apply.

### 6.1 New CW overlay rules

```python
# engine/security.py — _apply_director_overlay() refactor

# Republic crackdown — upgrade one tier
if zs.republic >= 75:
    LAWLESS → CONTESTED, CONTESTED → SECURED

# Republic martial law (extreme)
if zs.republic >= 90:
    result = SECURED  # Force regardless

# CIS surge — downgrade one tier (Separatist disruption)
if zs.cis >= 80:
    SECURED → CONTESTED, CONTESTED → LAWLESS

# Criminal surge — downgrade one tier (Hutt territory expansion)
if zs.criminal >= 80:
    SECURED → CONTESTED, CONTESTED → LAWLESS

# Both rules can apply in sequence, e.g. Republic 75 + CIS 80 = no net change
```

The director_config.yaml extension required for this is small — adding `republic`, `cis`, and `criminal` axis support to whatever GCW-flavored axes the existing config exposes. (Per the recent NPC drops + Drop 6a Director refactor, this should already be wired; flagged for verification when the doc is implemented.)

### 6.2 Geonosis inverse-faction handling

Geonosis is the special case. Per `clone_wars_era_design_v3.md`, Geonosis is CIS-friendly:

```python
# Per-planet override for Geonosis: CIS plays the "stabilizing" role
if planet == "geonosis":
    if zs.cis >= 75:
        LAWLESS → CONTESTED, CONTESTED → SECURED  # for CIS-aligned PCs
    if zs.republic >= 80:
        SECURED → CONTESTED, CONTESTED → LAWLESS  # Republic op disruption
```

Combined with the existing `faction_override` mechanism (per-room flag), this gives Geonosis its inverse-faction identity without inventing a parallel system.

### 6.3 Director event triggers

Director-narrated events that temporarily shift security:

| Event | Effect | Duration |
|---|---|---|
| Republic Operation | Contested → Secured in target zone | Per Director, typically 12–48h |
| Separatist Incursion | Secured → Contested, Contested → Lawless | Per Director, typically 6–24h |
| Hutt Crackdown | Restores order in Nar Shaddaa zones (Lawless → Contested) | Per Director |
| Coruscant Lockdown | All Coruscant zones forced Secured | Rare, 1–6h |
| Geonosian Hive Awakening | Geonosis surface zones forced Lawless for everyone | Per Director |

These are flavor events. The mechanical security shift is real but bounded.

---

## 7. Migration plan

The current state of zone security in the live CW database is **not deliberately set** — zones default to `'contested'` per the schema default, and any explicit values in `data/worlds/clone_wars/zones.yaml` may not match this doc.

Three steps to bring the live world into compliance:

### 7.1 Step 1 — Audit current state

Run a quick check against the live DB to see what each CW zone currently has set as security. This is a one-line SQL query against the `zones` table; result feeds Step 2.

### 7.2 Step 2 — Update zones.yaml

Apply the §3 catalog to `data/worlds/clone_wars/zones.yaml`. This is a YAML edit, no code changes. Zones not listed in §3 (if any exist that shouldn't) get flagged for builder review.

This step is naturally bundled with the **Apr 30 zone-naming-drift audit fix** that's already a pending YAML edit. Both are the same file.

### 7.3 Step 3 — Update existing live DB

Schema migration runs on next boot to apply the new security values to the `zones` table. The `@security` admin command can also do this immediately for any zone:

```
@security <zone> = <level>
```

Per `security_zones_design_v1.md`, this takes effect instantly without a server restart.

### 7.4 No code changes required for catalog application

The catalog change is data-only. The Director AI overlay re-tuning (§6) is a small code change to `engine/security.py` (replacing GCW faction names with CW), which is bundled with the broader Drop 6b Director refactor.

---

## 8. Implications for adjacent designs

### 8.1 Player cities

`player_cities_design_v1_2.md` §1 says cities exist only in contested or lawless zones. With this doc:

- **Settled cities** can be founded only in 5 contested zones (rare) or 5 lawless zones (canonically dangerous).
- **Frontier cities** are the default — wilderness regions are 100% lawless (modulo overrides).
- This makes wilderness the predominant home for territorial play, which matches the v1.2 design intent.

### 8.2 Drop 6 territory control

Drop 6's existing infrastructure (claims, influence, contests, hostile takeover) operates over zone+room granularity. With wilderness regions getting per-zone influence (per §4), Drop 6 covers wilderness without modification beyond the `wilderness_region_id` field added to the `zone_influence` table.

### 8.3 Tutorial flow

Tutorial routes new players through hand-built rooms. With those rooms predominantly secured, **new players cannot accidentally walk into PvP**. This is a major safety improvement over a hybrid model where contested rooms might be on a tutorial path. Worth flagging for the tutorial team but no design change required — the tutorial already routes through commercial/cantina/spaceport zones, all of which become secured.

### 8.4 Bounty hunter Guild PvP override

Per `progression_gates_and_consequences_design_v1.md` §4 + the existing `Guide_05_Security_Zones.md` §5, the BH override allows PvP in contested zones for active claimed contracts. With contested zones now scarce (5 hand-built), the BH override is functionally a wilderness-targeting mechanic. This is fine — bounty hunting against fringe PCs naturally happens in fringe space.

The override does NOT extend to secured zones (still blocked) or lawless (already free PvP). Unchanged.

### 8.5 Lawless zone incentives

The lawless-zone incentives from `security_zones_design_v1.md` §7 (rare crafting resources, higher-paying missions, smuggling routes, +25% CP tick rate, advanced trainers) move with the lawless zone catalog. Most of those incentives now live in wilderness regions, which is correct — the deep desert and the underworld are where the rare stuff is. A few stay in hand-built lawless (Nar Shaddaa undercity black-market vendors, Geonosis surface war loot) which is also correct.

---

## 9. Open questions

1. **Should Coruscant `southern_underground` be lawless instead of contested?** It's the transition layer to the Coruscant Underworld wilderness. Argument for lawless: continuity with the wilderness it borders. Argument for contested (current decision): it's still a hand-built zone, the wilderness is the lawless layer, and the contested status gives it gameplay distinction. **Locking as contested for v1; revisit if the transition feels jarring in playtest.**

2. **Should Geonosis `geonosis_petranaki` be lawless instead of contested?** It's a war-adjacent planet. The contested status assumes a tense neutral arena entrance; lawless would make it a free-PvP zone. **Locking as contested; the lawless content on Geonosis is in the surface and deep hive.**

3. **What happens to existing characters caught in zones when security changes?** Migration applies cleanly to zone definitions; if a player is currently in a zone that's been re-tiered, no immediate effect (combat hasn't initiated). The next combat attempt uses the new tier. **No migration required.**

4. **Should `Hutt Cartel territory` be a faction_override variant rather than a zone-level designation?** The current model treats Nar Shaddaa as inherently tense; an alternative would be marking specific Hutt-controlled rooms with `faction_override: hutt_cartel`. **Locking on zone-level for v1; revisit if Hutt-aligned PCs report unfair friction.**

5. **Should wilderness regions ever be hand-tuned to non-lawless?** §4 says yes via landmark `security_override` and Director events. Worth specifying a builder-policy default: **wilderness regions are Lawless unless explicitly overridden, and overrides are limited to ≤10% of region area.** Lock as a builder-guideline.

6. **Will the existing Drop 6A–6B influence accrual hooks fire correctly in wilderness regions?** The hooks fire on combat, missions, etc., resolved by the character's room → zone. For wilderness, the character's room is the sentinel, but the character also has `wilderness_region_id` set. The hook needs to resolve to the region for influence purposes. **Small engine change required — flagged for the Drop 6D implementation.**

---

## 10. Architecture invariants

- Every combat initiation routes through `get_effective_security()`. No shortcuts. (Unchanged.)
- Zone security is a static field; Director overlays are transient. (Unchanged.)
- Wilderness security defaults to Lawless. Overrides are explicit per-landmark or per-region.
- Frontier-city tile security follows `player_cities_design_v1_2.md` §6.2 (citizens contested, outsiders lawless).
- Geonosis inverse-faction is a per-planet special case in the overlay code, NOT a parallel security tier.
- Per-zone influence is the unit of territorial accrual. Wilderness regions are zones for this purpose.
- Per-tile PvP works as standard combat in any tile; the security tier determines the consent rules.
- The 31-zone CW catalog (§3) is the definitive list. Adding a zone requires a security assignment per §5.

---

## 11. Test plan

### 11.1 Catalog validation

- For each of the 31 CW zones in §3, verify:
  - `zones.yaml` matches the security tier listed
  - DB `zones.security` column reads the same after boot
  - `look` output displays the correct `[SECURED|CONTESTED|LAWLESS]` tag

### 11.2 Per-tier behavior

- In a secured zone: attempt PvE attack → blocked. Attempt PvP → blocked.
- In a contested zone: PvE → allowed. PvP without challenge → blocked. PvP with challenge → allowed.
- In a lawless zone: PvE → allowed. PvP → allowed (after one-time entry warning).
- In a wilderness region: same as lawless by default.
- In a frontier-city tile (citizen): contested behavior applies.
- In a frontier-city tile (outsider): lawless behavior applies.

### 11.3 Director overlay

- Set `republic` influence to 75 in a contested zone → effective security upgrades to secured.
- Set `cis` influence to 80 in a secured zone → effective security downgrades to contested.
- Set both Republic 75 + CIS 80 → no net change (both rules cancel out).
- Geonosis-specific: Republic 80 in CIS-claimed surface → downgrades for Republic PCs.

### 11.4 Migration

- Boot a CW server with stale zone security values.
- Apply the §3 catalog via zones.yaml.
- Verify DB updates correctly on next boot.
- Verify `@security <zone>` admin command works for runtime changes.

---

## 12. Documentation updates required

- `Guide_04_Security_Zones.md` — replace GCW-flavored zone catalog with §3 CW catalog. Remove Imperial/Rebel/criminal influence overlay description; replace with §6 CW overlay. Update refusal-text examples.
- `security_zones_design_v1.md` — mark as superseded for CW era; point to this doc.
- `data/worlds/clone_wars/zones.yaml` — apply §3 catalog (bundled with Apr 30 zone-naming audit fix).
- `engine/security.py::_apply_director_overlay()` — refactor for CW factions (Republic/CIS/Criminal axes; Geonosis special case). Bundled with Drop 6b.
- `data/worlds/clone_wars/director_config.yaml` — verify Republic / CIS / Criminal axes are wired (likely already done in Drop 6b).
- `clone_wars_era_design_v3.md` — note that this doc supersedes its security implications.
- `wilderness_system_design_v1.md` — note that wilderness regions get per-zone influence per `player_cities_design_v1_2.md` §21.5.
- `player_cities_design_v1_2.md` — no change required; this doc clarifies the city-zone interaction without conflicting.

---

## 13. Phased delivery plan

### Phase 1: Zone catalog application
- Edit `data/worlds/clone_wars/zones.yaml` to apply §3 catalog.
- Bundle with the existing Apr 30 zone-naming audit fix.
- Verify DB picks up changes on boot.
- **Effort:** Small. ~0.25 sessions (a YAML edit + smoke test).

### Phase 2: Director overlay CW refactor
- Update `engine/security.py::_apply_director_overlay()` for CW factions.
- Add Geonosis inverse-faction special case.
- Verify `director_config.yaml` axes are CW-aligned.
- **Effort:** Small-Medium. ~0.5 sessions.

### Phase 3: Refusal text + display polish
- Replace any remaining Imperial-flavored refusal text in `engine/security.py`.
- CW-flavored per-planet refusal variants.
- Tutorial-text review pass.
- **Effort:** Small. ~0.25 sessions.

### Phase 4: Wilderness-region influence (interlocked with Drop 6D)
- `zone_influence.wilderness_region_id` column.
- Drop 6 hooks resolve `wilderness_region_id` for influence accrual when character is in wilderness.
- Frontier-city contest plumbing (per `player_cities_design_v1_2.md` §21).
- **Effort:** Medium. ~1 session. (Bundled with Drop 6D.)

**Total:** ~2 sessions, mostly bundled with adjacent work.

---

*End of design v1.*
