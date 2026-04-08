# -*- coding: utf-8 -*-
"""
server/channels.py  --  Communication Channel Manager
SW_MUSH  |  Player Engagement P4

Routes global and faction-based messages to online sessions.
Pure in-memory — no DB persistence needed for transient comms.

Channels:
  ooc       -- Global out-of-character.  Always available.  Alias: newbie.
  comlink   -- Planet-wide IC channel.  Alias: cl.
  fcomm     -- Faction-only IC (Imperial / Rebel / Criminal / Independent).
  commfreq  -- Custom frequency IC (agree on a number with your crew).

Character faction is stored in character attributes JSON under key "faction".
Valid values: "imperial", "rebel", "criminal", "independent" (default).

Usage in commands:
    from server.channels import get_channel_manager
    cm = get_channel_manager()
    await cm.broadcast_ooc(session_mgr, sender_name, message)
    await cm.broadcast_comlink(session_mgr, sender_name, message)
    await cm.broadcast_fcomm(session_mgr, sender_name, faction, message)
    await cm.broadcast_freq(session_mgr, sender_name, freq, message, char_id)
"""

import json
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.session import SessionManager

log = logging.getLogger(__name__)

# ── Faction constants ──────────────────────────────────────────────────────────

FACTIONS = {"imperial", "rebel", "criminal", "independent"}
FACTION_LABELS = {
    "imperial":    "Imperial",
    "rebel":       "Rebel",
    "criminal":    "Criminal",
    "independent": "Independent",
}
FACTION_COLORS = {
    "imperial":    "\033[37m",   # white/grey
    "rebel":       "\033[31m",   # red
    "criminal":    "\033[33m",   # yellow
    "independent": "\033[36m",   # cyan
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def get_faction(char: dict) -> str:
    """Extract faction from character dict.  Defaults to 'independent'."""
    if not char:
        return "independent"
    # Check top-level key first
    if "faction" in char:
        f = str(char["faction"]).lower()
        return f if f in FACTIONS else "independent"
    # Fall back to attributes JSON blob
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        f = str(attrs.get("faction", "independent")).lower()
        return f if f in FACTIONS else "independent"
    except (json.JSONDecodeError, AttributeError):
        return "independent"


# ── Message formatting ─────────────────────────────────────────────────────────

def fmt_ooc(name: str, message: str) -> str:
    return f"\033[35m[OOC] {BOLD}{name}{RESET}\033[35m: {message}{RESET}"


def fmt_comlink(name: str, message: str) -> str:
    return f"\033[36m[Comlink] {BOLD}{name}{RESET}\033[36m: {message}{RESET}"


def fmt_fcomm(name: str, faction: str, message: str) -> str:
    color = FACTION_COLORS.get(faction, "\033[36m")
    label = FACTION_LABELS.get(faction, "Unknown")
    return f"{color}[{label}] {BOLD}{name}{RESET}{color}: {message}{RESET}"


def fmt_freq(name: str, freq: int, message: str) -> str:
    return f"\033[32m[Freq {freq}] {BOLD}{name}{RESET}\033[32m: {message}{RESET}"


# ── ChannelManager ─────────────────────────────────────────────────────────────

class ChannelManager:
    """
    Routes channel messages to the appropriate online sessions.

    All broadcast methods accept a SessionManager and iterate over its
    online sessions, filtering as needed.  No DB required — channels are
    ephemeral pub/sub, not persistent logs.
    """

    def __init__(self):
        # Set of (char_id, freq) tuples for custom frequency listeners.
        self._freq_listeners: set = set()

    # ── OOC ───────────────────────────────────────────────────────────────────

    async def broadcast_ooc(
        self,
        session_mgr: "SessionManager",
        sender_name: str,
        message: str,
    ) -> int:
        """Broadcast to all in-game sessions.  Returns recipient count."""
        line = fmt_ooc(sender_name, message)
        count = 0
        for sess in session_mgr.all:
            if sess.character:
                await sess.send_line(line)
                count += 1
        log.debug("[ooc] %s: %s  (%d recipients)", sender_name, message[:60], count)
        return count

    # ── Comlink ───────────────────────────────────────────────────────────────

    async def broadcast_comlink(
        self,
        session_mgr: "SessionManager",
        sender_name: str,
        message: str,
    ) -> int:
        """Broadcast planet-wide IC comlink to all in-game sessions."""
        line = fmt_comlink(sender_name, message)
        count = 0
        for sess in session_mgr.all:
            if sess.character:
                await sess.send_line(line)
                count += 1
        log.debug("[comlink] %s: %s  (%d recipients)", sender_name, message[:60], count)
        return count

    # ── Faction Comms ─────────────────────────────────────────────────────────

    async def broadcast_fcomm(
        self,
        session_mgr: "SessionManager",
        sender_name: str,
        faction: str,
        message: str,
    ) -> int:
        """Broadcast to all online members of the same faction."""
        faction = faction.lower()
        line = fmt_fcomm(sender_name, faction, message)
        count = 0
        for sess in session_mgr.all:
            char = sess.character
            if char and get_faction(char) == faction:
                await sess.send_line(line)
                count += 1
        log.debug(
            "[fcomm/%s] %s: %s  (%d recipients)",
            faction, sender_name, message[:60], count,
        )
        return count

    # ── Custom Frequency ──────────────────────────────────────────────────────

    def tune(self, char_id: int, freq: int) -> None:
        """Subscribe a character to a custom frequency."""
        self._freq_listeners.add((char_id, freq))

    def untune(self, char_id: int, freq: int) -> None:
        """Unsubscribe from a custom frequency."""
        self._freq_listeners.discard((char_id, freq))

    def tuned_freqs(self, char_id: int) -> list:
        """List all frequencies a character is currently tuned to."""
        return sorted(f for (cid, f) in self._freq_listeners if cid == char_id)

    def is_tuned(self, char_id: int, freq: int) -> bool:
        return (char_id, freq) in self._freq_listeners

    def cleanup_character(self, char_id: int) -> None:
        """Remove all freq subscriptions for a character (call on logout)."""
        self._freq_listeners = {
            (cid, f) for (cid, f) in self._freq_listeners if cid != char_id
        }

    async def broadcast_freq(
        self,
        session_mgr: "SessionManager",
        sender_name: str,
        freq: int,
        message: str,
        sender_char_id: int,
    ) -> int:
        """
        Broadcast to all characters tuned to a given frequency.
        Returns -1 if sender is not tuned in (cannot transmit).
        """
        if not self.is_tuned(sender_char_id, freq):
            return -1  # Caller should tell sender to tune in first

        line = fmt_freq(sender_name, freq, message)
        count = 0
        for sess in session_mgr.all:
            char = sess.character
            if char and self.is_tuned(char["id"], freq):
                await sess.send_line(line)
                count += 1
        log.debug(
            "[freq %d] %s: %s  (%d recipients)", freq, sender_name, message[:60], count
        )
        return count

    # ── Utility ───────────────────────────────────────────────────────────────

    def online_count(self, session_mgr: "SessionManager") -> int:
        """Count players currently in-game."""
        return sum(1 for s in session_mgr.all if s.character)


# ── Module-level singleton ─────────────────────────────────────────────────────

_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """Get or create the global ChannelManager."""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
