# -*- coding: utf-8 -*-
"""
IntentParser — natural language → structured combat action.

Sends the player's raw text to Ollama with a tightly bounded prompt
(SceneContext manifest), then validates the response through
BoundedContextValidator before returning a clean ActionRequest.

If Ollama is unavailable, offline, or returns garbage, falls back to
None so the caller can ask the player to rephrase.

Usage:
    parser = IntentParser(ai_manager)
    result = await parser.parse(raw_text, scene_ctx)
    if result:
        # result is a validated dict: {action, target_id?, skill?, damage?, cp?}
    else:
        # NL parsing failed — prompt the player to use explicit commands
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional, TYPE_CHECKING

from ai.bounded_validator import BoundedContextValidator, ValidationError

if TYPE_CHECKING:
    from ai.providers import AIManager
    from ai.scene_context import SceneContext

log = logging.getLogger(__name__)


# ── Static prefix (cached by Ollama across calls) ──────────────────────────────

_STATIC_PREFIX = """\
You are a game action parser for a Star Wars tabletop RPG game using the \
West End Games D6 system. Players type natural language commands and you \
extract a structured combat action from them.

VALID ACTION TYPES:
- attack     : Make an attack. Requires target_id from the entity list.
- dodge      : Dodge (uses an action slot, adds to ranged defense).
- fulldodge  : Full-round dodge (entire round spent dodging).
- parry      : Parry (melee defense, uses action slot).
- fullparry  : Full-round parry.
- aim        : Spend round aiming (+1D bonus to next attack).
- cover      : Move to cover (reduces incoming ranged damage).
- flee       : Attempt to leave combat.
- pass       : Take no action this round.

OUTPUT FORMAT:
Respond ONLY with a single JSON object. No prose, no markdown, no explanation.
Required field: "action" (string, one of the valid action types above).
Optional fields:
  "target_id"   : integer ID from the entity list — MUST be from the list
  "target_name" : string name (used if you cannot determine target_id)
  "skill"       : string skill name to use (e.g. "blaster", "melee combat")
  "damage"      : damage dice string (e.g. "4D+2", "STR+2D")
  "cp"          : integer Character Points to spend (default 0)

CRITICAL RULES:
1. target_id MUST be copied verbatim from the ENTITIES section below.
   NEVER invent an ID. If unsure, omit target_id and use target_name.
2. Only produce the action types listed above. Nothing else.
3. Output ONLY JSON. Example: {"action":"attack","target_id":42,"skill":"blaster"}
"""

# ── Dynamic suffix (rebuilt per scene) ────────────────────────────────────────

def _build_dynamic_suffix(player_text: str, scene_ctx: "SceneContext") -> str:
    lines = [
        f"\nPLAYER: {scene_ctx.char_name}",
        f"EQUIPPED WEAPON: {scene_ctx.weapon_summary()}",
        "\nENTITIES IN ROOM (use these exact IDs):",
        scene_ctx.entity_manifest(),
        f"\nVALID ACTIONS: {scene_ctx.actions_summary()}",
        f'\nPLAYER INPUT: "{player_text}"',
        "\nRespond with JSON only:",
    ]
    return "\n".join(lines)


# ── IntentParser ───────────────────────────────────────────────────────────────

class IntentParser:
    """
    Parses natural language combat input into a validated ActionRequest dict.
    """

    def __init__(self, ai_manager: "AIManager"):
        self.ai_manager = ai_manager
        self.validator = BoundedContextValidator()

    async def parse(
        self,
        raw_text: str,
        scene_ctx: "SceneContext",
        char_id: int = 0,
    ) -> Optional[dict]:
        """
        Parse natural language into a validated combat action.

        Returns:
            dict with keys: action, target_id (opt), skill (opt),
            damage (opt), cp (opt)  — or None if parsing failed.
        """
        if not raw_text or not raw_text.strip():
            return None

        # First try fast regex shortcuts (no LLM needed)
        shortcut = _try_regex_shortcut(raw_text, scene_ctx)
        if shortcut is not None:
            log.debug("IntentParser: regex shortcut matched: %s", shortcut)
            return shortcut

        # Build prompt
        dynamic = _build_dynamic_suffix(raw_text, scene_ctx)

        try:
            raw_json = await self.ai_manager.generate(
                system_prompt=_STATIC_PREFIX,
                messages=[{"role": "user", "content": dynamic}],
                char_id=char_id,
                max_tokens=120,
                temperature=0.0,    # deterministic — this is parsing, not creativity
                json_mode=True,
                fallback_text="",
            )
        except Exception as e:
            log.warning("IntentParser: AI call failed: %s", e)
            return None

        if not raw_json or not raw_json.strip():
            log.debug("IntentParser: empty AI response for input %r", raw_text)
            return None

        # Parse JSON
        parsed = _extract_json(raw_json)
        if parsed is None:
            log.warning(
                "IntentParser: could not extract JSON from response: %r",
                raw_json[:200],
            )
            return None

        # Validate against bounded context
        try:
            validated = self.validator.validate(parsed, scene_ctx)
        except ValidationError as e:
            log.warning("IntentParser: validation failed: %s", e)
            return None

        log.info(
            "IntentParser: parsed %r → %s",
            raw_text[:60],
            validated,
        )
        return validated


# ── Regex shortcuts (fast path, no LLM) ───────────────────────────────────────

# Single-word / very simple inputs we can parse without Ollama
_SHORTCUT_PATTERNS = [
    # "dodge", "fulldodge", "parry", "fullparry", "aim", "cover", "flee", "pass"
    (re.compile(r'^\s*(full\s*dodge|fulldodge)\s*$', re.I), {"action": "fulldodge"}),
    (re.compile(r'^\s*(full\s*parry|fullparry)\s*$', re.I), {"action": "fullparry"}),
    (re.compile(r'^\s*dodge\s*$', re.I), {"action": "dodge"}),
    (re.compile(r'^\s*parry\s*$', re.I), {"action": "parry"}),
    (re.compile(r'^\s*aim\s*$', re.I), {"action": "aim"}),
    (re.compile(r'^\s*(cover|take\s+cover|hide)\s*$', re.I), {"action": "cover"}),
    (re.compile(r'^\s*(flee|run|escape)\s*$', re.I), {"action": "flee"}),
    (re.compile(r'^\s*(pass|wait|nothing)\s*$', re.I), {"action": "pass"}),
]

# "shoot/attack/kill/hit <name>" — attack shortcut
_ATTACK_RE = re.compile(
    r'^\s*(shoot|attack|kill|fire at|hit|blast|stab|strike)\s+(.+)$', re.I
)


def _try_regex_shortcut(text: str, scene_ctx: "SceneContext") -> Optional[dict]:
    """
    Fast-path: parse trivially simple inputs without calling the LLM.
    Returns a validated dict or None.
    """
    # Non-attack single-verb shortcuts
    for pattern, result in _SHORTCUT_PATTERNS:
        if pattern.match(text):
            return dict(result)

    # Attack shortcuts
    m = _ATTACK_RE.match(text)
    if m:
        target_name = m.group(2).strip()
        # Try to resolve name to ID
        from ai.bounded_validator import _match_by_name
        tid = _match_by_name(target_name, scene_ctx)
        if tid is not None:
            return {
                "action": "attack",
                "target_id": tid,
                "skill": scene_ctx.default_skill,
                "damage": scene_ctx.default_damage,
            }
        # Name didn't match — let LLM handle it
        return None

    return None


# ── JSON extraction ────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[dict]:
    """
    Extract a JSON dict from LLM output.
    Handles: bare JSON, JSON wrapped in ```...```, leading/trailing prose.
    """
    text = text.strip()

    # Strip markdown fences
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find the first {...} block
    brace_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if brace_match:
        try:
            result = json.loads(brace_match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None
