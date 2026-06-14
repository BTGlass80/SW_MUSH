# Automated Sourcebook Ingestion Pipeline — v1

Makes ingesting many more sourcebooks (as LLM grounding fodder) **cheap** — turning the current
manual "GG7 loop" into an automatable pipeline. Pairs with
`sourcebook_grounding_reprioritization_v1.md` (what to ingest) and
`free_llm_enrichment_roadmap_v1.md` (what consumes the lore + the shared era-validator).

**Copyright note:** the WEG/WotC PDFs are gitignored/local-only. The committed artifact is the
EXTRACTED, era-translated, paraphrased lore (transformative) — same as the existing extractions.

## TL;DR

- **Total cost to ingest ~20-30 more books: ~$1-6.** OCR is ~free (local Tesseract); Haiku
  extraction is ~$0.01/book; validation is local; curation is the only real effort (~5-8
  person-hours total). Negligible vs. the corpus-wide quality gain. **The cost objection is gone.**
- **The QUICK WIN needs no ingestion at all:** the 16 done extractions ALREADY contain
  "Deliverable A: World Lore Entries" (~54 entries) in the lorebook format — harvest them into
  `lore.yaml` now for **$0**.
- **The one missing automation is OCR** — `make_sidecar.py` is text-layer-only and fails silently
  on scanned PDFs (~50% of the candidates).

## The pipeline (4 stages)

| Stage | What | Tool | Automatable | Per-book cost | Builds on |
|---|---|---|---|---|---|
| **1. OCR** | PDF → text. Try PyMuPDF text layer; if low yield, Tesseract (local, free) or Claude Vision (paid, high-confidence) | extend `make_sidecar.py` (`--ocr-engine tesseract\|vision\|hybrid`) | FULLY | ~$0 (Tesseract) | `make_sidecar.py` text-layer path |
| **2. Extract + era-translate + canonical-strip** | text → world_lore entries in the existing "Deliverable A" format; era-translate to ~20 BBY; reduce canonical figures to archetypes; emit `keywords/content/category/zone_scope/priority` + `planet` + `surface_affinity` tags | Haiku, structured prompt | LLM-ASSISTED | ~$0.01 | the existing extraction format (gg11 "Deliverable A") |
| **3. Era-validate** | reject/flag any entry whose CONTENT contains a banned token | the shared `_BANNED` validator (STEP 0 below) | FULLY | $0 | the same validator the enrichment uses |
| **4. Curate** | load validated entries into the `world_lore` table / `lore.yaml`, with keyword+planet+zone+affinity tags; reseed | a `lore.yaml` appender + reseed | MANUAL-SPOTCHECK | — | `world_lore` table + `get_relevant_lore` |

## STEP 0 (prerequisite, gates everything): the shared era-validator

No runtime CW-era validator exists today (tests only catch STATIC strings). Build
`engine/era_validator.py`: lift the `_BANNED` set from `test_laneb_era_cleanness.py` into a shared
importable frozenset (so test + runtime never drift), with `reject_entry(entry_dict) -> bool`.
**This single module is wired THREE places** — (1) this pipeline's stage 3 (gate ingested lore at
extract time), (2) T3.22 Phase 3's `AmbientLifeTask` (gate Ollama-generated NPC dialogue at
runtime), (3) the enrichment variant-pool pre-generator (gate all generated flavor). Build once,
inherit everywhere. ~50 lines, ~1h.

## The curation target (the `world_lore` schema)

`world_lore` (`engine/world_lore.py`): `title, keywords (comma-sep triggers, lowercased), content
(1-3 paragraphs), category (faction|location|technology|concept|person|organization), zone_scope
(comma-sep zone keys or null=global), priority (1-10)`. Grounds BOTH the Director
(`director.py:828`, 5 entries/800 chars) AND NPC dialogue (`npc_brain.py:276`). `lore.yaml` mirrors
it (~37 entries today).

**Schema recommendation (from Brian's "are there enough fields" question):** the cost driver is
INJECTED `content`, not field count — filter fields are free at generation time. Have stage 2 emit
two extra free filter tags: **`planet`** (explicit, cleaner than zone-key inference for
all-six-planets routing) and **`surface_affinity`** (dialogue/encounter/bounty/news/ambient — lets
each generation surface pull RELEVANT lore, cutting noise). The LLM emits these for ~free while
extracting; the corpus is retrieval-optimized from the start instead of needing a backfill. Do NOT
add vector embeddings (wrong for the corpus size/SQLite) or injected metadata (the only real cost
lever).

## Cost model (the answer to "is it worth the effort")

~20-30 books: OCR ~$0-5 (mostly free local Tesseract) · Haiku extraction 30×$0.01 = **$0.30** ·
validation $0 · curation ~5-8 person-hours. **TOTAL ~$1-6.** For reference, one live bounty-mission
Haiku generation costs ~0.3¢ — the entire ingestion's inference cost is under $1. **Cheap; the
break-even is paid in the first week of grounded generation.**

## Build plan

1. **STEP 0 — `engine/era_validator.py`** (shared `_BANNED` frozenset + `reject_entry`). ~1h.
   Prerequisite for this pipeline AND T3.22 Phase 3 AND the enrichment pools — build it first.
2. **QUICK WIN — harvest existing extractions into `lore.yaml`.** Parse the "Deliverable A: World
   Lore Entries" §2 from the ~7 extraction docs that have them (gg11, gg10, gg6, JAS, Platt's,
   totj, …), curate zone+planet+affinity tags, append, reseed. **~54 entries, $0, 2-3h.** Triples
   the lorebook with zero new ingestion. Do this before any new OCR work.
3. **STEP 2 — extend `make_sidecar.py` with OCR fallback** (`--ocr-engine`, PyMuPDF-first →
   Tesseract). Test on 3 scanned PDFs. ~3h, $0.
4. **STEP 3 — `tools/extract_lore.py`** (CLI: pdf → ocr → Haiku extract+era-translate → emit
   `world_lore` entries with planet+affinity tags → era-validate → yaml). The reusable ingestion
   driver. ~4h.
5. **INGEST in grounding-priority order** (per the reprioritization doc): Coruscant + Kuat (the
   under-grounded worlds) first, custom Kamino work, then breadth. Each book = run the driver,
   spot-check, reseed.

## Why this is the right shape

This mirrors the Nano map-automation framework: a content pipeline where the bottleneck was manual
effort, and automation flips the ROI. The era-validator is shared infrastructure (3 consumers).
The quick-win delivers value before any tooling is built. And the cost is low enough that the
all-six-planets grounding corpus can get deep fast — which is what makes the Director and the
free-Ollama enrichment feel like *your* Clone Wars galaxy rather than generic Star Wars.

## Retrieval-architecture decision — do NOT vector-ize (2026-06-13)

Decision, answering Brian's "can we make the local DB more LLM-like / is vector RAG a win?": **No. Keep
keyword + zone-scope + tag retrieval. Vector RAG is the wrong tool at this corpus size and query shape.**
Verified current retrieval = substring keyword match + zone-scope filter, top-5 by priority, ≤800–1200
chars injected (`engine/world_lore.py:134-139`); no embeddings anywhere. Live corpus = 74 entries (→ ~119
after the harvest). Rationale:

- **Corpus size.** Vectors earn their keep at 1k–millions of fuzzy chunks where keyword match drowns. At
  ~119 curated entries, keyword + the `planet`/`surface_affinity` tags give higher precision *and* full
  era-auditability. Embeddings buy recall you don't need.
- **The query is STRUCTURED, not fuzzy.** Retrieval keys are `zone` / `surface` / extracted keywords — not
  free-text natural language. Tag matching fits structured queries; embeddings fit fuzzy ones.
- **Era-auditability.** A keyword corpus is greppable → the `_BANNED` validator can prove the *whole* corpus
  era-clean. A float-vector index can't be grepped — it fights the project's load-bearing era invariant.
- **Debuggability.** Keyword match lets you trace which entry fed a given bark; similarity scores are opaque.
- **The real bottleneck is the injected-content budget (5 / ≤800–1200 chars) and corpus DEPTH** — not which
  5 of 119 get picked (keyword finds those fine). Smarter retrieval doesn't move the budget.

**The wins instead (ordered):** (1) corpus depth — the harvest + ingestion; (2) precision via the
`planet`/`surface_affinity` tags already emitted at extract time; (3) per-surface injection budget (the
Director/Haiku can swallow more lore than an Ollama bark — tune per consumer, not one fixed 5/800);
(4) synonym-rich keyword lists from the extractor (cheap fix for the one real keyword weakness, vocab
mismatch — captures most of the recall benefit of embeddings for a fraction of the cost).

**Escape hatch + threshold:** if substring keyword match ever feels brittle, the next rung is **SQLite
FTS5** — *confirmed available in this stack, zero new deps* — ranked full-text relevance, still
greppable/era-auditable. **Not embeddings.** Vectors only flip to worth-it past ~1–2k entries AND/OR a
genuinely fuzzy free-text query surface (e.g. an in-game HoloNet/datapad search where players type
natural-language questions). At that point: keyword/FTS prefilter + Ollama-embedding rerank (Ollama
embeddings are free; no embedding model is pulled today). Until then, FTS5 first, vectors never.

## Quest/hook extraction — a SEPARATE target, gated on the engine (2026-06-13)

Answering Brian's "are these sourcebooks a source for quest material too?": **yes as a SEED well, but quest
material is not grounding lore, and the gating constraint is the engine, not the source.** The sourcebooks
are deep with adventure hooks, NPC motives, location secrets; the modules (Tatooine Manhunt, Death in the
Undercity) are runnable scenarios. But a quest is structured/stateful/mechanical — objectives, triggers,
completion conditions, a giver NPC, and **rewards that hit the credit faucet/sink invariant** — a consumer
with code behind it, not a text blob. Therefore:

- **The engine must lead the data.** With only tutorial chains + T5s today, bulk-extracting quests would
  manufacture phantom data (entries with no consumer) — a hard-invariant violation. Don't ingest quests
  before the engine that runs them exists.
- **In-scope NOW:** extract sourcebook adventure HOOKS as **mission/bounty seeds** for the existing
  `missions.py` / `bounty_board.py` generators. New extraction TARGET (`category: hook` → mission template),
  same OCR + era-validate machinery. **Concrete near-term add to `tools/ingest_lore.py`** (a `--target
  hooks` mode that emits mission/bounty seed rows instead of lore rows).
- **Modules are hand-curation, not bulk ingest** — named protagonists + specific plots = higher canonical
  risk → era-translate by hand, treat as templates you adapt.
- **Strategic:** the *volume* of quest-grade material is itself the business case for a generalized
  scenario/quest engine beyond tutorial chains — a new top-level system = an explicit Brian design call
  (logged here, not slid in). Once that schema exists, the sourcebooks are its content firehose.
