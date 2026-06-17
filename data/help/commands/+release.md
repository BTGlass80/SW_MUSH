---
key: +release
title: +Release — Dissolve a Padawan Bond (Master-Side)
category: "Commands: Padawan-Master"
summary: Master voluntarily dissolves an active Padawan bond. The Padawan is notified and the dissolution is logged on both narrative records.
aliases: [release-padawan]
see_also: [+bond, +padawan, +leave-master, +trials, +knight]
tags: [padawan, master, bond, jedi, command]
access_level: 1
examples:
  - cmd: "+release Anakin"
    description: "Dissolve the bond with Anakin (no reason given)."
  - cmd: "+release Anakin = Reassigned by the Council"
    description: "Dissolve the bond with a recorded reason."
  - cmd: "+release"
    description: "Dissolve your sole active bond without naming the Padawan."
---

Voluntarily dissolve a Padawan-Master bond from the Master's side.
The dissolution is permanent (a new +bond is needed to reform one),
logged on both characters' narrative records, and notifies the
Padawan immediately if they are online.

SYNTAX

  +release <padawan>               Dissolve the bond with that Padawan.
  +release <padawan> = <reason>    Same, with a reason recorded.
  +release                         If you have exactly 1 bond, releases it.

WHAT HAPPENS

  - Bond is marked dissolved in the DB immediately.
  - Padawan sees a "bond went quiet" notification if online.
  - The reason (if given) is shown to the Padawan.
  - Both sides receive a narrative log entry (for the Director AI).
  - The Padawan's +master now shows "no active Master bond."

MASTERS WITH MULTIPLE PADAWANS

  If you hold more than one active bond (Council-authorized), you must
  name the Padawan. The convenience bare '+release' only works when
  you have exactly one bond.

EXAMPLES

  +release Anakin
  → "You release Anakin from your guidance."
  → Anakin (if online) hears: "You feel the bond with Obi-Wan go quiet."

  +release Anakin = Transferred to Master Yoda
  → Same, plus Anakin sees: "Reason given: Transferred to Master Yoda"

SEE ALSO

  +bond         Propose a new bond.
  +padawan      View current Padawan(s).
  +leave-master Padawan-side voluntary dissolution.
  +knight       Knight a Padawan (end bond via promotion).

CHEAT SHEET
  +release <name>            dissolve bond (Master use)
  +release <name> = <why>    dissolve with a recorded reason
