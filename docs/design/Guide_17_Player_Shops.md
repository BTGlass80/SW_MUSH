# SW_MUSH Detailed Systems Guide #17
# Player Shops & Trading

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Player shops are the **passive-revenue commerce layer** of SW_MUSH. You buy a vendor droid, place it in a public room, stock it with goods, set prices, and walk away. The droid sells to customers automatically. Revenue accumulates in escrow; you collect it when you check in.

This is the entrepreneur's system. It pairs naturally with crafting (Guide #7) and shopfront housing (Guide #13). Players who run shops successfully treat them as a sideline to their main play — the shop generates credits in the background while they run missions, do RP, or chase bounties.

If you only have ten minutes, read **§1 The Three Droid Tiers** and **§3 Setting Up Your First Shop**. The rest covers depth — pricing strategy, buy orders, the auto-recall protection, the market directory.

This is a new guide. There was no earlier version.

---

## 1. The Three Droid Tiers

Vendor droids come in three tiers. Each is a one-time purchase that you place in a room. The differences scale with cost.

| Tier | Droid | Cost | Slots | Listing Fee | Bargain Pool | Buy Orders |
|---|---|---|---|---|---|---|
| **Tier 1** | GN-4 Vendor Droid | 2,000 cr | 10 | 2.0% | None | No |
| **Tier 2** | GN-7 Merchant Droid | 5,000 cr | 25 | 1.5% | +2D | No |
| **Tier 3** | GN-12 Commerce Droid | 12,000 cr | 50 | 1.0% | +3D+1 | **Yes** |

**Slots** is how many distinct inventory items the droid can hold. A Tier 1 GN-4 can list 10 different items (each item slot can have a quantity — e.g., 5 medpacs counts as 1 slot). A Tier 3 GN-12 can list 50.

**Listing fee** is the per-transaction cost — a percentage of the sale price that is **destroyed** (not paid to anyone, removed from the economy) on every successful sale. A 1,000 cr sale on a Tier 1 droid pays the seller 980 cr and removes 20 cr from circulation. The fee is small but real, and it's lower on higher tiers.

**Bargain pool** is the droid's negotiation skill. When a customer haggles via the `bargain` command, the droid rolls Bargain against the customer's Bargain. A Tier 1 droid has no Bargain — customers can always haggle prices down. A Tier 2 droid has +2D Bargain — usually beats casual haggling. A Tier 3 droid has +3D+1 Bargain — strong enough to hold prices against most customers.

**Buy orders** (Tier 3 only) let your droid actively *purchase* items from passing customers. You set a buy price for a category of items; customers who have those items can sell them to the droid. The droid then resells at your set price. This is the high-end feature — turns your droid into both a shop *and* a passive sourcing channel for items you don't have to craft yourself.

### Choosing a tier

A new shop-owner's typical arc:

- **Tier 1 (GN-4)** for the first month or two. It's cheap, has enough slots for a focused niche, and pays back its cost within a couple of weeks of regular sales. The 2% listing fee adds up over time, but it's not catastrophic.
- **Tier 2 (GN-7)** when you've outgrown Tier 1 and want more slots. The 25-slot capacity supports a broader inventory. The Bargain pool protects pricing. The 1.5% listing fee is modestly better.
- **Tier 3 (GN-12)** for committed merchants running serious operations. The 50-slot capacity, the +3D+1 Bargain, and especially the buy-order capability make this the tool for the full-time merchant character. The 12,000 cr entry cost is significant but justified by the long-run revenue.

**You can upgrade tiers later.** Buy a higher-tier droid, transfer your inventory between them. The lower-tier droid can be sold back (with some refund) or repurposed for a second location.

---

## 2. Placement Rules

Where you can place a vendor droid is regulated.

### Allowed locations

- **Public rooms in cities and zones.** Most cantinas, markets, plazas, spaceport lounges, and similar accept droids.
- **Shopfront housing rooms (Tier 4 housing — Guide #13).** Your Market Stall, Merchant's Shop, or Trading House has dedicated droid slots designed for vendor placement. These are the *recommended* locations for serious commerce.

### Forbidden locations

- **Ship interiors.** No droids on starships.
- **Tutorial zones.** Tutorial rooms are gated to chain content.
- **Wilderness.** The wilderness grid doesn't support persistent objects (Guide #15).
- **Space.** Same reason.
- **Rooms flagged `no_commerce`.** Some special locations (private dwellings, sanctified zones) explicitly disallow commerce.

The engine checks placement and refuses with a clear error if your target room doesn't allow droids.

### Slot limits

- **2 vendor droids per room** by default. Tier 4 shopfront rooms can have more (set by the room's `droid_slots` property — typically 2-4 depending on shopfront tier).
- **3 vendor droids per owner** by default. Owning a shopfront raises this by 1 per shopfront. So a player with 2 shopfronts could have up to 5 vendor droids total.

These limits prevent any single player from monopolizing commerce in a region while letting committed merchants run serious operations.

### The placement workflow

```
shop buy droid <tier>        — Purchase a droid (it goes to your inventory)
shop place                   — Place a droid in your current room
shop recall                  — Recall a droid to your inventory
```

After purchase, the droid is in your inventory (no `room_id`). You travel to where you want to place it and use `shop place`. The engine validates the room and slots. Once placed, the droid is visible to all players who enter that room.

To move a droid to a different room, recall it first, travel, and re-place.

---

## 3. Setting Up Your First Shop

A start-to-finish walkthrough for a new shop-owner.

**Step 1 — Decide your niche.** Look at the existing market. What's underserved? Where do players have to wait for stock? Common niches: medpacs and stimpacks (medical), basic blasters (entry-level weapons), masterwork weapons (high-end signed weapons), specific ship components (for spacers), security gear (lockpicks, bugs), or specific crafted items in a particular planet's market.

**Step 2 — Buy a Tier 1 GN-4 droid.** 2,000 cr. From the shop dealer NPCs in major spaceports or via `shop buy droid gn4`. The droid materializes in your inventory.

**Step 3 — Pick a location.** Decide where you want to place it. The Mos Eisley cantina lobby? Coruscant's Senate District plaza? The Nar Shaddaa promenade? **Choose a high-traffic public room** — that's where customers will see your shop. Your Tier 4 shopfront's main room is the ideal location if you have one.

**Step 4 — Place the droid.** Travel to the room. Use `shop place`. The droid is visible to players entering the room. Other players can `browse <shop name>` to see what's on offer.

**Step 5 — Name and tag your shop.** Identity matters.

```
shop name <text>      — set the public-facing shop name
shop desc <text>      — set the tagline shown in directories
```

A vague shop name with no tagline is harder to find than a tagged shop with clear identity. "Voss Arms" + "Custom Blasters & Vibroblades" is more findable than "Random Goods."

**Step 6 — Stock initial inventory.** Use `shop stock <item> <price> [quantity]`. The item moves from your inventory into the droid's inventory at the specified price. You're now selling.

```
shop stock blaster_pistol 500 3
shop stock medpac_basic 200 10
shop stock stimpack_field 350 5
```

After this, the droid has 3 blaster pistols at 500 cr each, 10 medpacs at 200 cr each, and 5 stimpacks at 350 cr each. The droid is open for business.

**Step 7 — Check your dashboard.** Type `+shop` to see your shop status: where each droid is placed, what's stocked, total revenue in escrow, time since last sale, etc.

**Step 8 — Wait.** Customers will discover your shop through the market directory or by entering the room. They `browse Voss Arms` to see your inventory, then `buy <slot>` to purchase. The credit flows automatically — into the droid's escrow.

**Step 9 — Collect revenue.** Periodically (daily, weekly, whenever):

```
shop collect
```

The droid's accumulated escrow transfers to your wallet. Listing fees were already deducted during sales; what you collect is your net.

---

## 4. Pricing Strategy

Pricing is the most important active decision for shop-owners. Some patterns:

**The floor.** The engine enforces a minimum price: **50% of the NPC vendor's buy-back value** for that item type. You can't undercut the NPC market by more than half. This prevents loss-leader strategies that would dump items at unrealistic prices.

**The ceiling.** No formal cap, but customer behavior is the ceiling. Items priced 50% above the average market price tend not to sell, regardless of quality. Customers are price-aware.

**Quality matters.** A masterwork (quality-90+) item commands a real premium. Buyers pay 2-3x the standard price for a high-quality signed item. If you've crafted to quality 90+, price accordingly.

**Niche matters.** A medpac in Mos Eisley sells for ~150-250 cr because supply is high. The same medpac on a remote outpost might sell for 400 cr because supply is low. Know your local market.

**Volume matters.** A shop with 5 of an item at 500 cr sells faster than a shop with 1 of an item at 500 cr — customers feel the supply confidence. Stock in moderate quantities to signal supply.

**The bargain factor.** If you're on a Tier 1 droid with no Bargain pool, customers who `bargain` your prices can often knock 10-25% off. Either price higher to absorb the haggling, or upgrade to Tier 2+ to protect your prices.

### Adjusting prices

```
shop price <slot> <new price>
```

Updates the price of an existing inventory slot. Useful when:
- Demand spikes (price up).
- The item isn't selling (price down).
- You learn the local market better (recalibrate).

A common pattern: stock at 600 cr to start, watch sales for a week. If sales are slow, drop to 500 cr. If sales clear inventory quickly, raise to 700 cr next restock.

---

## 5. The Browse / Buy Flow

From the customer side:

```
market search                    — list shopfronts on the current planet
market search <planet>           — list shopfronts on a specific planet
market search all                — list every shopfront, all planets
browse <shop name>               — view a shop's inventory
buy <slot> [quantity]            — purchase from the shop you're browsing
bargain <slot>                   — attempt to haggle a price down
```

**`market search`** is the directory. It shows all player-run shopfronts in the queried area, with shop names, owners, locations, and (if set) taglines. This is how customers find your shop.

**`browse`** shows your droid's full inventory: each slot with item name, quality (if applicable), quantity, and price. Customers see what you're selling at what price.

**`buy <slot> [quantity]`** completes the transaction. The customer's wallet debits; the droid's escrow credits; the item moves to the customer's inventory. The listing fee is deducted from your payout.

**`bargain <slot>`** is the customer's negotiation move. They roll Bargain against your droid's Bargain pool. If they beat the droid's roll, they get a discount (typically 10-25%). Tier 1 droids with no Bargain auto-lose to any positive Bargain roll. Tier 2 (+2D) and Tier 3 (+3D+1) droids win most contests.

---

## 6. The Buy-Order System (Tier 3 Only)

A Tier 3 GN-12 Commerce Droid can do something the lower tiers can't: **actively buy items from passing customers**.

You set a buy order:

```
shop order <item> <max_price> [quantity]
```

Example: `shop order metal 50 100` posts an order to buy up to 100 units of metal at up to 50 cr per unit. Customers carrying metal can `sell <quantity> to <shop>` to fulfill the order. The droid pays them; the metal goes into your inventory (or into a pending-resale slot).

### Why this matters

Buy orders let your shop *source* items without you having to craft or survey for them. A merchant who buys raw materials from passing characters can resell them as crafted items (or as just-the-resource) at markup. Or buy completed items from other crafters at wholesale and resell at retail.

**The classic shop pattern with buy orders:**

1. Post a buy order for resource type X at a fair wholesale price.
2. Passing characters who have X to spare sell it to your shop.
3. You craft items from X (or have a hired crafter friend do it).
4. You stock the finished items at a higher retail price.
5. Margin = retail price − buy price − resource consumption − listing fees.

A well-run buy-order shop can be more profitable than a pure craft-and-sell shop, because the buy-order side becomes a passive income channel that doesn't require you to actively craft.

### Buy-order limits

- **Max simultaneous orders per droid: 5.** Limit the breadth of your buying.
- **Quantities are capped per order.** No "buy 10,000 metal at 1 cr each" cheese strategies.
- **Buy prices must be sensible.** The system rejects clearly-broken prices (1 cr for a masterwork weapon, etc.) — you can't extract free goods from naive customers.

### Cancelling an order

```
shop cancel <order_id>
```

Removes the buy order. Pending fulfillments aren't affected (if a customer is mid-transaction, it completes); future fulfillments stop.

---

## 7. The Auto-Recall Protection

Shop owners get distracted, take breaks, leave the game for stretches. The system protects against abandoned shops eating up room slots.

**The auto-recall mechanic:**

- After **30 days** of inactivity (no sales AND no owner interaction), the system notifies you that your shop is dormant.
- After **60 days** of inactivity, the droid is **automatically recalled** to your inventory. The room slot frees up.

"Inactivity" tracks two timestamps:
- **`last_sale_ts`** — the most recent sale at this droid.
- **`last_owner_ts`** — the most recent time you `shop`-anything'd this droid (stocked, collected, adjusted price, etc.).

Either timestamp resets the clock. A shop that's making sales (even small ones) stays placed forever. A shop where the owner periodically checks in (without sales happening) stays placed forever. Only shops that are *both* unsold and uninteracted-with get recalled.

**This protects:** room slots in popular zones (so abandoned shops don't permanently squat valuable real estate), and the owner's gear (so the droid doesn't get stuck somewhere they can't easily retrieve it from later).

**If you'll be away from the game:** make a final round of inventory adjustments before leaving. Even a small `shop price` change resets `last_owner_ts`, buying you another 60 days.

---

## 8. Common Inventory Categories

What sells well in a typical shop? A rough roster:

**Medical (always in demand).** Medpacs, stimpacks, bacta packs. These are consumables — players burn through them in combat and missions. A medical-focused shop with consistent stock and reasonable prices does steady business.

**Entry-level weapons.** Basic blaster pistols, sporting blasters, basic vibroblades. New characters buying their first weapon often visit a shop rather than chargen-grind for credits. Mass-produced quality-50-70 items at fair prices move well.

**Masterwork weapons (high-end).** Quality-90+ signed items. Smaller volume, higher prices. A weapon crafter who specializes in 1-2 masterwork pieces per week and prices them at 3-5x standard makes serious money per sale.

**Ship components.** Engine boosters, shield generators, sensor suites. The market is smaller (spacers only) but prices are high (4,000-10,000 cr per item). One sale per week from this category covers your housing.

**Security and sneak tools.** Lockpicks, comm bugs, trackers. Smaller-volume but consistent demand from underworld and intelligence characters.

**Personal protection.** Breath masks (for hazard environments), radiation suits, armor plating. Niche but consistent.

**Niche / themed.** Falleen-style luxury goods, Bothan-flavored intelligence tools, Wookiee-grade brawling weapons. A shop that leans into a faction or species identity can build a strong identity and customer loyalty.

---

## 9. Listing Fees and the Economy

Every successful sale destroys a percentage of the sale price (the listing fee):

| Tier | Listing Fee |
|---|---|
| Tier 1 (GN-4) | 2.0% |
| Tier 2 (GN-7) | 1.5% |
| Tier 3 (GN-12) | 1.0% |

A 5,000 cr sale on a Tier 1 droid pays the seller 4,900 cr and removes 100 cr from circulation. The fee is a **credit sink** — it's not paid to anyone, it's deleted from the economy. This serves two purposes:

1. **Compensate the marginal increase in money supply** caused by all the other income sources (missions, bounties, NPC vendor purchases, etc.). Without sinks, the economy inflates. The listing fee is one of several active sinks.
2. **Discourage churn-trading** between alts. If you "sell" items to your own alt through a vendor droid, you lose the listing fee on every transaction. Spinning items in circles for laundering purposes burns credits.

The total economic impact of listing fees scales with shop volume. A high-volume shop (50+ sales/week at average 1,000 cr each) pays roughly 1,000-2,000 cr/week in destroyed credits — meaningful but absorbable.

---

## 10. Shop Sales History

```
shop sales [droid_id]
```

Shows the recent sales activity for your droid(s). For each sale:
- The item sold.
- The buyer (name and id).
- The price paid (after bargain, if any).
- The listing fee deducted.
- The timestamp.

Useful for:
- Identifying which items move and which sit.
- Understanding your customer base (repeat buyers).
- Recalibrating prices based on actual sales velocity.

A typical week's sales report:

```
shop sales
   Voss Arms — Recent Sales:
   3d ago    Blaster Pistol     to Kael Voren        for 480 cr  (-9.6 fee)
   3d ago    Medpac (Basic)     to Trill Sethka      for 200 cr  (-4.0 fee)
   2d ago    Medpac (Basic)     to Trill Sethka      for 200 cr  (-4.0 fee)
   2d ago    Vibroblade         to Garth Zek         for 750 cr  (-15 fee)
   1d ago    Stimpack (Field)   to Sila Vannik       for 350 cr  (-7.0 fee)
   today     Medpac (Basic)     to Bram Vasur        for 200 cr  (-4.0 fee)
```

From this: medpacs are moving well; one repeat customer (Trill); the weapon sales are slower but higher value. Adjust accordingly.

---

## 11. The Market Directory

The `market search` command is how customers find shops, and it's also how you ensure your shop is discoverable.

```
market search                    — current planet's shops
market search Tatooine           — specific planet
market search all                — every shop everywhere
```

The directory shows:

```
market search Tatooine
   ── Tatooine Public Shops ──
   1. Voss Arms              (Owner: Kaylee Voss)     Mos Eisley Cantina Lobby
      "Custom Blasters & Vibroblades"
   2. Vannik Apothecary      (Owner: Sila Vannik)     Mos Eisley Market Row
      "Medical & Healing Supplies"
   3. The Honest Wreck       (Owner: Bram Vasur)      Anchorhead Outskirts
      "Salvage & Ship Parts"
```

Each entry shows shop name, owner, location, and tagline. The tagline is your elevator pitch — make it specific. "Quality goods" is meaningless; "Custom Blasters & Vibroblades" tells the customer what to expect.

**Visibility tips:**

- **Set a clear tagline.** This is your discoverability lever.
- **Place in high-traffic rooms.** A shop in Mos Eisley sees more browsers than a shop in a remote outpost.
- **Cross-reference with cantina RP.** Players who get to know you in scenes are more likely to remember and visit your shop. Build relationships in addition to listing inventory.
- **Maintain consistent inventory.** A shop that's frequently empty trains customers to look elsewhere. Keep at least a few items stocked at all times.

---

## 12. The Five Worked Shop Scenarios

Five concrete pictures.

**Scenario 1 — The new shop opener.** You're a Technician chargen character with 4D in First Aid. You buy a GN-4 droid (2,000 cr — most of your starting funds). You place it in the Nar Shaddaa promenade. You spend your first week crafting medpacs from purchased and surveyed chemicals/organics. You stock 5 medpac_basic at 200 cr each. In your first real week of operation, you sell 3 medpacs. Net revenue: 588 cr (after listing fees). The droid hasn't paid for itself yet, but you're learning what works.

**Scenario 2 — The established crafter.** You've been running a Tier 1 shop for 3 months. You've built up consistent customers; you're selling 8-15 medpacs and stimpacks per week. Weekly revenue averages 2,500 cr. You upgrade to a GN-7 (5,000 cr investment), which gives you 25 slots and protects pricing better. Within a month, you've added vibroblades and lockpicks to your inventory; weekly revenue rises to 4,500 cr. Your shop is now your primary income source.

**Scenario 3 — The masterwork specialist.** You're a 6D Blaster Repair crafter who specializes in masterwork weapons. You only craft 2-3 items per week — quality 95+ blasters with experimentation. You sell them at 4,000-8,000 cr each. Sales are slow (1 per week, maybe 2 in a good week), but margin is huge. Your shop is on a Tier 3 GN-12 in your own Tier 4 Trading House. Weekly revenue: 6,000-15,000 cr.

**Scenario 4 — The resource broker (Tier 3 buy-order shop).** You've moved to a Tier 3 GN-12 explicitly to use the buy-order feature. You post buy orders for chemicals (40 cr/unit), organics (35 cr/unit), and metal (50 cr/unit) in a market hub. Passing characters sell their excess to your shop. You then retail the resources at 60/55/75 per unit to other crafters in the same area. Margin per unit: 15-20 cr. You're moving 50-100 units of resources per week through buy-and-resell. Weekly revenue: ~1,500 cr in resource arbitrage, plus your own crafting on top. The shop has become a pure broker operation.

**Scenario 5 — The abandoned shop.** You opened a shop 2 months ago, stocked it well, made some sales — then you got busy and stopped checking in. The 30-day inactivity warning fires; you don't see it. At 60 days, the auto-recall triggers; the droid is in your inventory. Your inventory is intact (no items lost; the system protects you), but the shop slot in the original room is now free for someone else. When you come back to the game and check `+shop`, you see the droid in inventory and can re-place it (in the same room if no one else has taken the slot, or somewhere else). No harm done; the system's protection worked.

---

## 13. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `shop buy droid <tier>` | Purchase a vendor droid (gn4, gn7, gn12) |
| `shop place [id]` | Place a droid in the current room |
| `shop recall [id]` | Recall a droid to your inventory |
| `shop name <text>` | Set the shop's display name |
| `shop desc <text>` | Set the shop's tagline |
| `shop stock <item> <price> [qty]` | Add an item to a droid's inventory |
| `shop unstock <slot> [qty]` | Remove items from a slot |
| `shop price <slot> <new_price>` | Update a slot's price |
| `shop collect [id]` | Collect escrow revenue to your wallet |
| `shop sales [id]` | View recent sales history |
| `shop order <item> <max_price> [qty]` | Post a buy order (Tier 3 only) |
| `shop cancel <order_id>` | Cancel a posted buy order |
| `shop upgrade <tier>` | Upgrade droid tier (droid must be recalled) |
| `+shop` | Dashboard view of all your shops |
| `market search [planet \| all]` | Search shopfront directory |
| `browse <shop name>` | View a shop's inventory (customer side) |
| `buy <slot> [qty]` | Purchase from a browsed shop (customer side) |
| `bargain <slot>` | Haggle for a discount (customer side) |
| `sell <qty> to <shop>` | Sell to a shop's buy order (customer side) |

---

## 14. Numbers At A Glance

| Quantity | Value |
|---|---|
| **Tier 1 (GN-4) cost** | 2,000 cr |
| **Tier 1 slots** | 10 |
| **Tier 1 listing fee** | 2.0% |
| **Tier 2 (GN-7) cost** | 5,000 cr |
| **Tier 2 slots** | 25 |
| **Tier 2 listing fee** | 1.5% |
| **Tier 2 Bargain** | +2D |
| **Tier 3 (GN-12) cost** | 12,000 cr |
| **Tier 3 slots** | 50 |
| **Tier 3 listing fee** | 1.0% |
| **Tier 3 Bargain** | +3D+1 |
| **Tier 3 buy orders** | enabled |
| **Max droids per room (default)** | 2 |
| **Max droids per owner (base)** | 3 |
| **Shopfront ownership cap bonus** | +1 per shopfront owned |
| **Price floor** | 50% of NPC vendor buy-back value |
| **Inactivity warning** | 30 days |
| **Auto-recall** | 60 days |
| **Max active buy orders per droid** | 5 |

---

## 15. Common Pitfalls

**1. Placing in low-traffic rooms.** A shop in a dead-end corridor sees few browsers. High-traffic rooms (cantinas, plazas, market lobbies) sell faster.

**2. Underpricing.** The 50% floor exists for a reason — you can't go below it. But pricing close to the floor is leaving money on the table. Match market rates; let bargain rolls (or the lack thereof) finalize the price.

**3. Overstocking specialty items.** 20 masterwork carbines at 8,000 cr each will sit for months. The volume isn't there. Stock 2-3 high-end items at a time; let scarcity drive prices.

**4. Ignoring the auto-recall warning.** If you get the 30-day inactivity message, take a moment to interact with the droid (any `shop` command will reset the timer). Otherwise you'll come back to a recalled droid and lost shop placement.

**5. Treating buy orders as risk-free.** A Tier 3 buy order can drain your wallet if a flood of customers sells you the item. Don't post buy orders you can't afford to fulfill in volume. The cap on order quantity helps, but you can still get cleaned out if your max-price is too generous.

---

## 16. A Final Word

Player shops are how SW_MUSH's economy becomes a real ecosystem rather than just a series of NPC transactions. When you can buy a masterwork blaster signed by a Wookiee crafter you've never met, when you can sell your excess salvage to a Bothan broker's buy order without ever seeing her, when the cantina at Mos Eisley has three player-run shops competing for medpac customers — that's when the world starts to feel inhabited.

For shop-owners, the system is **passive revenue that pairs with active play**. You don't have to be at the shop for sales to happen. You craft or stock or post buy orders, and then you go run missions, do RP scenes, chase a PC bounty — and meanwhile your shop is generating credits in the background. A well-run shop generates more revenue per week than most active income streams, with the catch that it takes weeks of setup and stocking to reach that level.

The shopfront pairing (Guide #13's Tier 4 housing) is the natural endgame. Your own shopfront with multiple vendor droids in dedicated slots, a Tier 4 location that customers visit specifically because they know your work, and a customer base that's built up over months — that's where commerce becomes character identity.

If you're starting out: open a Tier 1 shop in a high-traffic area with focused inventory. Don't try to do everything; pick one niche and dominate it. Move up to Tier 2 once you've outgrown 10 slots. Move to Tier 3 (and the buy-order feature) when you're ready to broker at scale. The economy rewards patient, consistent shop-running. Most players who start shops in their first year of play are running profitable operations by year two.

---

*End of Guide #17 — Player Shops & Trading*
