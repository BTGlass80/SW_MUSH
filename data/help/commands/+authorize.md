---
key: +authorize
title: +Authorize — Master Pre-Authorization for Padawans
category: "Commands: Padawan-Master"
summary: Grant or revoke standing authorization for a Padawan in a category of otherwise approval-gated actions (offworld / powers / trials).
aliases: [authorise]
see_also: [+endorse, +trial, +trials, +master, +padawan]
tags: [padawan, master, authorization, jedi, command]
access_level: 1
examples:
  - cmd: "+authorize Anakin offworld"
    description: "Grant Anakin standing permission to take offworld missions."
  - cmd: "+authorize Anakin trials"
    description: "Grant Anakin standing Trial authorization (replaces +endorse)."
  - cmd: "+authorize Anakin powers off"
    description: "Revoke Anakin's standing Force-powers field authorization."
  - cmd: "+authorize Anakin"
    description: "List all standing authorizations for Anakin."
  - cmd: "+authorize"
    description: "List your Padawan's (or sole bond's) authorizations."
---

Grant a Padawan standing pre-authorization for a category of actions
that would otherwise require per-action Master approval. This is the
launch-era approval system: authorize once, routine activity proceeds
without repeated sign-off.

SYNTAX

  +authorize <padawan> <category>         Grant a category.
  +authorize <padawan> <category> off     Revoke a category.
  +authorize <category> [off]             Sole-bond Master shorthand.
  +authorize <padawan>                    List that Padawan's grants.
  +authorize                              List your sole Padawan's grants,
                                          or (as a Padawan) what your
                                          Master has authorized for you.

CATEGORIES

  offworld   Leave Coruscant for non-Council-sanctioned missions.
             Without this, Padawans are expected to stay on-planet.

  powers     Use Force powers in the field without per-use approval.
             Without this, field use of Powers is approval-gated.

  trials     Standing Trial endorsement (replaces repeated +endorse).
             The Padawan can attempt any Trial without a fresh
             '+endorse trials' each time.

  Aliases: travel/mission → offworld; force/power → powers; trial → trials.

EXAMPLES

  +authorize Anakin trials
  → "You grant Anakin standing authorization: trials."
  → +trials now shows Endorsement: standing.

  +authorize Anakin offworld off
  → "You revoke Anakin's standing authorization: offworld."

  +authorize Anakin
  → Lists: trials, offworld (or 'none granted')

  +authorize
  (as Padawan) Shows what your Master has authorized for you.

SEE ALSO

  +endorse    One-shot endorsement (consumed after one Trial pass).
  +trial      Record a passed Trial.
  +trials     View all Trial progress.
  +master     View bonded Master's status.

CHEAT SHEET
  +authorize <padawan> <category>       grant standing auth
  +authorize <padawan> <category> off   revoke
  +authorize <padawan>                  list grants
