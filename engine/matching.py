"""
Object Matching -- Inspired by LambdaMOO match.c

Centralized matching for all commands that reference game objects
(characters, NPCs, items, rooms). Eliminates duplicate ad-hoc
matching scattered across command handlers.

Match priority (per LambdaMOO):
  1. Exact name match (case-insensitive)
  2. Alias match (if object has aliases)
  3. Partial prefix match
  4. AMBIGUOUS if multiple partial matches

Search scope priority:
  1. Room contents (characters + NPCs in current room)
  2. Player inventory (carried items)
  3. Equipped items
  4. Self ("me", "self")
  5. Room itself ("here")

Special tokens:
  "me" / "self" -> the player's own character
  "here"        -> the current room
  "#<id>"       -> direct DB ID reference (builder/admin only)
"""
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

log = logging.getLogger(__name__)


class MatchResult(Enum):
    EXACT = auto()
    ALIAS = auto()
    PARTIAL = auto()
    AMBIGUOUS = auto()
    NOT_FOUND = auto()


@dataclass
class MatchCandidate:
    """A potential match target."""
    id: int
    name: str
    obj_type: str = ""     # "character", "npc", "object", "room"
    aliases: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)  # Full row data


@dataclass
class Match:
    """Result of an object match."""
    result: MatchResult
    candidate: Optional[MatchCandidate] = None
    # If AMBIGUOUS, these are the conflicting matches
    ambiguous_options: list[MatchCandidate] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.result in (MatchResult.EXACT, MatchResult.ALIAS, MatchResult.PARTIAL)

    @property
    def id(self) -> int:
        return self.candidate.id if self.candidate else 0

    @property
    def name(self) -> str:
        return self.candidate.name if self.candidate else ""

    def error_message(self, search_term: str) -> str:
        if self.result == MatchResult.AMBIGUOUS:
            names = ", ".join(c.name for c in self.ambiguous_options[:5])
            return f"Which one? (matches: {names})"
        return f"You don't see '{search_term}' here."


def match_one(search: str, candidates: list[MatchCandidate]) -> Match:
    """
    Match a search string against a list of candidates.

    Returns Match with result type and the matched candidate (if any).
    """
    if not search or not candidates:
        return Match(result=MatchResult.NOT_FOUND)

    search_lower = search.lower().strip()

    # Phase 1: Exact name match
    exact = [c for c in candidates if c.name.lower() == search_lower]
    if len(exact) == 1:
        return Match(result=MatchResult.EXACT, candidate=exact[0])
    if len(exact) > 1:
        return Match(result=MatchResult.AMBIGUOUS, ambiguous_options=exact)

    # Phase 2: Alias match
    alias_matches = []
    for c in candidates:
        for alias in c.aliases:
            if alias.lower() == search_lower:
                alias_matches.append(c)
                break
    if len(alias_matches) == 1:
        return Match(result=MatchResult.ALIAS, candidate=alias_matches[0])
    if len(alias_matches) > 1:
        return Match(result=MatchResult.AMBIGUOUS, ambiguous_options=alias_matches)

    # Phase 3: Partial prefix match
    partial = [c for c in candidates if c.name.lower().startswith(search_lower)]
    if len(partial) == 1:
        return Match(result=MatchResult.PARTIAL, candidate=partial[0])
    if len(partial) > 1:
        return Match(result=MatchResult.AMBIGUOUS, ambiguous_options=partial)

    # Phase 4: Substring match (less strict, last resort)
    substr = [c for c in candidates if search_lower in c.name.lower()]
    if len(substr) == 1:
        return Match(result=MatchResult.PARTIAL, candidate=substr[0])
    if len(substr) > 1:
        return Match(result=MatchResult.AMBIGUOUS, ambiguous_options=substr)

    return Match(result=MatchResult.NOT_FOUND)


async def match_in_room(
    search: str,
    room_id: int,
    char_id: int,
    db,
    session_mgr=None,
    include_npcs: bool = True,
    include_characters: bool = True,
    include_objects: bool = True,
    admin: bool = False,
) -> Match:
    """
    Match a search string against everything visible in a room.

    Handles special tokens: "me", "self", "here", "#<id>"

    Args:
        search: What the player typed
        room_id: Current room ID
        char_id: The searching character's ID
        db: Database reference
        session_mgr: SessionManager (for finding connected characters)
        include_npcs: Search NPCs
        include_characters: Search other characters
        include_objects: Search room objects
        admin: Allow #id references

    Returns:
        Match result
    """
    search = search.strip()
    if not search:
        return Match(result=MatchResult.NOT_FOUND)

    search_lower = search.lower()

    # Special tokens
    if search_lower in ("me", "self"):
        char = await db.get_character(char_id)
        if char:
            return Match(
                result=MatchResult.EXACT,
                candidate=MatchCandidate(
                    id=char["id"], name=char["name"],
                    obj_type="character", data=char,
                ),
            )

    if search_lower == "here":
        room = await db.get_room(room_id)
        if room:
            return Match(
                result=MatchResult.EXACT,
                candidate=MatchCandidate(
                    id=room["id"], name=room["name"],
                    obj_type="room", data=room,
                ),
            )

    # Direct ID reference (admin/builder only)
    if search.startswith("#") and admin:
        try:
            obj_id = int(search[1:])
            # Try character, NPC, room, object in order
            char = await db.get_character(obj_id)
            if char:
                return Match(
                    result=MatchResult.EXACT,
                    candidate=MatchCandidate(
                        id=char["id"], name=char["name"],
                        obj_type="character", data=char,
                    ),
                )
            npc = await db.get_npc(obj_id)
            if npc:
                return Match(
                    result=MatchResult.EXACT,
                    candidate=MatchCandidate(
                        id=npc["id"], name=npc["name"],
                        obj_type="npc", data=dict(npc),
                    ),
                )
        except (ValueError, TypeError):
            pass

    # Build candidate list from room contents
    candidates = []

    # Characters in room (from connected sessions)
    if include_characters and session_mgr:
        for s in session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] != char_id:
                candidates.append(MatchCandidate(
                    id=s.character["id"],
                    name=s.character["name"],
                    obj_type="character",
                    data=s.character,
                ))

    # NPCs in room
    if include_npcs:
        npcs = await db.get_npcs_in_room(room_id)
        for npc in npcs:
            candidates.append(MatchCandidate(
                id=npc["id"],
                name=npc["name"],
                obj_type="npc",
                data=dict(npc),
            ))

    # Objects in room (future: when inventory system is fuller)
    # if include_objects:
    #     objects = await db.get_objects_in_room(room_id)
    #     for obj in objects:
    #         candidates.append(MatchCandidate(...))

    return match_one(search, candidates)
