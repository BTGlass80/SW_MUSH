# -*- coding: utf-8 -*-
"""
server/channels.py  --  Communication Channel Manager
SW_MUSH  |  Player Engagement P4

Routes global and faction-based messages to online sessions.
Pure in-memory — no DB persistence needed for transient comms.

Channels:
  ooc       -- Global out-of-character.  Always available.  Alias: newbie.
  comlink   -- Planet-wide IC channel.  Alias: cl.
  fcomm     -- Faction-only IC. Display labels are era-agnostic (Imperial,
               Rebel, Republic, Separatist, Hutt, etc.); routing is
               per-PC (each PC's stored faction value is the bucket).
  commfreq  -- Custom frequency IC (agree on a number with your crew).

Character faction is stored in character attributes JSON under key "faction".
Valid values (B.1.a, Apr 29 2026): the union of GCW and CW codes. See the
FACTIONS constant below for the canonical set. Default: "independent".

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
#
# B.1.a (Apr 29 2026) — extended to cover both GCW and CW director-axis
# faction codes. `FACTIONS` is now the era-agnostic union; labels and
# colors carry entries for every code so a CW PC's stored
# `attributes.faction = "republic"` renders as `[Republic]`, not as the
# `Unknown` fallback.
#
# Why a union (not a per-era table): the channel system is per-PC
# (each PC's stored faction value is the source of truth for fcomm
# routing). A GCW PC with `imperial` and a CW PC with `republic` can
# co-exist on the same server — they just can't fcomm each other,
# which is the correct semantics. The era flag controls which set
# chargen surfaces; the channel layer just renders whatever's stored.

FACTIONS = {
    # GCW director-axis (legacy, byte-equivalent for all GCW PCs)
    "imperial", "rebel", "criminal", "independent",
    # CW director-axis (Brian Apr 29: "the CW pivot needs to be complete")
    "republic", "cis",
    # Shared org-axis codes that may also appear in `attributes.faction`
    # via chargen direct-stash (covers all reasonable input shapes the
    # web client and IntentParser might emit).
    "empire", "hutt", "bh_guild",
    "hutt_cartel", "bounty_hunters_guild", "jedi_order",
}

FACTION_LABELS = {
    # GCW
    "imperial":              "Imperial",
    "rebel":                 "Rebel",
    "criminal":              "Criminal",
    "independent":           "Independent",
    "empire":                "Imperial",        # org-axis alias for fcomm display
    "hutt":                  "Hutt",
    "bh_guild":              "Bounty Hunter",
    # CW
    "republic":              "Republic",
    "cis":                   "Separatist",
    "jedi_order":            "Jedi",
    "hutt_cartel":           "Hutt",
    "bounty_hunters_guild":  "Bounty Hunter",
}

FACTION_COLORS = {
    # GCW
    "imperial":              "\033[37m",   # white/grey
    "rebel":                 "\033[31m",   # red
    "criminal":              "\033[33m",   # yellow
    "independent":           "\033[36m",   # cyan
    "empire":                "\033[37m",
    "hutt":                  "\033[33m",
    "bh_guild":              "\033[35m",   # magenta
    # CW
    "republic":              "\033[1;34m", # bold blue (mirrors orgs.yaml)
    "cis":                   "\033[1;31m", # bold red
    "jedi_order":            "\033[1;36m", # bold cyan
    "hutt_cartel":           "\033[33m",
    "bounty_hunters_guild":  "\033[35m",
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
                await sess.send_json("chat", {"channel": "ooc", "from": sender_name, "text": message})
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
                await sess.send_json("chat", {"channel": "ic", "from": sender_name, "text": f"[COMLINK] {message}"})
                count += 1
        log.debug("[comlink] %s: %s  (%d recipients)", sender_name, message[:60], count)
        # ── Comlink intercept delivery (Tier 3 Feature #19) ──
        try:
            await self._deliver_intercepts(session_mgr, sender_name, message, "comlink")
        except Exception:
            log.debug("[channels] intercept delivery failed", exc_info=True)
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
        # ── Fcomm intercept delivery (Tier 3 Feature #19) ──
        try:
            await self._deliver_intercepts(
                session_mgr, sender_name, message, f"fcomm/{faction}")
        except Exception:
            log.debug("[channels] fcomm intercept delivery failed", exc_info=True)
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

    # ── Comlink Intercept delivery (Tier 3 Feature #19) ─────────────────

    async def _deliver_intercepts(
        self,
        session_mgr: "SessionManager",
        sender_name: str,
        message: str,
        channel_label: str,
    ) -> None:
        """
        Deliver muffled comlink/fcomm messages to active interceptors.
        Only delivers to interceptors who are NOT already recipients of
        the original broadcast (e.g. intercepting a different faction's
        fcomm).
        """
        from engine.espionage import (
            get_all_active_interceptors, muffle_for_intercept,
            increment_intercept_count,
        )

        interceptors = get_all_active_interceptors()
        if not interceptors:
            return

        muffled = muffle_for_intercept(message)
        if not muffled or muffled.replace("...", "").strip() == "":
            return  # Nothing survived muffling

        intercept_line = (
            f"\n  \033[2;3m[INTERCEPT/{channel_label}] "
            f"{sender_name}: {muffled}\033[0m"
        )

        for char_id, isess in interceptors:
            sess = session_mgr.find_by_character(char_id)
            if not sess or not sess.is_in_game:
                continue
            char = sess.character
            if not char:
                continue
            # For fcomm: skip if interceptor is same faction (already got it)
            if channel_label.startswith("fcomm/"):
                fac = channel_label.split("/", 1)[1]
                if get_faction(char) == fac:
                    continue
            await sess.send_line(intercept_line)
            increment_intercept_count(char_id)

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
