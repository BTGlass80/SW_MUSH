"""Field Kit Drop B — canonical pose_event factory.

Per `field_kit_design_decomposition_v2.md` §4 and `field_kit_open_questions_v1_1.md`
§D5, every NPC, Director, hazard, encounter, and combat-narration emit
that is meant for the pose log goes through this module. The client
consumes typed `pose_event` JSON messages instead of plain text that
would otherwise hit the legacy `classifyAndAppend` regex on the way to
the pose log.

What this fixes:
  · "Room says..." mis-render (regex fallback misclassifying ambient
    narration as dialogue)
  · Misattributed hazard messages
  · NPC dialogue ambients tripping the say/whisper detector
  · Director-driven scene beats appearing as terminal text instead of
    properly attributed pose-log rows

What this does NOT cover:
  · Player-issued commands (say, pose, whisper, mutter) — those are
    Drop B', a separate session. Player narration is already attributed
    correctly today via the parser path; migrating it is consistency
    work, not bug-fix work.
  · System messages, prompts, command echoes — those stay as
    send_line() / send_prompt(). Only NARRATION goes through here.

Schema reconciliation (important):
  The live client `handlePoseEvent` (static/client.html ~line 5268) already
  consumes a `pose_event` schema with these fields:
      event_type: "say"|"pose"|"emote"|"whisper"|"sys-event"|"sys-arrival"|"sys-ok"|"comm-in"|"desc-inline"
      who:        speaker name (or "" for systems)
      text:       narration content
      mode:       optional verb decoration ("says"/"whispers"/"poses")
      to:         optional whisper target

  The design doc v2 §4 spec uses `mode`/`speaker` field names (different
  from live). Rather than break the existing client and the boarding/
  encounter_boarding emit sites that already work, this factory emits
  the LIVE schema and adds the new D5 fields (`deduplication_key`,
  `timestamp_ms`) as additive properties. The client ignores unknown
  fields today; the dedup key becomes useful when client-side
  suppression lands as a follow-up.

Dedup key (per D5):
  Composite `speaker_id:timestamp_ms:sha1(text)[:8]`. Cheap to compute,
  no server-side state needed. Handles the actual dedup case (room
  broadcast + speaker self-echo arriving within milliseconds) without
  false positives on rapid-fire identical poses by the same speaker.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional


# Event-type values accepted by the live client. These are the row-type
# discriminators the client uses to pick rendering style. Defined as
# constants so call sites self-document their intent.
EVENT_SAY          = "say"           # in-character dialogue ("X says, '...'")
EVENT_POSE         = "pose"          # third-person narration ("X looks around")
EVENT_EMOTE        = "emote"         # alias of pose; client treats identically
EVENT_WHISPER      = "whisper"       # private with `to` field
EVENT_SYS_EVENT    = "sys-event"     # banner ("BLASTER FIRE — close")
EVENT_SYS_OK       = "sys-ok"        # green confirmation banner
EVENT_SYS_ARRIVAL  = "sys-arrival"   # arrival/departure notification
EVENT_COMM_IN      = "comm-in"       # incoming comm message (amber treatment)
EVENT_DESC_INLINE  = "desc-inline"   # ambient/flavor desc (dimmed italic, no attribution)


def make_dedup_key(
    speaker_id: Optional[int],
    text: str,
    timestamp_ms: int,
) -> str:
    """Composite dedup key for client-side suppression of duplicate
    arrivals within the 250ms window.

    Cheap to compute, no server-side state needed. The `speaker_id`
    component handles the case where a system-level event is broadcast
    from multiple call sites within the same tick; the `timestamp_ms`
    component prevents collision across distinct rapid events; the
    `sha1(text)[:8]` component disambiguates simultaneous events of
    different content from the same speaker at the same instant.

    A speaker_id of None is normalized to 'system' so system events
    still get a stable dedup key.
    """
    speaker_part = str(speaker_id) if speaker_id is not None else "system"
    text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{speaker_part}:{timestamp_ms}:{text_hash}"


def make_pose_event(
    event_type: str,
    text: str,
    *,
    who: str = "",
    speaker_id: Optional[int] = None,
    mode: str = "",
    to: Optional[str] = None,
    timestamp_ms: Optional[int] = None,
    deduplication_key: Optional[str] = None,
) -> dict:
    """Build a typed pose_event payload ready for `session.send_json("pose_event", payload)`.

    Args:
        event_type: One of EVENT_* constants. Determines client row type.
        text: Narration content. For dialogue (`say`/`whisper`), the
              spoken line; for `pose`/`emote`, the third-person
              narration; for sys-* events, the banner text; for
              `desc-inline`, the ambient/flavor text (no attribution).
        who: Speaker display name. Empty string for sys-* and
              desc-inline (no attribution shown).
        speaker_id: Character ID if known, else None. Used by the
              composite dedup key.
        mode: Optional verb decoration ("says"/"whispers"/"poses").
              The client uses this when present; defaults inferred
              from event_type if blank.
        to: For whisper mode, the target name. None otherwise.
        timestamp_ms: Override for tests. Defaults to current time.
        deduplication_key: Override; otherwise computed from
              (speaker_id, text, timestamp_ms).

    Returns:
        Dict ready to pass as the `data` argument to
        `Session.send_json("pose_event", data)`. Schema matches the
        live client's `handlePoseEvent` consumer.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if deduplication_key is None:
        deduplication_key = make_dedup_key(speaker_id, text, timestamp_ms)
    payload = {
        "event_type": event_type,
        "who": who,
        "text": text,
    }
    # Add optional fields only when populated, to keep the wire payload
    # tight and avoid sending null fields the client doesn't consume.
    if mode:
        payload["mode"] = mode
    if to is not None:
        payload["to"] = to
    if speaker_id is not None:
        payload["speaker_id"] = speaker_id
    payload["timestamp_ms"] = timestamp_ms
    payload["deduplication_key"] = deduplication_key
    return payload


def make_ambient_event(text: str) -> dict:
    """Convenience wrapper for ambient room narration (no attribution).

    Used by Director ambient flavor, room-flavor pools, and any narration
    that should render as dimmed italic prose without a speaker line.
    Maps to client `event_type='desc-inline'`.
    """
    return make_pose_event(
        event_type=EVENT_DESC_INLINE,
        text=text,
        who="",
    )


def make_system_event(text: str) -> dict:
    """Convenience wrapper for sys-event banner content.

    Used for hazard ticks, combat banners, transient notifications
    (lock acquired, shield impact, credits transferred). Renders as
    a banner row in the pose log without a speaker.
    """
    return make_pose_event(
        event_type=EVENT_SYS_EVENT,
        text=text,
        who="",
    )


def make_npc_pose(npc_name: str, text: str, *, npc_id: Optional[int] = None) -> dict:
    """Convenience wrapper for NPC third-person narration.

    Used when an NPC takes an in-room action ("Yenn shakes his head")
    that the client should attribute to that NPC.
    """
    return make_pose_event(
        event_type=EVENT_POSE,
        text=text,
        who=npc_name,
        speaker_id=npc_id,
        mode="poses",
    )


def make_npc_say(npc_name: str, text: str, *, npc_id: Optional[int] = None) -> dict:
    """Convenience wrapper for NPC dialogue.

    Used when an NPC speaks ("Yenn says, 'Move along.'") that the
    client should attribute to that NPC with say-style quoting.
    """
    return make_pose_event(
        event_type=EVENT_SAY,
        text=text,
        who=npc_name,
        speaker_id=npc_id,
        mode="says",
    )
