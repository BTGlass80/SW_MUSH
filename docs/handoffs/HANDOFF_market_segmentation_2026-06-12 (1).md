# HANDOFF — Market segmentation: the buy-verb gate
## Session 2026-06-12 (8th) · Drop 10 · Rollup: `SW_MUSH_drops1-10_rollup_2026-06-12.zip` (CUMULATIVE — supersedes ALL prior zips)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. Covers drops 1–10 at latest state.

---

## 1. The audit found the hole somewhere unexpected

The queue framed this as "vendor stock audit + grandfather-vs-withdraw." The stores that look
like stores were clean — commissary sells faction-issue keys (its blaster_pistol is band-25,
which your decision a explicitly allows at a requisition discount), and player-droid shops are
the decision's own sanctioned band-2/3 channel. The violation was the **bare `buy` verb**: its
fallthrough resolved the *entire weapon registry* by name — no stock gate, no vendor required
(haggling falls back to a generic 3D vendor in an empty room), no room gate — under a tag that
still says `ship_weapon_purchase`. Every Gundark drop silently widened that store: **the Drop G
contraband band was credit-purchasable anywhere, no Gundark needed.**

## 2. The fix

`vendor_stocked` on WeaponData, **default closed** — future rows ship off-market until someone
deliberately opens them. Exactly **11 Avail-1 commons** sell at book cost (hold-out, blaster
pistol, heavy pistol, the sporting pair, knife, vibroblade, stun baton, and the lane's Avail-1
trio). `buy` refuses everything else with the redirect — craft it, player shops, or "know the
right people." The `weapons` list keeps its full-reference job but only prices stocked rows;
unbuyables read "craft."

Worth telling you straight: **the consistency test rejected two of my own first-cut picks**
(vibroaxe and stun_pistol — both turned out to be band-40 schematic outputs) before the drop
shipped. The test that enforces "no band-40+ craft output on the open market" earned its keep
twice on day one, against me.

**Grandfather call, resolved:** nothing stocked needed withdrawing — owned items stay owned,
inventories untouched; the gate closes future purchases only.

**⚑ Windows watch #6:** `buy <anything unstocked>` now refuses. Anyone's muscle memory for
buying rifles/grenades off the open market breaks — by design.

## 3. Noted, not built (`OBS.buy_verb_followups`)

(a) `buy` still works **anywhere** — no vendor-presence or shop-room gate. Whether open commons
should require a storefront is your call; it's one conditional once decided. (b) The
`ship_weapon_purchase` tag mislabels ground buys — rename during T3.19 (ledger continuity
caveat). (c) Commissary's tracking_fob advertises "+1D to Search" with no consumer — one
`skill_bonus` field would put it on the Drop F tool seam, pending a check of how
issued/commissary items actually land.

## 4. Verification & queue

Segmentation suite 9/9 · adjacent net 174 · hygiene 9. Windows watch items now **six** across
drops 1–10 (pools jump · armor penalties live · grenades consume · gear depletes · tuition
charges · buy gates).

Queue after this: the deferred design passes — powered suits, mines/breaching,
`WEBIFY.commissary_vendor_mode`, CRAFT.HOOK passes, Lane C remainder + Lane F, Kamino, Drop-5
farming controls, `OBS.quality_and_boosts_not_combat_read`, plus the new buy-verb follow-ups.
On "continue" I'd take the **vendor-presence call + the small follow-ups (a)–(c)** as a quick
drop, or jump to a design pass if you'd rather — your pick.

## 5. Session learning

**Audit the verbs, not just the data.** Stock lists were clean because there were no stock
lists — the store was a command fallthrough nobody thought of as a store. Economy audits have
to walk every path credits can exit through, including the ones labeled as something else.
