"""
Party / Group System — engine layer.

Lightweight party system for co-op play:
  - Max party size: 6
  - Party leader: the inviter (transfers on leader leave)
  - Shared mission completion: all members in same room get full reward
  - Combat coordination: +1 pip initiative for party members in same combat
  - Party chat: private channel regardless of room
  - Persists across sessions (DB-backed)
  - Auto-disbands after 24h of leader inactivity

DB tables:
  parties (id, leader_id, created_at)
  party_members (party_id, char_id, joined_at)

Files:
  engine/party.py         (this file)
  parser/party_commands.py (commands)
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from db.database import Database

log = logging.getLogger(__name__)

# ── Constants ──

MAX_PARTY_SIZE = 6
DISBAND_TIMEOUT = 86400  # 24 hours of leader inactivity


@dataclass
class Party:
    """In-memory party representation."""
    id: int
    leader_id: int
    members: list[int] = field(default_factory=list)  # char_ids including leader
    created_at: float = 0.0

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def is_full(self) -> bool:
        return self.size >= MAX_PARTY_SIZE

    def has_member(self, char_id: int) -> bool:
        return char_id in self.members

    def is_leader(self, char_id: int) -> bool:
        return self.leader_id == char_id


class PartyManager:
    """
    Singleton managing all active parties.
    DB-backed with in-memory cache for fast lookups.
    """

    # DB table creation SQL (add to SCHEMA_SQL or run as migration)
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS parties (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        leader_id   INTEGER NOT NULL REFERENCES characters(id),
        created_at  REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS party_members (
        party_id    INTEGER NOT NULL REFERENCES parties(id),
        char_id     INTEGER NOT NULL REFERENCES characters(id),
        joined_at   REAL NOT NULL,
        PRIMARY KEY (party_id, char_id)
    );
    """

    def __init__(self):
        self._parties: dict[int, Party] = {}       # party_id -> Party
        self._char_party: dict[int, int] = {}      # char_id -> party_id
        self._invites: dict[int, int] = {}          # invitee_char_id -> inviter_char_id
        self._loaded = False

    async def ensure_loaded(self, db) -> None:
        """Load parties from DB on first access."""
        if self._loaded:
            return
        await self._load_from_db(db)
        self._loaded = True

    async def _load_from_db(self, db) -> None:
        """Pull all parties from DB into memory."""
        try:
            rows = await db._db.execute_fetchall(
                "SELECT * FROM parties"
            )
        except Exception:
            # Table may not exist yet
            log.info("[party] parties table not found — will create on first use")
            return

        for row in rows:
            party = Party(
                id=row["id"],
                leader_id=row["leader_id"],
                created_at=row["created_at"],
            )

            # Load members
            member_rows = await db._db.execute_fetchall(
                "SELECT char_id FROM party_members WHERE party_id = ?",
                (party.id,)
            )
            party.members = [r["char_id"] for r in member_rows]

            self._parties[party.id] = party
            for cid in party.members:
                self._char_party[cid] = party.id

        log.info("[party] Loaded %d parties from DB", len(self._parties))

    async def ensure_tables(self, db) -> None:
        """Create party tables if they don't exist."""
        try:
            await db._db.executescript(self.SCHEMA)
            await db._db.commit()
        except Exception as e:
            log.warning("[party] Table creation: %s", e)

    # ── Queries ──

    def get_party(self, char_id: int) -> Optional[Party]:
        """Get the party a character belongs to, or None."""
        pid = self._char_party.get(char_id)
        return self._parties.get(pid) if pid else None

    def get_party_members(self, char_id: int) -> list[int]:
        """Get party member char_ids (including self), or empty list."""
        party = self.get_party(char_id)
        return list(party.members) if party else []

    def in_same_party(self, char_id_a: int, char_id_b: int) -> bool:
        """Check if two characters are in the same party."""
        pa = self._char_party.get(char_id_a)
        pb = self._char_party.get(char_id_b)
        return pa is not None and pa == pb

    def has_pending_invite(self, char_id: int) -> Optional[int]:
        """Return the inviter char_id if this char has a pending invite."""
        return self._invites.get(char_id)

    # ── Mutations ──

    def invite(self, inviter_id: int, invitee_id: int) -> str:
        """
        Invite a player to the party.
        Returns error string or empty on success.
        """
        # Check invitee isn't already in a party
        if self.get_party(invitee_id):
            return "That player is already in a party."

        # Check invitee doesn't have a pending invite
        if invitee_id in self._invites:
            return "That player already has a pending invite."

        # Check inviter's party isn't full
        party = self.get_party(inviter_id)
        if party and party.is_full:
            return f"Party is full ({MAX_PARTY_SIZE} members max)."

        self._invites[invitee_id] = inviter_id
        return ""

    async def accept(self, invitee_id: int, db) -> tuple[str, Optional[Party]]:
        """
        Accept a pending invite.
        Returns (error_or_empty, party_or_none).
        """
        inviter_id = self._invites.pop(invitee_id, None)
        if inviter_id is None:
            return "You don't have a pending party invite.", None

        # Get or create the inviter's party
        party = self.get_party(inviter_id)
        if not party:
            # Create new party with inviter as leader
            party = await self._create_party(inviter_id, db)

        if party.is_full:
            return f"Party is full ({MAX_PARTY_SIZE} members max).", None

        # Add the invitee
        party.members.append(invitee_id)
        self._char_party[invitee_id] = party.id

        # Persist
        try:
            await db._db.execute(
                "INSERT INTO party_members (party_id, char_id, joined_at) VALUES (?, ?, ?)",
                (party.id, invitee_id, time.time())
            )
            await db._db.commit()
        except Exception as e:
            log.warning("[party] Failed to persist member: %s", e)

        return "", party

    async def leave(self, char_id: int, db) -> tuple[str, Optional[str]]:
        """
        Leave current party.
        Returns (error_or_empty, new_leader_name_or_none).
        """
        party = self.get_party(char_id)
        if not party:
            return "You're not in a party.", None

        party.members.remove(char_id)
        del self._char_party[char_id]

        # Persist removal
        try:
            await db._db.execute(
                "DELETE FROM party_members WHERE party_id = ? AND char_id = ?",
                (party.id, char_id)
            )
            await db._db.commit()
        except Exception as e:
            log.warning("[party] Failed to remove member: %s", e)

        new_leader_name = None

        if len(party.members) == 0:
            # Disband
            await self._delete_party(party.id, db)
        elif party.leader_id == char_id:
            # Transfer leadership
            party.leader_id = party.members[0]
            try:
                await db._db.execute(
                    "UPDATE parties SET leader_id = ? WHERE id = ?",
                    (party.leader_id, party.id)
                )
                await db._db.commit()
            except Exception:
                pass
            # We return the new leader id — caller resolves the name
            new_leader_name = str(party.leader_id)

        # If only 1 member left, disband
        if party.id in self._parties and len(party.members) <= 1:
            last = party.members[0] if party.members else None
            await self._delete_party(party.id, db)
            if last:
                self._char_party.pop(last, None)

        return "", new_leader_name

    async def kick(self, leader_id: int, target_id: int, db) -> str:
        """
        Kick a player from the party. Only the leader can kick.
        Returns error string or empty on success.
        """
        party = self.get_party(leader_id)
        if not party:
            return "You're not in a party."
        if not party.is_leader(leader_id):
            return "Only the party leader can kick members."
        if target_id == leader_id:
            return "You can't kick yourself. Use 'party leave'."
        if not party.has_member(target_id):
            return "That player isn't in your party."

        party.members.remove(target_id)
        self._char_party.pop(target_id, None)

        try:
            await db._db.execute(
                "DELETE FROM party_members WHERE party_id = ? AND char_id = ?",
                (party.id, target_id)
            )
            await db._db.commit()
        except Exception:
            pass

        # If only leader left, disband
        if len(party.members) <= 1:
            await self._delete_party(party.id, db)
            if party.members:
                self._char_party.pop(party.members[0], None)

        return ""

    def decline(self, invitee_id: int) -> str:
        """Decline a pending invite."""
        if invitee_id not in self._invites:
            return "You don't have a pending party invite."
        del self._invites[invitee_id]
        return ""

    # ── Internal ──

    async def _create_party(self, leader_id: int, db) -> Party:
        """Create a new party in DB and memory."""
        now = time.time()
        try:
            await self.ensure_tables(db)
            cursor = await db._db.execute(
                "INSERT INTO parties (leader_id, created_at) VALUES (?, ?)",
                (leader_id, now)
            )
            await db._db.commit()
            party_id = cursor.lastrowid

            # Add leader as first member
            await db._db.execute(
                "INSERT INTO party_members (party_id, char_id, joined_at) VALUES (?, ?, ?)",
                (party_id, leader_id, now)
            )
            await db._db.commit()
        except Exception as e:
            log.error("[party] Failed to create party: %s", e)
            # Fallback: in-memory only
            party_id = int(now * 1000) % 999999

        party = Party(id=party_id, leader_id=leader_id,
                      members=[leader_id], created_at=now)
        self._parties[party_id] = party
        self._char_party[leader_id] = party_id

        log.info("[party] Created party #%d, leader char #%d", party_id, leader_id)
        return party

    async def _delete_party(self, party_id: int, db) -> None:
        """Remove a party from DB and memory."""
        party = self._parties.pop(party_id, None)
        if party:
            for cid in party.members:
                self._char_party.pop(cid, None)

        try:
            await db._db.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
            await db._db.execute("DELETE FROM parties WHERE id = ?", (party_id,))
            await db._db.commit()
        except Exception:
            pass

        log.info("[party] Disbanded party #%d", party_id)


# ── Module-level singleton ──

_party_manager: Optional[PartyManager] = None


def get_party_manager() -> PartyManager:
    """Get or create the global PartyManager."""
    global _party_manager
    if _party_manager is None:
        _party_manager = PartyManager()
    return _party_manager
