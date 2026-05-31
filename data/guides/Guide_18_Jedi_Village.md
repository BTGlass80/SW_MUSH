---
category: paths
order: 2
summary: "The hidden monastery and the three branching paths a Force-sensitive can take."
tags: ["jedi", "village", "monastery", "path", "force-sensitive", "training"]
---

# The Jedi Village & Path A/B/C

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

The Jedi Village is the **most committed-to story arc** in SW_MUSH. It's the route from "non-Jedi character with hidden potential" to "recognized Jedi" — through the deep desert of Tatooine, five trials, and a final choice between three paths. It is multi-week real-time content.

Most players will never run the Village arc. The ones who do are typically committing months of play to a Jedi story, and the system is designed to honor that commitment. The Village isn't a fast unlock; it's a slow recognition of dedicated play.

If you only have ten minutes, read **§1 What the Village Is** and **§4 The Five Trials**. The rest is depth for players actually running the arc.

This is a new guide. There was no earlier version.

---

## 1. What the Village Is

The Jedi Village is a hidden settlement in the Jundland Wastes of Tatooine. It is not on any map. You cannot travel there directly. There is no taxi to the Village, no fast-travel waypoint, no public mention of its existence among standard NPCs. It exists because Master Yarael Kett — an old Jedi who walked away from the Order before the Clone Wars and has lived in exile ever since — chose to make it exist. The Village trains Force-sensitive beings the Order doesn't know about. Some Village graduates eventually report to the Order; some stay; some go darker. The Village is the seam in the Clone Wars galaxy where the rigid binary of "Jedi or non-Jedi" softens.

For a player, the Village is **the alternate path to playing a Jedi**. The other path — the chargen-template path — is locked at character creation in the Clone Wars era (see Guide #2). You cannot just pick "Jedi" off the menu. Either you complete the Village arc, or you start non-Jedi.

The Village arc has three acts:

**Act 1 — Pre-Invitation.** You're a non-Jedi character living an ordinary life. You wander the world. Sometimes — when you visit certain places, when enough time passes, when the conditions align — the Force *signs* itself to you. A flicker of intuition. A reading of someone's intent. A dream that turns out to be true. The system tracks these signs invisibly. After enough accumulation, the Hermit's invitation triggers.

**Act 2 — In the Village.** You've found the Hermit, who pointed you to the Village. You travel there through the dunes. You meet Master Yarael for the first audience. Then you face the five Trials, in sequence: Skill, Courage, Flesh, Spirit, Insight. Each one tests a different facet of what a Jedi must be. Each one has a cooldown — you cannot rush them. Real-time weeks pass.

**Act 3 — The Choice.** All five Trials complete. Master Yarael presents you with the question: report to the Order, stay with the Village, or — only if you failed the Spirit trial in a specific way — take the dark path. Your answer is irreversible.

The arc takes **weeks of real-time** to run, by design. There is a 7-day cooldown between Act 1 (invitation) and Act 2 (entering the trials), and a **14-day inter-trial cooldown** between each successful trial. From invitation to final choice is roughly **2 months of real-time** minimum, often more. This is intentional — being a Jedi is supposed to feel earned, not picked.

---

## 2. Act 1 — How the Invitation Comes

Becoming eligible for the invitation requires three things, accumulated invisibly:

**A. Fifty hours of total playtime.** Your character must have accumulated **50 real-time hours** of online play (`play_time_seconds >= 180,000`). This is the **gate** — until you've crossed it, no Force-signs fire at all, no matter what you do. It's the system's way of saying "the Village finds those who've stayed in the world long enough to belong."

**B. Force-sign accumulation to threshold.** Once past the 50-hour gate, **Force-signs** begin to fire automatically as you play. A Force-sign is a small event — a moment of intuition, a flash of perceptive clarity, a strange dream surfacing into your awareness. The narrative content varies; the mechanical effect is that your hidden `force_signs_accumulated` count increments. At **five signs**, the invitation becomes eligible.

**C. The Hermit visit.** With five signs accumulated, the Force gently steers you toward the **Hermit's Hut** in the Dune Sea. It's not auto-teleport; you have to actually travel there in the wilderness (Guide #15). When you arrive and `talk` to the Hermit, his **after-lines** fire — the invitation is formally delivered. Your `village_act` ticks from 0 to 1. You are *invited*.

**The mechanics of Force-signs.** They fire on a periodic tick handler. Base probability per tick is roughly 0.0028 — about one sign per 6 hours of play at base rate. Your character has a hidden `force_predisposition` value (0.0 to 1.0) set at chargen; higher predisposition multiplies the sign probability, capping at roughly one sign per 2 hours at the maximum. A character with high predisposition might accumulate five signs in 10 real-time hours of play; a character with low predisposition might take 30. The variance is intentional — the Force doesn't sign itself the same way to everyone.

**What you actually see when a sign fires.** The narrative is short and atmospheric. Example:

> You pause for a moment in the crowd. Something — not quite a thought, not quite a feeling — moves through you. A certainty that the small woman crossing in front of you is afraid. You don't know how you know. The moment passes; you keep walking.

These lines are short, in-character, and not labeled "FORCE SIGN ACQUIRED!" or anything bright. They read as moments of subtle awareness that someone might or might not notice in themselves. You're not told you got a sign. You just see the line and keep playing.

**Hidden by design.** The whole accumulation phase is **invisible to the player**. You don't have a UI for "Force-signs: 3/5." You don't see your `force_predisposition` value. You don't know when the next sign will fire. The system wants the invitation to feel like discovery, not progress-bar completion. New players who happen to hit the threshold without knowing the mechanic exist sometimes get the invitation as a genuine surprise.

**Force-resonant landmarks contribute too.** Visiting the wilderness landmarks tagged force-resonant — the Anchor Stones, the Ruined Obelisk, the Bantha Graveyard, the Forgotten Jedi Shrine — also triggers signs (see Guide #15 for the landmark roster). Each landmark visit is a separate sign opportunity. A player who deliberately tours the resonant places will tend to accumulate signs faster than one who doesn't.

**The Hermit appears at the Hermit's Hut.** Coordinates `(33, 16)` in the Dune Sea wilderness — west of the Anchor Stones. You don't see him there until you've crossed the threshold. If you visit the hut without enough signs, the room is empty (or has only ambient flavor); you see the dwelling but no Hermit appears. With five signs accumulated, he is there waiting. `talk hermit` triggers the invitation cutscene.

---

## 3. Act 2 — Crossing to the Village

Once invited, you have **seven real-time days** before you can enter the trials. This is the **Act 1 → Act 2 cooldown**. Try to enter sooner and the engine refuses with "you are not ready yet" framing. The cooldown exists to make the Village's "found" status feel like a real journey, not a same-session conclusion.

After the 7 days clear:

**Crossing the Dunes (Act 2 — Step 2).** You travel from the Hermit's Hut through the wilderness landmarks toward the Village. Several tiles are part of the path:

- **Village Outer Watch** — the first sentinel post, where the Village's anonymity begins to show. An old, weathered watch-stone.
- **Village Gate** — a wooden gate set into the rock. Closed. Knock to enter.
- **Village Common Square** — the heart of the village. A small clearing surrounded by carved dwellings.
- **Village Council Hut** — where Elder Saro Veck holds her records and offers the Insight Trial.
- **Master's Chamber** — where Master Yarael Kett waits.
- **Apprentice Tents** — where the Village's other initiates live (NPCs, currently).
- **Forge** — Smith Daro's lightsaber forge, site of the Skill Trial.
- **Meditation Caves** — deep caves below the village; site of the Flesh Trial.
- **Sealed Sanctum** — the Spirit Trial site, where Master Yarael also receives you for the dark-side temptation.

The geography matters because each Trial has its own location. You can't run all five from one room. You move through the Village as you advance.

**First Audience (Act 2 — Step 4).** Before any Trial fires, you must have the **first audience** with Master Yarael in the Master's Chamber. `talk Yarael`. The first-audience scene is mandatory; the engine flags `village_first_audience_done = True` only after this conversation. Until that flag is set, the trial NPCs deflect: "First speak with the Master." This forces the sequence: arrive → audience → trials.

The first audience is a single scene of 5–10 minutes of in-character conversation. Yarael asks why you've come. He listens. He explains, in his slow careful way, what the Village does and what the Trials will test. Your response in the scene is RP, not mechanical — there's no skill check at the first audience. But it's where Yarael takes your measure, and the framing shapes the rest of the arc.

---

## 4. The Five Trials

Once the first audience is done, the trials become available — but only in order. **Skill must come first**, then Courage, then Flesh, then Spirit, then Insight. Each requires the previous one to be complete. The engine enforces this sequencing.

Between each trial there is a **14-day inter-trial cooldown** — 14 real-time days. After passing the Skill Trial, you cannot attempt Courage until the 14 days have elapsed. This is the largest behavioral lever in the system: it stretches the Village arc to a multi-month commitment by design. You don't grind the Village; you live with it.

The five Trials:

---

### Trial of Skill — The Forge

**Location:** The Forge. **NPC:** Smith Daro. **Tests:** Patience, focus, craftsmanship.

Daro is a Twi'lek smith — old, kind, exacting. He puts a piece of the Village's stockpile in your hands and asks you to begin a lightsaber. Not finish — *begin*. The crystal is yours later; this trial is about whether you can do the work.

The mechanic is three sequential `craft_lightsaber` skill checks at increasing difficulty: 8, 12, 15. Each `trial skill` attempt runs one step. Pass all three and the trial is done. A failure at any step doesn't reset progress — the step counter stays where it is, and you wait out a 1-hour cooldown before retrying. Patience is the test, in both the fiction and the mechanic.

The reward at completion is **a kyber crystal**. You don't yet have a lightsaber, but you have its heart. Daro tucks the crystal into your hands and tells you to keep it safe. The crystal stays with you until Path A, B, or C resolves; what happens to it depends on which path you take.

The Skill Trial typically takes **two to four real-time hours** of play, spread across attempts. Players who go in confident often need three or four tries on the difficulty-15 final step. Players who go in patient often pass clean on attempts two or three. The trial is forgiving but uncompromising.

---

### Trial of Courage — The Common Square

**Location:** Common Square. **NPC:** Elder Mira Delen. **Tests:** Resolve in the face of difficulty.

Mira is the Village's elder of grief — an older woman who lost her own apprentice years ago. She does not ask easy questions. The Courage Trial is a dialogue-driven scene where Mira presents you with a situation — a moral choice, a difficult question about what you'd do — and asks you to answer with conviction. The mechanic is a **multi-turn dialogue completion**: you and Mira go back and forth several times, and your responses (selected from menu options) reveal whether you understand what courage means.

Courage in the Village's sense is not "willingness to fight." It's **willingness to act when acting will cost you something**. The Trial's dialogue tests this — Mira presents scenarios where the right answer involves loss (giving up a victory, refusing to use violence when violence would work, telling a hard truth). Players who choose the easy answers fail the Trial. Players who choose the costly answers pass.

There is no skill check on Courage; it is pure roleplay. The dialogue tree has multiple paths; the engine notes which path you took. You can fail the Trial and reattempt after the 14-day cooldown, but most players who fail Courage do so deliberately, because the costly answers are genuinely costly — they're committing to RP positions they may not have wanted to commit to. The Trial is unusually transparent that way: you know what the right answer is, and the question is whether you'll say it.

---

### Trial of Flesh — The Meditation Caves

**Location:** Meditation Caves. **NPC:** Elder Korvas. **Tests:** Endurance, the body's discipline.

Korvas is an ancient Trandoshan elder, scarred and slow-moving. He leads you into the meditation caves and sits you down on cold stone. The Trial is a **timed room dwell**: you must remain in the meditation chamber for an extended period without leaving. The duration is calibrated to be uncomfortable but not impossible — long enough that the body wants out, short enough that the mind can hold.

During the dwell, ambient flavor lines surface periodically — the cold, the silence, the small physical discomforts. You can `cpose` your character's experience. You cannot leave; if you leave the room, the Trial fails and you wait the 14-day cooldown.

The mechanic is straightforward but the experience is real: sitting in the same room for that long, watching the ambient flavor surface, posing the slow internal process. It's the Trial that most players find both easiest (no skill check) and hardest (it requires actually staying present). The Trial of Flesh isn't about combat injury; it's about the body's capacity to hold still when it wants to move.

---

### Trial of Spirit — The Sealed Sanctum

**Location:** Sealed Sanctum. **NPC:** Master Yarael Kett. **Tests:** Resistance to dark-side temptation. **Also: the gate to Path C.**

This is the Trial that decides the Path A/B/C choice. Master Yarael takes you into the Sealed Sanctum — a chamber set apart from the rest of the Village, kept locked. Inside, the air is heavier. He sits you down and presents you with **the temptation**.

The temptation is presented as a multi-turn dialogue. Yarael walks you through a scenario where dark-side power would solve a real problem you face — power to save someone you love, power to undo a regret, power to set right a wrong that was done to you. The framing is sympathetic; Yarael does not condemn you for being tempted, because the temptation is *meant* to test you. The dialogue offers escalating choices: each turn, Yarael asks if you're sure, and gives you a chance to refuse or to lean further in.

**Two outcomes are possible:**

- **Refuse the temptation.** You complete the Trial cleanly. `village_trial_spirit_done = 1`. Yarael nods, sad and proud, and dismisses you. You may now attempt the Insight Trial. Path A and Path B remain open.
- **Accept the temptation.** You complete the Trial — but not cleanly. The system records `village_trial_spirit_done = 1` AND `village_trial_spirit_path_c_locked = 1`. Yarael's framing in the final scene is **sadness, not anger**. You have not been expelled; you have made a choice the Village will honor by acknowledging it. Path C becomes available at the final choice. Path A and Path B are now closed.

This is the only Trial where you can "pass" by accepting the dark. It is also the only Trial that mechanically alters the final choice menu. Once Path C is locked in, you cannot retake the Spirit Trial to undo it. The choice is irrevocable.

Many players — the vast majority — refuse the temptation. Path C is a rare path. Players who take it are explicitly committing to a dark-side arc; the Village's response is to acknowledge the choice and let them walk it out.

---

### Trial of Insight — The Council Hut

**Location:** Council Hut. **NPC:** Elder Saro Veck. **Tests:** Perception, intuition, the ability to see what others miss.

Saro is a quiet, watchful Bothan elder. The Insight Trial is the final test — and the only one that requires all four previous Trials complete. Saro presents you with **three holocron fragments**. Two are authentic recordings; one is a forgery that contains a doctrinal tell — a phrase a true Jedi master would never speak. Your task is to identify the forgery.

The mechanic is a `targeted_choice` — you examine the fragments and select which one is false. The forgery's identity is set deterministically per character (so the answer can't be looked up by another player), but the doctrinal tell is consistent in style: a phrase that subtly puts power before service, possession before stewardship, mastery before harmony. A player paying attention to Jedi philosophy throughout their arc will catch it. A player who hasn't been thinking about the philosophy will guess and have a 1-in-3 chance.

There's no cooldown on Insight if you fail — you can re-examine immediately. The Trial is forgiving in time but unforgiving in attention. Players who breeze through Insight without engaging with the content tend to fail because the holocron fragments are nuanced; the right answer is not obvious unless you're reading carefully.

On success, all five Trials are recorded as complete. The path forward opens to **the final audience** with Master Yarael.

---

## 5. Act 3 — The Choice

With all five Trials done, you return to the Master's Chamber and `talk Yarael`. The audience hook intercepts: this is no longer the first-audience scene. Yarael presents you with the choice.

The menu of paths depends on what happened in the Spirit Trial. If you refused the temptation, Paths A and B are both open. If you accepted it, only Path C is offered.

```
path                    # See the menu
path a       (or  a)    # Commit to Path A — Report to the Order
path b       (or  b)    # Commit to Path B — Stay with the Village
path c       (or  c)    # Commit to Path C — Walk the dark
```

The choice is **irreversible**. Once `village_choice_completed = 1` is set, the menu never reappears. Yarael acknowledges the road taken in any future conversation, but he does not offer a chance to change.

---

### Path A — Report to the Jedi Order

You take the road to the Coruscant Jedi Temple. Yarael writes a letter of introduction sealed with his old Order signet — a small artifact he hasn't touched in years. The letter is your bona fide. At the Temple, you are received by **Master Tova Resh**, the Order's intake-archives liaison (an original NPC, not a canonical figure — the system's Q1 policy keeps canonical Jedi like Mace Windu and Yoda strictly off-screen or referenced only by absence).

Mechanically:
- `force_sensitive` is set on your character.
- `jedi_path_unlocked = True` — the Jedi tutorial chain (Path A variant) becomes available.
- `village_chosen_path_a = True` is recorded.
- You **join the Jedi Order** at rank 0.
- You teleport to the **Jedi Temple Main Gate** in Coruscant.
- The kyber crystal from the Skill Trial is held over for later — the lightsaber-construction chain (a future content drop) will consume it; for now, it remains in your inventory as a pending marker.

You are now a recognized Padawan of the Order. The Padawan-Master system (Guide #14) becomes available. You can be bonded to a Master. You can attempt the formal Jedi Trials. You can be Knighted.

**The fictional cost.** Path A is the orthodoxy path. You're now a Jedi the Order knows about. Your training is structured. You answer to the Council in the formal sense. The advantage: institutional support, peers, formal recognition. The disadvantage: less independence; the Order may give you missions you don't want; you cannot easily walk away.

---

### Path B — Stay With the Village

Yarael nods slowly. He tells you that the Village is yours as much as anyone's. You are Force-trained, but the Order will not know it.

Mechanically:
- `force_sensitive` is set.
- `jedi_path_unlocked = True` (the Jedi chain is technically available, but you've chosen not to take it now — the system's stance is permissive: you're free to change your mind years later).
- `village_chosen_path_b = True` is recorded.
- You **join the Independent faction** if it exists, +50 reputation.
- You teleport to **Village Common Square**.
- The kyber crystal remains uncommitted in your inventory.

You are now an **independent Force-trained character**. You can be bonded as a Padawan in the Padawan-Master system, though Path B graduates often bond to other Path B graduates or to lapsed Order Knights rather than to actively-serving Order Masters. You can attempt the Knight promotion eventually.

**The fictional cost.** Path B is the independent path. You don't have the Order's resources, but you also don't have its obligations. Most Path B characters operate as freelance Force-trained agents — sometimes helping the Order quietly, sometimes the Hutts, sometimes the Republic, sometimes no one. The Village remains a home base; the other graduates of the Village are your community. The advantage: freedom, philosophical breadth, room to grow your own way. The disadvantage: no institutional backing, less formal training, the loneliness of working alone.

---

### Path C — Walk the Dark

Available only if Spirit was failed-into-locked. Yarael does not condemn; his sadness is real. He acknowledges that you have made a choice the Village will honor by letting you walk it out.

Mechanically:
- `force_sensitive` is set.
- `jedi_path_unlocked = False` — the Order will not have you; the Jedi chain remains locked.
- `dark_path_unlocked = True`.
- `village_chosen_path_c = True` is recorded.
- A `dark_contact_freq` marker is added to your character data — a comlink frequency that should reach a dark-side contact. Currently the frequency returns static; the content for the dark-side comlink will land in a future drop.
- You do **not** join any organization. Path C is exile by definition.
- You teleport to the **Dune Sea Anchor Stones**.

You are now a Force-sensitive character on a Sith-adjacent or dark-aligned arc. The mechanics of being a Sith proper haven't fully shipped at launch; what exists is the Force-sensitive status, the dark-path flag, and the connection to dark-side content that's being developed. Your character can use Force powers, accumulate Dark Side Points (which they will, by their nature), and be visible to other characters as Force-using-but-not-Jedi.

**The fictional cost.** Path C is the abandoned-by-the-Village path. You are not welcome at the Village (despite Yarael's sadness, the Village's collective response is one of mourning your loss, not embrace). You are unknown to the Order. You walk alone, with whatever dark-aligned NPCs and content emerges over time. The advantage: the deepest mechanical freedom — no faction obligations, no formal hierarchy. The disadvantage: profound isolation, the moral cost of the path, and a slow drift toward irreversible darkness if you continue to accumulate DSP.

---

## 6. After the Choice

Once Path A, B, or C is committed, the Village arc is mechanically done. Your character carries the path-flag forward; the Village remains in the world (you can revisit if Path B), but the trial system is closed for you. You don't repeat the Village.

For Path A graduates: the **Jedi Path — Order** tutorial chain (Guide #16) becomes available. Run it. It's the formal Order training arc — a short, structured experience that takes you from "Padawan at the Temple Gate" to "Padawan in the field." After that chain, you're a full participant in Padawan-Master play (Guide #14) and Jedi political life.

For Path B graduates: the **Jedi Path — Independent** tutorial chain becomes available. Same structure, different content — Yarael (in the chain's framing) hands you off to a network of independent contacts, gives you a starting set of allies, points you at independent missions. The chain ends with you back in Village Common Square or one of the wilderness landmarks with the marker of "you can take a Padawan eventually if you choose to."

For Path C graduates: there is no chain yet. The dark-side content path is in development. What you have is the path-flag, the dark-contact marker, the Force-power access, and the framing of your character as someone who has chosen a darker road. Your roleplay carries the weight; the mechanical content will deepen over time.

**The Padawan-Master system applies regardless of path.** All three path-graduates can eventually bond as Padawans (or as Masters, once they've been Knighted). The system doesn't enforce path-purity in bonding — a Path A Padawan might be bonded to a Path B Master if both consent. The Council might frown, but the engine allows it. Played-out narrative is yours.

---

## 7. The Village NPCs

The Village is small. Its NPCs are deliberately few, and each one matters. A quick roster:

**Master Yarael Kett** (Master's Chamber, Sealed Sanctum). The Village's founder and master. A human Jedi who left the Order before the Clone Wars and has lived in exile on Tatooine for decades. Walks slowly, speaks slowly, watches everything. The first-audience NPC. The Spirit Trial NPC. The final-choice NPC. Every player who completes the Village will have several scenes with him; he is the arc's emotional center.

**Elder Mira Delen** (Common Square). An older human Jedi who lost her own apprentice — the Order never knew the apprentice was hers — and came to the Village to mourn and teach. The Courage Trial NPC. Mira's voice is the voice of grief and resolve; her trial questions are personal, never abstract. Players who care about Mira's history tend to do well on her trial.

**Elder Korvas** (Meditation Caves). An ancient Trandoshan elder, deeply scarred. Lost his sight years ago. Teaches the discipline of the body. The Flesh Trial NPC. Korvas speaks only when needed; the trial is silence and presence, with him there as the witness.

**Elder Saro Veck** (Council Hut). A quiet Bothan elder who keeps the Village's records. Suspicious by nature; trusts the Trials to reveal what people will or won't do. The Insight Trial NPC. Her trial is the most precise: three holocrons, one doctrinal lie, an attentive eye. Saro is the only Village NPC who never warms to anyone; she remains professional regardless of how the candidate performs.

**Smith Daro** (Forge). A Twi'lek smith, old, kind, exacting. The Skill Trial NPC. Daro is the most accessible of the elders — he likes apprentices, he likes to talk while you work, he gives small encouragements that mean a lot. Players often remember Daro fondly.

**The Hermit** (Hermit's Hut, Dune Sea — not technically in the Village). The Hermit is not named; he gives no biography. He delivers the invitation. Once delivered, the Hermit becomes less central — players rarely return to him after Act 1 — but his role at the threshold of the arc is fundamental.

**Apprentice NPCs** (Apprentice Tents). A small number of unnamed apprentices who live in the Village. They are background-NPC presence; they don't have full dialogue trees, but they nod, they're seen, they make the place feel populated. Future content will likely deepen them.

---

## 8. Cooldowns and Pacing

A summary of the time gates in the Village arc, because they're the largest design choice and the biggest source of confusion:

| Gate | Duration | What it does |
|---|---|---|
| **Playtime gate** | 50 real-time hours | Must be passed before any Force-signs fire |
| **Sign accumulation** | Variable (~10–30 hours of play after gate) | 5 signs must accrue before invitation eligibility |
| **Act 1 → Act 2 cooldown** | 7 real-time days | After invitation, must wait before entering Trials |
| **Inter-Trial cooldown** | 14 real-time days | Between each successful Trial |
| **Skill Trial attempt cooldown** | 1 real-time hour | After failure on Skill Trial step (not full cooldown reset) |
| **Total minimum Village time** | ~2 months real-time | Even running everything optimally |

The 14-day inter-trial cooldown is the single largest behavioral lever. It means you cannot run the Village in a marathon weekend. You will be back to ordinary play between Trials — and that's the point. The Village isn't a discrete quest you finish; it's an arc that runs in the background of your ordinary play.

Many players treat the inter-trial weeks as a chance to develop other parts of their character — running missions in the Inner Rim, building reputation with a faction, doing RP scenes — while the next Trial is on the horizon but not yet available. The Village asks for patience and rewards it with deepening engagement.

---

## 9. Failure States and Edge Cases

A few things that can go wrong:

**You fail a Trial.** Most Trials forgive failure: you wait the cooldown (or the Skill Trial's 1-hour) and retry. Your progress in the Trial isn't lost (the Skill Trial step counter persists across failed attempts), and you don't lose any prior Trial completions. Only the Spirit Trial has a "soft failure" that's actually a Path C lock-in — see §4.

**You never accumulate signs.** Your character may have a low `force_predisposition` value (set at chargen — some characters are simply less Force-attuned than others). If signs are accumulating very slowly, you can speed it up by deliberately visiting the four force-resonant landmarks (Anchor Stones, Ruined Obelisk, Bantha Graveyard, Forgotten Jedi Shrine). Each landmark visit is a sign trigger.

**You quit during the trials.** Your progress is preserved. If you log out mid-Trial, you return to the same Trial state on your next login. There's no abandonment penalty; the engine is patient.

**You don't have the right skill at chargen.** The Skill Trial requires `craft_lightsaber`, which most non-Jedi characters don't have at chargen. The Trial doesn't expect you to be skilled at it; the difficulty (8/12/15) is calibrated for raw attribute pools, and you can earn the skill through play if needed. Players who run the Village often spend CP on `craft_lightsaber` while the Trial is on the horizon.

**You fail to find the Village.** The path from the Hermit's Hut to the Village runs through visible wilderness landmarks. If you're losing yourself in the dunes, walk back to the Hermit's Hut and try again — the path is in the wilderness terrain and adjacency hints. Players occasionally get stuck for an hour or two figuring out the geography; usually they find it eventually.

**You want to talk to the Master before the Trials are available.** Yarael's first audience runs once. After that, attempting to `talk Yarael` in the Master's Chamber (where the chosen-path menu lives) before the Trials are complete results in fallback dialogue — he is there, he is willing to receive you, but the Trials must be done before he presents the choice.

**You die during the Village arc.** Death works normally. The corpse mechanic applies (Guide #3). However, dying in the Village's lawless zone (the Dune Sea wilderness) is genuinely risky — your corpse persists for 4 hours, and the Village isn't somewhere other players easily reach to recover your gear for you. Be cautious. Don't carry your irreplaceable gear into Trial attempts you might fail at.

---

## 10. The Hidden Information

A few things the system tracks but doesn't display:

**Your `force_signs_accumulated` count.** Hidden until the invitation fires. Even then, you don't see "5 / 5" on your sheet.

**Your `force_predisposition` value.** Set at chargen. You can't see it. You won't be told whether you're a high-predisposition or low-predisposition character. The Village's Trials are the same regardless — you just take longer or shorter to be invited.

**The Spirit Trial path-lock.** When you fail Spirit into Path C, the engine sets `village_trial_spirit_path_c_locked = 1`, but you don't see this flag. You learn the outcome at the final audience when the menu only offers Path C.

**The Insight Trial's correct holocron.** Set deterministically per character. You can't get told which one is right; you have to discern it yourself.

**Your trial cooldowns.** You can ask Yarael or use `status` to see whether a Trial is currently available, but you don't get an exact countdown.

The hiddenness is the design. The Village arc is supposed to feel like discovery, not progression. Players who try to read the source code or comb through the YAML to optimize their path can do so (this guide includes the broad strokes) — but the arc is built so that even doing that doesn't reduce the time investment, only the uncertainty. You still have to play the 14 days between Trials.

---

## 11. The Roleplay of the Village

The mechanics are scaffolding. The Village is, more than any other system in SW_MUSH, a **roleplay arc**. The scenes you play in the Forge with Daro, the slow conversation with Mira about courage, the silent sit in the Caves with Korvas, the temptation scene in the Sealed Sanctum, the holocron examination with Saro — these are the substance of the arc. The dice rolls are minor compared to what you write in `cpose`.

Players who run the Village well treat it as a months-long story arc, not a series of mechanical hurdles. They:

- Visit the Village between Trials to spend time with the NPCs in non-Trial scenes. The elders have ambient dialogue lines and respond to small talk; players who put in time get to know them.
- Pose carefully through each Trial. The Trial of Flesh, for example, is mechanically a room-dwell, but the experience of posing your character through the discomfort is what makes it meaningful.
- Engage with other players who are also running the Village. There are usually a small handful of active Village candidates at any given time; running into another candidate at the Common Square is a real scene.
- Treat the Choice as the climax. The final audience with Yarael is a long scene if you let it be — he asks questions, you answer, the path is committed in roleplay before it's committed in command. Players who treat the Choice as just typing `path a` miss the most narratively rich moment of the arc.

The Village is also where the **Director AI** (Guide #26, forthcoming) tends to surface its most thoughtful content. The Village's NPCs are partly AI-driven — their ambient lines, their reactions to your specific RP, their small in-character notes — and the Director is calibrated to make the Village feel alive and observant. Players who pose substantively get richer responses than players who treat the NPCs as flavor text.

---

## 12. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `talk hermit` (at Hermit's Hut) | Triggers invitation if signs ≥ 5 |
| `talk Yarael` (at Master's Chamber) | First audience (Act 2 Step 4); later, final-choice menu |
| `talk Daro` (at Forge) | Engages Smith Daro for the Skill Trial |
| `trial skill` | Attempt one step of the Skill Trial |
| `talk Mira` (at Common Square) | Courage Trial dialogue |
| `talk Korvas` (at Meditation Caves) | Flesh Trial briefing |
| `trial flesh` | (Implicit — Korvas initiates) |
| `talk Yarael` (at Sealed Sanctum) | Spirit Trial scene |
| `talk Saro` (at Council Hut) | Insight Trial — examine the holocron fragments |
| `examine <fragment>` | Examine a specific holocron fragment |
| `accuse <fragment>` | Identify the forgery (Insight completion) |
| `path` | Show the final-choice menu |
| `path a` (or `a`) | Commit to Path A — Order |
| `path b` (or `b`) | Commit to Path B — Independent |
| `path c` (or `c`) | Commit to Path C — Dark |
| `status` (in Village) | Show your Village quest progress |

---

## 13. A Final Word

The Village exists to make Jedi recognition feel earned. The chargen path is closed for a reason: the system doesn't want a server full of cheap Jedi. It wants Jedi who came to the role through weeks of attention, dozens of scenes, and a final choice that meant something. The arc isn't fast because fast wouldn't feel right.

If you're considering running the Village: commit. Plan for 2+ months of real-time. Visit the wilderness landmarks deliberately. Pose your scenes carefully. Treat the elders as people you'll know across months of play, not as gates to bypass. Take the inter-Trial weeks seriously — they are not "dead time"; they are where your character grows into the Jedi-shape that the Trials will recognize.

If you're not considering running it: that's fine too. Most characters never see the Village, and the rest of the game has plenty to offer. The Village's existence makes the *idea* of Jedi present in the world (every character knows, vaguely, that Force-sensitivity exists; every character knows the Order is selective). You don't need to walk the path to benefit from the path existing.

When you finish, regardless of which path you take, you'll have done something most players never do. The Village remembers you. Master Yarael remembers you. The kyber crystal you forged at Daro's anvil is in your inventory or your future lightsaber. The path you took — Order, Independent, or Dark — is now part of your character's defining history.

That's the system's promise: take the time, do the work, and the Village will receive you.

---

*End of Guide #18 — The Jedi Village & Path A/B/C*
