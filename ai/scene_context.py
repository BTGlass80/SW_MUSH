# -*- coding: utf-8 -*-
"""
SceneContext — bounded entity manifest for the IntentParser.

Captures only the entities, weapons, and valid actions present in the
current scene so the LLM cannot hallucinate IDs or targets.

Usage:
    ctx = await SceneContext.build(room_id, char_id, db, session_mgr, combat)
    # pass ctx into IntentParser.parse()
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports at runtime

log = logging.getLogger(__name__)


@dataclass
class EntityEntry:
    """A single entity (player or NPC) visible in the scene."""
    id: int
    name: str
    is_npc: bool
    is_hostile: bool = False       # already in combat as an opponent
    wound_label: str = "healthy"   # healthy / stunned / wounded / incap / mortal


@dataclass
class SceneContext:
    """
    Bounded snapshot of what is in scope during intent parsing.

    The LLM is constrained to produce IDs and names drawn exclusively
    from these collections.  BoundedContextValidator enforces this.
    """
    scene_id: int                        # room_id — used as a session key
    char_id: int                         # the acting player
    char_name: str

    # Entities visible to the player right now
    entities: dict[int, EntityEntry] = field(default_factory=dict)

    # Player's equipped weapon key (e.g. "blaster_pistol") and skill
    equipped_weapon_key: str = ""
    equipped_weapon_name: str = ""
    default_skill: str = "blaster"
    default_damage: str = "4D"

    # Skills the player actually has trained (for suggestion)
    trained_skills: list[str] = field(default_factory=list)

    # Active combat IDs in this room (so we know if we're mid-combat)
    combatant_ids: list[int] = field(default_factory=list)

    # Valid action verbs the LLM may produce
    valid_actions: list[str] = field(default_factory=list)

    # ── Serialization for the LLM prompt ──────────────────────────────────

    def entity_manifest(self) -> str:
        """Human-readable entity list to embed in the LLM prompt."""
        if not self.entities:
            return "  (no other beings in the room)"
        lines = []
        for eid, e in self.entities.items():
            tag = " [NPC]" if e.is_npc else " [player]"
            hostile = " [HOSTILE]" if e.is_hostile else ""
            lines.append(f"  id={eid}  name=\"{e.name}\"{tag}{hostile}  status={e.wound_label}")
        return "\n".join(lines)

    def weapon_summary(self) -> str:
        if self.equipped_weapon_name:
            return (
                f"equipped: {self.equipped_weapon_name} "
                f"(skill={self.default_skill}, damage={self.default_damage})"
            )
        return f"no weapon equipped — default brawling (skill=brawling, damage=STR+1D)"

    def actions_summary(self) -> str:
        return ", ".join(self.valid_actions) if self.valid_actions else "attack, dodge, flee"

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    async def build(
        cls,
        room_id: int,
        char_id: int,
        db,
        session_mgr,
        combat=None,          # CombatInstance or None
    ) -> "SceneContext":
        """
        Build a SceneContext from live game state.

        Args:
            room_id:     The room the player is in.
            char_id:     The player's character ID.
            db:          GameDatabase instance.
            session_mgr: SessionManager instance.
            combat:      Active CombatInstance if in combat, else None.
        """
        # Get player's own character row
        char_row = await db.get_character(char_id)
        char_name = char_row.get("name", "Unknown") if char_row else "Unknown"

        ctx = cls(
            scene_id=room_id,
            char_id=char_id,
            char_name=char_name,
            valid_actions=["attack", "dodge", "fulldodge", "parry", "aim",
                           "cover", "flee", "pass"],
        )

        # ── Equipped weapon ────────────────────────────────────────────────
        if char_row:
            import json as _json
            equip_raw = char_row.get("equipment", "{}")
            if isinstance(equip_raw, str):
                try:
                    equip_data = _json.loads(equip_raw)
                except Exception:
                    equip_data = {}
            else:
                equip_data = equip_raw or {}
            weapon_key = equip_data.get("weapon", "") if isinstance(equip_data, dict) else ""
            if weapon_key:
                try:
                    from engine.weapons import get_weapon_registry
                    wr = get_weapon_registry()
                    weapon = wr.get(weapon_key)
                    if weapon:
                        ctx.equipped_weapon_key = weapon_key
                        ctx.equipped_weapon_name = weapon.name
                        ctx.default_skill = weapon.skill
                        ctx.default_damage = weapon.damage
                except Exception as e:
                    log.debug("SceneContext: weapon lookup failed: %s", e)

            # Trained skills
            try:
                skills_raw = char_row.get("skills", "{}")
                if isinstance(skills_raw, str):
                    skills_dict = _json.loads(skills_raw)
                else:
                    skills_dict = skills_raw or {}
                ctx.trained_skills = list(skills_dict.keys())
            except Exception:
                log.debug("scene_context: skills fetch failed", exc_info=True)
                pass

        # ── Entities in room ───────────────────────────────────────────────
        hostile_ids: set[int] = set()
        if combat:
            ctx.combatant_ids = list(combat.combatants.keys())
            # Mark combatants that are opposing the player as hostile
            for cid, combatant in combat.combatants.items():
                if cid != char_id and combatant.is_npc:
                    hostile_ids.add(cid)

        # Other players
        for sess in session_mgr.sessions_in_room(room_id):
            if sess.character and sess.character["id"] != char_id:
                pid = sess.character["id"]
                pname = sess.character.get("name", "Unknown")
                wound = _wound_label(sess.character.get("wound_level", 0))
                ctx.entities[pid] = EntityEntry(
                    id=pid,
                    name=pname,
                    is_npc=False,
                    is_hostile=(pid in hostile_ids),
                    wound_label=wound,
                )

        # NPCs
        try:
            npcs = await db.get_npcs_in_room(room_id)
            for npc in npcs:
                nid = npc["id"]
                nname = npc.get("name", "Unknown NPC")
                # Get wound level from char_sheet_json
                try:
                    cs = json.loads(npc.get("char_sheet_json", "{}"))
                    wl = cs.get("wound_level", 0)
                except Exception:
                    wl = 0
                wound = _wound_label(wl)
                # Determine if hostile via ai_config_json
                try:
                    ac = json.loads(npc.get("ai_config_json", "{}"))
                    is_hostile = bool(ac.get("hostile", False)) or (nid in hostile_ids)
                except Exception:
                    is_hostile = nid in hostile_ids
                ctx.entities[nid] = EntityEntry(
                    id=nid,
                    name=nname,
                    is_npc=True,
                    is_hostile=is_hostile,
                    wound_label=wound,
                )
        except Exception as e:
            log.debug("SceneContext: NPC query failed: %s", e)

        return ctx


# ── Helpers ────────────────────────────────────────────────────────────────────

_WOUND_LABELS = {
    0: "healthy",
    1: "stunned",
    2: "wounded",
    3: "wounded",
    4: "incapacitated",
    5: "mortally wounded",
    6: "dead",
}


def _wound_label(level: int) -> str:
    return _WOUND_LABELS.get(level, "wounded")
