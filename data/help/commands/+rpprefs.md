---
key: +rpprefs
title: +Rpprefs — RP Preferences
category: "Commands: Social"
summary: Set and display your RP preferences, which appear on your +finger profile.
aliases: [rpprefs]
see_also: [+finger, +background, +sheet]
tags: [rpprefs, roleplay, preferences, social, command]
access_level: 0
examples:
  - cmd: "+rpprefs"
    description: "View your current RP preferences."
  - cmd: "+rpprefs/set combat = yes"
    description: "Mark yourself as open to combat RP."
  - cmd: "+rpprefs/set notes = Prefer scene-setup in OOC first"
    description: "Add a freeform notes line."
  - cmd: "+rpprefs/clear"
    description: "Clear all your RP preferences."
---

Manage your RP preferences. These appear on your +finger profile
so other players know what kinds of roleplay you enjoy or avoid.

SYNTAX

  +rpprefs                            View your preferences
  +rpprefs/set <pref> = <value>       Set a preference
  +rpprefs/set notes = <text>         Set a freeform notes field
  +rpprefs/clear                      Clear all preferences

VALID PREFERENCES

  combat      Open to combat RP
  romance     Open to romance storylines
  dark        Comfortable with dark/mature themes
  scheduled   Prefer scheduled scenes over spontaneous RP
  notes       Freeform text (any value)

  All preferences except notes accept: yes / no / maybe

EXAMPLES

  +rpprefs/set combat = yes
  → Marks you as open to combat RP.

  +rpprefs/set dark = maybe
  → Shows "dark: maybe" on your profile — interested but case-by-case.

  +rpprefs/set notes = OOC ping before combat please
  → Freeform text visible on your +finger.

  +rpprefs
  → Displays your currently set preferences.

SEE ALSO

  +finger      View another player's profile (includes RP prefs).
  +background  Your character's backstory.

CHEAT SHEET
  +rpprefs                        view your prefs
  +rpprefs/set <pref> = yes/no    set a flag
  +rpprefs/set notes = <text>     freeform note
  +rpprefs/clear                  wipe all prefs
