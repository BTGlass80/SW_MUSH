# -*- coding: utf-8 -*-
"""
engine/village_standing.py — Village standing attribute (F.7.f).

Per ``jedi_village_quest_design_v1.md`` §6.2: a per-character integer
that tracks how the Village's elders regard the character. Increments
on positive Village quest outcomes; never decrements at launch (the
only "negative" outcome is Path C lock-in, and per F.7.c.4 / design
§7.3 even Path C *passes* the Spirit trial — the Village's welcome
diverges at Step 10, not at the trials themselves).

The deltas come from the world-data field ``village_standing_delta``
in ``data/worlds/clone_wars/quests/jedi_village.yaml``:

  gate pass (Sister Vitha test) ........... +1
  First Audience (Master Yarael) .......... +1
  Trial of Skill (Forge / Daro) ........... +1
  Trial of Courage (Mira) ................. +2
  Trial of Flesh (Korvas) ................. +2
  Trial of Spirit (Yarael, Sanctum) ....... +3   (also +3 on Path C)
  Trial of Insight (Saro, Council Hut) .... +2
                                            ───
                                        max +12

This module exports the public delta constants and the
``adjust_village_standing`` helper. Wire-up sites (Sister Vitha,
audience, each trial completion) call the helper directly. The
helper handles the both halves of the persistence contract — updating
the in-memory char dict AND calling ``db.save_character`` — so call
sites are one-liners.

Future drops may grant standing for non-trial actions; the column
is unbounded. In practice a Village-completing PC tops out at 12
through F.7.f.

Read access: ``get_village_standing(char) -> int``. Used by Mira's
"deeper nod" check, the post-trial reception flavour, and Path B's
Village integration. None of those consumers exist yet — F.7.f only
*populates* the attribute. Consumers will read it in later drops as
needed (per the F.7.d carry-over plan).
"""
from __future__ import annotations

import logging
from typing import Mapping

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Delta constants — must match data/worlds/clone_wars/quests/jedi_village.yaml
# ─────────────────────────────────────────────────────────────────────────────
#
# These are exposed as named constants rather than read out of the
# yaml at runtime because (a) the value is small, (b) the runtime
# already loads the yaml only at chain-registration time, and (c) the
# call sites are in five different functions across two modules —
# threading the yaml-loaded value through all of them is more code
# than just exposing the constant.
#
# A tests/test_f7f_village_standing.py regression assertion confirms
# the constants below match the yaml deltas; if anyone ever needs to
# tune the deltas they'll get a clean test failure that points them
# at both files.

STANDING_DELTA_GATE_PASS         = 1   # Step 3: Sister Vitha
STANDING_DELTA_FIRST_AUDIENCE    = 1   # Step 4: Master Yarael
STANDING_DELTA_TRIAL_SKILL       = 1   # Step 5: Forge / Daro
STANDING_DELTA_TRIAL_COURAGE     = 2   # Step 6: Common Square / Mira
STANDING_DELTA_TRIAL_FLESH       = 2   # Step 7: Meditation Caves / Korvas
STANDING_DELTA_TRIAL_SPIRIT      = 3   # Step 8: Sealed Sanctum / Yarael
STANDING_DELTA_TRIAL_INSIGHT     = 2   # Step 9: Council Hut / Saro

# Sentinel cap used by tests; not enforced at runtime (the column
# is unbounded for forward-additivity).
STANDING_MAX_FROM_QUEST = (
    STANDING_DELTA_GATE_PASS
    + STANDING_DELTA_FIRST_AUDIENCE
    + STANDING_DELTA_TRIAL_SKILL
    + STANDING_DELTA_TRIAL_COURAGE
    + STANDING_DELTA_TRIAL_FLESH
    + STANDING_DELTA_TRIAL_SPIRIT
    + STANDING_DELTA_TRIAL_INSIGHT
)
assert STANDING_MAX_FROM_QUEST == 12, (
    "Total village_standing from the Village quest path must be 12; "
    f"got {STANDING_MAX_FROM_QUEST}. If the deltas changed, update "
    "this assertion AND the yaml AND the F.7.f handoff doc."
)


# ─────────────────────────────────────────────────────────────────────────────
# Accessors
# ─────────────────────────────────────────────────────────────────────────────


def get_village_standing(char: Mapping) -> int:
    """Return the character's current ``village_standing`` value
    (default 0 if column is missing or NULL)."""
    raw = char.get("village_standing")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Adjustment
# ─────────────────────────────────────────────────────────────────────────────


async def adjust_village_standing(db, char: dict, delta: int) -> int:
    """Apply ``delta`` to the character's ``village_standing``.

    Updates the in-memory char dict AND persists to the DB via
    ``db.save_character``. Returns the new standing value.

    Negative deltas are accepted (the column is just an integer) but
    are clamped at 0 — the Village does not subtract standing below
    zero. F.7.f's call sites only pass positive deltas; the negative-
    clamp is defense in depth for future call sites.

    A delta of 0 is a no-op (no DB write is performed).
    """
    if delta == 0:
        return get_village_standing(char)

    current = get_village_standing(char)
    new_val = max(0, current + int(delta))

    char["village_standing"] = new_val
    try:
        await db.save_character(char["id"], village_standing=new_val)
    except Exception:
        # Persistence failure logged but not raised — the in-memory
        # value is still updated, so the rest of the trial-completion
        # narration / state machine sees the correct standing for
        # this turn. The next save will re-attempt persistence.
        log.warning(
            "adjust_village_standing: save_character failed for char_id=%s "
            "(delta=%s); in-memory updated but not persisted",
            char.get("id"), delta, exc_info=True,
        )

    return new_val
