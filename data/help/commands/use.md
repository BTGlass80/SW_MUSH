---
key: use
title: Use — Activate or Consume an Inventory Item
category: "Commands: Basic"
summary: Activate or consume an item in your inventory. Consumable items are removed after use. Chain quest items trigger their completion hook.
aliases: []
see_also: [+inv, get, give, loot]
tags: [basic, inventory, command]
access_level: 0
examples:
  - cmd: "use sealed_data_packet"
    description: "Use the sealed data packet (exact key match)."
  - cmd: "use medpac"
    description: "Consume a medpac from your inventory."
  - cmd: "use Sealed Data Packet"
    description: "Use by display name (case-insensitive)."
  - cmd: "use packet"
    description: "Partial name match — finds 'Sealed Data Packet' if it's the only match."
---

Activate or consume an item from your inventory.

**Syntax:**

    use <item-name-or-key>

**Item resolution order:**

1. Exact item key match (case-sensitive)
2. Exact display name match (case-insensitive)
3. Single partial name match (case-insensitive prefix/substring)

If more than one item matches the partial name, you'll be asked to
be more specific.

**Consumable items:** Items flagged as consumable (stims, medpacs,
quest items) are removed from your inventory after successful use.

**Chain quest items:** Using a chain quest item (like a data packet
or keepsake) fires the `on_item_used` chain hook, which may advance
your current tutorial chain step.

**Custom messages:** Some items display a custom message on use
(defined by the item's `use_message` field). Others show a generic
"You use the X."

**See also:** `+inv` to list your inventory; `stim` for stim use
(which has its own command with overdose logic); `give` to hand an
item to another player.
