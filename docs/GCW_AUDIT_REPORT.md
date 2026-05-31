# GCW → Clone Wars Remediation Report

**Date:** 2026-05-23
**Status:** ✅ **Complete** — all 24 guides CW-era clean
**Active era:** Clone Wars (~20 BBY)
**Lock-in test:** `tests/test_guides_reorganization.py::TestCloneWarsEraCleanliness::test_all_guides_are_era_clean`

---

## Outcome

All 24 shipped guides in `data/guides/` are now Clone Wars era-correct. The regression test scans for 24 forbidden GCW-era patterns (Stormtrooper, Galactic Empire, Rebel Alliance, TIE Fighter family, X/Y/A-Wings, Imperial-prefixed terms, etc.) and asserts zero findings outside an explicit per-file allowlist.

The remediation was done in two complementary streams:

1. **Structural rewrites** — two guides that were structurally GCW (faction tables listing the Empire and Rebel Alliance as playable factions, Director AI guide explicitly framed as comparing GCW to CW) were rewritten end-to-end using the canonical CW data from `data/worlds/clone_wars/organizations.yaml` and `director_config.yaml` as source of truth:
   - **Guide_10 Organizations & Factions** (was 250 lines / 27 GCW findings → now 298 lines / 0 findings)
   - **Guide_26 Director AI** (was 378 lines / 36 GCW findings → now 316 lines / 0 findings)
2. **Substitution passes** — nine guides with prose-level GCW contamination received a two-pass substitution: a conservative automated regex pass for unambiguous terms (Stormtrooper → Clone Trooper, TIE Fighter → Vulture Droid Starfighter, etc.), followed by a contextual line-specific pass for the trickier bare "Imperial" usages.

The previous gold-standard rewrites of **Guide_03 Ground Combat** and **Guide_04 Security Zones** were CW-correct by construction and were not modified by this remediation.

---

## Findings remediated

Before the work began, the audit found:

| File | GCW findings | Remediation |
|---|---:|---|
| Guide_26 Director AI | 36 | Full structural rewrite |
| Guide_10 Organizations & Factions | 27 | Full structural rewrite (faction roster, ranks, equipment) |
| Guide_05 Space Systems | 14 | Substitution pass (ship tables) |
| Guide_21 Channels Mail News | 14 | Substitution pass (event names, news examples) |
| Guide_22 Espionage | 10 | Substitution pass (intel examples) |
| Guide_24 Encounters Hazards | 10 | Substitution pass (encounter types) |
| Guide_11 Territory Control | 6 | Substitution pass |
| Guide_01 Core Mechanics | 5 | Substitution pass + 1 allowlisted (Death Star scale) |
| Guide_06 Economy | 4 | Substitution pass |
| Guide_02 Character Creation | 1 | 1 allowlisted (WEG R&E rulebook quote) |
| Guide_12 Player Cities | 1 | Substitution pass |
| **Total** | **128** | |

After remediation: **0 findings outside the allowlist**. All 24 guides pass the era-cleanliness regression test.

---

## Allowlisted intentional preservations

Four references appear in the guides that *look* GCW-era but are deliberately preserved. Each is justified per-file in `TestCloneWarsEraCleanliness.ALLOWED_PRESERVATIONS`:

### `weg-d6-core-mechanics` (Guide_01) line 318

```
| Death Star scale | 18 | (Canonical scale-18 reference; no such weapon exists in the Clone Wars era) |
```

**Rationale:** The Death Star is the canonical WEG R&E Scale=18 example in the rules. Preserving it as a rules reference *with an explicit disclaimer* is cleaner than inventing a fictional Clone Wars superweapon to replace it. The disclaimer tells the reader exactly why a GCW artifact appears in a CW guide.

### `character-creation` (Guide_02) line 252

```
Per the WEG R&E rules: *"Force-sensitive characters can't be as mercenary
as Han Solo is at the beginning of A New Hope. They must be moral, honest
and honorable, like Luke Skywalker and Obi-Wan Kenobi, or the dark side
will dominate them."*
```

**Rationale:** Direct quotation from the WEG R&E rulebook. Changing the quote would misquote the source. Preserved verbatim in italics with attribution.

### `security-zones` (Guide_04) line 18

```
The Clone Wars era makes this system particularly meaningful. The Republic
doesn't have the reach the Empire will eventually claim — clone patrols
garrison the core worlds and important military assets, but the Outer Rim
is largely on its own.
```

**Rationale:** Deliberate forward-reference. The contrast with the future Empire is what makes the Republic's incomplete reach feel meaningful as a *Clone Wars* phenomenon. Removing it would weaken the framing.

### `space-systems` (Guide_05) line 81

```
| BTL-B Y-Wing | 5D | 1D+1 | 7 | 1D | 2 Laser Cannons + Ion Cannon + Torpedoes | x1 |
```

**Rationale:** The BTL-B is the canonical Clone Wars-era Y-Wing variant. The Y-Wing as a design predates the Empire — it was used by the Republic Navy during the Clone Wars before becoming associated with the Rebellion. The BTL-B prefix specifies the CW variant, so the reference is era-correct.

---

## Substitution catalog

For posterity, the substitution map used in the automated passes:

**Ships:**
- TIE Fighter / TIE/ln Fighter → Vulture Droid Starfighter
- TIE Bomber → Hyena-class Bomber
- TIE Interceptor → Tri-Fighter
- X-Wing → ARC-170 Starfighter
- Y-Wing → BTL-B Y-Wing (era-correct variant)
- A-Wing → Eta-2 Actis Interceptor
- Imperial Star Destroyer (generic) → Venator-class Star Destroyer

**Military hardware:**
- E-11 Blaster Rifle → DC-15 Blaster Rifle
- Stormtrooper Armor → Clone Trooper Armor

**Factions:**
- Galactic Empire → Galactic Republic
- Rebel Alliance → Confederacy of Independent Systems (CIS)
- Rebellion → CIS
- Rebel Operative → CIS Operative
- bare "Rebel" → "Separatist"

**Authorities (contextual):**
- Imperial patrol → Republic clone patrol
- Imperial Garrison → Republic Garrison
- Imperial Navy → Republic Navy
- Imperial Army → Grand Army of the Republic
- Imperial security / customs / intelligence → Republic equivalent
- Imperial checkpoint / crackdown → Republic equivalent
- "the Empire" → "the Republic" (in mechanical contexts)

---

## Open data issue: starships.yaml

The CW-era ship names introduced in the substitution pass (ARC-170, Vulture Droid, Tri-Fighter, Eta-2 Actis, Venator-class Star Destroyer, Hyena Bomber) **are not yet registered in `data/starships.yaml`**. The guides now describe the intended CW ship roster, but the game's actual ship registry still contains era-locked GCW templates (TIE/ln Fighter, X-Wing, A-Wing, Imperial-class Star Destroyer).

This is **intentional data drift** per the per-session direction: document intent in the guides, defer the engineering remediation to a follow-up drop.

**Recommended follow-up engineering drop:**

- Add `eras: ["clone_wars", "gcw"]` field to each ship template in `data/starships.yaml`
- Filter the registry by `active_era` at load time
- Add the CW-era ship templates as new entries: `arc_170`, `vulture_droid`, `tri_fighter`, `eta2_actis`, `venator`, `hyena_bomber`, `laat_gunship`, `aat`
- Add a test asserting that every ship name referenced in `data/guides/*.md` resolves to an active-era ship in the registry

Until that drop lands, players who try to `+spawn arc_170` will get a "ship not found" error. They can still spawn the era-neutral ships (YT-1300, Z-95 Headhunter, Ghtroc 720, Firespray) which work in both eras.

---

## Regression protection

The lock-in test `TestCloneWarsEraCleanliness::test_all_guides_are_era_clean` scans every shipped guide against 24 forbidden patterns. If anyone reintroduces a GCW-era term in a future guide rewrite — say, copy-pasting a paragraph from a sourcebook without era-correcting it — the test will fail with a line-by-line report naming the offending term and showing the exact line. The fix is then one edit away.

Adding a new intentional preservation requires editing `ALLOWED_PRESERVATIONS` in the test class. This is intentional — it forces a deliberate decision about why a GCW term should remain, rather than letting drift accumulate silently.
