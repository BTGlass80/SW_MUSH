# -*- coding: utf-8 -*-
"""
engine/chain_missions.py — F.8.c.2.b₃ tutorial mission/bounty loader.

Loads scripted tutorial missions and bounties from
data/worlds/<era>/tutorials/tutorial_missions.yaml and
.../tutorial_bounties.yaml, materializes them into ``Mission`` /
``BountyContract`` instances tagged with the appropriate
``chain_mission_id`` / ``chain_bounty_id``, and provides the
spawn-on-step-entry hook that injects them into the live board
when a character advances into a chain step that expects them.

Why a separate loader (not the procedural generator)
----------------------------------------------------
Procedural missions are random-generator output: random type,
destination, reward, giver. They are good content for the live
mission board but they're noise for a tutorial step that needs
specific narrative anchoring (Major Tarrn briefs you on YOUR first
deployment, not "Combat: Random Backwater").

Tutorial missions/bounties are scripted; they need authored copy,
fixed givers, fixed destinations, fixed rewards. Distinct
authoring path = distinct loader.

Spawn lifecycle
---------------
- Player advances INTO a chain step whose completion expects a
  mission_accepted, mission_completed, or bounty_accepted event.
- ``maybe_spawn_for_step()`` is called by ``advance_step()``'s
  hook in tutorial_chains.py.
- For mission_accepted: spawn the mission into the live
  MissionBoard; the player's `+missions` listing now includes it
  (gated by visibility filter).
- For mission_completed: spawn AND auto-accept it into the
  player's active mission slot (the chain's narrative is "you
  already accepted this off-screen at step 3"; step 4 just
  completes it).
- For bounty_accepted: spawn the contract into the live
  BountyBoard; the player's `+bounties` listing includes it.

Visibility filtering
--------------------
- ``is_chain_mission_visible_to(mission, char)``: True iff the
  mission is open OR the character's active chain matches the
  mission's chain tags. False otherwise.
- Same for ``is_chain_bounty_visible_to``.
- Parser commands (``MissionsCommand``, ``BountiesCommand``)
  filter through these helpers before rendering the board.

Tested by tests/test_f8c2b3_chain_missions.py.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── Module-level YAML caches ─────────────────────────────────────────


_MISSIONS_CACHE: dict = {}
_BOUNTIES_CACHE: dict = {}


def _resolve_era() -> str:
    """Resolve the active era code, defaulting to clone_wars (the
    only era that has chain tutorials today)."""
    try:
        from engine.era_state import get_active_era
        return get_active_era() or "clone_wars"
    except Exception:
        return "clone_wars"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        log.warning("[chain_missions] pyyaml unavailable")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.error("[chain_missions] YAML parse failed for %s: %s",
                  path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _missions_root(era: str) -> Path:
    return (Path("data") / "worlds" / era / "tutorials"
            / "tutorial_missions.yaml")


def _bounties_root(era: str) -> Path:
    return (Path("data") / "worlds" / era / "tutorials"
            / "tutorial_bounties.yaml")


def get_tutorial_missions(era: Optional[str] = None) -> list:
    """Return the cached list of tutorial-mission entries for the
    given era (or active era). Each entry is the YAML dict — not
    yet materialized into a Mission instance."""
    era = era or _resolve_era()
    if era not in _MISSIONS_CACHE:
        data = _load_yaml(_missions_root(era))
        _MISSIONS_CACHE[era] = data.get("missions", []) or []
    return _MISSIONS_CACHE[era]


def get_tutorial_bounties(era: Optional[str] = None) -> list:
    """Return the cached list of tutorial-bounty entries for the
    given era. Each entry is the YAML dict."""
    era = era or _resolve_era()
    if era not in _BOUNTIES_CACHE:
        data = _load_yaml(_bounties_root(era))
        _BOUNTIES_CACHE[era] = data.get("bounties", []) or []
    return _BOUNTIES_CACHE[era]


def _reset_caches() -> None:
    """Test hook. Production code does not call this."""
    _MISSIONS_CACHE.clear()
    _BOUNTIES_CACHE.clear()


# ── YAML entry → engine instance materializers ───────────────────────


def _materialize_mission(entry: dict):
    """Build a Mission from a tutorial_missions.yaml entry.

    Returns None if the entry is malformed (missing required
    fields). Required: chain_mission_id, mission_type, title,
    giver, objective, destination, reward, required_skill."""
    from engine.missions import (
        Mission, MissionType, MissionStatus,
        MISSION_TTL,
    )

    required = ("chain_mission_id", "mission_type", "title",
                "giver", "objective", "destination", "reward",
                "required_skill")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        log.warning(
            "[chain_missions] tutorial mission entry missing fields: %s "
            "(entry: %r)", missing, entry.get("chain_mission_id"),
        )
        return None

    try:
        mt = MissionType(entry["mission_type"])
    except ValueError:
        log.warning(
            "[chain_missions] tutorial mission has unknown "
            "mission_type %r", entry.get("mission_type"),
        )
        return None

    chain_mid = entry["chain_mission_id"]
    now = time.time()

    # Mission ID is derived from the chain mission id so that the
    # same tutorial mission isn't accidentally double-spawned with
    # two different generated IDs. Using the chain id directly also
    # makes server-log tracing easier.
    mission_id = f"chain_{chain_mid}"

    return Mission(
        id=mission_id,
        mission_type=mt,
        title=entry["title"],
        giver=entry["giver"],
        objective=entry["objective"],
        destination=entry["destination"],
        destination_room_id=entry.get("destination_room_id"),
        reward=int(entry["reward"]),
        required_skill=entry["required_skill"],
        status=MissionStatus.AVAILABLE,
        created_at=now,
        # Tutorial missions don't expire; players walk through chains
        # at their own pace. A long but finite TTL keeps the row
        # from being eternally pinned. Six months is more than
        # enough for any realistic chain run.
        expires_at=now + (MISSION_TTL * 30),
        mission_data={
            "chain_mission_id": chain_mid,
            "chain_id": entry.get("chain_id", ""),
            "chain_step": int(entry.get("chain_step", 0)),
            "destination_slug": entry.get("destination_slug", ""),
            "pre_accepted": bool(entry.get("pre_accepted", False)),
        },
    )


def _materialize_bounty(entry: dict):
    """Build a BountyContract from a tutorial_bounties.yaml entry.

    Returns None if the entry is malformed."""
    from engine.bounty_board import (
        BountyContract, BountyTier, BountyStatus,
    )

    required = ("chain_bounty_id", "tier", "target_name",
                "target_species", "target_archetype",
                "crime_description", "posting_org", "tip",
                "reward")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        log.warning(
            "[chain_missions] tutorial bounty entry missing fields: %s "
            "(entry: %r)", missing, entry.get("chain_bounty_id"),
        )
        return None

    try:
        tier = BountyTier(entry["tier"])
    except ValueError:
        log.warning(
            "[chain_missions] tutorial bounty has unknown tier %r",
            entry.get("tier"),
        )
        return None

    chain_bid = entry["chain_bounty_id"]

    return BountyContract(
        id=f"chain_{chain_bid}",
        tier=tier,
        target_name=entry["target_name"],
        target_species=entry["target_species"],
        target_archetype=entry["target_archetype"],
        crime_description=entry["crime_description"],
        posting_org=entry["posting_org"],
        tip=entry["tip"],
        reward=int(entry["reward"]),
        reward_alive_bonus=int(entry.get("reward_alive_bonus", 0)),
        target_npc_id=None,
        target_room_id=None,
        status=BountyStatus.POSTED,
        chain_bounty_id=chain_bid,
    )


# ── Lookup helpers ───────────────────────────────────────────────────


def find_mission_for_step(chain_id: str, step: int,
                          era: Optional[str] = None) -> Optional[dict]:
    """Return the tutorial mission entry for the given chain
    step, or None if no chain mission is authored for it."""
    for entry in get_tutorial_missions(era):
        if (entry.get("chain_id") == chain_id
                and int(entry.get("chain_step", -1)) == int(step)):
            return entry
    return None


def find_bounty_for_step(chain_id: str, step: int,
                         era: Optional[str] = None) -> Optional[dict]:
    """Return the tutorial bounty entry for the given chain
    step, or None if no chain bounty is authored for it."""
    for entry in get_tutorial_bounties(era):
        if (entry.get("chain_id") == chain_id
                and int(entry.get("chain_step", -1)) == int(step)):
            return entry
    return None


# ── Spawn entry points (hooks call these on chain step entry) ───────


async def maybe_spawn_for_step(db, char: dict, chain_id: str,
                               step_num: int) -> Optional[str]:
    """Inject a chain mission/bounty into the live board if the
    given chain step is one that expects mission_accepted,
    mission_completed, or bounty_accepted.

    Returns the chain_mission_id / chain_bounty_id of the spawned
    entity (for logging), or None if nothing was spawned.

    Failure-tolerant: any exception is logged and swallowed.
    Spawning a chain mission must NOT prevent the chain from
    advancing through the step; the player can still accept any
    other available mission, even if this spawn failed.

    Idempotent: spawning the same chain mission twice (e.g. if the
    player exits and re-enters a step) is a no-op — the second call
    detects the existing board entry and returns its id without
    creating a duplicate.
    """
    try:
        m_entry = find_mission_for_step(chain_id, step_num)
        if m_entry:
            return await _spawn_mission(db, char, m_entry)
        b_entry = find_bounty_for_step(chain_id, step_num)
        if b_entry:
            return await _spawn_bounty(db, char, b_entry)
    except Exception as e:
        log.warning("[chain_missions] maybe_spawn_for_step failed: %s",
                    e, exc_info=True)
    return None


async def _spawn_mission(db, char: dict, entry: dict) -> Optional[str]:
    """Materialize and inject a tutorial mission. Returns the chain
    mission id on success."""
    from engine.missions import get_mission_board, MissionStatus
    from engine.missions import MISSION_ACTIVE_TTL

    mission = _materialize_mission(entry)
    if mission is None:
        return None

    board = get_mission_board()

    # Idempotent: if a mission with our derived id is already on the
    # board (player already entered this step before, or restart), we
    # don't double-spawn.
    if mission.id in board._missions:
        existing = board._missions[mission.id]
        log.debug(
            "[chain_missions] mission %s already on board (status=%s); "
            "skip respawn", mission.id, existing.status.value,
        )
        return existing.mission_data.get("chain_mission_id")

    pre_accepted = bool(entry.get("pre_accepted", False))

    if pre_accepted:
        # Step is mission_completed — chain narrative says you
        # already accepted this off-screen. Drop it directly into
        # the player's accepted slot.
        now = time.time()
        mission.status = MissionStatus.ACCEPTED
        mission.accepted_by = str(char["id"])
        mission.accepted_at = now
        mission.expires_at = now + MISSION_ACTIVE_TTL

    board._missions[mission.id] = mission

    # Persist
    try:
        await db.create_mission(
            mission_type=mission.mission_type.value,
            title=mission.title,
            description=mission.objective,
            reward=mission.reward,
            skill_required=mission.required_skill,
            status=mission.status.value,
            expires_at=mission.expires_at,
            data=json.dumps(mission.to_dict()),
        )
    except Exception as e:
        log.warning("[chain_missions] DB persist failed for %s: %s",
                    mission.id, e)

    if pre_accepted:
        try:
            await db.accept_mission(
                mission.id, str(char["id"]),
                mission.expires_at, mission.to_dict(),
            )
        except Exception as e:
            log.warning(
                "[chain_missions] DB accept persist failed for %s: %s",
                mission.id, e,
            )

    log.info("[chain_missions] Spawned tutorial mission %s for char %s "
             "(pre_accepted=%s)",
             mission.id, char.get("id"), pre_accepted)

    return mission.mission_data["chain_mission_id"]


async def _spawn_bounty(db, char: dict, entry: dict) -> Optional[str]:
    """Materialize and inject a tutorial bounty. Returns the chain
    bounty id on success."""
    from engine.bounty_board import get_bounty_board

    contract = _materialize_bounty(entry)
    if contract is None:
        return None

    # drop 26 (2026-06-13): bind the tutorial bounty's target NPC + room
    # so `+bounty/track` works. `_materialize_bounty` leaves
    # target_npc_id / target_room_id None (it's sync, no DB); the
    # tutorial_bounties.yaml entry carries `target_room_slug`, and the
    # anchor NPC (e.g. Tarko Vinn) is placed in that room by the world
    # build. Resolve the slug → room id, then find the NPC by
    # `target_name` in that room and bind both. Best-effort: an
    # unresolvable slug or absent NPC logs and leaves the contract
    # unbound (the chain still drives capture via `chain attempt` +
    # `combat_won`, so this is quality, not a hard dependency). Without
    # it, BountyTrackCommand hard-errors "Contract data error — target
    # NPC not found" on the tutorial contract.
    target_slug = entry.get("target_room_slug")
    if target_slug:
        try:
            room = await db.get_room_by_slug(target_slug)
            if room:
                room_id = int(room["id"])
                contract.target_room_id = room_id
                npc_rows = await db.fetchall(
                    "SELECT id FROM npcs WHERE name = ? AND room_id = ?",
                    (contract.target_name, room_id),
                )
                if npc_rows:
                    contract.target_npc_id = int(npc_rows[0]["id"])
                else:
                    log.info(
                        "[chain_missions] tutorial bounty %s: target NPC "
                        "%r not found in room %s (slug %s) — +bounty/track "
                        "will be unavailable for this contract",
                        contract.id, contract.target_name, room_id,
                        target_slug,
                    )
            else:
                log.info(
                    "[chain_missions] tutorial bounty %s: target_room_slug "
                    "%r did not resolve to a room", contract.id,
                    target_slug,
                )
        except Exception as e:
            log.warning(
                "[chain_missions] tutorial bounty %s target binding "
                "failed: %s", contract.id, e,
            )

    board = get_bounty_board()

    # Idempotent
    if contract.id in board._contracts:
        existing = board._contracts[contract.id]
        log.debug(
            "[chain_missions] bounty %s already on board (status=%s); "
            "skip respawn", contract.id, existing.status.value,
        )
        return existing.chain_bounty_id

    board._contracts[contract.id] = contract

    # Persist (best-effort; the bounty board is in-memory primary)
    try:
        if hasattr(db, "save_bounty"):
            await db.save_bounty(contract)
    except Exception as e:
        log.warning("[chain_missions] DB persist failed for %s: %s",
                    contract.id, e)

    log.info("[chain_missions] Spawned tutorial bounty %s for char %s",
             contract.id, char.get("id"))

    return contract.chain_bounty_id


# ── Visibility filters (called by parser board commands) ────────────


def is_chain_mission_visible_to(mission, char_attrs: dict) -> bool:
    """Return True iff the player should see this mission on the
    `+missions` board.

    - Open (non-chain) missions: always visible. Returns True.
    - Chain-tagged missions: visible only to characters whose
      active chain matches the mission's tagged chain_id AND whose
      current step is at-or-near the step that expects this
      mission.

    The "at-or-near" rule lets a player see the mission both when
    they enter the step (so the +missions output matches the chain
    NPC's narrative cue) and one step earlier (so a player who
    runs +missions ahead of the briefing still sees the path
    forward instead of an empty board).
    """
    mdata = getattr(mission, "mission_data", None) or {}
    chain_mid = mdata.get("chain_mission_id", "") or ""
    if not chain_mid:
        return True  # Open mission

    # Chain-tagged. Check active chain on the character.
    state = (char_attrs or {}).get("tutorial_chain") or {}
    if state.get("completion_state") != "active":
        return False
    if state.get("chain_id") != mdata.get("chain_id"):
        return False

    expected_step = int(mdata.get("chain_step", 0))
    current_step = int(state.get("step", 0))
    # Visible at the expected step OR one step earlier (preview).
    return current_step in (expected_step, expected_step - 1)


def is_chain_bounty_visible_to(contract, char_attrs: dict) -> bool:
    """Return True iff the player should see this bounty on the
    `+bounties` board. Same chain-step gating as missions."""
    chain_bid = getattr(contract, "chain_bounty_id", "") or ""
    if not chain_bid:
        return True  # Open bounty

    state = (char_attrs or {}).get("tutorial_chain") or {}
    if state.get("completion_state") != "active":
        return False

    # Bounties don't carry chain_id/chain_step on the contract
    # itself; we look it up from the YAML by reverse-matching the
    # chain_bounty_id. Cheap because there are very few tutorial
    # bounties total.
    for entry in get_tutorial_bounties():
        if entry.get("chain_bounty_id") == chain_bid:
            if state.get("chain_id") != entry.get("chain_id"):
                return False
            expected_step = int(entry.get("chain_step", 0))
            current_step = int(state.get("step", 0))
            return current_step in (expected_step,
                                    expected_step - 1)
    return False


def filter_visible_missions(missions: list, char_attrs: dict) -> list:
    """Convenience: return a list of missions visible to the given
    character attrs. Used by parser board commands."""
    return [m for m in missions
            if is_chain_mission_visible_to(m, char_attrs)]


def filter_visible_bounties(contracts: list, char_attrs: dict) -> list:
    """Convenience: filter bounties for visibility."""
    return [c for c in contracts
            if is_chain_bounty_visible_to(c, char_attrs)]
