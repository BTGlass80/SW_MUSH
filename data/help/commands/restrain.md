---
key: restrain
title: Restrain / Cuff — Bind a Subdued Target
category: "Commands: Combat"
summary: Apply binders to a defeated or consenting character, preventing movement and combat until released or escaped. Requires binders in inventory. Release with uncuff.
aliases: [cuff, bind, uncuff, unbind]
see_also: [allowrestrain, escape, +combat]
tags: [combat, restraint, command]
access_level: 0
examples:
  - cmd: "cuff Grak"
    description: "Snap binders on the defeated Grak. Consumes one binder from inventory."
  - cmd: "restrain Grak"
    description: "Alias for cuff."
  - cmd: "bind Grak"
    description: "Alias for cuff."
  - cmd: "uncuff Grak"
    description: "Release Grak from their binders (captor or admin only)."
  - cmd: "unbind Grak"
    description: "Alias for uncuff."
---

Apply binders to a character who has been defeated in combat or who
has opted in to being restrained.

## Restrain (cuff / bind)

    cuff <target>       — apply binders
    restrain <target>   — alias
    bind <target>       — alias

**Requirements:**

- The target must be **defeated** (incapacitated in combat) **OR**
  have used `allowrestrain on` to consent to voluntary restraint.
- You must have **binders** in your inventory (consumed on use).
- You cannot cuff a healthy, unwilling player.

**Effect:** A restrained character cannot move, attack, or change
gear. They remain in place until freed.

## Release (uncuff / unbind)

    uncuff <target>     — release a restrained character
    unbind <target>     — alias

Only the captor or an admin can release a prisoner.

## Escape

The restrained player can attempt to break free with `escape`
(a Strength check, Difficulty Hard 20). See `+help escape`.

**See also:** `allowrestrain` to opt in/out of voluntary restraint;
`escape` to break free; `+combat` for the full combat system.
