# -*- coding: utf-8 -*-
"""
engine/chain_events.py — CW tutorial chain event dispatcher (F.8.c.2.b
Phase 1).

Maps runtime events to `tutorial_chains.advance_step` calls.

Phase 1 wired four `completion.type` values:

    completion.type     | seam                                        | impl
    --------------------+---------------------------------------------+-------
    command_executed    | parser/commands.py CommandParser._execute   |  ✅
    talk_to_npc         | parser/npc_commands.py _post_talk_hooks     |  ✅
    combat_won          | parser/combat_commands.py _try_auto_resolve |  ✅
    room_entered        | parser/builtin_commands.py _post_move_hooks |  ✅

Phase 2 (F.8.c.2.b₂, May 5 2026) adds four more:

    completion.type     | seam                                        | impl
    --------------------+---------------------------------------------+-------
    mission_accepted    | parser/mission_commands.py post-accept      |  ✅
    mission_completed   | parser/mission_commands.py post-complete    |  ✅
    bounty_accepted     | parser/bounty_commands.py post-claim        |  ✅
    item_acquired       | db/database.py add_to_inventory             |  ✅
    item_used           | parser/builtin_commands.py UseCommand       |  ✅

Phase 3 (split between F.8.c.2.b₅ and a future drop):

    completion.type     | seam                                        | impl
    --------------------+---------------------------------------------+-------
    requires_first      | this module (sub-step tracker)              |  ✅
                        |   state-machine extension; gates main
                        |   completion until prereq descriptors fire
    skill_check_passed  | parser/chain_commands.py ChainCommand       |  ✅
                        |   F.8.c.2.b₆ (May 20 2026): wired via the
                        |   explicit `chain attempt` player command.
                        |   The command reads the active step, runs
                        |   perform_skill_check at the authored
                        |   skill+difficulty, and dispatches to
                        |   on_skill_check_passed. See design note
                        |   below for the seam decision rationale.
    prerequisite        | engine/village_choice.py::_set_chargen_flags|  ✅
                        |   + server/game_server.py post-chargen
                        |   F.8.c.2.b₆ (May 19+20 2026): wired. Fires
                        |   from village_choice on chargen-flag
                        |   persistence AND from game_server after
                        |   chargen finalize (chargen_complete,
                        |   force_sensitive). Chain steps gate on
                        |   `jedi_path_unlocked`, `chargen_complete`,
                        |   `force_sensitive`, `tutorial_core_complete`.

F.8.c.2.b₆ design note — skill_check_passed seam: RESOLVED
----------------------------------------------------------
chains.yaml has six `skill_check_passed` completions across the
corpus (sneak/8, sneak/9 with on_fail abort, con/10 with combat
fallback, search/8, con/9 with starship_piloting fallback,
starship_repair/8 with retry). All six describe a single moment in
the chain where the character must succeed at a non-combat skill
check to advance.

The question was when the roll fires. RESOLVED May 20 2026 to
**Option 2: explicit `chain attempt` command**. The player types
`chain attempt` when standing in the chain step's authored
location; the parser command (parser/chain_commands.py) reads the
active step via `get_active_step_info`, runs the authored
`perform_skill_check` against the step's `skill` and `difficulty`,
and dispatches the result to `on_skill_check_passed`. Failure
consequences (on_fail / fallback) are driven by the command, not
this dispatcher — `on_skill_check_passed` with `succeeded=False`
remains a hard no-match here.

The other two candidates were:
1. Roll on step entry (silently, no player agency).
3. Roll on a scripted player action defined per step
   (`attempt_on_command: "sneak past patrol"`, new YAML schema).

Option 2 won on: (a) player agency — they choose when to try,
(b) no new YAML schema, (c) discoverable via a dedicated command
that can later carry `chain status`, `chain skip`, etc.

Phase 1+2 design constraints (unchanged through Phase 3)
--------------------------------------------------------
- One public coroutine per event-type. Hook sites import and `await`
  it — no global registries, no side-effect-on-import.
- Loads the chain corpus via `engine.tutorial_chains.load_tutorial_chains`
  and caches it in a module-level dict keyed by era. Corpus is
  immutable once loaded; cache invalidation is "process restart"
  (same model as every other YAML loader in this codebase).
- All character-attribute mutation goes through the existing
  `tutorial_chains.advance_step()` helper (and now also through
  `record_prereq_satisfied` for prereq tracking). This module is the
  matcher; the state machine stays where it is.
- Failure-tolerant: any unexpected condition logs at WARNING and
  returns silently. A broken chain hook MUST NOT prevent the player
  command from completing successfully. The hook is additive
  progression UI; the underlying action (talk, move, combat, command)
  must always succeed regardless.

Phase 3 (F.8.c.2.b₅, May 5 2026) — what `requires_first` does
------------------------------------------------------------
Three chain steps in chains.yaml use `requires_first`:
  * republic_soldier step 1: talk Major Tarrn AFTER `look` AND `+sheet`
  * smuggler step 5: `+factions` AFTER `give crate to Dyn`
  * shipwright_trader step 2: `examine subsystem` AFTER `scan subsystem`

Phase 1+2 treated `requires_first` as advisory — the main completion
fired regardless of whether prereqs were met. Phase 3 makes it gating:
the main event is silently refused (no advance, no state change) until
every prerequisite descriptor in the list has matched an event.

State extension on the `tutorial_chain` block:
    state["step_progress_satisfied"] = [0, 1]
A list of indices into the current step's `requires_first` array,
cleared whenever the step advances.

Today, only `on_command_executed` participates in prereq satisfaction
(every `requires_first` entry in chains.yaml is command-shaped). Other
dispatchers (`on_talk_to_npc`, `on_combat_won`, etc.) don't pass
`prereq_matcher` — they can't contribute to prereq satisfaction.
Adding talk- or combat-prereqs later is additive: a new prereq-shape
matcher plus the relevant dispatcher passing `prereq_matcher`.

Phase 1+2+3 NON-goals (still deferred)
--------------------------------------
- `skill_check_passed` (with `on_fail` and `fallback`). Six chain
  steps use it. Needs a per-step seam decision: which command's
  skill check should fire the chain event for each step. Three
  candidate approaches under discussion (per-step authoring, generic
  `+check` hook, new skill-named commands).
- `use <item>` parser command — `on_item_used` is defined but has no
  production trigger point. Phase 2.5.

Tested by tests/test_f8c2b_chain_events.py (Phase 1),
tests/test_f8c2b2_chain_events_phase2.py (Phase 2), and
tests/test_f8c2b5_requires_first.py (Phase 3 / requires_first).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Module-level corpus cache ─────────────────────────────────────────
#
# Keyed by era code. None values are valid (mean "this era has no
# chain tutorial"); they're cached so we don't keep hitting the
# filesystem for GCW characters whose era resolves to None.

_CORPUS_CACHE: dict = {}


def _get_corpus(era: Optional[str] = None):
    """Return the (cached) corpus for the given era. None if the era
    has no chains.yaml."""
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception:  # pragma: no cover — defensive
            era = "clone_wars"

    if era in _CORPUS_CACHE:
        return _CORPUS_CACHE[era]

    try:
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains(era)
    except Exception as e:
        log.warning("[chain_events] load_tutorial_chains(%r) failed: %s",
                    era, e)
        _CORPUS_CACHE[era] = None
        return None

    if corpus is not None and corpus.errors:
        log.warning("[chain_events] corpus for era %r has %d errors; "
                    "treating as unusable", era, len(corpus.errors))
        _CORPUS_CACHE[era] = None
        return None

    _CORPUS_CACHE[era] = corpus
    return corpus


def _reset_corpus_cache() -> None:
    """Test hook. Production code does not call this."""
    _CORPUS_CACHE.clear()


# ── Attribute load/save helpers ───────────────────────────────────────
#
# Character `attributes` may arrive as a JSON string (DB row form) or
# a dict (in-memory form). The parser sometimes hands us one shape and
# sometimes the other. Normalize on read; serialize on write.


def _load_attrs(char: dict) -> dict:
    raw = char.get("attributes", "{}")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("[chain_events] attributes JSON parse failed for "
                    "char %s: %s", char.get("id"), e)
        return {}


async def _persist_attrs(db, char: dict, attrs: dict) -> None:
    """Save attrs back to the character row and update the in-memory
    char dict so subsequent reads in this same request see the change."""
    serialized = json.dumps(attrs)
    char["attributes"] = serialized
    await db.save_character(char["id"], attributes=serialized)


# ── Step-matching helpers ─────────────────────────────────────────────


def _get_active_step(char_attrs: dict, corpus,
                     state_key: str = None):
    """Return (chain, current_step) or (None, None) if no active chain.

    Wraps tutorial_chains.get_current_step but also returns the chain
    (which the matcher needs for the eventual advance call).

    T5-questline arc (2026-06-13): `state_key` selects which slot to
    read — the onboarding `tutorial_chain` or the mid-game
    `active_questline`. Defaults to the onboarding slot
    (_TUTORIAL_CHAIN_KEY) so legacy callers are unchanged."""
    from engine.tutorial_chains import (
        get_current_step, get_active_chain_id, _TUTORIAL_CHAIN_KEY,
    )
    if state_key is None:
        state_key = _TUTORIAL_CHAIN_KEY
    chain_id = get_active_chain_id(char_attrs, state_key)
    if not chain_id:
        return None, None
    chain = corpus.by_id().get(chain_id)
    if chain is None:
        return None, None
    step = get_current_step(char_attrs, corpus, state_key)
    return chain, step


def _match_command_executed(completion: dict, command: str,
                            args: str) -> bool:
    """True iff a `command_executed` completion matches.

    Matches on `command` (case-insensitive). Optional sub-constraints:
      - target_contains: substring match (case-insensitive) against args
      - contains_any:    list of substrings; matches if any is present
                         in args (case-insensitive)
    """
    expected_cmd = (completion.get("command") or "").lower().strip()
    if not expected_cmd:
        return False
    if command.lower().strip() != expected_cmd:
        return False

    args_lower = (args or "").lower()

    target_contains = completion.get("target_contains")
    if target_contains:
        if str(target_contains).lower() not in args_lower:
            return False

    contains_any = completion.get("contains_any")
    if contains_any:
        if not any(str(x).lower() in args_lower for x in contains_any):
            return False

    return True


def _match_talk_to_npc(completion: dict, npc_name: str) -> bool:
    """True iff a `talk_to_npc` completion matches the NPC name.

    Match is case-insensitive exact on the trimmed name. Aliases /
    partials are NOT supported in Phase 1 — chain authors should put
    the canonical NPC name in the chain step."""
    expected = (completion.get("npc") or "").strip().lower()
    if not expected:
        return False
    return (npc_name or "").strip().lower() == expected


def _match_combat_won(completion: dict, defeated_template: str,
                     defeated_count: int) -> bool:
    """True iff a `combat_won` completion matches the post-combat tally.

    Required: `enemy_template` matches and `defeated_count` is at least
    `enemy_count` (default 1). `ally_count` and `stun_bonus_credits`
    are step-effect fields, not match constraints — they don't affect
    whether the step advances."""
    expected_tpl = (completion.get("enemy_template") or "").strip()
    if not expected_tpl:
        return False
    if (defeated_template or "").strip() != expected_tpl:
        return False
    expected_count = int(completion.get("enemy_count") or 1)
    return defeated_count >= expected_count


def _match_room_entered(completion: dict, room_slug: str) -> bool:
    """True iff a `room_entered` completion matches the room slug.

    Match is case-insensitive exact on `room` field."""
    expected = (completion.get("room") or "").strip().lower()
    if not expected:
        return False
    return (room_slug or "").strip().lower() == expected


# ── F.8.c.2.b₅ Phase 3 — `requires_first` sub-step matching ──────────
#
# Three chain steps use `requires_first` (republic_soldier step 1,
# smuggler step 5, shipwright_trader step 2). The shape varies a
# little:
#
#   - {"command": "look"}                                  (bare)
#   - {"command": "+sheet"}                                (bare)
#   - {"command": "give", "target_contains": "crate",
#      "target_npc": "Dyn"}                                (full)
#   - {"command": "scan", "target_contains": "subsystem"}  (mid)
#
# All real `requires_first` entries today are command-shaped. A
# prerequisite that's a talk/move/combat event would need its own
# matcher; that case isn't reachable from the current chains.yaml,
# so it isn't implemented here. Adding talk-prereqs later is
# additive: a new `_match_prereq_talk_to_npc` function plus a small
# fan-out in `_match_prereq`.


def _match_prereq_command_executed(prereq: dict, command: str,
                                   args: str) -> bool:
    """True iff a command-shaped prerequisite descriptor matches the
    given command/args.

    Same logic as `_match_command_executed` but operates on the
    prerequisite-descriptor shape (a dict inside `requires_first`,
    not a full `completion` block) and additionally honors
    `target_npc` as a substring constraint on args.

    Why `target_npc` is treated as a substring: the
    `on_command_executed` hook receives `(command, args)` only — it
    has no structured target metadata. The chains.yaml `target_npc`
    field is authored as a hint for human readers AND as a
    constraint for the matcher. Substring matching against args
    captures the common case (the player's command literal contains
    the NPC name, e.g. `give crate to Dyn`) without changing the
    `on_command_executed` signature. Future drops can promote this
    to a structured matcher when more event types want similar
    constraints.
    """
    expected_cmd = (prereq.get("command") or "").lower().strip()
    if not expected_cmd:
        return False
    if command.lower().strip() != expected_cmd:
        return False

    args_lower = (args or "").lower()

    target_contains = prereq.get("target_contains")
    if target_contains:
        if str(target_contains).lower() not in args_lower:
            return False

    target_npc = prereq.get("target_npc")
    if target_npc:
        if str(target_npc).lower() not in args_lower:
            return False

    return True


def _all_prereqs_satisfied(completion: dict,
                           satisfied: list) -> bool:
    """True iff the active step's `requires_first` is empty / absent
    OR every required index is in `satisfied`.

    A step without `requires_first` always reports True — this is
    the no-prereq fast path.

    F.8.c.2.b₅ Phase 3."""
    requires_first = completion.get("requires_first")
    if not requires_first:
        return True
    if not isinstance(requires_first, list):
        # Defensive: malformed corpus. Treat as no prereqs so we don't
        # block a chain step over a YAML typo.
        return True
    return all(i in satisfied for i in range(len(requires_first)))


# ── Public dispatch entry points (one per supported event type) ──────


async def on_command_executed(db, char: dict, command: str,
                              args: str = "") -> bool:
    """Hook: the player just ran a command successfully.

    Called from parser/commands.py CommandParser._execute after the
    command's execute() returned without raising. Returns True iff a
    chain step advanced.

    F.8.c.2.b₅ Phase 3 (May 5 2026): also handles `requires_first`
    prereq satisfaction. When the active step has a `requires_first`
    list and the current command matches an unsatisfied prereq
    descriptor, that prereq is recorded against the step state and
    the call returns False (no main-completion advance, but state
    changed and persisted). Subsequent calls that satisfy all
    prereqs and the main completion will advance normally. See the
    `_match_prereq_command_executed` and `_all_prereqs_satisfied`
    helpers above.

    Failure-tolerant: any exception is logged and swallowed — the
    parser must finish dispatching its post-execute side effects
    (HUD update, prompt) regardless of whether chain advancement
    works."""
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="command_executed",
            matcher=lambda c: _match_command_executed(c, command, args),
            prereq_matcher=lambda p: _match_prereq_command_executed(
                p, command, args,
            ),
        )
    except Exception as e:  # pragma: no cover — defensive belt+braces
        log.warning("[chain_events] on_command_executed failed: %s", e,
                    exc_info=True)
        return False


async def on_talk_to_npc(db, char: dict, npc_name: str) -> bool:
    """Hook: the player just successfully talked to an NPC.

    Called from parser/npc_commands.py TalkCommand._post_talk_hooks
    after the NPC dialogue dispatched. Returns True iff a chain step
    advanced."""
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="talk_to_npc",
            matcher=lambda c: _match_talk_to_npc(c, npc_name),
        )
    except Exception as e:
        log.warning("[chain_events] on_talk_to_npc failed: %s", e,
                    exc_info=True)
        return False


async def on_combat_won(db, char: dict, defeated_template: str,
                        defeated_count: int = 1) -> bool:
    """Hook: the player just survived combat with at least one defeated
    NPC of the given template.

    Called from parser/combat_commands.py _try_auto_resolve at the
    `combat.is_over` branch, once per surviving PC. Returns True iff
    a chain step advanced.

    `defeated_template` is the engine NPC template id (e.g.
    "b1_battle_droid_sim"). The chain step's `enemy_template` is
    matched against this exactly.

    drop 25 (2026-06-12): cumulative-kill accumulation. A
    `combat_won` step with `enemy_count > 1` (republic_soldier s2,
    separatist_commando s2) is met across MULTIPLE combats, because
    the paired drill enemies don't aggro together — the player fights
    them one at a time. We accumulate defeats of the step's template
    on the chain-step state and match against the running total, so
    two sequential count=1 wins satisfy enemy_count=2. The tally is
    keyed by template and cleared on step advance (see
    engine.tutorial_chains.record_combat_kills / get_combat_kills).
    Accumulation only fires when the defeated template matches the
    active step's `enemy_template`, so unrelated combats never
    pollute the tally."""
    try:
        # Resolve the active step's combat_won template (if any) so we
        # only accumulate kills that count toward THIS step. This is a
        # cheap pre-check; _try_advance re-resolves the step itself.
        #
        # T5-questline arc (2026-06-13): the cumulative tally is
        # per-slot (onboarding vs questline), so we accumulate into
        # whichever slot has a matching multi-enemy combat step and
        # remember that slot's running total. A player is only ever on
        # ONE combat step at a time, so at most one slot accumulates;
        # the matcher then uses that slot's total. Slots without a
        # matching multi-enemy step contribute the raw `defeated_count`
        # (single-kill steps need no accumulation).
        from engine.tutorial_chains import (
            CHAIN_STATE_KEYS, record_combat_kills,
        )
        # Map each slot to the kill total the matcher should see for it.
        slot_totals: dict = {k: defeated_count for k in CHAIN_STATE_KEYS}
        try:
            corpus = _get_corpus()
            if corpus is not None:
                attrs = _load_attrs(char)
                changed = False
                for skey in CHAIN_STATE_KEYS:
                    _chain, step = _get_active_step(attrs, corpus, skey)
                    completion = (step.completion or {}) if step else {}
                    if (completion.get("type") == "combat_won"
                            and (completion.get("enemy_template") or "").strip()
                            == (defeated_template or "").strip()
                            and int(completion.get("enemy_count") or 1) > 1):
                        slot_totals[skey] = record_combat_kills(
                            attrs, defeated_template.strip(),
                            defeated_count, skey,
                        )
                        changed = True
                if changed:
                    # Persist the running tally even if no step advances
                    # yet — otherwise the next combat would restart the
                    # count and the step could never complete.
                    await _persist_attrs(db, char, attrs)
        except Exception as e:  # pragma: no cover — defensive
            # WARNING, not DEBUG: if accumulation fails for a multi-enemy
            # step, the totals fall back to this combat's count alone
            # (e.g. 1), which never reaches enemy_count>1 — the step
            # would silently stall forever. An operational signal is
            # warranted so a stuck combat step is visible in logs.
            log.warning("[chain_events] combat-kill accumulation failed "
                        "for char %s (template=%s): %s",
                        char.get("id"), defeated_template, e,
                        exc_info=True)
            slot_totals = {k: defeated_count for k in CHAIN_STATE_KEYS}

        # Per-slot dispatch so each slot's matcher sees its own tally.
        advanced_any = False
        for skey in CHAIN_STATE_KEYS:
            try:
                if await _try_advance(
                    db, char,
                    event_type="combat_won",
                    matcher=lambda c, _t=slot_totals[skey]: _match_combat_won(
                        c, defeated_template, _t),
                    state_key=skey,
                ):
                    advanced_any = True
            except Exception as e:  # pragma: no cover — defensive
                log.warning(
                    "[chain_events] combat_won slot %r advance failed: %s",
                    skey, e, exc_info=True)
        return advanced_any
    except Exception as e:
        log.warning("[chain_events] on_combat_won failed: %s", e,
                    exc_info=True)
        return False


async def on_room_entered(db, char: dict, room_slug: str) -> bool:
    """Hook: the player just entered a room with the given slug.

    Called from parser/builtin_commands.py MoveCommand._post_move_hooks
    after the room's slug has been resolved. Returns True iff a chain
    step advanced.

    `room_slug` is the room's `properties.slug` (the chain step's
    canonical room identifier). If the player's current room has no
    slug (legacy room not yet migrated), the hook no-ops."""
    if not room_slug:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="room_entered",
            matcher=lambda c: _match_room_entered(c, room_slug),
        )
    except Exception as e:
        log.warning("[chain_events] on_room_entered failed: %s", e,
                    exc_info=True)
        return False


# ── Phase 2 matchers (mission / bounty / item) ───────────────────────


def _match_mission_accepted(completion: dict, chain_mission_id: str
                            ) -> bool:
    """True iff a `mission_accepted` (or `mission_completed`) completion
    matches the chain mission id.

    The chain step's `mission_id` is an abstract identifier like
    ``tutorial_republic_first_deployment``. Real mission rows carry
    a generated id (``m_abc123``); they tag themselves as
    chain-relevant by setting ``mission_data.chain_mission_id``
    to the abstract id at creation time. Match is exact on that tag.
    """
    expected = (completion.get("mission_id") or "").strip()
    if not expected:
        return False
    return (chain_mission_id or "").strip() == expected


def _match_bounty_accepted(completion: dict, chain_bounty_id: str
                          ) -> bool:
    """True iff a `bounty_accepted` completion matches the chain bounty id.

    Same tag-based match as missions. The bounty contract carries a
    ``chain_bounty_id`` field (added in F.8.c.2.b₂)."""
    expected = (completion.get("bounty_id") or "").strip()
    if not expected:
        return False
    return (chain_bounty_id or "").strip() == expected


def _match_item_acquired(completion: dict, item_key: str) -> bool:
    """True iff an `item_acquired` completion matches the item key.

    Items are matched on their registry key (e.g. ``capacitor_coil_t1``).
    The chain step's optional ``method`` field (e.g. ``+craft fetch``)
    is informational — used to teach the player how to acquire the
    item but not enforced by the matcher. A player who reaches the
    item via any path advances the step."""
    expected = (completion.get("item") or "").strip().lower()
    if not expected:
        return False
    return (item_key or "").strip().lower() == expected


def _match_item_used(completion: dict, item_key: str) -> bool:
    """True iff an `item_used` completion matches the item key.

    Same key-based match as item_acquired. Phase 2 wires the
    matcher; the trigger point (a `use` parser command, or
    instrumentation on `remove_from_inventory`) is deferred to the
    drop that introduces the use command."""
    expected = (completion.get("item") or "").strip().lower()
    if not expected:
        return False
    return (item_key or "").strip().lower() == expected


# ── Phase 3 matchers (prerequisite / skill_check_passed) ─────────────


def _match_prerequisite(completion: dict, flag_name: str) -> bool:
    """True iff a `prerequisite` completion matches the chargen flag.

    Two chain steps gate on `prerequisite` today:
      * jedi_path step 0: `prerequisite: jedi_path_unlocked`
      * jedi_path_independent step 0: `prerequisite: jedi_path_unlocked`

    Both fire when the village quest's path-commit code sets
    `jedi_path_unlocked=True` in chargen_notes. The matcher is exact
    case-sensitive string equality on the flag name."""
    expected = (completion.get("flag") or "").strip()
    if not expected:
        return False
    return (flag_name or "").strip() == expected


def _match_skill_check_passed(completion: dict, skill_name: str,
                              succeeded: bool) -> bool:
    """True iff a `skill_check_passed` completion matches.

    Match rule: the completion's `skill` equals `skill_name`
    (case-insensitive) AND `succeeded` is True. The completion's
    `difficulty`, `on_fail`, `fallback`, and `on_fail_narrative`
    fields are interpretation hints for the caller (which is
    expected to have rolled the check at that difficulty) — they
    are NOT re-evaluated here.

    Failure handling (on_fail / fallback / on_fail_narrative) is the
    trigger-site's responsibility — when a check fails, the
    trigger may dispatch a different event (e.g. `combat_won` for
    a fallback), or no event at all (for `abort_step_no_retry`),
    or re-trigger later (for `retry_allowed`). This dispatcher
    only fires for the success case.
    """
    if not succeeded:
        return False
    expected = (completion.get("skill") or "").strip().lower()
    if not expected:
        return False
    return (skill_name or "").strip().lower() == expected


# ── Phase 2 public hook coroutines ───────────────────────────────────


async def on_mission_accepted(db, char: dict,
                              chain_mission_id: str) -> bool:
    """Hook: the player just accepted a mission tagged with
    ``chain_mission_id``.

    Called from parser/mission_commands.py after MissionBoard.accept
    succeeds, with the mission's ``mission_data.chain_mission_id``
    value (or empty string for non-chain missions). Returns True
    iff a chain step advanced.

    Empty/missing tag → no-op (most missions aren't chain-tagged)."""
    if not chain_mission_id:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="mission_accepted",
            matcher=lambda c: _match_mission_accepted(
                c, chain_mission_id),
        )
    except Exception as e:
        log.warning("[chain_events] on_mission_accepted failed: %s",
                    e, exc_info=True)
        return False


async def on_mission_completed(db, char: dict,
                               chain_mission_id: str) -> bool:
    """Hook: the player just completed a mission tagged with
    ``chain_mission_id``.

    Called from parser/mission_commands.py after MissionBoard.complete
    succeeds, with the mission's ``mission_data.chain_mission_id``
    value. Returns True iff a chain step advanced."""
    if not chain_mission_id:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="mission_completed",
            matcher=lambda c: _match_mission_accepted(
                c, chain_mission_id),
        )
    except Exception as e:
        log.warning("[chain_events] on_mission_completed failed: %s",
                    e, exc_info=True)
        return False


async def on_bounty_accepted(db, char: dict,
                             chain_bounty_id: str) -> bool:
    """Hook: the player just claimed a bounty tagged with
    ``chain_bounty_id``.

    Called from parser/bounty_commands.py after BountyBoard.claim
    succeeds, with the contract's ``chain_bounty_id`` field value.
    Returns True iff a chain step advanced."""
    if not chain_bounty_id:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="bounty_accepted",
            matcher=lambda c: _match_bounty_accepted(
                c, chain_bounty_id),
        )
    except Exception as e:
        log.warning("[chain_events] on_bounty_accepted failed: %s",
                    e, exc_info=True)
        return False


async def on_item_acquired(db, char: dict, item_key: str) -> bool:
    """Hook: the player just received an item with the given registry
    key into their inventory.

    Called from db/database.py Database.add_to_inventory after the
    inventory write succeeds. Returns True iff a chain step advanced.

    Empty key → no-op (defensive — every item should have a key)."""
    if not item_key:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="item_acquired",
            matcher=lambda c: _match_item_acquired(c, item_key),
        )
    except Exception as e:
        log.warning("[chain_events] on_item_acquired failed: %s",
                    e, exc_info=True)
        return False


async def on_item_acquired_by_char_id(db, char_id: int,
                                       item_key: str) -> bool:
    """Variant of `on_item_acquired` for callers that have only a
    character id (e.g. the Database.add_to_inventory seam, where the
    full char row isn't on hand). Fetches the char row, then dispatches
    through the standard hook.

    Failure-tolerant in the same way as the rest of the dispatcher.
    Returns False on any error fetching the row."""
    if not item_key:
        return False
    try:
        char = await db.get_character(char_id)
    except Exception as e:
        log.debug("[chain_events] get_character(%s) failed: %s",
                  char_id, e)
        return False
    if not char:
        return False
    return await on_item_acquired(db, char, item_key)


async def on_item_used(db, char: dict, item_key: str) -> bool:
    """Hook: the player just used (consumed / activated) an item.

    Wired from `parser/builtin_commands.py::UseCommand` post-effect
    block. The trigger fires on every successful `use <item>` for
    any item key.

    (Historic note: this hook was originally wired-but-untriggered
    in Phase 2; the production trigger site landed in a later
    F.8.c.2.b drop. The docstring was updated to reflect that in
    F.8.c.2.b₆ May 20 2026.)

    Empty key → no-op."""
    if not item_key:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="item_used",
            matcher=lambda c: _match_item_used(c, item_key),
        )
    except Exception as e:
        log.warning("[chain_events] on_item_used failed: %s",
                    e, exc_info=True)
        return False


# ── Phase 3 public hook coroutines (F.8.c.2.b₆) ──────────────────────


async def on_prerequisite_flag_set(db, char: dict,
                                   flag_name: str) -> bool:
    """Hook: a chargen flag was just persisted with truthy value.

    Called from engine/village_choice.py::_set_chargen_flags after
    the save_character returns. Each flag in the persisted set is
    dispatched separately, in iteration order.

    Returns True iff a chain step advanced. Failure-tolerant: any
    exception inside the dispatcher is logged at WARNING and the
    coroutine returns False — chargen-flag persistence must not be
    blocked by a chain-event hook.

    Today two chain steps gate on this dispatcher, both on the
    `jedi_path_unlocked` flag. Setting that flag during Path A or
    Path B commit (engine/village_choice.py::_commit_path_a and
    ::_commit_path_b) is the production trigger.

    Other chargen flags (e.g. `village_chosen_path_a`,
    `village_trial_lightsaber_construction_pending`) flow through
    the same dispatcher but currently match no chain step — the
    dispatcher no-ops for them. Authoring a chain step that
    gates on a new flag is now zero engine work: add a
    `prerequisite` completion to chains.yaml with the flag name."""
    if not flag_name:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="prerequisite",
            matcher=lambda c: _match_prerequisite(c, flag_name),
        )
    except Exception as e:
        log.warning(
            "[chain_events] on_prerequisite_flag_set failed: %s",
            e, exc_info=True,
        )
        return False


async def on_skill_check_passed(db, char: dict, skill_name: str,
                                succeeded: bool,
                                difficulty: Optional[int] = None
                                ) -> bool:
    """Hook: the engine just resolved a skill check that may
    correspond to a chain step's `skill_check_passed` completion.

    F.8.c.2.b₆ (May 20 2026): now wired from
    `parser/chain_commands.py::ChainCommand._handle_attempt`. The
    player types `chain attempt`; the parser command reads the
    active step via `get_active_step_info`, runs
    `engine.skill_checks.perform_skill_check` against the step's
    authored `skill` and `difficulty`, and dispatches the result
    here. See module docstring "F.8.c.2.b₆ design note" for the
    seam decision.

    `skill_name` is the lowercase WEG skill identifier (e.g.
    "sneak", "con", "search", "starship_repair"). `succeeded` is
    the boolean outcome of the roll (caller is expected to have
    invoked engine.skill_checks.perform_skill_check at the chain
    step's authored `difficulty`).

    `difficulty` is accepted for logging/observability only — the
    dispatcher does not re-check it. The chain step's authored
    difficulty is informational once the roll has been made.

    A failed check (`succeeded=False`) is a hard no-match (returns
    False without consulting any chain step). The caller is
    responsible for dispatching failure consequences per the
    chain step's `on_fail` / `fallback` / `on_fail_narrative`
    fields — `parser/chain_commands.py` does this.

    Returns True iff a chain step advanced. Failure-tolerant.
    """
    if not skill_name:
        return False
    try:
        return await _try_advance_all_slots(
            db, char,
            event_type="skill_check_passed",
            matcher=lambda c: _match_skill_check_passed(
                c, skill_name, succeeded
            ),
        )
    except Exception as e:
        log.warning(
            "[chain_events] on_skill_check_passed failed: %s",
            e, exc_info=True,
        )
        return False


# ── Internal: shared advance-the-chain machinery ─────────────────────


async def _try_advance_all_slots(db, char: dict, *, event_type: str,
                                 matcher, prereq_matcher=None) -> bool:
    """T5-questline arc (2026-06-13): run `_try_advance` against every
    chain slot a player can carry (onboarding `tutorial_chain` +
    mid-game `active_questline`), returning True iff ANY slot advanced.

    Walks slots in `CHAIN_STATE_KEYS` order (onboarding first). In
    practice at most one slot has a matching active step — a new player
    has only the onboarding chain; a veteran's onboarding chain is long
    graduated — but the engine supports both being active at once. Each
    slot is evaluated independently; a match/advance in one does not
    short-circuit evaluation of the other, so an event that legitimately
    completes a step in both slots advances both.

    Failure-tolerant per slot: an exception advancing one slot is logged
    and does not prevent the other slot from being tried."""
    from engine.tutorial_chains import CHAIN_STATE_KEYS
    advanced_any = False
    for state_key in CHAIN_STATE_KEYS:
        try:
            if await _try_advance(
                db, char,
                event_type=event_type,
                matcher=matcher,
                prereq_matcher=prereq_matcher,
                state_key=state_key,
            ):
                advanced_any = True
        except Exception as e:  # pragma: no cover — defensive
            log.warning(
                "[chain_events] slot %r advance failed (event=%s): %s",
                state_key, event_type, e, exc_info=True,
            )
    return advanced_any


async def _try_advance(db, char: dict, *, event_type: str,
                       matcher, prereq_matcher=None,
                       state_key: str = None) -> bool:
    """Common implementation: load attrs, find active step, check
    match, advance, persist. Returns True iff a step actually
    advanced.

    T5-questline arc (2026-06-13): `state_key` selects the slot
    (onboarding vs questline). Defaults to the onboarding slot. The
    public hooks call this once per slot via `_try_advance_all_slots`
    so a single runtime event advances whichever slot owns a matching
    active step.

    `matcher` is a callable taking the completion dict and returning
    True iff the event satisfies the step's completion criteria.

    F.8.c.2.b₅ Phase 3 (May 5 2026): added optional `prereq_matcher`.
    When provided, the active step's `requires_first` list (if any)
    is consulted before the main matcher runs. Each prereq is a
    descriptor dict (today: command-shaped) and `prereq_matcher(p)`
    returns True iff the current event satisfies that descriptor.

    Behaviour with `prereq_matcher`:

    1. If the active step has a `requires_first` list and the event
       matches an unsatisfied prereq descriptor, the prereq is
       recorded against the step state, persisted, and the function
       returns False (event consumed; no advance).
    2. If the event matches the main completion (`event_type` and
       `matcher`), the function additionally requires that ALL
       `requires_first` prereqs be satisfied before allowing the
       advance. A main-event hit with unmet prereqs is silently
       refused (return False) — no advance, no state change.
    3. If both conditions could apply (degenerate corpus where the
       main matcher and a prereq descriptor match the same event),
       prereq-recording wins. The next event of the same shape will
       then attempt to fire the main completion.

    `prereq_matcher=None` (the default) preserves Phase 1+2
    semantics: no prereq tracking, no prereq gating. Event types
    whose dispatchers don't pass `prereq_matcher` simply can't
    contribute to `requires_first` satisfaction. None of the chain
    steps in chains.yaml use non-command prereqs today, so leaving
    other dispatchers (talk_to_npc, combat_won, etc.) at the default
    is correct."""
    from engine.tutorial_chains import _TUTORIAL_CHAIN_KEY
    if state_key is None:
        state_key = _TUTORIAL_CHAIN_KEY

    corpus = _get_corpus()
    if corpus is None:
        return False

    attrs = _load_attrs(char)
    chain, step = _get_active_step(attrs, corpus, state_key)
    if chain is None or step is None:
        return False

    completion = step.completion or {}

    # F.8.c.2.b₅ Phase 3: prereq satisfaction. Runs before the main
    # matcher so a single command_executed event satisfies a prereq
    # OR fires the main completion, never both. Order matters only
    # in the degenerate case where the same event would do both —
    # which no chain step exercises today.
    if prereq_matcher is not None:
        requires_first = completion.get("requires_first")
        if isinstance(requires_first, list) and requires_first:
            from engine.tutorial_chains import (
                get_satisfied_prereqs, record_prereq_satisfied,
            )
            already_satisfied = get_satisfied_prereqs(attrs, state_key)
            for i, prereq in enumerate(requires_first):
                if i in already_satisfied:
                    continue
                try:
                    if not isinstance(prereq, dict):
                        continue
                    if not prereq_matcher(prereq):
                        continue
                except Exception as e:  # pragma: no cover — defensive
                    log.debug(
                        "[chain_events] prereq matcher raised on "
                        "step %d index %d: %s", step.step, i, e,
                    )
                    continue
                # Match. Record and persist; return without advancing.
                if record_prereq_satisfied(attrs, i, state_key):
                    await _persist_attrs(db, char, attrs)
                    log.info(
                        "[chain_events] char %s satisfied prereq "
                        "%d of chain %r step %d",
                        char.get("id"), i, chain.chain_id, step.step,
                    )
                # First match wins. Don't try other prereq slots — a
                # single event satisfying multiple prereq descriptors
                # at once would be a corpus-authoring error and is
                # not exercised by any chain.
                return False

    if completion.get("type") != event_type:
        return False

    if not matcher(completion):
        return False

    # F.8.c.2.b₅ Phase 3: gate the advance on prereqs. The main
    # event matched but if any `requires_first` slot is still
    # unsatisfied, refuse the advance silently. The player will
    # have to satisfy the missing prereqs and try the main
    # completion again.
    satisfied = []
    if completion.get("requires_first"):
        from engine.tutorial_chains import get_satisfied_prereqs
        satisfied = get_satisfied_prereqs(attrs, state_key)
    if not _all_prereqs_satisfied(completion, satisfied):
        log.debug(
            "[chain_events] char %s hit main completion of chain %r "
            "step %d but %d/%d prereqs satisfied — refusing advance",
            char.get("id"), chain.chain_id, step.step,
            len(satisfied),
            len(completion.get("requires_first") or []),
        )
        return False

    # Advance
    from engine.tutorial_chains import advance_step
    new_step, graduated = advance_step(attrs, corpus, state_key)

    # F.8.c.2.b₄: per-step reward delivery. The just-completed
    # step's reward (typically narrative-prop items like
    # sealed_data_packet) lands in inventory now. Failure-tolerant:
    # item-grant errors are logged but never block chain
    # advancement.
    try:
        from engine.chain_rewards import apply_step_rewards
        await apply_step_rewards(db, char, step, chain.chain_id)
    except Exception as e:
        log.debug("[chain_events] step reward delivery failed: %s",
                  e, exc_info=True)

    # F.8.c.2.c: graduation teleport. Resolves drop_room slug,
    # persists room change, stamps pending_drop_room_id flag for
    # parser hook sites to deliver the session-aware UI work.
    # Runs BEFORE _persist_attrs so the pending flag and the
    # graduated state save in the same write.
    if graduated:
        try:
            from engine.chain_graduation import apply_graduation
            await apply_graduation(
                db, char, attrs, chain.graduation.drop_room, state_key,
            )
        except Exception as e:
            log.debug("[chain_events] graduation teleport persist "
                      "failed: %s", e, exc_info=True)

        # F.8.c.2.d: graduation reward delivery. Awards credits,
        # faction rep, items, achievements; stamps a
        # graduation_summary onto chargen_notes for the parser-side
        # summary line delivery. Runs after apply_graduation so
        # the room change is already committed if reward delivery
        # races a save. Failure-tolerant: per-reward errors are
        # logged inside apply_graduation_rewards.
        try:
            from engine.chain_rewards import apply_graduation_rewards
            await apply_graduation_rewards(
                db, char, attrs,
                graduation=chain.graduation,
                chain_id=chain.chain_id,
                chain_label=chain.chain_name or chain.chain_id,
            )
        except Exception as e:
            log.debug("[chain_events] graduation reward delivery "
                      "failed: %s", e, exc_info=True)

    # F.8.c.2.e (2026-06-12): inter-step teleport (non-graduation
    # advance). Move the player to the NEW step's authored `location`
    # so the exit-less tutorial rooms connect via the state machine —
    # the movement rooms.yaml's EXIT POLICY always assumed but which
    # was only ever implemented for graduation, stranding players at
    # the first step whose room differed from `starting_room`. Runs
    # BEFORE the final _persist_attrs so the stamped pending_step_room_id
    # flag rides that attrs write. NOTE: apply_step_teleport issues its
    # OWN save_character(room_id=...) for the move, so the room change
    # and the pending flag are TWO separate writes, not one atomic write
    # — a crash between them would advance room_id without the pending
    # flag (the parser finisher then just skips the arrival UI; the
    # player is in the right room, only the "you make your way" flavor
    # is lost). apply_step_teleport no-ops when the new step shares the
    # current room or has no location
    # slug; it is failure-tolerant (a bad slug logs and leaves the
    # player put rather than stranding them worse).
    elif new_step is not None:
        try:
            from engine.chain_graduation import apply_step_teleport
            await apply_step_teleport(
                db, char, attrs, new_step.location, state_key,
            )
        except Exception as e:
            # WARNING (not DEBUG): a real save_character/DB failure here
            # leaves the player in the wrong room — worth an operational
            # signal. The advance itself already persisted; this is the
            # convenience move.
            log.warning("[chain_events] inter-step teleport failed: %s",
                        e, exc_info=True)

    await _persist_attrs(db, char, attrs)

    log.info("[chain_events] char %s advanced chain %r past step %d "
             "(event=%s); graduated=%s",
             char.get("id"), chain.chain_id, step.step,
             event_type, graduated)

    # F.8.c.2.b₃: On step entry, spawn any chain-tutorial mission /
    # bounty that this new step depends on. No-op if the new step's
    # completion type isn't mission-/bounty-driven, or if the
    # tutorial roster has no entry for this chain step.
    # Failure-tolerant: spawn errors are swallowed inside
    # maybe_spawn_for_step so a YAML loader hiccup never blocks a
    # chain advancement.
    if new_step is not None and not graduated:
        try:
            from engine.chain_missions import maybe_spawn_for_step
            await maybe_spawn_for_step(
                db, char, chain.chain_id, new_step.step,
            )
        except Exception as e:
            log.debug("[chain_events] spawn-on-step-entry hook "
                      "failed: %s", e, exc_info=True)

    return True


# ── Optional: introspection helpers used by tests + UI ───────────────


def get_active_step_info(char: dict, era: Optional[str] = None,
                         state_key: str = None,
                         ) -> Optional[dict]:
    """Return a small JSON-friendly view of the character's current
    chain step, or None if no active chain. Used by web HUD, by
    tests, and by the `chain attempt` command (F.8.c.2.b₆,
    May 20 2026) which needs the full `completion` payload to
    drive the explicit skill roll.

    F.8.c.2.b₆ extension: the `completion` field is now included
    so callers that need the full step contract (skill name,
    difficulty, on_fail behavior, fallback) can read it without
    a second corpus walk. Pre-extension consumers reading only
    `completion_type` still work — the new key is additive.

    T5-questline arc (2026-06-13): `state_key` selects which slot to
    introspect. Defaults to the onboarding slot (so the web HUD and
    `chain status` are unchanged); the `quests` command passes the
    questline slot.
    """
    from engine.tutorial_chains import _TUTORIAL_CHAIN_KEY
    if state_key is None:
        state_key = _TUTORIAL_CHAIN_KEY
    corpus = _get_corpus(era)
    if corpus is None:
        return None
    attrs = _load_attrs(char)
    chain, step = _get_active_step(attrs, corpus, state_key)
    if chain is None or step is None:
        return None
    return {
        "chain_id": chain.chain_id,
        "chain_name": chain.chain_name,
        "step": step.step,
        "title": step.title,
        "objective": step.objective,
        "location": step.location,
        "npc": step.npc,
        "completion_type": (step.completion or {}).get("type"),
        # F.8.c.2.b₆: full completion dict for callers (chain
        # attempt command) that need the authored skill/difficulty/
        # fallback/on_fail payload. dict() copy so callers can't
        # accidentally mutate the corpus.
        "completion": dict(step.completion or {}),
        # ── Webify UI-7 (2026-06-10): additive fields for the web
        # onboarding panel. Existing consumers (chain status/attempt,
        # tests) read named keys and are unaffected. list() copies so
        # callers can't mutate the corpus.
        "chain_total_steps": len(chain.steps),
        "teaches": list(step.teaches or []),
        "npc_role": step.npc_role,
        "npc_intro": step.npc_intro,
        # drop 26 (2026-06-13): surface the authored `next_hint` so the
        # web onboarding panel can render a NEXT line under the
        # objective (it was authored in the corpus but never sent).
        "next_hint": step.next_hint or "",
        "completed_steps": list(
            (attrs.get(state_key) or {}).get("completed_steps") or []
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# T5-questline arc (2026-06-13) — mid-game questline start surface
# ─────────────────────────────────────────────────────────────────────
#
# A questline is a `kind: questline` chain a veteran starts deliberately
# mid-game (vs. an onboarding chain assigned at chargen). It lives in the
# `active_questline` attributes slot. These functions back the `quests` /
# `quest start` player commands (parser/questline_commands.py) and the
# NPC-offer surface (a questline-giver NPC names the questline it offers
# via its ai_config `offers_questline` field).
#
# Eligibility reuses `is_chain_locked_for_character` against the
# questline's `prerequisites` — which is where the rep-floor /
# faction-intent gate is authored. A player may carry at most ONE active
# questline at a time (the single `active_questline` slot); they must
# finish or abandon it before starting another.


def list_questlines(era: Optional[str] = None) -> list:
    """Return every `kind: questline` chain in the corpus (TutorialChain
    objects). Empty list if the era has no chains or no questlines."""
    corpus = _get_corpus(era)
    if corpus is None:
        return []
    return [c for c in corpus.chains
            if getattr(c, "kind", "tutorial") == "questline"]


def get_questline_status(char: dict, era: Optional[str] = None
                         ) -> Optional[dict]:
    """Step-info view of the character's ACTIVE questline, or None.

    Thin wrapper over get_active_step_info pinned to the questline
    slot."""
    from engine.tutorial_chains import _QUESTLINE_KEY
    return get_active_step_info(char, era, _QUESTLINE_KEY)


def has_active_questline(char: dict) -> bool:
    """True iff the character currently has an active (non-graduated)
    questline in the questline slot."""
    from engine.tutorial_chains import get_active_chain_id, _QUESTLINE_KEY
    attrs = _load_attrs(char)
    return get_active_chain_id(attrs, _QUESTLINE_KEY) is not None


def get_questline_offer(char: dict, npc_name: str,
                        era: Optional[str] = None) -> Optional[dict]:
    """If `npc_name` is the start-NPC of a questline the character is
    ELIGIBLE for and has not already started/completed, return a small
    offer dict {chain_id, chain_name, description, locked, reason}.
    Returns None when there's nothing to offer.

    "Start-NPC" = the questline's step-1 `npc`. This reuses the existing
    talk_to_npc seam: when a player talks to a questline's step-1 NPC and
    has no active questline + meets prereqs, the talk surfaces this offer.

    Eligibility is `is_chain_locked_for_character` against the
    questline's prerequisites (the rep/faction gate). An already-active
    or already-graduated questline of the same id is never re-offered."""
    from engine.tutorial_chains import (
        is_chain_locked_for_character, has_completed_chain,
        get_active_chain_id, _QUESTLINE_KEY,
    )
    if not npc_name:
        return None
    attrs = _load_attrs(char)
    # One questline at a time: if any questline is active, no new offers.
    if get_active_chain_id(attrs, _QUESTLINE_KEY) is not None:
        return None
    npc_lower = npc_name.strip().lower()
    # Each t5 trainer is the start-NPC of exactly ONE questline (design
    # intent), so first-match is the common path. Defensive against a
    # future author wiring two questlines to one NPC: prefer an UNLOCKED
    # match (return immediately), and fall back to a locked match only
    # if no unlocked one is found — so a locked questline can't suppress
    # a valid offer the player IS eligible for.
    locked_fallback = None
    for ql in list_questlines(era):
        if not ql.steps:
            continue
        start_npc = (ql.steps[0].npc or "").strip().lower()
        if start_npc != npc_lower:
            continue
        if has_completed_chain(attrs, ql.chain_id):
            continue  # already done — don't re-offer
        locked, reason = is_chain_locked_for_character(ql, attrs)
        offer = {
            "chain_id": ql.chain_id,
            "chain_name": ql.chain_name,
            "description": ql.description,
            "locked": locked,
            "reason": reason,
        }
        if not locked:
            return offer
        if locked_fallback is None:
            locked_fallback = offer
    return locked_fallback


async def start_questline(db, char: dict, chain_id: str,
                          era: Optional[str] = None) -> tuple:
    """Begin a questline for the character. Returns (ok: bool,
    message: str). Persists the new questline slot on success.

    Validation (in order):
      - corpus loads + chain_id resolves to a `kind: questline` chain
      - the character has no active questline already (one at a time)
      - the character hasn't already completed this questline
      - the chain is unlocked for the character
        (is_chain_locked_for_character — the rep/faction gate)

    On success the questline slot is initialized at step 1 and the
    character is teleported to step 1's location (reusing the same
    inter-step teleport the dispatcher uses on advance), so the player
    lands where the questline begins."""
    from engine.tutorial_chains import (
        is_chain_locked_for_character, has_completed_chain,
        get_active_chain_id, select_chain, _QUESTLINE_KEY,
    )
    corpus = _get_corpus(era)
    if corpus is None:
        return False, "Questlines are unavailable right now."
    chain = corpus.by_id().get(chain_id)
    if chain is None or getattr(chain, "kind", "tutorial") != "questline":
        return False, f"No questline '{chain_id}'."

    attrs = _load_attrs(char)
    active = get_active_chain_id(attrs, _QUESTLINE_KEY)
    if active is not None:
        return False, ("You're already on a questline. Finish or "
                       "abandon it before starting another.")
    if has_completed_chain(attrs, chain.chain_id):
        return False, "You've already completed that questline."

    locked, reason = is_chain_locked_for_character(chain, attrs)
    if locked:
        return False, reason or "You don't meet the requirements yet."

    select_chain(attrs, chain, state_key=_QUESTLINE_KEY)
    # Teleport to step 1's location so the player lands at the start.
    first_loc = chain.steps[0].location if chain.steps else ""
    if first_loc:
        try:
            from engine.chain_graduation import apply_step_teleport
            await apply_step_teleport(db, char, attrs, first_loc,
                                      _QUESTLINE_KEY)
        except Exception as e:
            log.warning("[chain_events] questline start teleport "
                        "failed: %s", e, exc_info=True)
    await _persist_attrs(db, char, attrs)
    log.info("[chain_events] char %s started questline %r",
             char.get("id"), chain.chain_id)
    return True, f"You begin: {chain.chain_name}."


async def abandon_questline(db, char: dict) -> tuple:
    """Abandon the character's active questline. Returns (ok, message).
    Clears the questline slot; the player may re-start it later (subject
    to the same gate)."""
    from engine.tutorial_chains import (
        get_active_chain_id, reset_chain_state, _QUESTLINE_KEY,
    )
    attrs = _load_attrs(char)
    if get_active_chain_id(attrs, _QUESTLINE_KEY) is None:
        return False, "You have no active questline to abandon."
    reset_chain_state(attrs, _QUESTLINE_KEY)
    await _persist_attrs(db, char, attrs)
    log.info("[chain_events] char %s abandoned their questline",
             char.get("id"))
    return True, "You abandon your current questline."


# ─────────────────────────────────────────────────────────────────────
# Webify UI-7 (2026-06-10) — onboarding_state producer for the web client
# ─────────────────────────────────────────────────────────────────────


def build_onboarding_state(char: dict, era: Optional[str] = None
                           ) -> Optional[dict]:
    """Assemble the `onboarding_state` push for the web training panel.

    Pinned ABI (web_client_vision_and_protocol_v1_4.md §1.8)::

        active chain  → { active: True, chain_id, chain_name,
                          step, total_steps, completed_steps,
                          title, objective, location, npc, npc_role,
                          npc_intro, teaches, completion_type,
                          next_hint }
        graduated     → { active: False, graduated: True,
                          chain_id, chain_name }
        no chain ever → None

    drop 26 (2026-06-13): `next_hint` added to the active payload
    (additive — pre-existing consumers ignore the new key).

    The graduated payload fires on EVERY call once
    `completion_state == "graduated"` — push-once gating is the
    session's job (the `_last_chain_step` memo), so a reconnect after
    graduation pushes nothing. Layered on the same cached corpus as
    `get_active_step_info`; pure aside from that cache; never raises
    (malformed attrs → None).
    """
    try:
        info = get_active_step_info(char, era)
        if info is not None:
            return {
                "active": True,
                "chain_id": info["chain_id"],
                "chain_name": info["chain_name"],
                "step": info["step"],
                "total_steps": info["chain_total_steps"],
                "completed_steps": info["completed_steps"],
                "title": info["title"],
                "objective": info["objective"],
                "location": info["location"],
                "npc": info["npc"],
                "npc_role": info["npc_role"],
                "npc_intro": info["npc_intro"],
                "teaches": info["teaches"],
                "completion_type": info["completion_type"],
                # drop 26 (2026-06-13): authored pointer to the next
                # step / graduation, rendered as a NEXT line in the
                # web panel.
                "next_hint": info.get("next_hint", ""),
            }

        # No ACTIVE chain — distinguish "graduated" from "never had one".
        attrs = _load_attrs(char)
        state = attrs.get("tutorial_chain") or {}
        if state.get("completion_state") != "graduated":
            return None
        chain_id = state.get("chain_id") or ""
        chain_name = chain_id
        corpus = _get_corpus(era)
        if corpus is not None:
            chain = corpus.by_id().get(chain_id)
            if chain is not None:
                chain_name = chain.chain_name
        return {
            "active": False,
            "graduated": True,
            "chain_id": chain_id,
            "chain_name": chain_name,
        }
    except Exception:
        log.debug("build_onboarding_state failed", exc_info=True)
        return None
