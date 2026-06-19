---
key: allowrestrain
title: Allow Restrain — Consent to Voluntary Binder Application
category: "Commands: Combat"
summary: Opt in or out of being cuffed by another player without being defeated first. Default is off. Being defeated in combat always allows cuffing regardless of this setting.
aliases: [consentrestrain]
see_also: [restrain, escape, +pvp]
tags: [combat, restraint, consent, command]
access_level: 0
examples:
  - cmd: "allowrestrain on"
    description: "Allow any player to apply binders to you (voluntary capture / RP)."
  - cmd: "allowrestrain off"
    description: "Revert to default — only defeated characters can be cuffed."
  - cmd: "consentrestrain on"
    description: "Alias for allowrestrain on."
---

Toggle whether other players can apply binders to you without first
defeating you in combat.

**Syntax:**

    allowrestrain on     — consent to voluntary restraint
    allowrestrain off    — revoke consent (default)
    consentrestrain on   — alias
    consentrestrain off  — alias

**Default:** `off`. You can only be cuffed after being **defeated**
in combat (incapacitated / 0 wound points remaining).

**With `on`:** Any player can `cuff` you for RP purposes — willing
captures, prisoner scenarios, story scenes, etc. You can still
`escape` to break free at any time.

**Note:** Being defeated in combat always allows cuffing regardless of
this setting. `allowrestrain` only gates the voluntary / RP path.

**See also:** `restrain` / `cuff` to apply binders; `escape` to
break free; `+pvp` for consensual PvP flagging.
