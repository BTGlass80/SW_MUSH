---
key: attune
title: Attune — Draw a Kyber Shard from a Force Landmark
category: "Commands: Force"
summary: Force-sensitive characters at a force-resonant wilderness landmark meditate to draw a kyber shard (quality 75–95). Essential T5 crafting component for master-crafted lightsabers. 24-hour per-landmark cooldown. Jedi only.
aliases: []
see_also: [craft, wilderness, +powers, +forcestatus, meditate]
tags: [force, crafting, jedi, command]
access_level: 0
examples:
  - cmd: "attune"
    description: "At a force-resonant landmark: meditate and attempt a Knowledge check to draw a kyber shard."
---

Performed at a **force-resonant wilderness landmark**, `attune`
lets a Force-sensitive character draw a raw kyber shard from the
living Force. The shard is an essential Tier 5 crafting component
for master-crafted lightsabers.

REQUIREMENTS

  Force-sensitive    You must have at least one Force skill
                     (Control, Sense, or Alter) to attempt this.
  Location           You must be in a room flagged `force_resonant`.
                     These are rare landmarks — wilderness maps
                     hint at them through room descriptions.
  Cooldown           24-hour per-landmark cooldown. The landmark's
                     resonance "settles" after one successful draw
                     and yields nothing further until it recharges.
                     A failed attempt also starts the cooldown.

SKILL CHECK

The check uses Scholar (preferred) or Willpower, falling back
to raw Knowledge attribute if neither skill is trained.

  DC 11 (Moderate) — achievable for a well-rounded Jedi but
  not trivial for a newly-attuned Padawan.

  Success:   Kyber shard added to inventory (quality 75–95,
             scaled to margin above DC).
  Failure:   No shard. Cooldown still starts. The Force
             was not with you this time.

KYBER SHARD USES

Kyber shards are T5 crafting inputs. The primary use is
lightsaber construction via the `craft` system. Shards cannot
be bought or sold through normal market channels — attuning
at landmarks is the intended acquisition path.

EXAMPLES

  (in a force-resonant glade)
  attune
  → You settle into meditation. The Force stirs…
  → Roll Scholar 4D+1 vs DC 11 … success (margin +6)
  → A pale kyber shard surfaces from the stone. (quality 87)

  attune        (immediately after)
  → The resonance here has stilled. Return in 24 hours.

  attune        (in a non-resonant room)
  → There is no Force resonance here.

CHEAT SHEET
  attune   = draw a kyber shard at a force-resonant landmark
             (Force-sensitive only; 24h per-landmark cooldown)
  craft    = use the shard to build a lightsaber component
