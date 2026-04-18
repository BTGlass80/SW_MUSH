---
key: +shop
title: Shop — Vendor Droid Management & Market Browsing
category: "Commands: Economy"
summary: All shop verbs live under +shop/<switch>. Manage your vendor droid shop, browse other players' shops, or search the planetary market directory. Shop subcommands (buy, place, stock, etc.) also work as switches.
aliases: [shop, shopinfo, browse, shops, shoplist, market, mkt]
see_also: [shops, market, housing, shopfront, economy]
tags: [economy, shop, vendor, command]
access_level: 0
examples:
  - cmd: "+shop"
    description: "Shop dashboard — your vendor droid status, escrow, inventory (default)."
  - cmd: "shop"
    description: "Same as +shop (bare alias preserved)."
  - cmd: "+shop/buy droid gn4"
    description: "Buy a GN-4 vendor droid (cheap tier). Forwarded to ShopCommand positional parser."
  - cmd: "+shop/place"
    description: "Deploy your vendor droid in the current room (must be a shopfront residence)."
  - cmd: "+shop/stock Blaster Pistol 250 5"
    description: "Stock 5 Blaster Pistols at 250 cr each."
  - cmd: "+shop/collect"
    description: "Collect accumulated revenue from your droid's escrow."
  - cmd: "+shop/sales"
    description: "View recent sales log."
  - cmd: "+shop/browse Jex's Goods"
    description: "Browse another player's shop inventory."
  - cmd: "browse Jex's Goods"
    description: "Same as +shop/browse (bare alias)."
  - cmd: "+shop/market"
    description: "Search this planet's shopfront directory — lists all player shops."
  - cmd: "+shop/market tatooine"
    description: "Search a specific planet's shopfronts."
  - cmd: "market all"
    description: "Search across all planets (bare alias preserved)."
---

All shop verbs live under +shop/<switch>. Bare forms (shop, browse,
market) still work as aliases. The canonical form is +shop/<switch>;
the rest of this page uses it everywhere.

See `+help shops` for the conceptual overview of the vendor-droid
economy and shopfront residences. This page is the command reference.

SWITCH REFERENCE

  /shop      Manage your vendor droid (default — bare +shop)
  /browse    Browse another player's shop
  /market    Search the planetary shopfront directory
  /admin     Admin-only shop commands (@shop)

  /shop POSITIONAL SUBCOMMANDS (forwarded to ShopCommand):
  /buy       Purchase a vendor droid
  /place     Deploy droid in current room
  /recall    Recall droid to inventory
  /name      Set shop display name
  /desc      Set shop tagline
  /stock     Add item to shop inventory
  /unstock   Remove item from shop
  /price     Update item price
  /collect   Collect accumulated revenue
  /sales     View recent sales
  /order     Open order book
  /cancel    Cancel pending order
  /upgrade   Upgrade droid tier

VENDOR DROID TIERS

  gn4   GN-4  (cheap — small inventory, basic AI)
  gn7   GN-7  (mid — more slots, better responses)
  gn12  GN-12 (premium — max slots, full personality)

Each tier costs more credits but holds more inventory and gives
better customer responses.

THE UMBRELLA FORWARDING PATTERN (S58)

ShopCommand uses positional-argument subcommands (shop buy droid
gn4) rather than switch syntax. The +shop umbrella recognizes all
ShopCommand subcommands as switches and forwards them — so
`+shop/buy droid gn4` reaches ShopCommand as `shop buy droid gn4`
and works identically.

This forwarding is transparent — players can type either form:
  +shop/stock Blaster 250 5     (canonical)
  shop stock Blaster 250 5      (legacy bare form)
Both reach the same code.

CHEAT SHEET
  +shop                 = dashboard (also: shop)
  +shop/buy droid <t>   = buy vendor droid (also: shop buy droid <t>)
  +shop/place           = deploy droid
  +shop/stock <i> <p>   = add item to inventory
  +shop/collect         = collect revenue
  +shop/browse <name>   = browse another shop (also: browse)
  +shop/market          = planetary directory (also: market)

Sources: Vendor-droid economy is game-original (inspired by SWG
vendor droids and EVE market interface). The S58 umbrella forwards
to ShopCommand which uses standard R&E trade rules where applicable.
