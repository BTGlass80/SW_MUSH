# Dice animation + UI/UX polish (2026-06-22)

**Origin:** Brian — "what if we added animations into the UI/UX? Dice actually rolling came to
mind. Add or detract?" Verdict: **add** — dice are the single best-justified animation in the whole
game — **but** the value lives entirely in execution discipline, and the failure mode (animating every
roll, blocking on it) would make play *worse* than the text we have. This doc designs it with the
discipline baked in, and answers the crux: **how we decide which rolls are "dramatic."**

Scope: **web client only** (`static/client.html` / `static/spa/*`). Telnet is unaffected (web-first
policy). The engine change is tiny + additive: it already routes every out-of-combat roll through one
funnel and already sends the roll breakdown — we add one `drama` field.

---

## 1. Why dice are the special case (not arbitrary polish)

This is a **WEG R&E D6** game — the dice pool *is* the signature mechanic. Every skill check, combat
swing, and Force power resolves on `ND+P` with an exploding **wild die**. Animating dice isn't
decorating the game; it's animating its **identity**. Text flattens the suspense-and-reveal of a throw
into "you rolled 17 vs Moderate." For *this* ruleset, restoring the throw is on-theme, not ornamental.

It's also cheap-to-the-engine: `engine/skill_checks.py::perform_skill_check` (the mandated funnel) already
computes the roll, the wild-die explosion, and `critical_success` (`roll.exploded and success`), and the
result dict already carries `critical` + the dice breakdown. The client already has (or trivially gets)
the data to animate the **real** dice.

---

## 2. Non-negotiable rules (this is what makes it add vs detract)

Players roll **constantly** — every combat round, every search. An animation delightful once is
infuriating the 500th time. So:

1. **Never gate information or pace.** The result TEXT renders **immediately**; the dice animate in
   *parallel*, never as a barrier. The player never waits to learn if they hit.
2. **Animate dramatic rolls, not routine ones** (see §3). The 5th combat round and passive perception get
   nothing; the Force power and the killing blow get the throw.
3. **Skippable** — any click/keypress jumps straight to the result.
4. **A user toggle** — `Off / Minimal (tier-2 only) / Full`. Default Minimal-or-Full for new players;
   power users set Off. (Mirror the existing settings pattern, e.g. the `fk_clean_mode` / onboarding-tour
   localStorage flags in `client.html`.)
5. **Show the REAL dice** — your actual `4D+1` pool, the pips, and the **wild die exploding**. Generic
   dice that don't reflect the roll are hollow decoration with latency. Real dice are authentic *and*
   double as a D6 **teaching tool** for new players (ties into the NPE work — you *see* the system).

If any of 1–5 is violated, the feature detracts. If all hold, it's pure upside.

---

## 3. ⭐ Determining which rolls are "dramatic" (Brian's question)

**The wrong way:** a hardcoded list of "dramatic" command types. Brittle, doesn't generalize, and misses
that drama is a property of the **moment** (stakes + outcome), not the command.

**The right way:** compute a **`drama` tier** from signals the engine *already* has, at the dice funnel(s)
— `perform_skill_check()` (the out-of-combat funnel) and the combat resolver. Send it on the roll result.
The client animates by tier, then applies its own pace discipline.

### The signals (all already known at the funnel)
1. **The wild die** — WEG's built-in drama engine. An **exploding 6** (cascade) or a rolled **1**
   (complication) is *inherently* dramatic. This alone is a gorgeous native trigger. (`roll.exploded`
   already exists; a wild-die-1 "complication" flag is a trivial add.)
2. **Outcome significance / state change** — did the roll change something that matters? A hit that
   **incapacitates/kills**, a **Force power** that succeeds, a **contested PvP** win, a sabacc **Idiot's
   Array**, a lock **sliced open** — vs. a routine pass/fail of a search.
3. **Criticality** — already flagged in places (`critical_success` on the funnel result; sabacc crit;
   combat incapacitation). A critical success *or* failure is tier-2.
4. **Category / stakes** — Force powers, the combat-**deciding** blow (drops a foe, or would drop you),
   opposed/contested rolls (PvP), gambling, chargen/advancement. High-stakes by nature. (The funnel
   already takes a `tag`/context; combat knows the decider.)
5. **Difficulty + margin** — a **success against a hard difficulty** (Very Difficult/Heroic), or a roll
   landing **within a pip or two** of the target (a nail-biter), beats a Very-Easy pass or a blowout.
   (Difficulty + `roll - difficulty` are both in hand at the funnel.)

### The tiers (computed server-side; sent as `drama` on the roll result)
- **Tier 2 — full roll animation:** wild-die explosion or 1; any critical; a high-stakes-category roll
  that resolves a real stake (Force power, combat-decider, sabacc hand, PvP-contested, chargen); a clutch
  success vs a hard difficulty.
- **Tier 1 — quick flourish (sub-second):** a deliberate, player-initiated check that isn't routine, or
  the **first** roll of a new encounter — a brief dice flash.
- **Tier 0 — instant, no animation:** routine/repeated/ambient rolls (every *subsequent* combat round,
  passive perception, the Nth search).

### Pace discipline lives on the CLIENT (regardless of tier)
- **Rate-limit:** at most one animation per ~N seconds (tune N). The first dramatic roll in a window
  animates; a flurry behind it resolves instantly. (Combat round 1 animates; rounds 2-6 don't, even if
  "dramatic" — you're in a rhythm.)
- **Skip + toggle** per §2.
- **Result text is never delayed** per §2.

So "dramatic" is **not a guess** — it's `f(wild-die, outcome-significance, criticality, category,
difficulty+margin)` classified into tiers at the funnel, then gated by the client's rate-limit + the
player's preference. The engine already has every input; the only new server work is a small `drama`
classifier at **1–2 chokepoints** (the skill-check funnel + the combat resolver).

---

## 4. Architecture / implementation sketch

- **Engine (small, additive):** a `classify_drama(...)` helper near `perform_skill_check` returns
  `drama: 0|1|2` from the signals in §3; attach it to the existing roll-result payload (the dict that
  already carries `critical` + the breakdown). Mirror the funnel for the combat resolver's per-swing
  result. **No new top-level system; extend the funnel** (CLAUDE.md: extend-don't-add). Funnels stay the
  single source of truth, so the classification is consistent everywhere a roll happens.
- **Wire payload:** the roll message gains `{drama, dice:[…pips…], wild:[…explosion chain…], pips, target,
  result, success, critical}`. (Most of this is already sent; confirm `dice`/`wild` are present, add if not.)
- **Client:** a `renderDiceRoll(payload)` that, when `drama >= threshold AND animations enabled AND
  rate-limit ok`, plays a short dice-tumble (CSS/SVG/canvas; 3D via three.js only if we decide it's worth
  the bytes) showing the real pool + the wild die exploding, then settling on the result — while the
  result text is **already** on screen. Otherwise it no-ops (text only). A `dice-animations` setting in
  localStorage (Off/Minimal/Full) + a click-to-skip handler.
- **Test:** a jsdom click-through test (same harness as `tests/spa/test_client_onclick_exports.py`):
  a `drama:2` payload schedules an animation + the result text is present *immediately*; a `drama:0`
  payload renders text with no animation; the toggle/skip paths work; the rate-limiter suppresses a
  second animation inside the window. Plus an engine unit test pinning `classify_drama` on a matrix
  (wild-die explosion → 2; routine search pass → 0; Force-power success → 2; etc.).

---

## 5. Other animation candidates (same framework: feedback or theme, never decoration)

- **Sabacc card flips** — a gambling minigame practically *demands* animation; the most "core" non-dice case.
- **Credit / XP / CP tick-up** — satisfying numerical feedback on a faucet.
- **Map room-to-room pan** on movement — reinforces spatial sense (dovetails with the in-flight map-nav work).
- **Force/lightsaber glow-pulse** on a Force power; a brief **hit / wound-bar flash** in combat.
- **Avoid:** decorative transitions that delay the keyboard-driven flow, loading spinners, motion that
  fights the medium's strengths (speed + density).

---

## 6. Phasing

- **Polish, behind the launch-blockers** (map-nav fix, rally rework, QA tail come first).
- **A small "dramatic-only" slice could land pre-launch** and is a cheap first-impression differentiator:
  the `drama` field + the client dice renderer wired to just **Force powers + sabacc + the combat finishing
  blow**, fully skippable/toggleable. Most MUSHes are pure text; a web client where the *signature mechanic*
  has tactile feedback signals "this game is cared for."
- **Full set + the other §5 animations: post-launch.**

---

## 7. Open knobs (tune during build, not blockers)
- Rate-limit window `N`, animation duration (target sub-second for tier-1, ~1s for tier-2).
- Default toggle state for new vs returning players.
- Whether the combat-decider/PvP detection lives in the resolver or a thin wrapper (keep it out of the
  `engine/combat.py` avoid-lane if possible — classify from the resolver's *output*, like the
  Director-sanitize fix classified at the display seam).
