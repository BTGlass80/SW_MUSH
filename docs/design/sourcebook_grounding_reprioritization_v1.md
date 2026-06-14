# Sourcebook Grounding Re-Prioritization — v1

Re-scores the sourcebook list (`sourcebook_extraction_roadmap_v1.md`) through the **grounding
lens** (LLM-fodder) instead of the **mechanics-need lens** — because grounding is a different
value calculation, and the game is **all-six-planets-alive**, not Tatooine-anchored. Pairs with
`free_llm_enrichment_roadmap_v1.md` (the consuming system) and
`sourcebook_ingestion_pipeline_v1.md` (how to ingest cheaply).

## Why the lens flips the ROI

The original roadmap rated books by "does it feed a live system we built" — under which stopping
after Tier 1 was correct. The grounding lens is different on three axes:
- **Lower bar:** no re-statting, no system integration — just era-clean TEXTURE/LORE text.
- **Cumulative, not diminishing:** more good lore improves generation EVERYWHERE (all ~35
  enrichment surfaces + both AI layers), not one system. Returns stay flat as the corpus grows.
- **Re-weighted by texture-density + planet-coverage,** not system-need. Books that were LOW
  mechanics-ROI (planet gazetteers, species rosters, underworld guides) become HIGH grounding-ROI.

**Two filters still gate everything:** (1) era-cleanliness (WEG D6 = extract+translate; WotC d20 =
setting-only); (2) the **canonical-figure trap** — protagonist-heavy books (e.g. *Han Solo and the
Corporate Sector*) pull canonical figures into generation = bad grounding. **Texture-dense +
character-light = the sweet spot.**

## THE HEADLINE: planet-coverage gaps (the all-six-planets priority)

The done-set is Tatooine/Outer-Rim-heavy. For "all planets alive," grounding must balance across
the six:

| Planet | Grounding status | Fill with |
|---|---|---|
| **Tatooine** | ✅ WELL-GROUNDED | GG7 Mos Eisley, Secrets of Tatooine, Creatures — all done |
| **Coruscant** | ⚠️ UNDER-GROUNDED | **Coruscant and the Core Worlds** (WotC, setting-only) + GG11/Wretched Hive/Platt's (crime+venue texture) + Death in the Undercity (quests) |
| **Geonosis** | ✅ grounded | Geonosis/Outer Rim Worlds (done) |
| **Kamino** | ⚠️ UNDER-GROUNDED | Geonosis/ORW covers some (cloning, Tipoca); needs **custom Kamino extraction** (interior/wilderness/cloning-facility) — no single book covers it; Platt's Starport (ocean-world ports) helps |
| **Nar Shaddaa** | ⚠️ partial | GG11/Wretched Hive/Platt's (Hutt-space crime); **Black Sands of Socorro** (smuggler-world texture) |
| **Kuat** | 🔴 SEVERELY UNDER-GROUNDED | **No sourcebook covers Kuat.** It's the industrial/shipyard world — needs custom extraction or grounding from ship/industrial sources (Stock Ships, Pirates & Privateers for the orbital/traffic texture). The biggest gap. |

**So the all-planets-alive priority isn't "more Tatooine books" — it's CORUSCANT and KUAT first
(the under-grounded worlds), plus custom Kamino work.** This is the inversion the lens produces.

## Re-scored priority (grounding lens)

**T1-grounding (HIGH texture, fill the planet gaps, low canonical risk) — do first:**
- Already-done HIGH-value (harvest their lore entries NOW — see pipeline quick-win): **Creatures
  of the Galaxy** (all 6 biomes, ~70 beasts), **GG11 Criminal Orgs** (underworld, all crime
  planets), **Wretched Hive** (venue/cantina ambient, all planets), **Platt's Smugglers** (crime
  economy), GG7 Mos Eisley, Secrets of Tatooine, Geonosis/ORW.
- **NOT yet done, high-priority for the gaps:** **Coruscant and the Core Worlds** (the Coruscant
  gap), and **custom Kamino + Kuat extraction** (no book covers them — the real content need).

**T2-grounding (MEDIUM texture, breadth) — after the gaps are filled:**
- Fantastic Tech: Guns & Gear (gear catalog, atomic), GG8 Scouts (wilderness texture), GG9
  Fragments (Outer Rim breadth), Stock Ships (Kuat/space traffic texture), Pirates & Privateers
  (space encounters), Platt's Starport (ports), GG4/GG12 Alien Races (species rosters — texture
  for NPC variety across all planets), Tatooine Manhunt + Death in the Undercity (quest-template
  seeds, MEDIUM canonical risk → era-translate targets), Black Sands of Socorro (Nar-Shaddaa-like
  smuggler world).

**SKIP-for-grounding (low texture OR high canonical risk):**
- Pure-rules supplements (GM's Guide heuristics — that's Director-LOGIC fodder, not grounding;
  keep it in the mechanics roadmap). **Han Solo and the Corporate Sector** + any
  protagonist-centric adventure (canonical-figure-heavy → bad grounding). WotC d20 rules content.

## Schema note (folds in Brian's "are there enough fields" question)

The lorebook's cost driver is INJECTED content, not field count — filter fields are free at
generation time. The ingestion pipeline should tag each extracted entry with the existing fields
(keywords/category/zone_scope/priority) PLUS — recommended — a **`surface_affinity`** tag
(dialogue/encounter/bounty/news/ambient) so each generation surface pulls RELEVANT lore instead of
generic keyword matches (less noise = better grounding, $0 cost). Have the LLM emit `planet` +
`surface_affinity` tags during extraction (nearly free while it's extracting anyway) so the corpus
is retrieval-optimized from the start. See the pipeline spec.

## Bottom line

Worth more ingestion — but **re-ordered: Coruscant + Kuat (the under-grounded worlds) first, custom
Kamino work, then breadth.** Not "everything" — the two filters (era, canonical-figure) still cut
the protagonist-heavy and pure-rules books. The grounding value is corpus-wide and cumulative, and
(per the pipeline spec) the ingestion is cheap enough (~$1-6 total) that the bar to "ingest it" is
now very low.

## Quest-source note (2026-06-13)

The adventure modules flagged above (Tatooine Manhunt, Death in the Undercity) and the per-book
adventure-hook sections are quest-SEED material, **not grounding lore** — treat them on a different track.
See the "Quest/hook extraction — a SEPARATE target, gated on the engine" decision in
`sourcebook_ingestion_pipeline_v1.md`. Summary: near-term, hooks feed the existing mission/bounty
generators (in-scope, a `--target hooks` add to `tools/ingest_lore.py`); a general scenario/quest engine is
a separate Brian design call that the free content well argues FOR but does not by itself justify building.
Do NOT ingest quests before that engine exists (phantom-consumer invariant). The grounding-lens
prioritization in this doc is unchanged — quest seeds ride a parallel target, not this list.
