# -*- coding: utf-8 -*-
"""
engine/tutorial_chains.py — CW tutorial chains loader + state machine.

Drop F.8 (Apr 30 2026) — Phase 1: ships the chain loader, typed
dataclasses, and stateless state-machine helpers consuming
data/worlds/<era>/tutorials/chains.yaml. Does NOT integrate with the
running tutorial engine yet — that's F.8.b.

Phase 1 scope (this module)
---------------------------
- `load_tutorial_chains(era)` — YAML loader returning typed corpus
- `TutorialChain` / `TutorialStep` / `Graduation` dataclasses
- Stateless state-machine helpers for chain selection / step
  advancement / locked-chain rejection / graduation detection
- All operations work against character `attributes` JSON dicts;
  no DB, no session, no parser dependencies

Phase 2 scope (F.8.b — future drop)
-----------------------------------
- Integration with `engine/tutorial_v2.py` or replacement
- Wire 11 `completion.type` values into engine event hooks (parser,
  combat, NPC dialogue, missions, bounties, inventory, movement)
- Build the 25 new tutorial-zone rooms from the chain definitions
- Locked-chain rejection wired into chargen tutorial-selection UI

Why phase split
---------------
The CW tutorial engine refactor is sized at "one full implementation
sitting" per cw_tutorial_chains_design_v1.md §6. Phase-splitting
isolates the loader + state shape (this drop) from the runtime
integration (next drop). Same pattern as F.6a.1 (loader without
integration) and F.7 (seam with deferred runtime).

Tested by tests/test_f8_tutorial_chains_yaml.py.

F.7.j (May 4 2026) — extension
------------------------------
`is_chain_locked_for_character` now recognizes a second mapped-key
prerequisite shape: ``{"village_chosen_path": "a"|"b"|"c"}``. This
lets the Jedi Path branch into Order- and Independent-flavored
chains after the Village quest commits a path. No schema change;
no parser change; the new vocabulary is additive.

Tested by tests/test_f7j_path_chain_branching.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── Schema constants ─────────────────────────────────────────────────────

ALLOWED_COMPLETION_TYPES = frozenset({
    "command_executed",
    "talk_to_npc",
    "combat_won",
    "skill_check_passed",
    "mission_accepted",
    "mission_completed",
    "bounty_accepted",
    "item_acquired",
    "item_used",
    "room_entered",
    "prerequisite",
})

ALLOWED_NPC_ROLES = frozenset({"instructor", "contact", "antagonist"})

ALLOWED_PREREQUISITE_FLAGS = frozenset({
    "chargen_complete",
    "force_sensitive",
    "jedi_path_unlocked",
    "tutorial_core_complete",
})


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class TutorialStep:
    """One step in a tutorial chain.

    Mirrors the per-step schema in chains.yaml. `completion` is left as
    a raw dict because the inner shape varies by completion.type — the
    engine event-hook wiring (F.8.b) is the right place to type it.
    """
    step: int
    title: str
    location: str
    npc: str
    npc_role: str
    teaches: list  # list[str]
    objective: str
    npc_intro: str
    completion: dict
    npc_complete: str
    reward: dict
    next_hint: str


@dataclass
class Graduation:
    """Chain graduation rewards. drop_room is the room slug the player
    is teleported to on chain completion (typically the live-world
    counterpart to the tutorial-zone starting room)."""
    drop_room: str
    credits: int = 0
    faction_rep: dict = field(default_factory=dict)  # {faction_code: int}
    items: list = field(default_factory=list)        # list[str]
    achievements: list = field(default_factory=list) # list[str]
    follow_up_hint: str = ""


@dataclass
class TutorialChain:
    """One tutorial profession chain.

    `prerequisites` is a list where each entry is either a flag string
    (e.g. "chargen_complete") OR a single-key dict like
    {"faction_intent": "republic"}. Flag strings draw from
    ALLOWED_PREREQUISITE_FLAGS; the only allowed mapped-key prereq is
    `faction_intent`.

    `locked=True` chains use `locked_message` instead of letting the
    player select. `prerequisites` for locked chains additionally
    name flags the engine must check (e.g. jedi_path_unlocked,
    force_sensitive) before the chain becomes available.
    """
    chain_id: str
    chain_name: str
    description: str
    archetype_label: str
    faction_alignment: Optional[str]
    starting_zone: str
    starting_room: str
    prerequisites: list  # list[str | dict]
    duration_minutes: int
    locked: bool
    graduation: Graduation
    steps: list  # list[TutorialStep]
    locked_message: str = ""


@dataclass
class TutorialChainsCorpus:
    """Parsed chains.yaml corpus.

    `errors` and `warnings` are Phase-1 carry-forward — same convention
    as world_loader's ValidationReport. Engine consumers should treat
    a corpus with errors as broken and surface fail-loud per §18.19.
    """
    schema_version: int
    chains: list  # list[TutorialChain]
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def by_id(self) -> dict:
        """Return chains keyed by chain_id (preserves YAML order
        across recent Pythons)."""
        return {c.chain_id: c for c in self.chains}


# ── Loader ───────────────────────────────────────────────────────────────

def load_tutorial_chains(
    era: Optional[str] = None,
    *,
    worlds_root: Optional[Path] = None,
) -> Optional[TutorialChainsCorpus]:
    """Load the tutorial chains YAML for the given era.

    Returns None if the era's tutorials/chains.yaml file doesn't
    exist (e.g. GCW has no chain-based tutorial — its tutorial is
    `engine/tutorial_v2.py`'s 8-elective module model). Callers
    should treat None as "this era doesn't use chain tutorials" and
    fall through to the era's native tutorial path.

    Returns a TutorialChainsCorpus on success. The corpus carries
    `errors` and `warnings` lists; an `errors`-bearing corpus is
    structurally broken and consumers should refuse to use it.
    """
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception as e:
            log.warning(
                "[tutorial_chains] era_state import failed (%s); "
                "defaulting to 'clone_wars' (the only era with "
                "chain-based tutorials).", e,
            )
            era = "clone_wars"

    root = worlds_root or (Path("data") / "worlds")
    chains_path = Path(root) / era / "tutorials" / "chains.yaml"

    if not chains_path.is_file():
        log.info(
            "[tutorial_chains] No chains.yaml at %s; this era uses "
            "the native tutorial path.", chains_path,
        )
        return None

    try:
        import yaml
    except ImportError as e:
        log.error("[tutorial_chains] pyyaml unavailable (%s).", e)
        return None

    try:
        with open(chains_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        log.error(
            "[tutorial_chains] Failed to parse %s: %s", chains_path, e,
        )
        return TutorialChainsCorpus(
            schema_version=0, chains=[],
            errors=[f"YAML parse error: {e}"],
        )

    if not isinstance(raw, dict):
        return TutorialChainsCorpus(
            schema_version=0, chains=[],
            errors=[f"Top-level must be a mapping; got "
                    f"{type(raw).__name__}"],
        )

    schema_version = int(raw.get("schema_version", 1))
    chain_blocks = raw.get("chains")

    if not isinstance(chain_blocks, list):
        return TutorialChainsCorpus(
            schema_version=schema_version, chains=[],
            errors=[f"`chains` must be a list; got "
                    f"{type(chain_blocks).__name__}"],
            raw=raw,
        )

    chains: list = []
    errors: list = []
    warnings: list = []

    for idx, cb in enumerate(chain_blocks):
        chain_obj, c_errors, c_warnings = _parse_chain(cb, idx)
        errors.extend(c_errors)
        warnings.extend(c_warnings)
        if chain_obj is not None:
            chains.append(chain_obj)

    return TutorialChainsCorpus(
        schema_version=schema_version,
        chains=chains,
        errors=errors,
        warnings=warnings,
        raw=raw,
    )


def _parse_chain(cb: dict, idx: int) -> tuple:
    """Parse one chain block. Returns (TutorialChain or None,
    errors, warnings). A missing-required-field chain returns None
    so the corpus can keep loading the rest."""
    if not isinstance(cb, dict):
        return None, [f"chain[{idx}]: must be a mapping"], []

    cid = cb.get("chain_id", f"<unknown #{idx}>")
    errors: list = []
    warnings: list = []

    required = {
        "chain_id", "chain_name", "description", "archetype_label",
        "faction_alignment", "starting_zone",
        "prerequisites", "duration_minutes", "locked", "graduation",
        "steps",
    }
    missing = required - set(cb.keys())
    if missing:
        errors.append(
            f"chain[{idx}] ({cid}): missing required fields: "
            f"{sorted(missing)}",
        )
        return None, errors, warnings

    # `starting_room` is optional — locked stub chains (jedi_path) carry
    # only a starting_zone since they have no steps to anchor. Engine
    # consumers that need a room slug should use chain.starting_room
    # only when chain.steps is non-empty.

    # Type checks — fail fast on shape problems
    if not isinstance(cb["duration_minutes"], int):
        errors.append(
            f"chain[{idx}] ({cid}): duration_minutes must be int",
        )
        return None, errors, warnings

    if not isinstance(cb["locked"], bool):
        errors.append(
            f"chain[{idx}] ({cid}): locked must be bool",
        )
        return None, errors, warnings

    if cb["locked"] and not cb.get("locked_message"):
        warnings.append(
            f"chain[{idx}] ({cid}): locked chain has empty/missing "
            f"locked_message",
        )

    # NPC role validation per step + completion type validation
    raw_steps = cb.get("steps", [])
    if not isinstance(raw_steps, list):
        errors.append(
            f"chain[{idx}] ({cid}): steps must be a list",
        )
        return None, errors, warnings

    steps: list = []
    for sidx, sb in enumerate(raw_steps):
        step_obj, s_errors = _parse_step(sb, cid, sidx)
        errors.extend(s_errors)
        if step_obj is not None:
            steps.append(step_obj)

    # 1-indexed contiguous step numbers
    if steps:
        step_nums = [s.step for s in steps]
        expected = list(range(1, len(steps) + 1))
        if step_nums != expected:
            errors.append(
                f"chain[{idx}] ({cid}): step numbers must be 1.."
                f"{len(steps)} contiguous; got {step_nums}",
            )

    grad_block = cb.get("graduation")
    if not isinstance(grad_block, dict):
        errors.append(
            f"chain[{idx}] ({cid}): graduation must be a mapping",
        )
        return None, errors, warnings
    if not grad_block.get("drop_room"):
        errors.append(
            f"chain[{idx}] ({cid}): graduation.drop_room is required",
        )
        return None, errors, warnings

    graduation = Graduation(
        drop_room=str(grad_block["drop_room"]),
        credits=int(grad_block.get("credits", 0)),
        faction_rep=dict(grad_block.get("faction_rep") or {}),
        items=list(grad_block.get("items") or []),
        achievements=list(grad_block.get("achievements") or []),
        follow_up_hint=str(grad_block.get("follow_up_hint") or ""),
    )

    chain = TutorialChain(
        chain_id=str(cb["chain_id"]),
        chain_name=str(cb["chain_name"]),
        description=str(cb["description"]),
        archetype_label=str(cb["archetype_label"]),
        faction_alignment=cb.get("faction_alignment"),
        starting_zone=str(cb["starting_zone"]),
        starting_room=str(cb.get("starting_room") or ""),
        prerequisites=list(cb.get("prerequisites") or []),
        duration_minutes=int(cb["duration_minutes"]),
        locked=bool(cb["locked"]),
        graduation=graduation,
        steps=steps,
        locked_message=str(cb.get("locked_message") or ""),
    )

    return chain, errors, warnings


def _parse_step(sb: dict, cid: str, sidx: int) -> tuple:
    """Parse one step block. Returns (TutorialStep or None, errors)."""
    errors: list = []
    if not isinstance(sb, dict):
        return None, [f"chain {cid} step[{sidx}]: must be a mapping"]

    required = {
        "step", "title", "location", "npc", "npc_role",
        "teaches", "objective", "npc_intro", "completion",
        "npc_complete", "reward", "next_hint",
    }
    missing = required - set(sb.keys())
    if missing:
        errors.append(
            f"chain {cid} step[{sidx}]: missing fields: "
            f"{sorted(missing)}",
        )
        return None, errors

    if sb["npc_role"] not in ALLOWED_NPC_ROLES:
        errors.append(
            f"chain {cid} step[{sb.get('step', sidx)}]: invalid "
            f"npc_role {sb['npc_role']!r}; allowed "
            f"{sorted(ALLOWED_NPC_ROLES)}",
        )
        return None, errors

    if not isinstance(sb["teaches"], list):
        errors.append(
            f"chain {cid} step[{sb.get('step', sidx)}]: teaches "
            f"must be a list",
        )
        return None, errors

    completion = sb["completion"]
    if not isinstance(completion, dict):
        errors.append(
            f"chain {cid} step[{sb.get('step', sidx)}]: completion "
            f"must be a mapping",
        )
        return None, errors

    ctype = completion.get("type")
    if ctype not in ALLOWED_COMPLETION_TYPES:
        errors.append(
            f"chain {cid} step[{sb.get('step', sidx)}]: completion."
            f"type {ctype!r} not in allowed set "
            f"{sorted(ALLOWED_COMPLETION_TYPES)}",
        )
        return None, errors

    return (
        TutorialStep(
            step=int(sb["step"]),
            title=str(sb["title"]),
            location=str(sb["location"]),
            npc=str(sb["npc"]),
            npc_role=str(sb["npc_role"]),
            teaches=list(sb["teaches"]),
            objective=str(sb["objective"]),
            npc_intro=str(sb["npc_intro"]),
            completion=dict(completion),
            npc_complete=str(sb["npc_complete"]),
            reward=dict(sb.get("reward") or {}),
            next_hint=str(sb["next_hint"]),
        ),
        errors,
    )


# ── State-machine helpers ────────────────────────────────────────────────
#
# All helpers operate on a character `attributes` dict (the JSON-backed
# state shape used by engine/tutorial_v2.py). They never touch the DB
# directly; DB persistence is the caller's job. This keeps the helpers
# pure functions for easy testing.
#
# Tutorial chain state shape (added in F.8 Phase 1):
#
#     attributes["tutorial_chain"] = {
#         "chain_id": "republic_soldier",
#         "step": 1,                     # 1-indexed; 0 = not started
#         "started_at": <unix_ts>,
#         "completed_steps": [],         # list of completed step ints
#         "completion_state": "active",  # "active" | "graduated" | None
#     }
#
# When a chain is graduated, `completion_state == "graduated"` is the
# durable "you finished this chain" marker. Players who graduate one
# chain may select another (the design allows multiple chain runs).


_TUTORIAL_CHAIN_KEY = "tutorial_chain"


def is_chain_locked_for_character(
    chain: TutorialChain,
    char_attrs: dict,
) -> tuple:
    """Check whether a chain is selectable by the given character.

    Returns (is_locked: bool, reason: str). reason is the
    `locked_message` from the chain when locked, or the missing
    prerequisite description when prerequisites aren't met.

    Logic:
      - If `chain.locked` is True (Jedi Path), check the additional
        prerequisite flags listed in `chain.prerequisites` against
        character attributes. ALL must be satisfied for the chain to
        be unlocked. (e.g. jedi_path_unlocked AND force_sensitive AND
        chargen_complete.) Empty `chain.locked_message` falls back to
        a generic "not yet available" message.
      - If `chain.locked` is False, prerequisites are still checked
        but this counts as the unlocked-but-prerequisite-blocked case
        (e.g. `chargen_complete` missing) — same flag-checking logic,
        different message.

    Prerequisite types:
      - String flags (chargen_complete, force_sensitive, etc.):
        check `char_attrs.get(flag) is True`.
      - {"faction_intent": "republic"}: check
        `char_attrs.get("faction_intent") == "republic"`.
        F.8.c.1 special case: the sentinel value "__chargen_any__"
        passes any faction_intent prereq. This lets the chargen
        wizard show all chains regardless of faction commitment —
        at chargen, picking a chain IS the faction commitment, so
        gating chargen visibility on faction_intent is circular.
        The wizard sets char_attrs["faction_intent"] =
        "__chargen_any__" only during the chargen render; runtime
        callers always pass the real faction_intent (or None).
      - {"village_chosen_path": "a"|"b"|"c"}: check
        `char_attrs.get("village_chosen_path") == <expected>`.
        F.7.j: lets the Jedi Path branch into Order- and
        Independent-flavored chains after the Village quest commits
        a path. Unlike `faction_intent`, there is NO chargen
        sentinel — the Jedi-Path chains MUST stay locked at
        chargen, so a chargen-fresh attrs dict (no village_chosen_path
        set) correctly fails this prereq.
    """
    CHARGEN_FACTION_ANY = "__chargen_any__"
    missing_flags: list = []
    for prereq in chain.prerequisites:
        if isinstance(prereq, str):
            if not char_attrs.get(prereq):
                missing_flags.append(prereq)
        elif isinstance(prereq, dict):
            for k, v in prereq.items():
                if k == "faction_intent":
                    actual = char_attrs.get("faction_intent")
                    if actual == CHARGEN_FACTION_ANY:
                        # Chargen sentinel — pass.
                        continue
                    if actual != v:
                        missing_flags.append(f"faction_intent={v}")
                elif k == "village_chosen_path":
                    # F.7.j: post-Village path-flavored gate.
                    actual = char_attrs.get("village_chosen_path")
                    # Normalize for case-tolerance — village_choice
                    # writes lowercase 'a'/'b'/'c' but defensive in
                    # case some path through `chargen_notes` JSON
                    # picks up a different shape.
                    actual_norm = (
                        str(actual).strip().lower() if actual else ""
                    )
                    expected_norm = str(v).strip().lower()
                    if actual_norm != expected_norm:
                        missing_flags.append(
                            f"village_chosen_path={expected_norm}"
                        )
                else:
                    # Unknown mapped-key prereq — surface as missing
                    missing_flags.append(f"{k}={v}")

    if chain.locked:
        if missing_flags:
            msg = chain.locked_message or (
                f"This path is not yet available. Required: "
                f"{', '.join(missing_flags)}."
            )
            return True, msg
        # Locked chain whose prereqs are all met — unlocked.
        return False, ""

    # Unlocked chain: prereqs still apply, but error message differs.
    if missing_flags:
        return True, (
            f"You don't yet meet the requirements for this path. "
            f"Required: {', '.join(missing_flags)}."
        )
    return False, ""


def select_chain(char_attrs: dict, chain: TutorialChain,
                 *, now: Optional[float] = None) -> dict:
    """Initialize tutorial-chain state for the character.

    Mutates `char_attrs` in place AND returns the new state block for
    convenience. Caller is responsible for persisting.

    Pre-condition: caller has already verified the chain is selectable
    via `is_chain_locked_for_character`. This function does NOT
    re-validate; it trusts the caller.

    Sets:
      attributes["tutorial_chain"] = {
        "chain_id": chain.chain_id,
        "step": 1,
        "started_at": now or time.time(),
        "completed_steps": [],
        "completion_state": "active",
      }
    """
    import time
    char_attrs[_TUTORIAL_CHAIN_KEY] = {
        "chain_id": chain.chain_id,
        "step": 1,
        "started_at": now if now is not None else time.time(),
        "completed_steps": [],
        "completion_state": "active",
    }
    return char_attrs[_TUTORIAL_CHAIN_KEY]


def get_current_step(char_attrs: dict,
                     corpus: TutorialChainsCorpus) -> Optional[TutorialStep]:
    """Return the current step the character is on, or None if no
    chain is active or the chain has graduated."""
    state = char_attrs.get(_TUTORIAL_CHAIN_KEY)
    if not state or state.get("completion_state") != "active":
        return None

    chain_id = state.get("chain_id")
    if not chain_id:
        return None

    chain = corpus.by_id().get(chain_id)
    if chain is None:
        log.warning(
            "[tutorial_chains] Character has chain_id %r but no such "
            "chain in corpus", chain_id,
        )
        return None

    step_num = state.get("step", 1)
    for step in chain.steps:
        if step.step == step_num:
            return step
    return None


def advance_step(char_attrs: dict,
                 corpus: TutorialChainsCorpus) -> tuple:
    """Mark the current step complete and advance to the next.

    Returns (new_step: TutorialStep or None, graduated: bool).

    If the current step was the last in the chain, sets
    `completion_state="graduated"` and returns (None, True). Otherwise
    increments step and returns (next_step, False).

    Mutates `char_attrs` in place. Caller persists.

    No-ops (returns (None, False)) if no active chain.
    """
    state = char_attrs.get(_TUTORIAL_CHAIN_KEY)
    if not state or state.get("completion_state") != "active":
        return None, False

    chain_id = state.get("chain_id")
    chain = corpus.by_id().get(chain_id)
    if chain is None:
        return None, False

    current_step_num = state.get("step", 1)
    completed = list(state.get("completed_steps") or [])
    if current_step_num not in completed:
        completed.append(current_step_num)
    state["completed_steps"] = completed

    next_step_num = current_step_num + 1
    if next_step_num > len(chain.steps):
        state["completion_state"] = "graduated"
        return None, True

    state["step"] = next_step_num
    for step in chain.steps:
        if step.step == next_step_num:
            return step, False
    # Step numbers were validated as 1..N contiguous at load time;
    # a missing step here would be a data-corruption surprise.
    log.warning(
        "[tutorial_chains] Step %d not found in chain %s after "
        "advance — corpus may be corrupt", next_step_num, chain_id,
    )
    return None, False


def is_chain_complete(char_attrs: dict) -> bool:
    """True iff the character has graduated their current chain."""
    state = char_attrs.get(_TUTORIAL_CHAIN_KEY) or {}
    return state.get("completion_state") == "graduated"


def get_active_chain_id(char_attrs: dict) -> Optional[str]:
    """Return the active chain_id or None."""
    state = char_attrs.get(_TUTORIAL_CHAIN_KEY) or {}
    if state.get("completion_state") == "active":
        return state.get("chain_id")
    return None


def reset_chain_state(char_attrs: dict) -> None:
    """Clear the tutorial_chain block. Used when a character abandons
    their chain (allowed only via admin command in Phase 1, possibly
    player-facing later). Mutates in place."""
    char_attrs.pop(_TUTORIAL_CHAIN_KEY, None)
