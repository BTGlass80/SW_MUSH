---
category: paths
order: 3
summary: "Apprenticeship: how a Padawan and Master bond, train, and share Character Points."
tags: ["padawan", "master", "apprentice", "bond", "jedi", "training", "mentor"]
---

# The Padawan-Master Bond

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.2**

---

## How to Read This Guide

The Padawan-Master system is the **mentorship layer** of Jedi play. It's where two characters become formally bonded — one as the senior, one as the student — and the system tracks their relationship, their teaching, their trials, and ultimately the Padawan's promotion to Knight.

This is a **small-population system**. Most players will never be in a bond. The system is for characters who have come through the Village quest (Guide #18) and earned Jedi recognition, and even then only the ones who choose to formalize a mentorship. A typical server might have a half-dozen active bonds at any given time, scattered across the player base.

If you're playing a non-Jedi character, you can skip this guide — it doesn't affect you directly. If you're playing a Jedi or thinking about becoming one, read it. The bond is the central social structure of Jedi life on the server.

This is a new guide. There was no earlier version.

---

## 1. What the Bond Is

A **Padawan-Master bond** is a persistent mechanical relationship between two characters, formally tracked by the engine. One character is the Master; the other is the Padawan. The bond appears as a marker in their `look` output, in their sheet, and in their character data — both publicly visible (`[Master]` in bright cyan, `[Padawan]` in bright green) and in the relationship table.

The bond does several things:

1. **It establishes a teaching channel.** Force powers can be transferred from Master to Padawan via `+teach`. The Padawan pays the normal Character-Point cost to raise the underlying Force skill to its 1D foundation — or learns for free if they already meet it. Either way, the Padawan learns from the Master in a way they couldn't learn alone.
2. **It establishes a training loop.** The bonded pair can `+spar` — a structured training duel that grants CP to both characters and counts toward the Padawan's combat experience for trials.
3. **It establishes the Trials path.** The Padawan can attempt the five Jedi Trials (Skill, Courage, Flesh, Spirit, Insight) only with their Master's endorsement. Without endorsement, attempts auto-fail.
4. **It establishes the Knight promotion mechanism.** The Padawan becomes a Knight when all five Trials are recorded and the Master invokes the promotion ceremony.
5. **It creates a public identity.** Other players see the markers. Your relationship is visible at the cantina, at the Temple, in any shared scene.

The bond is, in short, the engine-enforced version of the canon "I will teach you the ways of the Force" relationship. It's a real commitment and a real reward.

---

## 2. Who Can Bond

Three preconditions exist for a bond to form.

**The Padawan must be a recognized Padawan.** This means they've completed the Village quest (Guide #18) and graduated through one of the Jedi chains (Path A — Order, or Path B — Independent). Path A graduates land in the Jedi Order's framework; Path B graduates land in the independent-but-Force-trained framework. Either can be a Padawan; the chain you came through doesn't lock you out.

**The Master must be tier-eligible.** Tier-eligibility for Master is currently a soft gate. At launch, **any character can theoretically be a Master**, gated only by the `master_cap` (default 1 — most characters can only hold one Padawan). The intent is that future Trials/promotion content will harden this gate so only Knights and Masters can take a Padawan. For now, the gate is loose; staff manage assignments via the `@bond` admin command for the tester-cohort scenario where Knights and Masters are assigned by hand.

**The Padawan must not already be bonded.** A Padawan with an active bond cannot accept a second one. The engine refuses. The Padawan must `+release` (Master initiates) or be knighted (formal graduation) before they can bond again — and at that point, they're no longer a Padawan, they're a Knight.

**Bonds are mutual.** Both parties must consent. There's no way for a Master to "force-bond" a Padawan against their will, and vice versa.

---

## 3. The Bond Proposal Flow

The launch-day flow is straightforward and modeled on the combat challenge/accept pattern.

**Master:** Stand in the same room as the prospective Padawan. Type:

```
+bond <padawan name>
```

The system posts a pending proposal. The Padawan gets a notification:

> Master Kael Voren proposes a Padawan-Master bond with you. Type `+bond accept Kael Voren` to consent, or `+bond decline Kael Voren` to refuse. The proposal expires in 10 minutes.

**Padawan:** Decide. To accept:

```
+bond accept Kael Voren
```

The engine validates everything — Padawan is not already bonded, Master hasn't hit their cap, both characters exist, the proposal hasn't expired — and creates the bond. Both characters now see the markers in look output. The bond is persistent across reconnects.

To decline:

```
+bond decline Kael Voren
```

The proposal clears. No relationship is formed. The Master can re-propose at a later time if circumstances change.

**The 10-minute window** is enough time for the Padawan to consider, possibly OOC-discuss the implications, possibly ask the Master a clarifying question — and short enough that proposals don't pile up. If the Padawan doesn't respond within 10 minutes, the proposal expires and the Master has to propose again.

**The Admin path (`@bond Master = Padawan`).** Staff can directly create a bond without going through the player-flow proposal/accept cycle. This is used for the tester cohort at launch (where staff have curated specific Knight/Master assignments to specific Padawans) and for any mediated scenarios where the Council formally assigns mentorship. The `@bond` command skips the consent prompt — staff are taking responsibility for the assignment.

---

## 4. What Changes When You Bond

The moment the bond forms, several things become visible:

**Look output markers.** Anyone who looks in a room with you sees the markers:

```
You are in the Jedi Archives.
  Master Kael Voren [Master] is here, examining a holocron.
  Padawan Sila Vannik [Padawan] is here, listening to her Master.
```

Bright cyan for Master, bright green for Padawan. These render in any room where you're co-located, similar to how `[PvP]` markers work for flagged-for-PvP characters.

**`+master` and `+padawan` commands light up.**

```
+master    (Padawan: see your Master's current status)
+padawan   (Master: see your Padawan(s)' status)
```

Each shows the other party's name, whether they're **online or offline**, and how long you've been **bonded**. For Jedi pairs, it also shows the partner's **Weight-of-War state sensed through the bond** — a line like "Through the bond: Burdened — *(descriptor)*" — and a running **Trials passed: N of 5** count. The Weight-sense is deliberate: the bond *is* the sensing channel, so there's no separate `+forcebond` command. Useful for "where's my Padawan, how are they carrying the war?" check-ins. (These commands report status and online presence, not a live location or wound readout — to see a Padawan's injuries, be in the room with them.)

**The teaching channel opens.** The Master can `+teach <power>` to grant Force powers to the Padawan. The Padawan can `+learn <power> from <master>` to formally request instruction. See §5.

**The training channel opens.** Either bonded character can initiate `+spar` to begin a training duel — grants 1 CP per spar to both, capped at one spar per 24 real-time hours per pair. See §6.

**The trials path opens.** The Padawan can begin working toward the five Trials. Without a bond there's no Master to attest them, so a Trial can't be recorded at all. See §7.

**Your bond status is always one command away.** A Padawan runs `+master`, a Master runs `+padawan`, and the relationship — partner, online status, bond age, Weight-sense, Trials progress — is right there. The public-facing markers in `look` output do the rest: anyone sharing a room with you can see at a glance that you're bonded.

**The pre-authorization channel opens.** Several Padawan actions are considered "approval-gated" by design — leaving Coruscant on unsanctioned missions, using Force powers in the field, and attempting the Trials without a fresh per-session endorsement. Rather than requiring per-action Master sign-off (which would create friction in real-time play), the system uses **standing pre-authorization**. The Master grants a category once; thereafter, routine activity in that category no longer needs approval. See §5 for the `+authorize` command.

---

## 4.1 Pre-Authorization — `+authorize`

The pre-authorization system lets a Master grant standing permissions for approval-gated actions so day-to-day play isn't blocked waiting for a sign-off.

**The command:**

```
+authorize <padawan> <category>        Grant a category.
+authorize <padawan> <category> off    Revoke it.
+authorize <category> [off]            Shorthand if you have 1 Padawan.
+authorize <padawan>                   List a Padawan's current grants.
+authorize                             Show all your standing grants.
```

**Categories:**

| Category | What it covers |
|---|---|
| `offworld` | Leave Coruscant for non-sanctioned missions |
| `powers` | Use Force powers in the field unsupervised |
| `trials` | Attempt the Trials without a fresh `+endorse` per attempt |

**From the Padawan side:** run bare `+authorize` to see what your Master has pre-authorized for you. Seeing `trials` in that list means you can attempt any Trial without waiting for your Master to type `+endorse trials` first. The `+trials` display also shows "Endorsement: standing" when the `trials` category is granted.

**Design rationale.** Pre-authorization doesn't replace the Master's oversight — it replaces the friction of real-time approval when both players aren't online at the same time. A Master who has authorized `offworld` is saying "I trust you to take assignments outside Coruscant; you don't have to find me before every mission." It's a posture of trust, not a relinquishment of oversight.

---

## 5. Teaching — `+teach` and `+learn`

The teaching mechanic is where the Master actually transfers Force-power knowledge to the Padawan. Two paths through it:

**The Master-initiated path.**

```
+teach <power name>
```

If the Master has multiple bonded Padawans (rare — `master_cap` defaults to 1), they specify which: `+teach <padawan> <power name>`.

The engine validates:
- The Master has a Padawan bond (or the specified Padawan is theirs).
- The Master can actually use the power — they hold at least 1D in every Force skill it requires (Control, Sense, and/or Alter). You can't pass on what you can't do.
- The Padawan is in the same room as the Master (you can't teach across a galaxy).

On success, the engine brings each Force skill the power requires up to a **1D foundation** for the Padawan, spending the Padawan's CP for any skill that was below 1D. A power becomes usable the moment you hold 1D in its required skill(s) — so establishing that foundation *is* learning the power. If the Padawan already meets the foundation, the `+teach` is a free narrative/audit event — the lesson reinforces what they already know but spends nothing.

**The Padawan-initiated path.**

```
+learn <power name> from <master name>
```

This is the Padawan saying "Master, I'd like to learn X." It posts a pending request in memory. The Master then sees:

> Sila Vannik requests to learn Telekinesis from you. Type `+teach Telekinesis` (within 5 minutes) to grant the power.

The Master types `+teach Telekinesis` and the teaching completes. The request expires after 5 minutes if the Master doesn't respond — typical for "Padawan asked while Master was AFK" scenarios.

**Why two paths?** The Master-initiated path is the proactive lesson — "today we work on Saber Throw, my Padawan." The Padawan-initiated path is the curiosity prompt — "Master, I've been thinking about Mind Trick, can we work on it?" Both fit different narrative beats.

**The CP cost.** Raising a Force skill from 0 to its 1D foundation costs the Padawan the standard rate — three pips at the skill's per-pip price, the same cost the `train` command charges. The Padawan must be able to afford it; if they can't, the teaching is refused with a clear "needs N CP" message. If they already hold the required skills at 1D or higher, the teaching is free — they don't pay for what they already know; the bond just deepens the existing skill.

**The Master teaches the next thing, not the future thing.** `+teach` always establishes the 1D foundation — it doesn't vault a Padawan to a high rating. Higher Control, Sense, or Alter makes a power *more reliable* (a better roll), but it isn't a gate on learning: any power is teachable once the Padawan has the foundation. To grow a power beyond 1D, the Padawan trains it up the normal way over time. The bond opens the door; the practice walks through it.

---

## 6. Sparring — `+spar`

Sparring is the training-combat mechanic for bonded pairs. Either party can initiate; both consent by being bonded.

```
+spar
```

Conditions:
- Both characters are in the same room.
- The bond is active.
- It's been at least 24 real-time hours since the last spar between this pair.

On success, the system:
- Awards **1 CP to both** the Master and the Padawan.
- Records a `spar` entry in the training log.
- Posts a brief narrative event ("Master Kael Voren and Padawan Sila Vannik begin a training duel...").

The 24-hour cooldown prevents grinding — you get 1 CP per pair per day, not per minute. Multiple sessions of intense sparring don't compound. The Force lessons are gradual.

**The launch-MVP scope.** The current spar implementation is the validation-plus-reward layer. A future drop will hook the spar into a full combat loop where the bonded pair actually runs a non-lethal duel through the combat system — the dice rolled, the Force powers used, the techniques tested. For now, the spar is mechanical bookkeeping: the validation passes, the CP gets awarded, the log is written.

**Why sparring matters for Trials.** Several of the five Trials (especially the Trial of Skill and the Trial of Flesh) count sparring as evidence of training. Padawans who spar regularly are more credible candidates for promotion. The training log is part of the Master's case for endorsing a Trial attempt.

---

## 7. The Five Trials

The five Jedi Trials are the path from Padawan to Knight. They are:

| Trial | What It Tests |
|---|---|
| **Trial of Skill** | Combat or Force-power demonstration |
| **Trial of Courage** | Solo mission in a hostile zone |
| **Trial of Flesh** | Endurance under sustained injury |
| **Trial of Spirit** | Refusing dark-side temptation |
| **Trial of Insight** | Perception, puzzle-solving, intuition |

These are not sequential — they can be attempted in any order. They are not strict skill checks — they're often role-played events that the Master observes (or that the Council adjudicates) and then attests as passed via the `+trial` command.

---

### How a Trial Works

The flow:

**1. The Padawan prepares.** This is where the bulk of the work happens. A Trial isn't a single command; it's an arc of play that the Padawan goes through with their Master's awareness. The Trial of Courage might be a solo mission to a Hutt-controlled zone to recover something stolen — the Padawan does the mission. The Trial of Spirit might be a Sith infiltrator approaching the Padawan with an offer — the Padawan refuses (and the refusal is observable in scene). The Trial of Flesh might be the Padawan sustaining significant injury without disengaging from a mission — the Padawan plays through it.

**2. The Master endorses.** Before the Padawan attempts the formal completion, the Master types:

```
+endorse trials <padawan>
```

This records the Master's standing vouch for the Padawan's readiness — the engine writes the endorsement onto the Padawan (and the next attested Trial consumes it). At launch the operative gate is the attestation itself: **only the bonded Master, or staff, can record a Trial pass at all** (step 3). The endorsement is the Master saying, on the record, "yes — this Padawan has done the work." The Padawan can confirm it landed: `+trials` then shows **Endorsement: ready** (or **Endorsement: standing** if the Master pre-authorized the whole category via `+authorize`; see §4.1). A future Padawan-side attempt surface will read this flag and turn an unsanctioned attempt into an automatic failure; for now, the Master's `+trial` *is* the gate.

**3. The Master attests the pass.** After the Trial has been completed in roleplay (the mission succeeded, the temptation was refused, the Padawan held under fire), the Master types:

```
+trial <trial name> [<padawan>]
```

For example, `+trial courage Sila` or `+trial skill Vannik`. The engine records that this Padawan has passed that Trial. If the Master has only one Padawan, the trailing `<padawan>` arg is optional.

**4. (Staff alternative.)** Council fiat: staff can attest a Trial directly via `@trial <name> = <padawan>`. This is used when the Council mediates — for canon-style Trials where a full Council convocation observes and adjudicates, not just the individual Master.

**5. The Padawan reviews progress.**

```
+trials
```

The Padawan sees which Trials they've passed and which remain. The Master sees the same view for their Padawan.

```
+trials
  Trial Progress for Sila Vannik (bonded to Kael Voren):
    ✓ Skill     (attested 18 May 2026 by Kael Voren)
    ✓ Courage   (attested 22 May 2026 by Kael Voren)
    ✗ Flesh     (not yet)
    ✗ Spirit    (not yet)
    ✗ Insight   (not yet)
  3 of 5 Trials remaining.
```

---

### The Five Trials In Detail

**Trial of Skill — Combat or Force-Power Demonstration.** The Padawan demonstrates mastery of a combat technique or a Force power. The classic scene: the Padawan duels a senior Jedi (often their Master) in a non-lethal spar that shows real growth. Alternative scenes: the Padawan succeeds in a battlefield engagement against a serious opponent, the Padawan executes a complex Force technique under pressure. The Master attests the Trial when they've seen the Padawan act at a Knight-credible level.

**Trial of Courage — Solo Mission in a Hostile Zone.** The Padawan completes a mission, alone, in a zone that is genuinely dangerous to them. Hutt Space, the Coruscant underworld, a Separatist-held world. The scene is run in actual play — the Padawan goes, the danger is real (real combat, real risk, real loss possible). The mission's success is the Trial. The Master attests when they've heard the report and verified the Padawan acted as a Jedi should.

**Trial of Flesh — Endurance Under Injury.** The Padawan endures and continues. This isn't "you have to die almost" — it's "you have to keep going when most would stop." The Padawan takes a Wounded result in a mission and finishes the mission. They survive a torturous situation (interrogation, captivity, extended hostile environment). They don't tap out. The Master attests when they've seen the Padawan refuse to surrender.

**Trial of Spirit — Refusing Dark-Side Temptation.** The Padawan is presented with an offer that would, if accepted, slide them toward the dark. A Sith infiltrator promises power. A captured enemy begs to be killed. A friend turns on the Padawan and there's an opportunity for retributive violence. The Padawan refuses or chooses the lighter path. The Master attests when they've seen the Padawan resist. This is often the most narratively rich Trial because it requires a specific scenario someone constructs — often the Master themselves, or staff for Council-mediated versions.

**Trial of Insight — Perception, Puzzle-Solving, Intuition.** The Padawan sees what others miss. A riddle. A coded message. A puzzle in a mission. A truth hidden in someone's lies. The Padawan demonstrates the kind of intuition that separates Knights from less-experienced fighters. The Master attests when they've seen the Padawan see clearly.

---

## 8. The Knight Promotion Ceremony

When all five Trials are recorded, the Master can invoke the Knight promotion:

```
+knight <padawan>
```

The engine validates:
- The bond exists and is active.
- All five Trials are recorded for this Padawan.
- The actor is the Master in the bond.

If the gate passes, the ceremony fires:
- The bond's status changes to `knighted`.
- A `knight_promotion_at` timestamp is recorded.
- The Padawan gains **+1 Force Point** (capped at a generous launch ceiling of 50, but few characters hit this).
- A `pc_action_log` entry is written on both sides — narrative-memory hook for future content that will surface "the day Sila Vannik became a Knight" as a referenceable event.
- The Padawan's status becomes "Knight" — they're no longer a Padawan; they're a peer to other Knights.

**Council fiat — `@knight <padawan>`.** Staff can promote a Padawan to Knight even without all five Trials, using the admin override. This is the canon precedent of mid-Clone-Wars battlefield knightings — Anakin Skywalker is famously knighted before completing all formal Trials. The staff override exists for that kind of story moment, when the narrative calls for "this Padawan has earned the title in a moment of crisis, regardless of formal completion."

**What changes for the new Knight.** Several things, immediately:

- The bond is closed — they're no longer in a Master-Padawan relationship. They're an independent Knight.
- They are now **tier-eligible to take a Padawan of their own**, in the future. The `master_cap` still applies (default 1), but the Knight can be on the receiving end of a `+bond <padawan>` invitation.
- They get the +1 Force Point. Their first Knight scene is often a moment where that extra FP matters.
- They lose the `[Padawan]` marker; depending on whether they take a Padawan later, they may eventually gain `[Master]`.
- Their public sheet now shows "Knight" rather than "Padawan."

**What doesn't change immediately.** Their underlying skills are the same. Their Force powers are the same. Their faction reputation is the same. The Knight promotion is a ceremonial and political shift, not a mechanical power-up beyond the +1 FP. The Knight earns their power through continued play — through `+kudos`, scene bonuses, missions, ongoing Force-power training. The promotion changes their *standing*, not their *strength*.

---

## 9. Releasing a Bond

Sometimes a bond ends short of knighting. The Master can release the Padawan:

```
+release
```

If the Master has multiple Padawans (rare): `+release <padawan>`. Optional reason: `+release <padawan> = <reason>`.

The bond dissolves. The Padawan is no longer bonded; they're still a Padawan (their tier doesn't change), but they're now unbonded. They can be re-bonded to a different Master via the normal proposal flow.

**A release is logged on both sides.** A `pc_action_log` entry of type `bond_dissolved` writes to both characters' history. The reason (if given) is captured. This is the narrative-memory hook for future content that will surface "the bond between Kael Voren and Sila Vannik ended because [reason]" as part of memory and history.

**Why release a bond?**

- **The relationship soured.** Personal conflict, irreconcilable differences, a Padawan who's gone in a direction the Master can't or won't follow.
- **The Master is leaving.** A character retiring from active play; an actor stepping back from the role.
- **The Padawan has grown beyond the Master.** The Master acknowledges they've taught what they can teach; the Padawan needs different mentorship.
- **A formal Council action.** The Council removes the Master from the role (perhaps due to dark-side drift, perhaps for political reasons in the era's complex Jedi politics).

Released Padawans are not punished — they're just no longer in this bond. They can keep their progress (Trial attestations remain, their Force powers remain), but they may need a new Master to continue toward Knight. Trial endorsement requires an active bond.

**Padawans can also leave the bond voluntarily** using `+leave-master`. A reason is required — the system won't accept an empty reason, which discourages impulsive breaks and creates a record for both parties and staff:

```
+leave-master <reason>
```

The bond dissolves immediately. The dissolution is logged on both sides, the Master is notified if online (offline: recorded for their next login), and the reason is preserved. Masters use `+release`; Padawans use `+leave-master`. The language differs intentionally: Masters *release*, Padawans *leave*. The initiative determines the framing.

---

## 10. Multiple Padawans and the Cap

Each character has a `master_cap` field, default 1. This is how many active Padawans a Master can hold at once.

- Standard characters: cap of 1.
- Some Knights (rare, staff-set): cap of 2 or 3, for the kind of high-profile teacher who runs multiple Padawans.
- Masters (in the long-term future, when the tier system hardens): may have higher caps by default.

**Hitting the cap blocks new bonds.** If you're at your cap, `+bond <new padawan>` returns an error telling you to release an existing bond first. The cap is enforced at proposal time, not at acceptance — you can't propose if you're at the cap.

**The cap is set per-character, not per-tier.** A Knight with cap 1 takes one Padawan; a Master with cap 2 takes two. The cap is data on the character row, not a tier-derived value. Staff can raise it for specific characters via admin actions.

**Most bonds at launch are 1:1.** The cap-2 and cap-3 scenarios are reserved for staff-mediated cases (a tester-Knight who's running multiple test Padawans, a high-profile Council member with multiple students). Normal play assumes one Padawan at a time.

---

## 11. Bonds and Other Systems

The bond interacts with several other game systems.

**Combat.** Bonded characters can spar (§6). They also have a small narrative buff when fighting alongside each other — the engine doesn't enforce it mechanically, but RP-wise, a Master and Padawan fighting together is a recognizable team scene. The combat system itself doesn't change for bonded characters.

**Force powers.** The teaching channel (§5) is the formal hook. Beyond that, bonded characters often have shared power preferences — a Master who specializes in Control will tend to teach Control-line powers to their Padawan, leading to a "tradition" of Force philosophy passed down. There's no mechanical enforcement; it's emergent from the teaching pattern.

**Reputation.** A Padawan inherits some of their Master's reputation in Jedi-adjacent contexts. If the Master is a famous Council member, the Padawan benefits from that. If the Master is a controversial figure, the Padawan inherits some of that complication. This is RP, not engine-enforced.

**Player cities.** A bond's geography matters when the Master has citizenship. A Padawan can be added to their Master's city's guest list (Guide #12) so they have free movement. Some Padawans become full citizens of their Master's faction as part of the bond's commitment.

**Death.** The death loop's recovery (Guide #3) applies to a Padawan exactly as it does anyone. The engine doesn't push an automatic death alert down the bond, but a Master watching `+padawan` sees their student drop offline, and the Weight-sense line tells its own story over time. The Master might choose to provide bacta, heal, or otherwise support the Padawan's recovery; none of that is enforced, but it's the natural RP move.

**The Director AI.** Bond-aware Director content — events that pull both characters in, rumors about the Master a Padawan should hear, openings for joint missions — is a design direction the system is built toward, not a wired feature today; the Director doesn't yet read bond state. In practice, bonded characters' scenes interconnect anyway, because the two players seek each other out and the bond gives them a standing reason to share a stage.

---

## 12. The Roleplay of a Bond

The mechanics are scaffolding. The actual experience of a bond is the roleplay — the scenes you build together, the lessons you teach, the missions you run, the disagreements you have, the trust you accrue. A bond that exists only as a mechanical relationship is a thin thing; a bond that's been played in scene for weeks is a real one.

Some common RP rhythms:

**The teaching scene.** The Master demonstrates a Force technique. The Padawan attempts it (`+spar` provides the mechanical context; the RP fills it in). The Master corrects, encourages, sometimes scolds. These are short scenes — 30 minutes or so — and they happen often, especially in the early bond.

**The mission together.** Master and Padawan go on a mission as a team. The Padawan is often in over their head; the Master observes, teaches in the moment, and intervenes only when necessary. The mission's outcome is a Padawan-development scene, even if it's mechanically just a normal mission.

**The mission alone.** The Padawan is sent solo. The Master doesn't accompany; they wait at the Temple (or wherever) for the report. This is often the Trial of Courage moment, but it can also be smaller — a "Padawan, I trust you with this" mission that builds toward larger Trials.

**The philosophical disagreement.** Master and Padawan see something differently. The Sith infiltrator is captured — does the Padawan want to interrogate her, the Master object? The Master is asked to fight in a Republic battle that the Padawan thinks is the wrong cause — the Padawan questions the order. These scenes are where the bond becomes complex, where the relationship is tested, where the Master sees what kind of Jedi the Padawan will become.

**The Trial scene.** Built deliberately. The Master sets up a situation (often with staff help or Director-AI assistance) that constitutes one of the five Trials. The Padawan plays through it. The Master observes. After the scene, the Master types `+trial <name>` to attest the pass.

**The Knighting.** When all five Trials are recorded, the ceremony happens. This is a one-time scene — a Master cuts the Padawan's braid, says the words, marks the moment. Most Knighting ceremonies are public; other Jedi attend; the Director-AI is encouraged to surface narrative atmosphere; the Padawan becomes a Knight visibly, in front of witnesses. After, the +1 Force Point quietly appears in the new Knight's sheet.

The mechanics are 5% of what makes the bond work. The other 95% is what you do with the time.

---

## 13. The Bond In Decline — When It Ends Badly

Not all bonds end with a Knighting ceremony. Some end with a release. Some end with the Padawan's death. Some end with the Master's death. Some end with one or the other character being retired from active play.

**A bond that ends in release** leaves the Padawan with their progress intact (their Force powers, their attested Trials) but without endorsement to continue. They can find a new Master, but the social weight of being released matters — other Jedi will ask why. The reason field on the release matters here; "personal conflict" reads very differently from "Council intervention" reads differently from "the Padawan no longer needs me."

**A bond that ends in the Padawan's death** is grief. The Master may take a new Padawan later, but the loss is part of the Master's story now. The death is recorded in the Master's history. The Padawan's old Force-power transfers are still in the world — those powers don't get rescinded.

**A bond that ends in the Master's death** is the harder transition. The Padawan continues unbonded; their Trial progress is preserved; they can find a new Master, but the relationship was specifically with this person, this voice, this teacher. A new Master is a different relationship, not a substitute. Many Padawans choose to remain unbonded for a while after their Master's death, then either find a new Master or accept Council fiat in the future.

**A bond can also be politically ended.** In the Clone Wars era's complex Jedi politics, the Council can formally end a bond — usually because the Master is suspected of drift or the Padawan is in trouble. This is staff-mediated; admins use `@bond` to reassign, or use database-level actions to dissolve. Such bonds end with public consequence and ongoing narrative implications.

The bond is meant to be permanent within its arc. The fact that it sometimes ends short of Knighting is part of what makes the system serious. Not every Padawan becomes a Knight. Not every Master sees their student through to the end.

---

## 14. Player Commands Quick Reference

| Command | Who | What it does |
|---|---|---|
| `+bond <padawan>` | Master | Propose a bond (10-min window) |
| `+bond accept <master>` | Padawan | Accept a pending bond proposal |
| `+bond decline <master>` | Padawan | Decline a pending bond proposal |
| `+release [<padawan>] [= <reason>]` | Master | Master-initiated bond dissolution |
| `+leave-master <reason>` | Padawan | Padawan-initiated voluntary bond dissolution |
| `+authorize <padawan> <category> [off]` | Master | Grant/revoke standing pre-authorization (offworld / powers / trials) |
| `+authorize` | Either | List standing pre-authorization grants |
| `+master` | Padawan | Show bonded Master's status |
| `+padawan` | Master | Show bonded Padawan(s)' status |
| `+teach <power>` | Master | Teach a Force power to your Padawan |
| `+teach <padawan> <power>` | Master with multiple Padawans | Same, target-specific |
| `+learn <power> from <master>` | Padawan | Request instruction (5-min request) |
| `+spar` | Either bonded character | Initiate a training duel (24h cooldown, +1 CP each) |
| `+trials [<padawan>]` | Either | View Trial progress |
| `+endorse trials <padawan>` | Master | One-shot endorsement for Trial attempts |
| `+trial <name> [<padawan>]` | Master | Attest a Trial pass |
| `+knight <padawan>` | Master | Promote Padawan to Knight (gated on 5 Trials) |
| `@bond <master> = <padawan>` | Staff | Force-create a bond (no consent prompt) |
| `@trial <name> = <padawan>` | Staff | Attest a Trial via Council fiat |
| `@knight <padawan>` | Staff | Promote a Padawan without all 5 Trials (Council fiat) |

---

## 15. Numbers At A Glance

| Quantity | Value |
|---|---|
| Bond proposal window | 10 real-time minutes |
| Default master_cap | 1 active Padawan |
| Knight Force-Point grant | +1 FP |
| Knight FP cap | 50 (launch ceiling) |
| Spar CP reward | 1 CP to both parties |
| Spar cooldown | 24 real-time hours per pair |
| `+learn` request window | 5 real-time minutes |
| Padawan marker color | bright green `[Padawan]` |
| Master marker color | bright cyan `[Master]` |
| Number of Trials | 5 (Skill, Courage, Flesh, Spirit, Insight) |
| Trials required for Knight | All 5 (soft gate; staff can override with `@knight`) |
| Endorsement | Master vouch recorded via `+endorse trials <padawan>`; consumed by the next `+trial` |

---

## 16. A Final Word

The Padawan-Master bond is one of the most demanding systems in Parsec because it's a real two-person relationship that plays out over weeks. Both characters have to commit. Both have to show up. Both have to be willing to play the slow scenes that build the bond's substance — the teaching scene, the mission, the disagreement, the Trial.

When it works, it's the heart of Jedi play on the server. A bonded pair has texture that a solo Jedi character doesn't have. The Master sees their Padawan grow; the Padawan sees their Master in close detail; the relationship accrues a private vocabulary of shared scenes and references. The Knighting at the end (when it comes) is genuinely earned.

When it doesn't work, the release is real, and that's also fine. Not every Master is the right Master for every Padawan. Not every story ends in promotion. The system doesn't require perfection; it gives you the structure within which to play, and the play decides what happens next.

If you're considering becoming a Master: take the Padawan seriously. They're committing 5+ Trials of real-time play to your guidance. You owe them attention, consistency, and good-faith teaching.

If you're considering becoming a Padawan: pick a Master whose play you respect, whose presence you'll seek out, whose teaching you'll actually use. The bond is only as good as the time you put into it.

If you're considering neither: that's also fine. The bond is for those who want it. Most players don't, and the rest of the game has plenty to offer.

---

*End of Guide #14 — The Padawan-Master Bond*
