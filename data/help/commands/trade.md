---
key: trade
title: Trade — Player-to-Player Credit and Item Exchange
category: "Commands: Economy"
summary: Offer credits or inventory items to another player in the same room. The target must accept within 2 minutes. A 5% tax applies to credit trades.
aliases: [offer, +trade]
see_also: [+inv, +credits, give, sell, buy]
tags: [economy, trading, social, command]
access_level: 0
examples:
  - cmd: "trade Jex 500 credits"
    description: "Offer Jex 500 credits (475 delivered after 5% tax)."
  - cmd: "trade Jex item Heavy Blaster Pistol"
    description: "Offer an item from your inventory — no tax on items."
  - cmd: "trade accept Jex"
    description: "Accept Jex's incoming trade offer."
  - cmd: "trade decline Jex"
    description: "Decline Jex's offer."
  - cmd: "trade cancel"
    description: "Cancel your own outgoing offer."
  - cmd: "trade list"
    description: "List all pending trade offers (incoming and outgoing)."
---

Exchange credits or inventory items with another player in the same
room. Both players must be co-located — this is a face-to-face trade.

**Syntax:**

    trade <player> <amount> credits      — offer credits
    trade <player> item <item name>      — offer an inventory item
    offer <player> <amount> credits      — alias for trade
    trade accept <player>                — accept an incoming offer
    trade decline <player>              — decline an incoming offer
    trade cancel                         — cancel your own offer
    trade list                           — show pending offers

**How it works:**

1. You initiate with `trade <player> ...`. The target sees a prompt.
2. They have **2 minutes** to `trade accept <your-name>` or the offer
   expires automatically.
3. For credits, a **5% economy tax** is deducted from the amount
   delivered (you pay 500, they receive 475).
4. Item trades have no tax — the item moves directly.

**Limits:** Only one outgoing offer at a time. Cancel with
`trade cancel` before making a new offer.

**See also:** `give` to hand items without the trade-window consent
flow; `sell` to sell to NPC vendors; `+credits` for your balance.
