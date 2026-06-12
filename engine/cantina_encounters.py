# -*- coding: utf-8 -*-
"""
engine/cantina_encounters.py — the d66 Cantina Encounter Table.

Source: Wretched Hives of Scum and Villainy §2C (WEG, 1997), reproduced in our
own words and era-translated to the Clone Wars (~20 BBY). This is a GM/Director
SCENE-SEEDING table (intentional, one beat at a time), distinct from the passive
ambient-room pool in data/worlds/clone_wars/ambient_events.yaml — many entries
here (explosions, hostages, arrests) are plot hooks that a GM triggers on purpose,
not background flavor that fires unbidden every few minutes.

Mechanic (WEG d66): roll 2d6, read one die as the tens digit and the other as the
ones — no addition — yielding 11–16, 21–26, …, 61–66 (36 equally-likely codes).

Era translation (Galactic Civil War -> Clone Wars): the four off-era source
entries are recast away from the old galactic regime and its insurgency — local
enforcers / clone patrol, off-duty soldiers or clones, and a double agent for a
rival faction or the Hutts. No off-era military framing (B3); no canonical named
figures (Q1).
"""
from __future__ import annotations
import random as _random
from typing import Optional, Tuple

# The 36 d66 codes (tens/ones, no 7s/8s/9s/0s).
D66_CODES: tuple[int, ...] = (
    11, 12, 13, 14, 15, 16,
    21, 22, 23, 24, 25, 26,
    31, 32, 33, 34, 35, 36,
    41, 42, 43, 44, 45, 46,
    51, 52, 53, 54, 55, 56,
    61, 62, 63, 64, 65, 66,
)

# code -> encounter beat (era-translated, B3-clean, Q1-safe).
CANTINA_ENCOUNTERS: dict[int, str] = {
    11: "A furtive figure peddles a datacard of stolen secrets.",
    12: "A barroom brawl erupts out of nowhere.",
    13: "Local enforcers — cartel toughs or a clone patrol — burst in chasing a fugitive.",
    14: "Drunken starfighter pilots loudly embellish their latest exploits.",
    15: "Two old rivals lock eyes across the room and clear leather.",
    16: "An attractive stranger buys one of the patrons a drink.",
    21: "Off-duty soldiers, loud and spoiling for it, start antagonizing the patrons.",
    22: "A badly wounded being staggers through the door and collapses.",
    23: "A vendor works the tables, hawking exotic — and clearly illegal — goods.",
    24: "A nervous stranger nurses one drink and keeps one eye on the entrance.",
    25: "Someone is quietly shopping the room for passage offworld.",
    26: "A knot of gamblers is deep in a high-stakes sabacc hand.",
    31: "A bounty hunter leans on the bartender, asking pointed questions.",
    32: "Two beings argue furiously at the next table, voices climbing.",
    33: "Security sweeps the room with a slow, deliberate visual search.",
    34: "A lost child wanders in, looking for its parents.",
    35: "A pickpocket drifts close, sizing up an easy mark.",
    36: "A face famous across the sector is, improbably, drinking here tonight.",
    41: "A sudden explosion rocks the bar; dust sifts from the ceiling.",
    42: "A nasty-looking alien fixes an unblinking stare on one of the patrons.",
    43: "Someone drops a loaded cred-stick on their way out the door.",
    44: "A sharp-eyed patron catches a man slipping something into a drink.",
    45: "Blaster fire breaks out between two rival swoop gangs.",
    46: "A passing alien levels a blaster at a patron — and then laughs.",
    51: "Heavily-armed gunmen shoulder in and start taking hostages.",
    52: "A patron keels over dead; authorities arrive and start questioning the crowd.",
    53: "A man stands, calm and deliberate, and arms two thermal detonators.",
    54: "A private investigator quietly tails the regulars out the door.",
    55: "A pair of mercenaries is openly looking for bodyguard work.",
    56: "A serving droid malfunctions and starts swinging at the patrons.",
    61: "The staff walk out on strike; the bar is forced to close for the night.",
    62: "A disgruntled owner shoves the deed across the bar at a patron and walks out.",
    63: "An out-of-control airspeeder crashes through the cantina wall.",
    64: "A desperate stranger begs the room for help getting offworld.",
    65: "A tactical team storms in, weapons up, hunting someone in the crowd.",
    66: "A contact someone came here to meet turns out to be a double agent — working for a rival faction, or the Hutts.",
}


def roll_cantina_encounter(rng: Optional[_random.Random] = None) -> Tuple[int, str]:
    """Roll the d66 cantina table. Returns (code, beat_text).

    True WEG d66: two independent d6 read as tens/ones (NOT 2d6 summed), so all
    36 codes are equally likely. Pass a seeded Random for deterministic tests."""
    r = rng or _random
    tens = r.randint(1, 6)
    ones = r.randint(1, 6)
    code = tens * 10 + ones
    return code, CANTINA_ENCOUNTERS[code]
