"""
NPC Brain - handles dialogue, prompt assembly, and memory.

Each NPC has an ai_config that defines their personality, knowledge,
faction, and model tier. The brain assembles a rich system prompt
from all these sources and manages conversation context.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ai.providers import AIManager

log = logging.getLogger(__name__)


@dataclass
class NPCConfig:
    """AI configuration for a single NPC."""
    enabled: bool = True
    model_tier: int = 1                  # 1=fast, 2=premium, 3=cloud
    model_override: str = ""             # Specific model (overrides tier)
    provider_override: str = ""          # Specific provider (overrides default)
    personality: str = ""                # Core personality description
    knowledge: list[str] = field(default_factory=list)  # Things this NPC knows
    faction: str = ""                    # Imperial, Rebel, Hutt Cartel, neutral, etc.
    dialogue_style: str = ""             # How they speak (short/verbose/formal/slang)
    temperature: float = 0.7
    max_tokens: int = 150
    fallback_lines: list[str] = field(default_factory=list)  # Canned responses if AI is down

    @classmethod
    def from_dict(cls, data: dict) -> "NPCConfig":
        if not data:
            return cls()
        return cls(
            enabled=data.get("enabled", True),
            model_tier=data.get("model_tier", 1),
            model_override=data.get("model_override", ""),
            provider_override=data.get("provider_override", ""),
            personality=data.get("personality", ""),
            knowledge=data.get("knowledge", []),
            faction=data.get("faction", ""),
            dialogue_style=data.get("dialogue_style", ""),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 150),
            fallback_lines=data.get("fallback_lines", []),
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "model_tier": self.model_tier,
            "model_override": self.model_override,
            "provider_override": self.provider_override,
            "personality": self.personality,
            "knowledge": self.knowledge,
            "faction": self.faction,
            "dialogue_style": self.dialogue_style,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "fallback_lines": self.fallback_lines,
        }


@dataclass
class NPCData:
    """Complete NPC definition."""
    id: int = 0
    name: str = ""
    room_id: int = 0
    species: str = "Human"
    description: str = ""
    char_sheet: dict = field(default_factory=dict)  # Simplified stats for combat
    ai_config: NPCConfig = field(default_factory=NPCConfig)

    @classmethod
    def from_db_row(cls, row: dict) -> "NPCData":
        npc = cls()
        npc.id = row.get("id", 0)
        npc.name = row.get("name", "")
        npc.room_id = row.get("room_id", 0)
        npc.species = row.get("species", "Human")
        npc.description = row.get("description", "")

        cs = row.get("char_sheet_json", "{}")
        npc.char_sheet = json.loads(cs) if isinstance(cs, str) else cs

        ai = row.get("ai_config_json", "{}")
        ai_dict = json.loads(ai) if isinstance(ai, str) else ai
        npc.ai_config = NPCConfig.from_dict(ai_dict)

        return npc


class NPCBrain:
    """
    Handles dialogue for a single NPC.

    Assembles the system prompt from NPC config, room context,
    and player memory, then calls the AI provider.
    """

    def __init__(self, npc: NPCData, ai_manager: AIManager):
        self.npc = npc
        self.ai = ai_manager
        self.conversation_history: list[dict] = []  # Short-term memory

    def _build_system_prompt(self, room_desc: str = "",
                             player_name: str = "",
                             player_memory: str = "",
                             persuasion_context: str = "") -> str:
        """Assemble the full system prompt for this NPC."""
        cfg = self.npc.ai_config
        parts = []

        # Identity
        parts.append(
            f"You are {self.npc.name}, a {self.npc.species} in a Star Wars setting."
        )
        if self.npc.description:
            parts.append(f"Your appearance: {self.npc.description}")

        # Personality
        if cfg.personality:
            parts.append(f"Personality: {cfg.personality}")

        # Dialogue style
        if cfg.dialogue_style:
            parts.append(f"Speech style: {cfg.dialogue_style}")
        else:
            parts.append(
                "Keep responses to 1-3 sentences. Stay in character. "
                "Never break the fourth wall or mention being an AI."
            )

        # Faction
        if cfg.faction:
            parts.append(f"Faction allegiance: {cfg.faction}")

        # Knowledge
        if cfg.knowledge:
            parts.append("Things you know:")
            for k in cfg.knowledge:
                parts.append(f"  - {k}")

        # Room context
        if room_desc:
            parts.append(f"Current location: {room_desc}")

        # Player memory
        if player_memory:
            parts.append(f"Your history with {player_name}: {player_memory}")

        # Persuasion context (injected by skill check in TalkCommand)
        if persuasion_context:
            parts.append(persuasion_context)

        # Constraints
        parts.append(
            "RULES: Stay in character at all times. Do not reference game mechanics, "
            "dice rolls, or being an AI. Respond as your character would speak. "
            "Keep responses concise (1-3 sentences). Do not narrate actions for the player."
        )

        return "\n".join(parts)

    def _get_model(self) -> str:
        """Determine which model to use based on NPC tier."""
        cfg = self.npc.ai_config
        if cfg.model_override:
            return cfg.model_override
        ai_cfg = self.ai.config
        if cfg.model_tier == 2:
            return ai_cfg.tier2_model
        elif cfg.model_tier == 3:
            return ai_cfg.tier3_model
        return ai_cfg.tier1_model

    def _get_fallback(self) -> str:
        """Get a canned fallback response."""
        if self.npc.ai_config.fallback_lines:
            import random
            return random.choice(self.npc.ai_config.fallback_lines)
        return f"{self.npc.name} grunts noncommittally."

    async def dialogue(
        self,
        player_input: str,
        player_name: str = "",
        player_char_id: int = 0,
        room_desc: str = "",
        db=None,
        persuasion_context: str = "",
    ) -> str:
        """
        Generate an NPC dialogue response.

        Args:
            player_input: What the player said/asked.
            player_name: Player character name.
            player_char_id: For rate limiting and memory lookup.
            room_desc: Current room description for context.
            db: Database reference for memory lookup/save.
            persuasion_context: Hint injected by Persuasion skill check.
                Empty string = no check was run (casual greeting).

        Returns:
            NPC's spoken response as a string.
        """
        if not self.npc.ai_config.enabled:
            return self._get_fallback()

        # Load player memory from DB
        player_memory = ""
        if db and player_char_id:
            player_memory = await self._load_memory(db, player_char_id)

        # Build prompt
        system_prompt = self._build_system_prompt(
            room_desc=room_desc,
            player_name=player_name,
            player_memory=player_memory,
            persuasion_context=persuasion_context,
        )

        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": f"{player_name} says: {player_input}",
        })

        # Keep history manageable (last 6 exchanges)
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]

        # Generate
        response = await self.ai.generate(
            system_prompt=system_prompt,
            messages=self.conversation_history,
            char_id=player_char_id,
            max_tokens=self.npc.ai_config.max_tokens,
            temperature=self.npc.ai_config.temperature,
            model=self._get_model(),
            provider=self.npc.ai_config.provider_override,
            fallback_text=self._get_fallback(),
        )

        # Add response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response,
        })

        # Save memory asynchronously
        if db and player_char_id and response != self._get_fallback():
            try:
                await self._save_memory(db, player_char_id, player_input, response)
            except Exception as e:
                log.warning("Failed to save NPC memory: %s", e)

        return response

    async def _load_memory(self, db, char_id: int) -> str:
        """Load NPC's memory of a specific player."""
        try:
            rows = await db._db.execute_fetchall(
                """SELECT memory_json FROM npc_memory
                   WHERE npc_id = ? AND character_id = ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (self.npc.id, char_id),
            )
            if rows:
                data = json.loads(dict(rows[0])["memory_json"])
                return data.get("summary", "")
        except Exception:
            pass
        return ""

    async def _save_memory(self, db, char_id: int,
                           player_input: str, npc_response: str):
        """Save/update NPC's memory of this interaction."""
        # Load existing memory
        existing = await self._load_memory(db, char_id)

        # Build new memory entry
        new_entry = f"Player said '{player_input[:100]}', I responded '{npc_response[:100]}'"
        if existing:
            summary = f"{existing} | {new_entry}"
            # Keep summary under 500 chars
            if len(summary) > 500:
                summary = summary[-500:]
        else:
            summary = new_entry

        memory_json = json.dumps({"summary": summary, "last_interaction": time.time()})

        # Upsert
        await db._db.execute(
            """INSERT INTO npc_memory (npc_id, character_id, memory_json, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(npc_id, character_id)
               DO UPDATE SET memory_json = ?, updated_at = datetime('now')""",
            (self.npc.id, char_id, memory_json, memory_json),
        )
        await db._db.commit()
