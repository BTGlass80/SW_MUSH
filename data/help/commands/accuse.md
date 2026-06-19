---
key: accuse
title: Accuse — Commit Answer in Trial of Insight
category: "Commands: Village Quest"
summary: Accuse a holocron fragment of being the Sith-tainted one during the Trial of Insight. Use after examining all three fragments in the Council Hut. Wrong answers allow retries.
aliases: []
see_also: [examine, "+trial", "+village", gate, path]
tags: [village, quest, command]
access_level: 0
examples:
  - cmd: "accuse fragment_1"
    description: "Accuse fragment 1 of being the corrupted Sith fragment."
  - cmd: "accuse fragment_2"
    description: "Accuse fragment 2."
  - cmd: "accuse fragment_3"
    description: "Accuse fragment 3."
---

Commit your answer in the **Trial of Insight** — the third trial of
the Village Force-sensitive quest path.

**Syntax:**

    accuse fragment_<1|2|3>

**How it works:**

1. Enter the Council Hut and speak with Elder Saro Veck (`talk Veck`).
2. Examine each holocron fragment:
   - `examine fragment_1`
   - `examine fragment_2`
   - `examine fragment_3`
3. One fragment is tainted by the dark side. Accuse the one you
   believe carries the corruption.
4. Wrong answers are allowed — they trigger a retry with a hint.
   Correct: the trial advances.

**See also:** `examine` to inspect the fragments; `gate` for the
gate dialogue with Sister Vitha; `path` for the final path choice;
`+trial` for the full trial system overview.
