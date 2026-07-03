# -*- coding: utf-8 -*-
"""Regression: comlink is planet-scoped.

Design call COMM.comlink_not_planet_scoped, resolved Option A (Brian 2026-07-02):
`comlink` rides the planetary comm net, so `broadcast_comlink(db=..., sender_planet=...)`
delivers only to characters on the sender's planet. A sender with no planet
(deep space / a ship in transit) reaches only their own echo. With `db=None`
(no location context, e.g. legacy unit harnesses) it degrades to the old
unfiltered broadcast.

Also pins that the non-prefixed Coruscant districts (senate_district,
jedi_temple, …) resolve to one planet via engine.housing._planet_for_room's
_NONPREFIXED_ZONE_PLANET map, so comlink does not fragment across Coruscant.
"""
import asyncio

from server.channels import ChannelManager


class _Proto:
    def __init__(self, is_web):
        self.value = "websocket" if is_web else "telnet"


class _Sess:
    def __init__(self, name, room_id, is_web=False):
        self.protocol = _Proto(is_web)
        self.character = {"id": room_id, "name": name, "room_id": room_id}
        self.sent_lines = []
        self.sent_jsons = []

    async def send_line(self, text):
        self.sent_lines.append(text)

    async def send_json(self, msg_type, data):
        self.sent_jsons.append((msg_type, data))


class _Mgr:
    def __init__(self, *sessions):
        self.all = list(sessions)


class _StubDB:
    """Maps room_id -> zone name, mimicking the rooms-join-zones lookup that
    engine.housing._planet_for_room performs."""

    def __init__(self, room_zone):
        self._room_zone = room_zone

    async def fetchall(self, sql, params):
        zone = self._room_zone.get(params[0])
        return [] if zone is None else [{"name": zone}]


def _received(sess):
    return bool(sess.sent_lines or sess.sent_jsons)


def test_comlink_reaches_only_same_planet():
    cm = ChannelManager()
    sender = _Sess("Trill", room_id=10)   # tatooine
    same = _Sess("Mara", room_id=11)      # tatooine
    other = _Sess("Rax", room_id=20)      # coruscant (non-prefixed district)
    space = _Sess("Vex", room_id=30)      # deep space -> None
    mgr = _Mgr(sender, same, other, space)
    db = _StubDB({10: "tatooine_mos_eisley", 11: "tatooine_cantina",
                  20: "senate_district", 30: "space_tatooine"})

    count = asyncio.run(cm.broadcast_comlink(
        mgr, "Trill", "anyone around?", db=db, sender_planet="tatooine"))

    assert _received(sender)      # sender always hears their own echo
    assert _received(same)        # same planet
    assert not _received(other)   # different planet (Coruscant)
    assert not _received(space)   # off-planet
    assert count == 2


def test_comlink_coruscant_districts_share_a_planet():
    """Non-prefixed Coruscant districts must resolve to one planet, not fragment."""
    cm = ChannelManager()
    sender = _Sess("Jax", room_id=40)     # senate_district
    temple = _Sess("Yon", room_id=41)     # jedi_temple
    under = _Sess("Dob", room_id=42)      # coruscant_underworld (prefixed)
    offworld = _Sess("Kip", room_id=43)   # tatooine
    mgr = _Mgr(sender, temple, under, offworld)
    db = _StubDB({40: "senate_district", 41: "jedi_temple",
                  42: "coruscant_underworld", 43: "tatooine_market"})

    count = asyncio.run(cm.broadcast_comlink(
        mgr, "Jax", "convene", db=db, sender_planet="coruscant"))

    assert _received(sender)
    assert _received(temple)      # jedi_temple -> coruscant
    assert _received(under)       # coruscant_underworld -> coruscant
    assert not _received(offworld)
    assert count == 3


def test_comlink_offplanet_sender_reaches_only_self():
    cm = ChannelManager()
    sender = _Sess("Vex", room_id=30)     # deep space -> None
    ground = _Sess("Mara", room_id=11)    # tatooine
    mgr = _Mgr(sender, ground)
    db = _StubDB({30: "space_tatooine", 11: "tatooine_cantina"})

    count = asyncio.run(cm.broadcast_comlink(
        mgr, "Vex", "mayday", db=db, sender_planet=None))

    assert _received(sender)
    assert not _received(ground)
    assert count == 1


def test_comlink_db_none_is_unfiltered_legacy():
    cm = ChannelManager()
    a = _Sess("A", room_id=10)
    b = _Sess("B", room_id=20)
    mgr = _Mgr(a, b)

    count = asyncio.run(cm.broadcast_comlink(mgr, "A", "hello"))  # no db arg

    assert _received(a) and _received(b)
    assert count == 2
