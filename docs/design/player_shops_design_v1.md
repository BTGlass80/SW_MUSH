# SW_MUSH — Player Shop System
## Design Document v1.0
### April 2026 · BTGlass80 · WEG D6 R&E

---

## 1. Design Philosophy

The crafting system builds supply. NPC shops provide a floor. But right now there's no way for a player to turn crafting into a *business* — to set up shop, stock a shelf, set prices, and earn credits while offline. Player shops fix this gap and create the demand pipeline the competitive analysis identified as the #1 long-term retention driver.

### 1.1 Why Vendor Droids?

The vendor droid model wins over alternatives for several reasons:

**Thematic fit.** The Star Wars universe is full of automated kiosks and droid-run stalls. The WEG Equipment Cost Chart lists First-Degree through Fifth-Degree droids at 1,000–5,000 credits — perfectly placed as a mid-game investment. A player buys a vendor droid, programs it with their stock and prices, and places it in a room. Other players interact with the droid to browse and buy. The owner earns credits while offline.

**No room ownership needed.** We don't need a property system. The droid is an object placed in a public room — like placing a vending machine. This avoids the massive complexity of room rental, property taxes, and territorial disputes. If the player wants to move, they pick up their droid and place it elsewhere.

**Scales with the world.** One player might have a single droid in Mos Eisley Market. A Hutt Cartel boss might have droids on four planets. No architecture changes needed — just more droid objects.

**NPC vendor parity.** Vendor droids use the same buy interface as NPC shops. Players already know how to `buy` and `sell`. The only new command is the owner's management interface.

### 1.2 Guiding Principles

**Offline income, not AFK income.** The droid sells for you when you're logged off. This rewards the *crafting investment*, not screen time.

**Prices are player-set.** The owner decides what to charge. The market determines if anyone buys. NPC shops set a price floor (since players can always sell to Kayson). Player shops compete on quality, availability, and pricing.

**No monopoly mechanics.** Any player with enough credits can buy a vendor droid. No exclusive shop licenses, no limited stall slots. The market is open.

**Credit sinks built in.** Droid purchase cost, restocking fee, optional upgrade costs — all remove credits from circulation. This offsets the income generation.

**Dual-Interface Principle applies.** All shop commands work on Telnet. Web client gets a nicer browse panel but never gates content.

---

## 2. Vendor Droid Model

### 2.1 Droid Types

Three tiers, matching the WEG droid cost scale:

| Tier | Name | Cost | Inventory Slots | Listing Fee | Special |
|------|------|------|----------------|-------------|---------|
| 1 | GN-4 Vendor Droid | 2,000cr | 10 | 2% per sale | Basic — text-only listing |
| 2 | GN-7 Merchant Droid | 5,000cr | 25 | 1.5% per sale | Bargain skill 2D (haggles with buyers) |
| 3 | GN-12 Commerce Droid | 12,000cr | 50 | 1% per sale | Bargain 3D+1, can accept buy orders |

**Inventory slots** = distinct item stacks. A slot can hold multiple copies of the same item (e.g., "10x Medpac (Basic), quality 72, 45cr each" = 1 slot).

**Listing fee** is a percentage taken from each sale as a credit sink. The droid "charges" for its services. Higher-tier droids take a smaller cut.

**Bargain skill** (Tier 2+): When a buyer uses `buy` at a vendor droid, the droid makes a Bargain check vs. the buyer. If the droid wins, the buyer pays the listed price. If the buyer wins, they get a small discount (margin-scaled, max 10%). This is flavor — it makes the shopping interaction feel alive — and mechanically it means savvy Bargain-spec characters get better deals everywhere, including player shops. The roll goes through `perform_skill_check()` as always.

**Buy orders** (Tier 3 only): The owner can post "Wanted: 5x Metal, quality 70+, paying 80cr each." Other players can fill the order by selling to the droid. This creates demand signals — crafters can see what the market wants.

### 2.2 Droid Object Model

Vendor droids are stored in the existing `objects` table with `type = 'vendor_droid'`. The droid's configuration and inventory live in the object's `attributes` JSON blob:

```json
{
    "type": "vendor_droid",
    "tier": 2,
    "owner_id": 42,
    "owner_name": "Kaylee Voss",
    "shop_name": "Voss Custom Arms",
    "shop_desc": "Quality custom blasters. Satisfaction guaranteed or your money back (no refunds).",
    "bargain_dice": "2D",
    "max_slots": 25,
    "listing_fee_pct": 1.5,
    "placed_room_id": 7,
    "inventory": [
        {
            "slot": 1,
            "item_key": "blaster_pistol",
            "item_name": "Blaster Pistol (Basic)",
            "crafter": "Kaylee Voss",
            "quality": 78,
            "condition": 100,
            "max_condition": 120,
            "price": 650,
            "quantity": 3,
            "item_data": { ... }
        }
    ],
    "buy_orders": [
        {
            "order_id": 1,
            "resource_type": "metal",
            "min_quality": 60,
            "quantity_wanted": 10,
            "price_per_unit": 75,
            "quantity_filled": 3
        }
    ],
    "escrow_credits": 0,
    "total_sales": 0,
    "total_revenue": 0,
    "created_at": 1712700000.0
}
```

### 2.3 Droid Placement Rules

- A vendor droid can be placed in any room that is NOT: a ship interior, a tutorial room, a wilderness/outdoor combat zone, or a room flagged `no_commerce`.
- Maximum **2 vendor droids per room** to prevent clutter. First-come, first-served.
- Maximum **3 vendor droids per character** across all rooms/planets. Prevents monopoly.
- Placed droids appear in the room description when players `look`, listed after NPCs.
- A droid left in a room with no sales for 30 days gets an owner notification. After 60 days of no sales AND no owner interaction, it auto-recalls to the owner's inventory (prevents abandoned droids cluttering the world).

---

## 3. Shop Commands

### 3.1 Owner Commands

| Command | Aliases | Function |
|---------|---------|----------|
| `shop buy droid <tier>` | — | Purchase a vendor droid from an NPC droid dealer |
| `shop place` | `shop deploy` | Place a droid from inventory into the current room |
| `shop recall` | `shop pickup` | Recall your droid from the current room to inventory |
| `shop name <text>` | — | Set your shop's display name |
| `shop desc <text>` | — | Set your shop's description/tagline |
| `shop stock <item> <price> [quantity]` | `shop add` | Move item(s) from your inventory to the droid's stock |
| `shop unstock <slot#> [quantity]` | `shop remove` | Move item(s) from droid stock back to your inventory |
| `shop price <slot#> <new_price>` | — | Change the price on a stocked item |
| `shop restock <slot#> <quantity>` | — | Add more of the same item from inventory |
| `shop order <resource> <quality> <qty> <price>` | — | Post a buy order (Tier 3 only) |
| `shop cancel <order_id>` | — | Cancel a buy order (refunds remaining escrow) |
| `shop sales` | `shop log` | View recent sales history |
| `shop collect` | `shop withdraw` | Collect accumulated sales revenue from the droid |
| `+shop` | `shopinfo` | View your droid(s) status, revenue, inventory summary |

### 3.2 Buyer Commands

| Command | Function |
|---------|----------|
| `browse` | List all vendor droids in the current room |
| `browse <droid/shop name>` | View a specific droid's inventory with prices |
| `buy <item> from <shop>` | Purchase an item from a vendor droid |
| `sell <resource> to <shop>` | Fill a buy order at a vendor droid (Tier 3 only) |

The `buy` and `sell` commands already exist for NPC vendors. The parser extension recognizes the `from <shop>` / `to <shop>` suffix and routes to the vendor droid handler instead of the NPC handler.

### 3.3 Admin Commands

| Command | Function |
|---------|----------|
| `@shop list [planet]` | List all active vendor droids |
| `@shop inspect <owner>` | View full droid details |
| `@shop remove <droid_id>` | Force-remove a droid (admin moderation) |
| `@shop limit <player> <max>` | Override droid limit for a player |

---

## 4. Buyer Experience

### 4.1 Browsing

```
> browse

  ══════════════════════════════════════════
   VENDOR DROIDS — Mos Eisley Market
  ══════════════════════════════════════════
   [GN-7] Voss Custom Arms
          Owner: Kaylee Voss
          "Quality custom blasters. Satisfaction guaranteed."
          8 items in stock
   
   [GN-4] Bantha Surplus
          Owner: Rex Dalton
          "Used gear, fair prices."
          4 items in stock
  ──────────────────────────────────────────
   Type 'browse <shop name>' to see inventory.
```

```
> browse voss

  ══════════════════════════════════════════
   Voss Custom Arms — Inventory
   Owner: Kaylee Voss  |  Droid: GN-7 Merchant
  ══════════════════════════════════════════
   #  Item                        Qty  Qual  Cond   Price
   ─────────────────────────────────────────────────────────
   1  Blaster Pistol (Basic)       3    78   100%   650cr
   2  Blaster Rifle                1    85   100%   1,800cr
   3  Heavy Vibroblade             2    72   100%   900cr
   4  Medpac (Basic)               8    65   100%   55cr
   5  Medpac (Advanced)            4    80   100%   180cr
   ─────────────────────────────────────────────────────────
   [WANTED]
   W1 Metal (quality 60+)     7 more needed    75cr/unit
  ──────────────────────────────────────────
   Type 'buy <item> from voss' to purchase.
   Type 'sell <resource> to voss' to fill an order.
```

### 4.2 Purchasing

```
> buy blaster pistol from voss

  A GN-7 Merchant Droid whirs to life.
  "Ah, a fine choice! Kaylee Voss crafts excellent work."
  
  [Bargain Check: Your Bargain 3D vs. Droid 2D]
  You roll: 14  |  Droid rolls: 8
  Your sharp haggling earns a 5% discount!
  
  Blaster Pistol (Basic) — Quality 78 — 617cr (was 650cr)
  
  Purchase confirmed. 617 credits deducted.
  Item added to your inventory.
```

If the buyer's Bargain roll loses or ties, they pay full listed price — no penalty, just no discount. The droid never charges *more* than listed. This keeps the system predictable for sellers while rewarding skilled buyers.

### 4.3 Filling Buy Orders

```
> sell metal to voss

  Voss Custom Arms is buying: Metal (quality 60+) — 75cr/unit
  You have: Metal x12, quality 68
  
  Sell how many? (max 7 needed): 7
  
  Sale confirmed. 525 credits received.
  7x Metal transferred to Voss Custom Arms.
```

Credits for buy order fills come from the owner's escrow (deposited when the order was placed). If the escrow runs out, the order goes inactive until the owner adds more.

---

## 5. Economic Integration

### 5.1 Pricing Dynamics

Player shops exist in a three-layer market:

**NPC buy-back (floor):** Kayson buys crafted weapons at `base_cost × (quality/100) × 1.5`. A quality-70 blaster pistol sells to Kayson for ~525cr. No player would price below this — they'd just sell to the NPC.

**Player shop (middle):** The crafter prices above NPC buy-back but below NPC retail. A quality-70 blaster pistol might list at 600-700cr in a player shop. The buyer gets a better price than the NPC shop; the seller gets more than NPC buy-back. Both win.

**NPC retail (ceiling):** Kayson sells a stock blaster pistol (no crafter name, quality ~50) for the full 500cr base price. Player-crafted items at higher quality justify higher prices, but the NPC sets the baseline for "generic" gear.

This creates a healthy spread: crafters are incentivized to make quality items, price them competitively, and sell through their shops. Buyers are incentivized to check player shops before buying from NPCs.

### 5.2 Credit Flow

```
Buyer pays 650cr for a blaster
  → 1.5% listing fee: 9.75cr (rounded to 10cr) → DESTROYED (credit sink)
  → 640cr → Droid escrow (owner collects with 'shop collect')
```

Revenue sits in the droid's escrow until the owner collects it. This prevents instant-gratification farming — the owner has to actively manage their business. (The droid doesn't auto-deposit because the player might have droids on different planets and want to manage funds per-shop.)

### 5.3 Interaction with Existing Systems

**Crafting pipeline:** Player crafts item → stocks in shop → buyer purchases → crafter profits. The full loop from resource to revenue.

**Item durability:** Used items can be sold in shops at reduced prices. Condition is visible in the browse display. This creates a second-hand market and gives combat characters a way to recoup value from worn gear.

**Faction vendors:** Faction-exclusive gear CANNOT be sold in player shops (flagged `faction_issued` in item data). This preserves the exclusivity of faction equipment from the organizations design.

**Director AI:** The Director can read aggregate shop data (total active shops, average prices, sales velocity) for economic monitoring. The `@economy` admin dashboard would include a shop summary. The Director never manipulates player shop prices or inventory.

**Speculative trading:** Bulk cargo (from the trade goods system) cannot be sold through vendor droids — cargo is ship-hold quantities, not personal items. Vendor droids deal in equipment, consumables, and crafting resources.

### 5.4 Transaction Logging

All vendor droid transactions are logged to a new `shop_transactions` table:

```sql
CREATE TABLE IF NOT EXISTS shop_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    droid_id    INTEGER NOT NULL,
    seller_id   INTEGER NOT NULL,    -- shop owner
    buyer_id    INTEGER NOT NULL,    -- purchasing character
    item_key    TEXT    NOT NULL,
    item_name   TEXT    NOT NULL,
    quality     INTEGER DEFAULT 0,
    quantity    INTEGER DEFAULT 1,
    unit_price  INTEGER NOT NULL,
    total_price INTEGER NOT NULL,
    listing_fee INTEGER DEFAULT 0,
    txn_type    TEXT    DEFAULT 'sale',  -- 'sale', 'buy_order_fill'
    created_at  REAL    NOT NULL,
    FOREIGN KEY (droid_id)  REFERENCES objects(id),
    FOREIGN KEY (seller_id) REFERENCES characters(id),
    FOREIGN KEY (buyer_id)  REFERENCES characters(id)
);
```

This feeds the `shop sales` command (per-owner) and the `@economy` admin dashboard (aggregate).

---

## 6. Droid Purchase & Upgrades

### 6.1 Where to Buy

A new NPC droid dealer is added to each planet's commercial hub:

| Planet | NPC | Room |
|--------|-----|------|
| Tatooine | Rik Tano (Jawa droid dealer) | Mos Eisley Market |
| Nar Shaddaa | Unit-77 (droid vendor droid — yes, a droid that sells droids) | Promenade |
| Corellia | Fen Solari (Corellian merchant) | Coronet City Market |
| Kessel | — (no vendor droids available — Kessel is too lawless) | — |

`talk` to the NPC → choose tier → confirm purchase → droid added to inventory.

### 6.2 Upgrades

Owners can upgrade a droid from Tier 1→2 or Tier 2→3 at the droid dealer. Cost is the difference between tiers. Inventory carries over. The droid must be recalled (not placed) to upgrade.

```
> talk rik
  "Looking to upgrade your droid? Ah, a GN-4. Fine unit, but 
   the GN-7 has a real Bargain processor — it'll negotiate for
   you! Upgrade cost: 3,000 credits. Interested?"
```

### 6.3 Droid Maintenance

Vendor droids don't break or require maintenance. They're durable goods — you buy once, use forever. This is a deliberate simplification. The purchase price and per-sale listing fee are sufficient credit sinks. Adding maintenance would punish casual crafters who don't log in daily.

---

## 7. Anti-Exploit Measures

### 7.1 Price Manipulation

**Floor enforcement:** Items cannot be listed below 50% of their NPC buy-back value. This prevents credit laundering (listing a 1,000cr item for 1cr to transfer wealth).

**Ceiling:** No maximum price. If someone wants to list a quality-95 experimental blaster rifle for 50,000cr, that's their right. The market will decide.

### 7.2 Alt Farming

**Same-account restriction:** Characters on the same account cannot buy from each other's shops. The system checks `account_id` on both sides of the transaction.

**Transaction velocity cap:** A single buyer can purchase at most 10 items per hour from the same shop. Prevents bot-like bulk purchasing.

### 7.3 Shop Spam

**Room limit:** 2 droids per room max.

**Character limit:** 3 droids per character max.

**Naming filter:** Shop names run through the same content filter as character names. No offensive shop names.

### 7.4 Escrow Safety

Buy order escrow is held in the droid's `escrow_credits` field, *not* in the owner's wallet. If the owner goes offline, the escrow still pays out to sellers who fill orders. If the owner deletes their character, escrow is returned to their account balance before deletion.

---

## 8. Web Client Integration

### 8.1 Browse Panel

When a player enters a room with vendor droids, the web sidebar gains a "Shops" tab (similar to the combat sidebar panel). Clicking a shop opens an inventory view with item details, quality indicators (color-coded), and a "Buy" button.

### 8.2 Owner Dashboard

The `+shop` command on web renders as a management panel: revenue graph, inventory status per droid, recent sales feed. This is pure visual convenience — the same data is available via text commands.

### 8.3 Telnet Parity

All shop interactions work identically on Telnet. The `browse` and `buy` commands produce formatted ANSI text output. No web-only features.

---

## 9. Implementation Plan

### Drop 1: Vendor Droid Core
- `shop buy droid`, `shop place`, `shop recall`
- Droid appears in `look` output
- `browse` command (room-level and shop-level)
- DB: vendor droid object creation in `objects` table
- **Files:** `parser/shop_commands.py` (new), `engine/vendor_droids.py` (new)

### Drop 2: Stocking & Selling
- `shop stock`, `shop unstock`, `shop price`, `shop restock`
- `buy <item> from <shop>` with Bargain check
- Listing fee deduction, escrow accumulation
- `shop collect`, `shop sales`
- Transaction logging to `shop_transactions` table
- **Files:** `engine/vendor_droids.py` extended, `parser/builtin_commands.py` (extend BuyCommand)

### Drop 3: Buy Orders (Tier 3)
- `shop order`, `shop cancel`
- `sell <resource> to <shop>`
- Escrow deposit/refund logic
- **Files:** `engine/vendor_droids.py` extended

### Drop 4: NPC Dealers & Upgrades
- Droid dealer NPCs added to `PLANET_NPCS`
- `talk` integration for droid purchase/upgrade
- `+shop` owner dashboard
- Admin commands: `@shop list`, `@shop inspect`, `@shop remove`
- **Files:** `engine/npc_loader.py` (add dealers), `parser/shop_commands.py` extended

### Drop 5: Web Client & Polish
- Sidebar shop browse panel
- Owner management panel
- Auto-recall for abandoned droids (tick loop)
- Abandoned droid notification
- `@economy` dashboard shop integration

---

## 10. Database Changes

**Schema version:** v9 → v10 (or wherever the org system lands)

**New table:** `shop_transactions` (see §5.4)

**Objects table usage:** Vendor droids use the existing `objects` table. No schema change needed — the `attributes` JSON blob holds all droid-specific data. The `objects` table already has `owner_id`, `room_id`, `type` fields.

If the `objects` table doesn't currently have an `owner_id` column, one is added:

```sql
ALTER TABLE objects ADD COLUMN owner_id INTEGER DEFAULT NULL
    REFERENCES characters(id);
```

---

## 11. Files Modified/Created

| File | Change |
|------|--------|
| `engine/vendor_droids.py` | **NEW** — Droid lifecycle, inventory ops, transaction logic |
| `parser/shop_commands.py` | **NEW** — All `shop` commands + `browse` |
| `parser/builtin_commands.py` | Extend `BuyCommand` and `SellCommand` for `from/to <shop>` |
| `engine/npc_loader.py` | Add droid dealer NPCs to `PLANET_NPCS` |
| `data/vendor_droids.yaml` | **NEW** — Droid tier definitions (cost, slots, fee, bargain dice) |
| `db/database.py` | Add `shop_transactions` table creation, object owner_id migration |
| `static/client.html` | Shop browse sidebar panel, owner dashboard |
| `game_server.py` | Register shop commands, droid auto-recall tick |

---

## 12. Open Questions

1. **Should crafted items show the crafter's name in the shop listing?** Recommendation: Yes. This is free advertising and builds crafter reputation. "Blaster Pistol by Kaylee Voss, quality 78" is more compelling than an anonymous listing.

2. **Should shops support consignment?** (Player A stocks items in Player B's shop, revenue splits.) This adds social depth but significant complexity. Recommendation: Defer to v2. The current design supports one owner per droid.

3. **Droid destruction in combat?** If someone attacks a room with a vendor droid, can the droid be destroyed? Recommendation: Droids are non-targetable objects, like furniture. They're bolted to the floor. PvP shop raiding is a cool concept but belongs in a future "crime" system with security droids and insurance.

4. **Galactic marketplace?** A cross-planet search command (`market search <item>`) that shows listings across all planets? Recommendation: Defer to v2. For now, players must physically visit shops. This encourages travel and foot traffic, which generates RP encounters.

5. **Tax for faction-controlled zones?** If the Empire controls a zone, should Imperial shops get a tax break and Rebel shops pay extra? This ties into the Director AI zone influence system. Recommendation: Yes, but defer until the organizations system is live. The Director could adjust listing fees based on zone faction alignment.

6. **Shop rating system?** Buyers can rate shops? Recommendation: No. Too easily gamed, and in a small playerbase it creates social friction. Let quality and price speak for themselves.
