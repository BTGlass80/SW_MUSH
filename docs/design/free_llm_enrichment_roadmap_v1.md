# Free-LLM (Ollama) Enrichment Roadmap — v1

> Captured ~Drop 46. Read-only design analysis. The session is actively building the substrate
> this extends (Drop 46 = T3.22 Ambient NPC Life Phase 0). **This roadmap is the natural
> completion of T3.22, not a competitor** — it generalizes the same mechanism. Align with
> `ambient_npc_life_design_v1.md` + `ollama_idle_queue_design_v1.md`.

Brian's ask: "squeeze all the enrichment we can out of the free local LLM" + "we have tons of
scraped content (sourcebooks, quests) — are they good LLM inputs and have we worked that in?"
This doc answers both — the **output surfaces** (what Ollama writes) AND the **input grounding**
(what it writes from) — because they're two halves of one system.

## TL;DR

- **~56 enrichment opportunities** found (21 HIGH-value): ~35 templated `random.choice` surfaces
  (anomalies, missions, bounties, encounters, ambient, combat prose) + a class of mechanics-only
  "dead-silence" outputs. All currently read identically every time.
- **The infrastructure already exists and is proven** — `engine/idle_queue.py` pre-generates
  variant pools (8 barks/NPC) into a cache, served instantly. The pattern is right; it's just
  bespoke to NPC barks.
- **ONE generalization unlocks ~80%:** promote the bark cache into a generic keyed variant-pool
  pre-generator. Then every static surface becomes Ollama-enriched by wrapping its existing
  `random.choice` call.
- **TWO hard prerequisites, and they're the same problem from two sides:** a runtime **era-guard**
  (no runtime CW validator exists today — tests only catch STATIC strings; Mistral WILL invent
  Stormtroopers), and **canon grounding** (feed the sourcebook lore so it generates from YOUR
  CW-clean world, not its GCW-saturated training). Grounding is the positive half of the
  era-guard.

## The core mechanism — pre-generate pools, serve instantly (the hard constraint)

A local Mistral 7B **serializes**: one model, seconds per call, low-single-digit gens/sec. So the
ONLY safe pattern (which `idle_queue.py` already encodes) is:
1. **Generate during genuine idle** (the priority queue processes ≤1 task/tick, backs off 5s after
   any player request — `idle_queue.py:380`).
2. **Batch N variants per call** into a per-key pool (the bark task asks for 5-8 in one call).
3. **Serve a `random.choice` from the cached pool instantly** on the player action — zero added
   latency, identical UX to today's static pick.
4. **ALWAYS fall back to today's static template** when the pool is empty/stale — zero regression.

**NEVER call Ollama synchronously on a player action** — that puts seconds of stall in front of a
combat round or mission turn-in. The free layer fills texture in the background; it is never on
the critical path.

## THE REUSABLE MECHANISM (build once, ~80% of the roadmap becomes cheap)

Promote the bespoke bark cache into a **generic keyed variant-pool pre-generator**:
- `VariantPoolTask(surface_key, prompt_context, n_variants)` — asks Ollama once for a JSON array
  of N variants (the existing batch trick).
- `_variant_pools[surface_key] -> {variants, generated_at}` — one keyed cache with the existing
  staleness/refresh logic.
- `get_variant(surface_key, fallback_fn)` — returns a cached pick OR calls the surface's existing
  static `random.choice` (so every call site degrades to TODAY's behavior when empty).
- The **era-validator applied inside the task** before any variant enters the pool (drops
  banned-token variants).
- The **lorebook context fed into the prompt** (grounding — see below).

Adding a new enriched surface then = pick a key, write a prompt-context builder, wrap the existing
static call in `get_variant(key, existing_static_fn)`. No new caches, no new task/serving logic,
era-guard + grounding + fallback inherited automatically. **This is exactly the substrate T3.22
Phase 3's `AmbientLifeTask` should sit on** — build it for the quick-wins and Phase 3 inherits it.

## PREREQUISITE 1 — the runtime era-guard (no runtime validator exists today)

**The load-bearing risk.** `bounded_validator.py` is a combat-INTENT validator (verbs/IDs), NOT a
prose era-guard, and no runtime era validator exists anywhere. Era cleanness is enforced ONLY by
tests over STATIC strings (`test_laneb_era_cleanness.py` carries the canonical `_BANNED` set:
Imperial/Empire/Rebel/TIE/Stormtrooper/X-Wing…). **A test cannot catch text Ollama invents at
runtime** — and Mistral prompted for "Star Wars" will absolutely emit Stormtroopers, the Empire,
TIEs, and canonical figures (one existing flavor task even hardcodes "Galactic Civil War era" in
its prompt — actively inviting leaks).

**Required (STEP 0, gates everything):** a runtime CW-era validator that sources the **same
`_BANNED` token set** as the tests (lift it into a shared importable constant so they never
drift), applied to every generated variant before it caches/serves — reject-and-drop a banned
variant (the pool gets one fewer entry; the static fallback covers the gap). Pair with prompt
hardening (system prompt: "Clone Wars ~20 BBY; Republic/CIS/Separatist; NO Empire/Imperial/
stormtroopers/TIEs; no canonical named figures").

## PREREQUISITE 2 — canon grounding (Brian's content question, answered)

**Yes, the scraped content is excellent LLM input, the mechanism is ALREADY built and wired, but
it's fed a fraction of the corpus.** The **Lorebook Pattern** (`engine/world_lore.py`) is
keyword-triggered context injection wired into BOTH the Director (`director.py:828`,
`get_relevant_lore` 5 entries/800 chars) AND NPC dialogue (`npc_brain.py:276`). It is NOT vector
RAG — keyword + zone-scope matching — which is the RIGHT call for a curated corpus on SQLite (no
embedding infra needed).

**The gap:** the lorebook is fed `lore.yaml` (~1,200 lines). Meanwhile **18 sourcebook extraction
docs = ~7,500 lines** of era-appropriate, mechanically-grounded WEG canon (gg7 Mos Eisley, gg10
Bounty Hunters, gg11 Criminal Orgs, Creatures of the Galaxy, Geonosis, Tramp Freighters, Hideouts
& Strongholds…) sit in `docs/design/` UNUSED as runtime grounding.

**Grounding IS the positive half of the era-guard:** a model told "draw from this Mos Eisley
sourcebook lore" generates from YOUR Clone Wars canon instead of its GCW-saturated training — so it
stops inventing the wrong era *on its own*, and the validator (prereq 1) catches the residue.
Quality and era-safety, same solution.

**The TRAP:** do NOT ground flavor in `wookieepedia_extracts/` — **41 of 46 files name banned
canonical figures** (Ahsoka, Anakin, Grievous, Dooku). The game's rule is "canonical figures never
appear as open-world NPCs"; grounding flavor in character wikis would pull them INTO generated
content. Use the **sourcebook extractions** (era texture, no protagonist-centric naming), not the
character wikis.

**Curation work (data, not infra):** tag-and-load the sourcebook extractions into the existing
keyword-scoped `world_lore` table. **The game is NOT Tatooine-anchored** — Tatooine is just the
most-developed starting area; the intent is ALL SIX planets alive (Tatooine, Coruscant, Kamino,
Kuat, Geonosis, Nar Shaddaa). So curate **breadth-first across planets**, not Tatooine-first:
the era-neutral texture corpora (gg10 Bounty Hunters, gg11 Criminal Orgs, Creatures of the
Galaxy, Hideouts & Strongholds) ground EVERY planet's underworld/wilderness and should land
first; planet-specific extracts (gg7 Mos Eisley, Geonosis) ground their respective worlds and
should be balanced across the six, not Tatooine-loaded. This immediately enriches grounding for
BOTH AI layers, galaxy-wide.

## The opportunity surface (56 found; 21 HIGH)

| Tier | Surfaces (file:line) | Latency | Era-risk |
|---|---|---|---|
| **Dead-silence one-liners** (highest value/byte, mostly era-safe) | mission turn-in (`mission_commands.py:549`), bounty collect (`bounty_commands.py:465`), harvest (`harvest_command.py:94`), craft (`crafting_commands.py:346`), training (`cp_commands.py:205`) | pre-gen generic pool | low |
| **Wilderness anomalies** (15 templates) | `wilderness_anomalies.py:170-300` | pre-gen per template+region | YES |
| **Space anomalies** (7×3 tiers) | `space_anomalies.py:27-108` | pre-gen per type+tier | YES |
| **Bounty crime/tips/orgs** | `bounty_board.py:107-196` | pre-gen per-bounty on creation | YES |
| **Mission objectives + givers** | `missions.py:184-263` | pre-gen at board refresh | mixed |
| **Space encounter texture** | `encounter_texture.py:58-257` | pre-gen | low |
| **Ambient room events** | `ambient_events.py` + `ambient_events.yaml` | pre-gen per zone+tone | YES |
| **Combat miss/hit prose** | `combat.py:281-347`, `combat_flavor.py` | pre-gen pool per (skill×margin×wound), seeded-select | low |

## Higher-order bets (bigger build, big payoff)

- **NPC memory-grounded barks** — feed `npc_memory.memory_json` + world_lore into the pool prompt
  so barks reference what actually happened ("Heard the Cartel raised the spice tax again"). The
  cache mechanism is unchanged; only the prompt-context grows. (Ties directly to T3.22's
  `npc_ambient_relationship`.)
- **Procedural news generation** — `EventRewriteTask` already rewrites Director headlines; extend
  to generate ambient news ITEMS from world_lore + zone_influence during idle. A free local
  newsfeed thickening the Director's paid macro-state. (Era validator critical — news is exactly
  where the Empire leaks.)
- **Outcome-aware combat prose** — the sim/combat already decides the result in Python; Ollama
  only DECORATES a known outcome (safe + cacheable per outcome-bucket).
- **T3.22 reactive NPC-NPC dialogue** — Phase 3's interaction lines; "Layer 2 (Python) decides,
  Layer 3 (Ollama) only decorates" — exactly this pattern.

## Prioritized plan

0. **Era-validator (shared `_BANNED` constant) + retrofit into the LIVE bark task** (which has NO
   guard today). Prerequisite, small, de-risks the in-flight T3.22 too.
1. **The generic variant-pool pre-generator** (generalize the bark cache) + migrate bark/housing
   caches onto it for parity. The load-bearing drop; everything after is incremental.
2. **Curate the sourcebook extractions into `world_lore`** (grounding) — Mos Eisley / bounty
   hunters / criminal orgs first. Data work, enriches both AI layers immediately.
3. **Dead-silence one-liners** (mostly era-safe, highest value/byte).
4. **HIGH-value pre-generatable descriptions** (wilderness/space anomalies, bounties) — era-risk,
   so they ride the validator + grounding.
5. **Higher-order bets** (NPC memory, news gen) as T3.22 Phase 3 matures.

## T3.22 alignment (the session is building this NOW — Drop 46 landed Phase 0)

T3.22's design (`ambient_npc_life_design_v1.md`) already specifies the pre-gen-pool +
template-fallback pattern and "Python decides, Ollama decorates." **Two concrete couplings:** (1)
the runtime era-validator this roadmap demands is ALSO a hard prerequisite for T3.22 Phase 3's
generated NPC dialogue — build it now and the in-flight feature inherits it; (2) the generic
variant-pool pre-generator IS the substrate Phase 3's `AmbientLifeTask` should be built on.
**Recommendation: land the era-validator + generic pool pre-generator + lorebook grounding as
shared infrastructure alongside T3.22, so the ambient sim and the 35-surface enrichment draw from
one mechanism** — not two parallel one-offs.
