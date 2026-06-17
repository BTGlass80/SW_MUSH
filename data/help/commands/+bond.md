---
key: +bond
title: +Bond — Propose or Accept a Padawan-Master Bond
category: "Commands: Padawan-Master"
summary: Player-flow bond formation — Masters propose, Padawans accept or decline. Proposals expire in 10 minutes.
aliases: [bond]
see_also: [+master, +padawan, +release, +leave-master, +trials]
tags: [padawan, master, bond, jedi, command]
access_level: 1
examples:
  - cmd: "+bond Anakin"
    description: "(Master) Propose a bond to Anakin, who must be in the same room."
  - cmd: "+bond accept Obi-Wan"
    description: "(Padawan) Accept Obi-Wan's pending bond proposal."
  - cmd: "+bond decline Obi-Wan"
    description: "(Padawan) Decline Obi-Wan's pending bond proposal."
---

Form a Padawan-Master bond through the two-step player-flow handshake:
the Master proposes, the Padawan accepts or declines. Both must be in
the same room for the proposal; acceptance can happen from anywhere
within 10 minutes.

SYNTAX

  +bond <padawan name>          (Master) Propose a bond.
  +bond accept <master name>    (Padawan) Accept a pending proposal.
  +bond decline <master name>   (Padawan) Decline a pending proposal.

THE PLAYER FLOW

  1. Master and Padawan are in the same room.
  2. Master types '+bond <padawan>'.
  3. Padawan is notified in real time (or on next login if offline).
  4. Padawan types '+bond accept <master>' to confirm.
  5. The bond is established; both characters are linked.

  Proposals expire 10 minutes after they are made. The Master can
  re-propose at any time after expiry.

RESTRICTIONS

  - A Padawan can hold only one active bond at a time.
  - A Master's default cap is 1 Padawan; staff can raise it
    per-character for Council-authorized Masters.
  - A Master cannot bond with themselves.
  - The Padawan target must be a player character (no droids/NPCs).

STAFF ASSIGNMENT

  Staff use '@bond <master> = <padawan>' to directly establish a
  bond without the consent handshake (for tester-cohort pairings
  and mediated assignments).

EXAMPLES

  (Master and Padawan in the same room:)
  +bond Anakin
  → "You offer to take Anakin as your Padawan..."
  → Anakin sees: "Obi-Wan offers to take you as their Padawan."

  (Anakin responds:)
  +bond accept Obi-Wan
  → "You accept the bond. Obi-Wan is now your Master."
  → Obi-Wan sees: "Anakin has accepted your bond proposal."

  +bond decline Obi-Wan
  → "You decline the bond proposal from Obi-Wan."

SEE ALSO

  +master       View bonded Master's status (Padawan).
  +padawan      View bonded Padawan(s) status (Master).
  +release      Master dissolves a bond voluntarily.
  +leave-master Padawan leaves a bond voluntarily.
  +trials       Trial progress leading to knighting.

CHEAT SHEET
  +bond <name>          propose a bond (Master, same room required)
  +bond accept <name>   accept a proposal (Padawan, 10m window)
  +bond decline <name>  decline a proposal (Padawan)
