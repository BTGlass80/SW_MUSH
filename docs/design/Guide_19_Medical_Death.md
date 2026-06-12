# SW_MUSH Detailed Systems Guide #19
# Medical & Death

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide covers what happens when your character gets hurt, treated, or killed. It's the **survivability layer** — wounds, healing, stims, corpses, respawn, the wound-state debuff, and how all of these compose together in extended play.

You'll touch this system often. Combat (Guide #3) leaves characters wounded most of the time. Hazards (Guide #24, forthcoming) chip at characters in dangerous zones. Force-power use (Guide #8) interacts with healing. The death loop (Guide #4 — Security Zones) is the consequence layer underneath it all. Knowing how the medical system works is knowing how to **stay in play** through setbacks.

If you only have ten minutes, read **§1 The Wound Ladder** and **§3 Getting Healed**. The rest covers depth: stims, the death loop, recovery strategy.

This is a new guide. There was no earlier version.

---

## 1. The Wound Ladder

Your character's physical state is tracked by a **wound level** — a step on a ladder from "perfectly fine" to "permanently dead." Every dice penalty, every recovery rule, every healing target keys to this ladder.

| Level | Name | Penalty | Can Act? |
|---|---|---|---|
| 0 | **Healthy** | none | yes |
| 1 | **Stunned** | −1D per stun timer | yes |
| 2 | **Wounded** | −1D | yes |
| 3 | **Wounded Twice** | −2D | yes |
| 4 | **Incapacitated** | (out) | **no** |
| 5 | **Mortally Wounded** | (bleeding) | no |
| 6 | **Dead** | — | — |

You move up the ladder when you take damage; you move down when you heal. Each step has its own implications:

**Healthy.** Default state. No penalties to your dice rolls. Your `+sheet` shows "Healthy."

**Stunned.** Temporary fog from a glancing blow or shock. Each stun-result against you adds a stun timer that lasts a few rounds (typically 2). While the timer is active, you have **−1D per timer** on all rolls. Multiple stuns stack: three concurrent stun timers means −3D for the duration. Stun timers expire one at a time as rounds tick; they're the only wound-level penalty that automatically lifts without intervention.

**Wounded.** Real injury. A blaster bolt through the leg, a heavy melee strike, a serious fall. **−1D to all rolls** until healed. Lasts until removed by treatment.

**Wounded Twice.** Cumulative damage past the first wound. **−2D to all rolls**. Still able to act, but at significant cost. Many fights end here — characters at Wounded Twice often flee rather than risk Incapacitation.

**Incapacitated.** Unconscious. You cannot act. Your character is out of the scene mechanically — they can't attack, defend, move, or respond. Any further damage typically pushes you to Mortally Wounded. Other characters can stabilize you (move you to a med-droid, administer treatment), but you can't do anything yourself.

**Mortally Wounded.** Bleeding out. Each round, the engine rolls a death check — if it fails, you progress to Dead. Without intervention (someone healing you, applying bacta, etc.), most Mortally Wounded characters die within 3-5 rounds. This is the "save them quickly" tier.

**Dead.** Your character has died. The corpse persists at the death location (see §4); you respawn at a safe location (see §5). Some Force-sensitive characters (with Remain Conscious or similar powers) can stretch the boundary briefly, but ultimately the death is real.

The cumulative wound effect can hit fast. A skilled character in a sustained fight against multiple opponents might go from Healthy → Stunned → Wounded → Wounded Twice → Incapacitated across 4-6 rounds. The penalty accumulates as you fight, making each subsequent action harder.

---

## 2. Where Wounds Come From

The main sources:

**Combat damage (Guide #3).** Each successful attack against you that gets past your soak roll adds a wound. The amount depends on damage vs. your soak — clean blaster hits typically inflict Wounded; explosions and high-damage weapons can inflict Incapacitated in one shot.

**Hazards (Guide #24, forthcoming).** Extreme heat, toxic atmosphere, radiation. These tick periodically (every 5 minutes) and apply debuffs (Dehydration, Toxic Exposure, Radiation Sickness) that can escalate into wound-level damage with prolonged exposure.

**Failed adrenaline shots.** Treating someone with an adrenaline shot that fails the Medicine check **inflicts a wound** on the target — the chemistry went wrong. Be very careful who you give an adrenaline shot to.

**Spice and addictive substances.** Heavy spice use over time can damage Strength and apply long-term debuffs that interact with wound-soak rolls.

**Force powers.** Injure/Kill (Guide #8) does damage. Using Affect Mind in extended sequence is rough on the target.

**Environmental.** Falls, drowning, vehicular accidents in space combat (your ship blowing up while you're aboard). The engine has miscellaneous damage types beyond direct combat.

---

## 3. Getting Healed

There are several paths to recovery, each at different cost and consequence.

### Player-to-player healing (`heal`)

```
heal <player>
```

If you have **First Aid or Medicine skill**, you can offer to heal another player in the same room. The target must type `healaccept` to consent.

The mechanics:
- **Roll**: Your First Aid (or Medicine) skill vs. a difficulty based on the target's wound level.
- **Pay**: The target pays your **heal rate** (set with `+healrate`, default 200 cr). You collect the credits on success.
- **Effect**: On success, the target's wound level drops by one step.

Difficulty by wound level:

| Target's Wound Level | Difficulty |
|---|---|
| Stunned | Easy (8) |
| Wounded | Moderate (11) |
| Wounded Twice | Moderate+ (14) |
| Incapacitated | Difficult (16) |
| Mortally Wounded | Very Difficult (21) |
| Dead | Beyond medical help |

Each level higher is harder. A medic treating Stunned has it easy; treating Mortally Wounded is genuine work, often requiring CP burns or Force Points to push the roll. Players who specialize in First Aid or Medicine at 5D+ can reliably heal across the ladder; lower-skill characters can handle stunned and Wounded but struggle with the upper tiers.

**Setting your rate:**

```
+healrate <amount>
```

Updates the per-treatment cost. Heal rates vary from 100 cr (charity / new medic) to 500+ cr (premium specialist). Most active medics charge 200-300 cr per treatment. The market sets the rate; your skill and reputation determine where you sit in it.

**Why payment?** It's the in-game compensation for medics. A medic-character can make a real living healing wounded fighters and missioneers. The fee is also how the engine prevents free constant healing exploits — every heal costs the recipient, so they have to choose when to spend.

### Stims (`stim`)

Stims are **consumable buffs** that medics administer in the same way as heal, but instead of reducing wound levels they apply a temporary stat boost.

```
stim <player>                                — Default stimpack
stim <player> with adrenaline_shot           — Adrenaline shot variant
stim <player> with combat_stim               — Combat stim variant
stim <player> with focus_stim                — Focus stim variant
```

The target consents via `stimaccept`.

| Stim | Skill | Difficulty | Effect |
|---|---|---|---|
| **Stimpack** | First Aid | Easy (10) | +1D Strength for one roll |
| **Adrenaline Shot** | Medicine | Moderate (15) | +1D Strength, sustained |
| **Combat Stim** | Medicine | Difficult (20) | +1D Dexterity for 5 min |
| **Focus Stim** | Medicine | Moderate (15) | +1D Knowledge for one roll |

**Stimpack** is the everyday combat utility — administered before a fight to push the soak roll. Easy to get right.

**Adrenaline shot** is harder. On failure (not fumble), it **inflicts a wound** on the target. Don't try adrenaline shots with low Medicine skill. Self-administration is blocked.

**Combat stim** is the most powerful but the hardest. +1D Dexterity is significant for a combat character. On failure, the target gets the Intimidated debuff (jitter) instead. Self-administration is blocked.

**Focus stim** is the social/intel application — boosts Knowledge for negotiations, slicing, investigations. Self-administration is allowed (you can focus-stim yourself before a key roll).

Stims **stack with** healing. A medic can heal a wound and apply a stimpack in the same exchange — the patient walks away wounded-less and Strength-buffed.

### Bacta tank (`bacta`)

```
bacta
```

The medical-droid-administered treatment. You walk into a med-droid's room (typical urban room — there's one in every cantina and spaceport), type `bacta`, and pay **500 cr**. The bacta tank:

- **Clears your wound-state debuff** (the post-death −1D — see §5).
- Does **not** clear current wound levels (Wounded, Wounded Twice, etc.). Those need actual healing.

Bacta tank is specifically for the **post-death wound-state debuff**. If you died and respawned, you have an hour of −1D until it auto-clears. Bacta clears it immediately for 500 cr. A useful cost for active players who don't want to wait.

### Bacta pack consumable

```
use bacta_pack
```

A **150 cr inventory consumable** that does the same thing as the bacta tank — clears your wound-state debuff. Less expensive per use (150 cr vs. 500 cr) but consumed each use. Crafters can produce bacta packs (Doc Vashar's schematic, Guide #7); they're sold at vendor droids and med-droids alike.

The choice between bacta pack and bacta tank is a price decision: bacta pack is cheaper per use, but you need to keep them in inventory; bacta tank requires walking to a med-droid but works on demand. Most experienced characters carry 1-3 bacta packs and use bacta tanks when they're out.

### Force-based healing

If you're Force-sensitive (Guide #8) with sufficient Control skill, you can self-heal:

```
force accelerate_healing
```

**Accelerate Healing** at Moderate (15) difficulty reduces your wound level by one step. Once per day of rest. The narrow application: when you're alone, wounded, and no medic is available, Accelerate Healing is your way out.

**Control Pain** doesn't heal — it masks the pain (and the −1D penalty) for the scene. Useful for finishing the fight you're in; not useful for actual recovery. The wound returns when the scene ends.

---

## 4. The Death Loop

When you take enough damage to die, the **death loop** activates.

### What happens at death

1. **WoundLevel transitions to DEAD.**
2. **The on_pc_death hook fires.** This determines what happens next based on the security tier of the death location.
3. **Your inventory snapshots onto a corpse.** All carried items move from your character to the corpse row in the database. Your equipped weapon stays equipped on the corpse. Your credits **stay with you** (they're not transferred to the corpse).
4. **A corpse is created at the death location** — unless you died in a secured zone, in which case no corpse and you instant-respawn with all gear.
5. **Your `wound_state` is set to `wounded`** for 1 hour real-time. This is the **post-death debuff**: −1D to all rolls, separate from the in-combat wound ladder.
6. **You're moved to a safe respawn location** — typically the nearest cantina or medical center. The engine picks the destination based on where you died.
7. **A "blackout" message displays.** Then the respawn message. You're alive again, in a new location, wounded, and your gear is back at the death site.

### The corpse persistence

Corpses persist for a security-dependent duration:

| Security Tier | Corpse Decay |
|---|---|
| Secured | (no corpse — instant respawn with gear) |
| Contested | 2 hours |
| Lawless | 4 hours |

During the persistence window, the corpse exists as a lootable object at the death location. Anyone in the room can:

```
look corpse                   — Examine the corpse and see what's on it
loot <item> from corpse       — Take a specific item
loot all from corpse          — Take everything
```

The looting check has some friction. Bound items (Guide #19 — character-bound items that can't be looted) return to the owner automatically. Unbound items can be taken by anyone — fighters who killed you, third-party looters, your own friends who arrive to retrieve your gear.

**After the decay window**, the corpse and any unlooted items are gone permanently. Items bound to you may return automatically (the system tracks owner-bound items and tries to deliver them on decay).

### The respawn

You respawn at a **safe location** — never in combat, never in a hostile zone. The engine picks the closest safe room. From Mos Eisley combat zones, you typically respawn at the cantina. From Nar Shaddaa, you respawn at the BHG chapter house or the safehouse. From wilderness, the closest connected town's cantina.

**You retain:** your credits, your bank balance, your character data, your faction reputation, your skills, your CP, your achievements, your active quests. Death doesn't erase progress.

**You lose:** access to your gear (which is back at the death site, slowly decaying), 1 hour of effective performance (the wound-state debuff), and the time it takes to travel back to recover your gear (if you choose to).

### The wound-state debuff

The `wound_state = wounded` field is **separate from** the in-combat WoundLevel. It applies a flat **−1D penalty** to all your dice rolls for 1 real-time hour (3,600 seconds) after death. This stacks with normal wound penalties.

You can clear it three ways:
- **Wait it out.** 1 hour after death, the debuff auto-clears.
- **Bacta tank.** 500 cr at a med-droid. Immediate clear.
- **Bacta pack consumable.** 150 cr; consumes the item. Immediate clear.

Most active players bacta-tank within minutes of respawning. The cost is small relative to play loss; an hour of −1D is a long time to take suboptimal rolls.

### Recovering your gear

```
travel <to-death-location>          — Get back to where you died
look corpse                         — See what's still there
loot <items>                        — Take them back
```

If you can reach the corpse before decay (2 hours contested, 4 hours lawless), and if other players haven't looted it, your gear is yours. The race against time and against potential looters is the gear-recovery game.

**If you can't reach the corpse in time**, your gear is gone. This is the genuine cost of death in lawless zones — fail to recover, and you've lost everything you were carrying.

---

## 5. Recovery Strategy

How active characters manage the medical layer:

**Carry stimpacks and bacta packs always.** A character with 0 inventory medical items is fragile. 3-5 stimpacks (for combat utility) and 2-3 bacta packs (for post-death debuff clearance) is a reasonable minimum.

**Know which medics are around.** Active medics in your community have rates and schedules. Pay attention to who's online and what they charge. A good medic in the cantina is an emergency resource.

**Buy from vendor droids.** Many shopfronts (Guide #17) stock medical consumables. Build a habit of checking medical-focused shops as part of your loadout routine.

**Don't carry valuables into lawless when you don't have to.** This is the biggest preventable medical-loss scenario: dying in lawless wilderness with expensive gear on. The corpse decay is 4 hours, and other players may loot before you can return. Carry your minimum loadout into risky terrain.

**Use the wound-state cost realistically.** If you're going to die in a contested zone with 50 cr of cargo, don't bacta-tank for 500 cr to clear the debuff. The math doesn't work. Wait the hour, play through the −1D.

**Pre-fight: stim up.** Before a known-dangerous combat (a PvP duel, a Veteran-tier bounty), have a medic combat-stim you. The +1D Dexterity makes a real difference in a tight fight.

**Mid-fight: be aware of your tier.** A Wounded character should be looking for the exit. A Wounded Twice character should be running. Once you're Incapacitated, you can't decide anything; your friends have to drag you out.

**Post-respawn: pace yourself.** The hour after death is a recovery hour. Don't immediately jump into another fight. Let the wound-state clear (or bacta it). Re-equip. Plan the next move calmly. The system rewards patience.

---

## 6. The Medic Profession

For players who want to specialize as medics — the doctor / field medic / Force healer archetype — the system supports a real economic niche.

### Building a medic character

**Attributes:** High Technical (medic skills live here) and reasonable Knowledge. Dexterity matters less unless you also want to be combat-active.

**Skills:** First Aid at 4D+ for routine work. Medicine at 5D+ for the harder stims. Stamina for personal survivability. Persuasion for negotiating with patients.

**Force-sensitive medics** add Control 4D+ for Accelerate Healing (self-heals + others through extended scene work). This is the most powerful medic build — Force healing + technical First Aid covers all wound tiers.

### The economics

A medic charging 200 cr per heal can do roughly 10-20 heals per session of active cantina presence. That's 2,000-4,000 cr per session, with no risk and no inventory cost. The income is reliable and meaningful — comparable to mid-tier mission running.

Medics also sell consumables. Crafted stimpacks and bacta packs through a vendor droid (Guide #17) generate passive revenue. A medic-shopfront with consistent stim and bacta stock is a high-traffic shop.

### The social position

Medics are **socially valuable**. Players seek you out when they're hurt. Faction members in war zones rely on you. Your reputation in the medic community matters; players remember who saved them, who charged fairly, who refused to heal them when they couldn't pay.

Many medics build extensive networks. The cantina medic everyone knows. The Republic field surgeon attached to a unit. The Hutt-aligned spice clinic that asks fewer questions. Your medic identity shapes your social position as much as any other archetype.

---

## 7. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — Routine combat patch-up.** You finish a mission Wounded (one wound). You walk to the Mos Eisley cantina. The cantina has a medic, Sila Vannik, charging 200 cr per heal. You `heal accept` her offer. She rolls First Aid 4D vs. Moderate 11 — easy success. Your wound level drops to Healthy. You pay 200 cr. Total time: 2 minutes. You're ready for the next thing.

**Scenario 2 — Mid-fight stim.** You're in a tough fight against three bandits. Your medic friend, in the same room, casts `stim <you> with combat_stim`. You consent via `stimaccept`. She rolls Medicine 5D+1 vs. Difficult 20 — passes with margin. You gain +1D Dexterity for 5 minutes. The fight tilts in your favor with the extra dice; you finish without taking another wound.

**Scenario 3 — Death in the Dune Sea.** You're hunting bandits in the Dune Sea (lawless). They're tougher than expected. You get Wounded → Wounded Twice → Incapacitated → dead. Corpse drops at your tile (`(20, 15)` in the Dune Sea). 2,000 cr of glitterstim cargo on your corpse. You respawn at Mos Eisley cantina with `wound_state = wounded`. You travel back to the Dune Sea (45 minutes real-time of overland traversal). When you arrive, your corpse is still there — no other player found it — and you loot all your items. The 2,000-cr cargo is yours. Total loss: 2 hours of play and 500 cr for a bacta tank (you don't carry packs). Not great, but recovered.

**Scenario 4 — Death in Coruscant Underworld with looters.** You're in a contested room of the underworld. Two PvP-flagged hunters challenge you and accept. You die in the fight. Corpse drops at the underworld room. Your blaster and 8,000 cr of equipment are on the corpse. The hunters loot it immediately. You respawn at the Coruscant central hub, wounded-state debuffed. The hour passes; the debuff clears. But your blaster is gone — you'll need to buy a new one (3,000 cr) and resign yourself to the cargo loss. Total impact: 11,000 cr in actual loss. The hunter takes a payout from your death; the system enforces the consequence.

**Scenario 5 — The Force healer.** You're a Padawan with Control 4D and Accelerate Healing learned. After a tough day-night cycle, you're Wounded Twice. You retreat to a safe Tier 3 home for rest. You use `force accelerate_healing` on yourself. The roll succeeds; you drop to Wounded. The "once per day of rest" gate prevents you from healing further today. You sleep through the next day-rest cycle and wake up Wounded; next session, you Accelerate Healing again to Healthy. Force healing is slow but cost-free.

---

## 8. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `heal <player>` | Offer to heal a player (they accept via `healaccept`) |
| `healaccept` | Accept a pending heal offer |
| `+healrate <amount>` | Set your healing rate (default 200 cr) |
| `stim <player>` | Administer stimpack (default) |
| `stim <player> with adrenaline_shot` | Administer adrenaline shot |
| `stim <player> with combat_stim` | Administer combat stim |
| `stim <player> with focus_stim` | Administer focus stim |
| `stimaccept` | Accept a pending stim offer |
| `bacta` | Pay 500 cr at a med-droid; clears wound-state debuff |
| `use bacta_pack` | Use a bacta pack from inventory; clears wound-state debuff |
| `respawn` (or `revive`) | Return from death (works only when dead) |
| `loot <item> from corpse` | Take a specific item from a nearby corpse |
| `loot all from corpse` | Take everything from a corpse |
| `look corpse` | Examine a corpse without taking anything |
| `force accelerate_healing` | Force-sensitive: heal one wound level (1/day) |
| `force control_pain` | Force-sensitive: mask wound penalties for the scene |
| `+sheet` | View character sheet (includes wound level and wound_state) |
| `+medical` | Medical dashboard / status |

---

## 9. Numbers At A Glance

| Quantity | Value |
|---|---|
| Wound levels | 7 (Healthy through Dead) |
| Default heal rate | 200 cr |
| Stimpack difficulty | Easy (10) |
| Adrenaline shot difficulty | Moderate (15) |
| Combat stim difficulty | Difficult (20) |
| Focus stim difficulty | Moderate (15) |
| Heal difficulty — Stunned | Easy (8) |
| Heal difficulty — Wounded | Moderate (11) |
| Heal difficulty — Wounded Twice | 14 |
| Heal difficulty — Incapacitated | Difficult (16) |
| Heal difficulty — Mortally Wounded | Very Difficult (21) |
| Bacta tank cost | 500 cr |
| Bacta pack cost | 150 cr (inventory consumable) |
| Wound-state debuff | −1D for 1 real-time hour after death |
| Corpse decay — Secured | (no corpse, instant respawn) |
| Corpse decay — Contested | 2 hours |
| Corpse decay — Lawless | 4 hours |
| Accelerate Healing cooldown | once per day of rest |
| Adrenaline shot failure consequence | +1 wound level on target |
| Hazard check interval | 5 minutes (300 seconds) |

---

## 10. Common Pitfalls

**1. Trying to heal yourself.** The `heal` command requires a target player who isn't you. Self-healing comes from bacta, bacta packs, or Force powers. The system enforces this — characters can't medic themselves up casually.

**2. Adrenaline shot at low Medicine.** Adrenaline shot at Medicine 2D vs. difficulty 15 fails 60-70% of the time, and each failure inflicts a wound on the target. Don't try adrenaline shots until your Medicine is 4D+.

**3. Bacta-tanking when the debuff is about to clear.** Bacta-tanking at minute 55 of a 60-minute timer for 500 cr is wasteful. Check `+sheet` to see how much wound-state time is left; if it's under 10 minutes, wait it out.

**4. Carrying expensive gear into lawless without backup.** Death in lawless = 4-hour decay window. If you can't return within that window (you live elsewhere, you need to log off, you're traveling far), other players may loot the corpse. Carry only what you can afford to lose.

**5. Forgetting that bacta packs are crafted.** They're not infinite at vendor droids; production depends on crafters. If the market is empty, you can't buy them. Stock up when supply is available.

---

## 11. A Final Word

The medical system is the safety net underneath everything dangerous in the game. Without it, every combat would be a binary "win-or-lose-everything" event. With it, combat is a tactical exchange — you take wounds, you survive them, you heal, you fight another day. The death loop is the final escalation — if you genuinely die, you lose gear and time, but you don't lose the character.

The system supports a specific kind of play: **you can engage with risk and recover from it**. The cost of failure is real (gear loss, time, wound-state debuff) but not catastrophic. Players who lean into combat and missions in lawless terrain take occasional setbacks but keep playing. Players who avoid all risk play it safe but progress slowly.

For most characters, the medical layer is **infrastructure** — you interact with it during normal play. Carry stimpacks. Visit medics. Pay 500 cr for bacta when you die. The mechanics are calibrated to be slightly painful but never punitive.

For medics, the layer is **identity**. You provide a service the community relies on. You set rates, build reputation, become known. A career medic can play for years on the strength of their healing practice alone.

If you're starting out: keep 2-3 stimpacks and 1-2 bacta packs in your inventory. When you die, bacta-tank within a few minutes. Pay attention to your wound level during combat and disengage at Wounded Twice rather than push to Incapacitated. The system rewards players who treat their character's survival as a real decision, not an afterthought.

---

*End of Guide #19 — Medical & Death*
