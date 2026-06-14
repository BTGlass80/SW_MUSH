# -*- coding: utf-8 -*-
"""engine/era_validator.py — single source of truth for Clone Wars era cleanness.

Two halves of one job, both keyed on the SAME canon so the three former copies
(tests/test_laneb_era_cleanness.py, tools/ingest_lore.py, and this module) can
never drift again:

  * ``BANNED_ERA_TOKENS`` / ``CANONICAL_FIGURES`` — the canon every era check
    shares. The era-cleanness tests import ``BANNED_ERA_TOKENS`` for their
    static-string asserts; ``tools/ingest_lore.py`` imports both for its
    ingestion quality-gate.

  * ``era_violations()`` / ``is_era_clean()`` / ``ERA_PROMPT_HINT`` — a RUNTIME
    guard for LLM-generated text. A local Mistral 7B prompted for "Star Wars"
    reliably invents Stormtroopers, the Empire, TIEs, and canonical figures
    (its training is saturated with the Galactic Civil War). A static test can
    only catch off-era *source* strings; it cannot catch text the model
    generates at runtime. So Ollama idle-queue output is filtered HERE before
    it ever caches or serves — the negative half of the guard. ``ERA_PROMPT_HINT``
    is the positive half: prepend it to a generation prompt so the model writes
    FROM the Clone Wars era instead of its GCW default.

    See ``docs/design/free_llm_enrichment_roadmap_v1.md`` STEP 0 (this module is
    the "runtime era-guard" that roadmap names as the load-bearing prerequisite)
    and ``docs/design/ollama_idle_queue_design_v1.md``.

The runtime guard intentionally errs toward DROPPING: a false-drop costs one
pool entry (the caller's static fallback covers the gap), while a false-accept
leaks off-era text to players. It therefore matches case-insensitively as
substrings — broader than the case-sensitive static-string tests on purpose.

Pure stdlib; imports NOTHING from ``engine`` (safe for tools/ + tests to import
without an import cycle).
"""
from __future__ import annotations

# ── The era canon ──────────────────────────────────────────────────────────
# GCW / post-Clone-Wars tokens that must not appear in production CW strings.
# Identical to the set the era-cleanness tests assert on; those tests now import
# this tuple rather than carry their own copy.
BANNED_ERA_TOKENS = (
    "Imperial", "IMPERIAL", "imperial",
    "Stormtrooper", "stormtrooper",
    "Empire", "Rebel", "rebel",
    "TIE fighter", "TIE-", "X-Wing", "x-wing",
    # Post-Clone-Wars / GCW / New-Republic-era tokens (added 2026-06-13 — the
    # lore-ingestion LLM quality-gate caught these slipping past the original
    # Empire/Imperial list):
    "New Republic", "Grand Moff", "Death Star", "Order 66",
    "Order Sixty-Six", "New Order", "Galactic Civil War",
)

# Canonical figures that must never be voiced as open-world NPCs (Q1 policy).
# The ingestion extractor reduces these to archetypes; the runtime guard drops
# any generated line that still names one. Matched case-insensitively as
# substrings, so "Mothma" catches "Mon Mothma", "Gunray" catches "Nute Gunray".
CANONICAL_FIGURES = (
    "Anakin", "Ahsoka", "Obi-Wan", "Obi Wan", "Palpatine", "Sidious",
    "Dooku", "Grievous", "Maul", "Yoda", "Windu", "Padme", "Padmé",
    "Jabba", "Ventress", "Cad Bane", "Bossk", "Aurra Sing", "Boba",
    "Jango", "Tarkin", "Mon Mothma", "Mothma", "Talzin", "Valorum",
    "Nute Gunray", "Gunray", "Hondo", "Wat Tambor", "Sio Bibble",
    "Lama Su", "Taun We", "Shaak Ti", "Mas Amedda",
)

# Pre-lowered, de-duplicated forms for the runtime substring scan.
_BANNED_LOWER = tuple(dict.fromkeys(t.lower() for t in BANNED_ERA_TOKENS))
_FIGURES_LOWER = tuple(dict.fromkeys(f.lower() for f in CANONICAL_FIGURES))


def era_violations(text: str) -> list[str]:
    """Return the off-era tokens / canonical figures found in ``text``.

    Case-insensitive substring match. Empty list means the text is era-clean.
    Used as the runtime drop-gate over LLM-generated content; the returned
    tokens are handy for an operator log line ("dropped: empire, anakin").
    """
    if not text:
        return []
    low = text.lower()
    hits: list[str] = []
    for tok in _BANNED_LOWER:
        if tok in low:
            hits.append(tok)
    for fig in _FIGURES_LOWER:
        if fig in low:
            hits.append(fig)
    return hits


def is_era_clean(text: str) -> bool:
    """True iff ``text`` contains no off-era tokens or canonical figures."""
    return not era_violations(text)


# Prompt-hardening fragment — prepend to any Ollama generation system prompt so
# the model generates FROM the Clone Wars era. The positive half of the guard;
# ``era_violations()`` (the negative half) catches whatever residue leaks past.
ERA_PROMPT_HINT = (
    "SETTING: Star Wars, the Clone Wars era (~20 BBY). The galaxy is the "
    "Galactic Republic at war with the Separatist Confederacy (CIS): clone "
    "troopers and Jedi versus battle droids, against a backdrop of Hutt "
    "space and the criminal underworld. STRICT: never mention the Empire, "
    "Imperials, stormtroopers, TIE fighters, the Rebellion, X-Wings, the "
    "Death Star, or anything from later eras. Do NOT name canonical figures "
    "(no Anakin, Obi-Wan, Dooku, Grievous, Palpatine, and the like)."
)
