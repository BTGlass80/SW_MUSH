# -*- coding: utf-8 -*-
"""
engine/npc_space_combat_ai.py — NPC Space Combat AI
Space Overhaul v3, Drop 3

Provides combat AI for NPC traffic ships (pirates, bounty hunters,
Imperial patrols) that have been promoted to active combatants.

Architecture:
  - SpaceNpcCombatant wraps a TrafficShip with combat state
  - 5 combat profiles determine tactical behaviour
  - Action pacing: NPCs act every 3-5 seconds (not every tick)
  - Uses the SAME resolve_space_attack() as player fire
  - Damage applied to player ship via DB, same as player-on-NPC fire
  - Combat messages broadcast to the target's bridge room

Lifecycle:
  1. promote_to_combat() — creates combatant, adds NPC to SpaceGrid
  2. tick() — called every tick, paces actions
  3. Combat end (NPC destroyed/fled, player disabled) — cleanup + rewards

No DB tables. Combatant state is transient (in-memory).
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.dice import DicePool
from engine.json_safe import load_ship_systems
from engine.starships import (
    get_ship_registry, get_space_grid, resolve_space_attack,
    SpaceRange, RelativePosition, resolve_evade, can_weapon_fire,
)

log = logging.getLogger(__name__)

# ── ANSI ─────────────────────────────────────────────────────────────────────
RED = "\033[1;31m"
AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
DIM = "\033[2m"
RST = "\033[0m"

# ── Combat Profiles ──────────────────────────────────────────────────────────

class SpaceCombatProfile(str, Enum):
    AGGRESSIVE = "aggressive"
    CAUTIOUS = "cautious"
    PURSUIT = "pursuit"
    AMBUSH = "ambush"
    PATROL = "patrol"

PROFILE_CONFIG = {
    SpaceCombatProfile.AGGRESSIVE: {
        "preferred_range": SpaceRange.SHORT,
        "flee_threshold": 0.30,
        "action_interval": 4,
        "uses_lockon": False,
    },
    SpaceCombatProfile.CAUTIOUS: {
        "preferred_range": SpaceRange.MEDIUM,
        "flee_threshold": 0.50,
        "action_interval": 5,
        "uses_lockon": True,
    },
    SpaceCombatProfile.PURSUIT: {
        "preferred_range": SpaceRange.CLOSE,
        "flee_threshold": 0.25,
        "action_interval": 4,
        "uses_lockon": False,
    },
    SpaceCombatProfile.AMBUSH: {
        "preferred_range": SpaceRange.CLOSE,
        "flee_threshold": 0.60,
        "action_interval": 3,
        "uses_lockon": False,
    },
    SpaceCombatProfile.PATROL: {
        "preferred_range": SpaceRange.SHORT,
        "flee_threshold": 0.40,
        "action_interval": 5,
        "uses_lockon": True,
    },
}

ARCHETYPE_PROFILES = {
    "pirate":        SpaceCombatProfile.AGGRESSIVE,
    "bounty_hunter": SpaceCombatProfile.PURSUIT,
    "patrol":        SpaceCombatProfile.PATROL,
    "interceptor":   SpaceCombatProfile.AGGRESSIVE,
    "ambush":        SpaceCombatProfile.AMBUSH,
}


# ── SpaceNpcCombatant ────────────────────────────────────────────────────────

@dataclass
class SpaceNpcCombatant:
    """An NPC ship actively engaged in space combat."""
    npc_ship_id: int
    target_ship_id: int
    target_bridge_room: int
    profile: SpaceCombatProfile
    zone_id: str
    template_key: str = ""
    display_name: str = "Unknown Ship"
    crew_skill: str = "3D"
    hull_max_pips: int = 12
    hull_damage: int = 0
    scale_value: int = 0
    last_action_time: float = 0.0
    actions_taken: int = 0
    created_at: float = field(default_factory=time.time)
    flee_announced: bool = False
    _boarding_attempted: bool = False

    @property
    def hull_fraction(self) -> float:
        if self.hull_max_pips <= 0:
            return 1.0
        return max(0.0, 1.0 - (self.hull_damage / self.hull_max_pips))

    def should_flee(self) -> bool:
        cfg = PROFILE_CONFIG.get(self.profile, {})
        return self.hull_fraction <= cfg.get("flee_threshold", 0.30)

    def is_destroyed(self) -> bool:
        return self.hull_damage >= self.hull_max_pips

    def action_ready(self) -> bool:
        cfg = PROFILE_CONFIG.get(self.profile, {})
        return (time.time() - self.last_action_time) >= cfg.get("action_interval", 4)


# ── NPC Combat Manager ───────────────────────────────────────────────────────

class NpcSpaceCombatManager:
    """Manages all active NPC space combatants."""

    def __init__(self):
        self._combatants: dict[int, SpaceNpcCombatant] = {}

    def get_combatant(self, npc_ship_id: int) -> Optional[SpaceNpcCombatant]:
        return self._combatants.get(npc_ship_id)

    def get_combatant_targeting(self, target_ship_id: int) -> Optional[SpaceNpcCombatant]:
        for c in self._combatants.values():
            if c.target_ship_id == target_ship_id:
                return c
        return None

    @property
    def active_count(self) -> int:
        return len(self._combatants)

    def promote_to_combat(
        self,
        npc_ship_id: int,
        target_ship_id: int,
        target_bridge_room: int,
        zone_id: str,
        template_key: str,
        display_name: str,
        crew_skill: str = "3D",
        profile: str = "aggressive",
        starting_range: SpaceRange = SpaceRange.SHORT,
    ) -> SpaceNpcCombatant:
        """Create a combatant and add the NPC to the SpaceGrid."""
        reg = get_ship_registry()
        tmpl = reg.get(template_key)
        hull_pips = DicePool.parse(tmpl.hull if tmpl else "4D").total_pips()
        speed = tmpl.speed if tmpl else 5
        scale = tmpl.scale_value if tmpl else 0

        prof = ARCHETYPE_PROFILES.get(profile, None)
        if prof is None:
            try:
                prof = SpaceCombatProfile(profile)
            except ValueError:
                prof = SpaceCombatProfile.AGGRESSIVE

        c = SpaceNpcCombatant(
            npc_ship_id=npc_ship_id,
            target_ship_id=target_ship_id,
            target_bridge_room=target_bridge_room,
            profile=prof,
            zone_id=zone_id,
            template_key=template_key,
            display_name=display_name,
            crew_skill=crew_skill,
            hull_max_pips=hull_pips,
            scale_value=scale,
            last_action_time=time.time(),
        )

        self._combatants[npc_ship_id] = c
        get_space_grid().add_ship(npc_ship_id, speed, default_range=starting_range)

        log.info("[npc_combat] promoted %d '%s' (profile=%s, target=%d, range=%s)",
                 npc_ship_id, display_name, prof.value, target_ship_id,
                 starting_range.label)
        return c

    def remove_combatant(self, npc_ship_id: int) -> Optional[SpaceNpcCombatant]:
        c = self._combatants.pop(npc_ship_id, None)
        if c:
            get_space_grid().remove_ship(npc_ship_id)
        return c

    def apply_damage_to_npc(self, npc_ship_id: int, hull_damage: int) -> bool:
        """Apply hull damage to an NPC combatant. Returns True if destroyed."""
        c = self._combatants.get(npc_ship_id)
        if c is None:
            return False
        c.hull_damage += hull_damage
        return c.is_destroyed()

    # ── Tick ─────────────────────────────────────────────────────────────

    async def tick(self, db, session_mgr) -> None:
        """Called every tick. Run combat actions for ready combatants."""
        to_remove = []

        for npc_id, c in list(self._combatants.items()):
            if c.is_destroyed():
                to_remove.append((npc_id, "destroyed"))
                continue
            if not c.action_ready():
                continue
            try:
                result = await self._run_action(c, db, session_mgr)
                if result in ("fled", "target_destroyed"):
                    to_remove.append((npc_id, result))
            except Exception as e:
                log.error("[npc_combat] tick error ship %d: %s", npc_id, e,
                          exc_info=True)

        for npc_id, reason in to_remove:
            c = self._combatants.get(npc_id)
            if c:
                await self._handle_combat_end(c, reason, db, session_mgr)
            self.remove_combatant(npc_id)

    async def _run_action(self, c: SpaceNpcCombatant, db, session_mgr) -> str:
        c.last_action_time = time.time()
        c.actions_taken += 1

        grid = get_space_grid()
        rng = grid.get_range(c.npc_ship_id, c.target_ship_id)

        # Flee check
        if c.should_flee():
            if not c.flee_announced:
                c.flee_announced = True
                await self._bcast(c,
                    f"  {AMBER}[SENSORS]{RST} {c.display_name} is breaking off — "
                    f"trailing smoke!", session_mgr)
                return "continue"
            await self._bcast(c,
                f"  {GREEN}[SENSORS]{RST} {c.display_name} jumps to hyperspace. "
                f"Combat over!", session_mgr)
            return "fled"

        action = self._select_action(c, rng)

        if action == "board":
            return await self._do_board(c, db, session_mgr)
        elif action == "fire":
            return await self._do_fire(c, rng, db, session_mgr)
        elif action == "close":
            return await self._do_maneuver(c, "close", db, session_mgr)
        elif action == "tail":
            return await self._do_maneuver(c, "tail", db, session_mgr)
        elif action == "evade":
            return await self._do_evade(c, session_mgr)
        elif action == "lockon":
            return await self._do_lockon(c, session_mgr)
        return "continue"

    def _select_action(self, c: SpaceNpcCombatant, rng: SpaceRange) -> str:
        cfg = PROFILE_CONFIG.get(c.profile, {})
        preferred = cfg.get("preferred_range", SpaceRange.SHORT)
        uses_lockon = cfg.get("uses_lockon", False)
        grid = get_space_grid()

        if rng in (SpaceRange.EXTREME, SpaceRange.OUT_OF_RANGE):
            return "close"

        if c.profile == SpaceCombatProfile.PURSUIT:
            their_pos = grid.get_position(c.target_ship_id, c.npc_ship_id)
            if their_pos != RelativePosition.REAR:
                return "tail"

        if rng.value > preferred.value:
            return "close"

        if uses_lockon and c.actions_taken % 3 == 0:
            if grid.get_lockon(c.npc_ship_id, c.target_ship_id) < 3:
                return "lockon"

        if c.profile == SpaceCombatProfile.CAUTIOUS and c.actions_taken % 3 == 2:
            return "evade"

        # Boarding check — pirates/hunters at Close range may attempt to board
        from engine.encounter_boarding import should_npc_board
        if should_npc_board(c, rng):
            return "board"

        return "fire"

    # ── Action Implementations ───────────────────────────────────────────

    async def _get_target_pilot_skill(self, target_ship: dict, target_tmpl, db) -> DicePool:
        """Read the target ship pilot's actual skill instead of hardcoded 3D."""
        default = DicePool(3, 0)
        try:
            crew = target_ship.get("crew", "{}")
            if isinstance(crew, str):
                crew = json.loads(crew) if crew else {}
            pilot_id = crew.get("pilot") if crew else None
            if not pilot_id:
                return default
            pilot_char = await db.get_character(pilot_id)
            if not pilot_char:
                return default
            from engine.character import Character
            from engine.dice import SkillRegistry
            sr = SkillRegistry()
            char_obj = Character.from_db_dict(pilot_char)
            skill_name = (
                "capital ship piloting" if target_tmpl and target_tmpl.scale == "capital"
                else "starfighter piloting"
            )
            pool = char_obj.get_skill_pool(skill_name, sr)
            if pool.dice == 0 and pool.pips == 0:
                return default
            return pool
        except Exception:
            log.warning("_get_target_pilot_skill failed", exc_info=True)
            return default

    async def _do_fire(self, c: SpaceNpcCombatant, rng: SpaceRange,
                       db, session_mgr) -> str:
        reg = get_ship_registry()
        tmpl = reg.get(c.template_key)
        if not tmpl or not tmpl.weapons:
            return "continue"

        grid = get_space_grid()
        rel_pos = grid.get_position(c.npc_ship_id, c.target_ship_id)

        # Pick weapon
        weapon = None
        for w in tmpl.weapons:
            if can_weapon_fire(w.fire_arc, rel_pos):
                if c.profile == SpaceCombatProfile.PATROL and w.ion:
                    weapon = w
                    break
                if weapon is None:
                    weapon = w
        if weapon is None:
            return await self._do_maneuver(c, "close", db, session_mgr)

        # Get target data
        target_ship = await db.get_ship(c.target_ship_id)
        if not target_ship:
            return "target_destroyed"
        target_ship = dict(target_ship)
        target_tmpl = reg.get(target_ship.get("template", ""))
        if not target_tmpl:
            return "continue"

        from engine.starships import get_effective_stats
        t_sys = load_ship_systems(target_ship)
        t_eff = get_effective_stats(target_tmpl, t_sys)

        target_pilot_pool = await self._get_target_pilot_skill(
            target_ship, target_tmpl, db)

        result = resolve_space_attack(
            attacker_skill=DicePool.parse(c.crew_skill),
            weapon=weapon,
            attacker_scale=c.scale_value,
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(
                t_eff.get("maneuverability", target_tmpl.maneuverability)),
            target_hull=DicePool.parse(t_eff.get("hull", target_tmpl.hull)),
            target_shields=DicePool.parse(t_eff.get("shields", target_tmpl.shields)),
            target_scale=target_tmpl.scale_value,
            range_band=rng,
            relative_position=rel_pos,
            attacker_ship_id=c.npc_ship_id,
            target_ship_id=c.target_ship_id,
        )

        # Apply damage
        if result.hull_damage > 0:
            new_dmg = target_ship.get("hull_damage", 0) + result.hull_damage
            updates = {"hull_damage": new_dmg}
            if result.systems_hit:
                for s in result.systems_hit:
                    t_sys[s] = False
                updates["systems"] = json.dumps(t_sys)
            await db.update_ship(c.target_ship_id, **updates)

            hull_pips = DicePool.parse(t_eff.get("hull", target_tmpl.hull)).total_pips()
            if new_dmg >= hull_pips:
                await self._bcast(c,
                    f"  {RED}[CRITICAL]{RST} Hull breach! Ship disabled!", session_mgr)
                return "target_destroyed"

        # Ion effects
        if result.ion_disabled:
            if result.ion_disabled == "dead":
                t_sys["controls_dead"] = True
                t_sys["ion_penalty"] = 99
            else:
                try:
                    ion_count = int(result.ion_disabled)
                except ValueError:
                    ion_count = 1
                t_sys["ion_penalty"] = t_sys.get("ion_penalty", 0) + ion_count
            await db.update_ship(c.target_ship_id, systems=json.dumps(t_sys))

        # Broadcast
        ion_tag = " (ION)" if weapon.ion else ""
        if result.hit:
            await self._bcast(c,
                f"  {RED}[INCOMING]{RST} {c.display_name} fires "
                f"{weapon.name}{ion_tag}! {result.narrative.strip()}",
                session_mgr)
        else:
            await self._bcast(c,
                f"  {AMBER}[INCOMING]{RST} {c.display_name} fires "
                f"{weapon.name}{ion_tag} — missed!",
                session_mgr)

        if result.hit:
            await self._refresh_hud(c, db, session_mgr)
        return "continue"

    async def _do_maneuver(self, c: SpaceNpcCombatant, action: str,
                           db, session_mgr) -> str:
        grid = get_space_grid()
        reg = get_ship_registry()
        tmpl = reg.get(c.template_key)
        skill = DicePool.parse(c.crew_skill)
        maneuver = DicePool.parse(tmpl.maneuverability if tmpl else "1D")
        speed = tmpl.speed if tmpl else 5

        t_ship = await db.get_ship(c.target_ship_id)
        t_ship_dict = dict(t_ship) if t_ship else {}
        t_tmpl = reg.get(t_ship_dict.get("template", "")) if t_ship else None

        target_pilot_pool = await self._get_target_pilot_skill(
            t_ship_dict, t_tmpl, db) if t_ship else DicePool(3, 0)

        success, narrative = grid.resolve_maneuver(
            pilot_id=c.npc_ship_id,
            pilot_skill=skill,
            pilot_maneuverability=maneuver,
            pilot_speed=speed,
            target_id=c.target_ship_id,
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(
                t_tmpl.maneuverability if t_tmpl else "1D"),
            target_speed=t_tmpl.speed if t_tmpl else 5,
            action=action,
        )

        label = {"close": "CLOSING", "tail": "FLANKING"}.get(action, action.upper())
        if success:
            await self._bcast(c,
                f"  {AMBER}[SENSORS]{RST} {c.display_name} [{label}] {narrative}",
                session_mgr)
        else:
            await self._bcast(c,
                f"  {DIM}[SENSORS] {c.display_name} maneuvers — {narrative}{RST}",
                session_mgr)
        return "continue"

    async def _do_evade(self, c: SpaceNpcCombatant, session_mgr) -> str:
        tmpl = get_ship_registry().get(c.template_key)
        result = resolve_evade(
            DicePool.parse(c.crew_skill),
            DicePool.parse(tmpl.maneuverability if tmpl else "1D"),
        )
        if result.success:
            await self._bcast(c,
                f"  {AMBER}[SENSORS]{RST} {c.display_name} performs evasive maneuvers!",
                session_mgr)
        return "continue"

    async def _do_lockon(self, c: SpaceNpcCombatant, session_mgr) -> str:
        val = get_space_grid().add_lockon(c.npc_ship_id, c.target_ship_id)
        await self._bcast(c,
            f"  {AMBER}[SENSORS]{RST} {c.display_name} locks weapons — "
            f"targeting lock +{val}D!", session_mgr)
        return "continue"

    async def _do_board(self, c: SpaceNpcCombatant, db, session_mgr) -> str:
        """Attempt to board the target ship — spawn hostile NPCs on their bridge."""
        from engine.encounter_boarding import initiate_npc_boarding

        # Mark that we attempted boarding (only try once per combat)
        c._boarding_attempted = True

        await self._bcast(c,
            f"\n  {RED}[ALERT]{RST} {c.display_name} is launching a boarding party!\n"
            f"  {AMBER}[SENSORS]{RST} Grappling lines detected — hostiles inbound!",
            session_mgr)

        success = await initiate_npc_boarding(c, db, session_mgr)
        if not success:
            await self._bcast(c,
                f"  {GREEN}[SENSORS]{RST} Boarding attempt repelled!",
                session_mgr)
        return "continue"

    # ── Combat End ───────────────────────────────────────────────────────

    async def _handle_combat_end(self, c: SpaceNpcCombatant, reason: str,
                                 db, session_mgr) -> None:
        if reason == "destroyed":
            await self._bcast(c,
                f"\n  {GREEN}[COMBAT]{RST} {c.display_name} explodes! Combat over.\n"
                f"  {DIM}Type 'salvage' for wreckage.{RST}", session_mgr)
            try:
                from engine.space_anomalies import add_wreck_anomaly
                add_wreck_anomaly(c.zone_id, c.display_name)
            except Exception as e:
                log.warning("[npc_combat] wreck spawn: %s", e)
            try:
                from engine.npc_space_traffic import get_traffic_manager
                sessions = session_mgr.sessions_in_room(c.target_bridge_room)
                if sessions:
                    for sess in sessions:
                        if sess.character:
                            awarded = await get_traffic_manager().handle_traffic_ship_destroyed(
                                c.npc_ship_id, sess.character, db, session_mgr)
                            if awarded:
                                await sess.send_line(
                                    f"  {GREEN}[BOUNTY]{RST} Recovered {awarded:,} credits!")
                            break
            except Exception as e:
                log.warning("[npc_combat] kill reward: %s", e)

        elif reason == "fled":
            try:
                from engine.npc_space_traffic import get_traffic_manager, TrafficState
                ts = get_traffic_manager().get_ship(c.npc_ship_id)
                if ts:
                    ts.tailing_ship_id = None
                    ts.hail_sent = False
                    ts.enter_state(TrafficState.FLEEING, duration=0)
            except Exception as e:
                log.warning("[npc_combat] flee transition: %s", e)

        elif reason == "target_destroyed":
            await self._bcast(c,
                f"\n  {RED}[CRITICAL]{RST} Ship disabled. {c.display_name} moves in.\n"
                f"  {DIM}(Ship is disabled, not destroyed. Repairs needed.){RST}",
                session_mgr)

        # Resolve associated encounter
        try:
            from engine.space_encounters import get_encounter_manager
            enc = get_encounter_manager().get_encounter(c.target_ship_id)
            if enc and enc.state == "active":
                get_encounter_manager().resolve(enc, outcome=f"combat_{reason}")
        except Exception as e:
            log.warning("[npc_combat] encounter resolve: %s", e)

        await self._refresh_hud(c, db, session_mgr)

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _bcast(self, c: SpaceNpcCombatant, msg: str, session_mgr):
        try:
            await session_mgr.broadcast_to_room(c.target_bridge_room, msg)
        except Exception as e:
            log.warning("[npc_combat] broadcast: %s", e)

    async def _refresh_hud(self, c: SpaceNpcCombatant, db, session_mgr):
        try:
            from parser.space_commands import broadcast_space_state
            ship = await db.get_ship(c.target_ship_id)
            if ship:
                await broadcast_space_state(dict(ship), db, session_mgr)
        except Exception as e:
            log.warning("[npc_combat] HUD refresh: %s", e)


# ── Module singleton ─────────────────────────────────────────────────────────

_combat_manager: Optional[NpcSpaceCombatManager] = None

def get_npc_combat_manager() -> NpcSpaceCombatManager:
    global _combat_manager
    if _combat_manager is None:
        _combat_manager = NpcSpaceCombatManager()
    return _combat_manager
