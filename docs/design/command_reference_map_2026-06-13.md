# Command Reference Map — what a rename must update (snapshot 2026-06-13)

> ## ⚠️ THE REFERENCE SURFACE IS LARGE AND THIS MAP IS A STARTING SET, NOT COMPLETE
> Captured at commit `294679b` (Drop 36). The question "have we accounted for tutorials,
> guides, and other places that reference commands?" prompted this. The honest answer:
> command references are spread across SIX surfaces and the total is **~759+ command-shaped
> hits** — large enough that a single automated sweep UNDERCOUNTED it (the sweep covered
> chains densely but came back thin on guides/help/web). **Do NOT trust any one sweep as the
> full map.** Before EACH rename batch, regenerate the reference list for that batch's commands
> with a context-aware grep across the full surface set (patterns below), and enforce a guard
> test that no dropped key survives anywhere.

Companion to `command_syntax_rework_spec_v1.md` (approach) and
`command_catalog_snapshot_2026-06-13.md` (the rename catalog). This doc answers: *when we
rename command X, what else must change in the same drop?*

## The SIX reference surfaces (verified hit counts, HEAD)

| Surface | Files | Command-shaped hits | Breaks on clean rename? |
|---|---|---:|---|
| **Tutorial/quest chains** | `data/worlds/clone_wars/tutorials/chains.yaml` | ~28 commands × 200+ line-locs | **HARD** — teaches-lists, `command_executed`/`requires_first`/`skill_check_passed` completions go unreachable; npc prose hints go wrong |
| **Codex guides** | `data/guides/*.md` (26) | **803 backtick-command refs** | player-facing prose/tables — wrong instructions |
| **Help markdown** | `data/help/commands/*.md` + `topics/*.md` | ~313 hits; **69 files with `aliases:` front-matter** | help body wrong AND `aliases:` lists desync from parser |
| **In-code help** | `data/help_topics.py` (TOPIC_HELP) + `help_text=` in parsers | ~25+ | help body wrong |
| **Web client SPA** | `static/spa/m3_*.js` + `static/*.html` | **88 functional bindings** (`id:'attack'`, `data-cmd="fire"`) | **SILENT HARD break** — dead buttons; web-first = most-played surface |
| **Tests + parser internals** | `tests/**`, `parser/*_commands.py` cross-refs | ~many | test assertions fail; parser alias-deps break |

The web-client surface (`data-cmd="fire"`, `data-cmd="evade"`, combat-theater `id:'attack'`)
is the most dangerous because it breaks **silently** — no test failure, just a dead button —
and it's the web-first primary surface. A chain-only update (what the catalog alone covered)
would ship a broken client.

## Highest-reference commands (renaming these touches the most surfaces)

Each appears on 4–6 surfaces; these are the expensive renames:
`+missions` (~135 md + chains + help + parser), `attack` (~131 md + chains + web + parser —
**all 5 content surfaces**), `fire` (~114 + web cockpit), `dodge` (~104 + chains + web —
**all 5**), `search` (~83 + 10 chain skill-check steps), `+craft` (~75 + chains), `+sheet`
(~69 + every starter chain step 1), `scan` (~69 + chains + web), `talk` (~66 + 14 chain locs).

**`chain attempt`** is special: it's the ONLY mechanism for `skill_check_passed` chain steps
(~18 line-locs across jedi/hutt/armorer/hyperdrive chains). If its underlying command is
touched, EVERY skill-check chain step hard-breaks. Treat as a top-priority coupling.

## Noun-collision warning (false-positive trap)

Several command words are common English: `fire`, `board` (mission board / bounty board),
`pass`, `cover`, `close`, `scan`, `search`, `land`. A bare grep over prose floods with
non-command uses. The per-batch regeneration MUST match command-SHAPED occurrences only:
backtick-fenced `` `cmd` ``, fenced code blocks, markdown table cells, `cmd:`/`aliases:` YAML
keys, JS `id:'x'`/`data-cmd=` patterns — never bare-word match.

## Per-batch reference load (what to update when each rename batch runs)

- **Combat batch** (attack/dodge/parry/aim/cover/flee/…): chains combat steps (ll.150,603,
  964,1476,1631,1784,1936,2088 — `combat_won` completions, HARD); `help_topics.py:429-435`;
  `Guide_03_Ground_Combat.md` (~58 hits incl. the `| attack <target> |` syntax table);
  `help/commands/+combat.md` (~40-entry `aliases:` list + `cmd:` examples); `help/topics/`
  combat/dodge/cover/ranged/melee; web `m3_combat_theater.js` (`id:'attack'`/`id:'dodge'`) +
  `m3_cockpit.js`; `parser/combat_commands.py` name+aliases; ~12 test files.
- **Ship/space batch**: `help_topics.py:846-851,869-870`; `Guide_05_Space_Systems.md`;
  `help/commands/+ship|+pilot|+gunner|+sensors|+bridge.md`; `help/topics/` space/spacecombat/
  sensors/navigation/hyperdrive/shields; web `m3_cockpit.js` + gunner UI; `parser/space_commands.py`;
  chains scan refs (ll.1238-1250,1717-1742). **Watch `board` noun-collision.**
- **Run-on collapse**: chains is the epicenter — **`chain attempt` ll.334-2067 (~18 locs) is
  the skill_check_passed mechanism**; `+missions cis`/`+missions republic` prose; cross-module
  run-ons (questcomplete/collectbounty/buyresources).
- **Remaining game-system**: chains examine*/search/scan/+craft/+survey/+sheet/+missions/talk
  steps + their guide/help/web refs.
- **Switch-norm**: the help `aliases:` front-matter (69 files) MUST be rewritten or help +
  autocomplete desync from the parser — this batch's risk is desync, not crash.

## THE GUARD TEST (the discipline that makes clean-rename safe)

Per batch, a test reads the batch's dropped-key list (the rename manifest) and FAILS the build
if any dropped key survives in:
1. any `chains.yaml` teaches-list OR completion trigger (`requires_first`/`command_executed`/
   `skill_check_passed`) — these HARD-break progression;
2. any `data/guides/*.md` or `data/help/**/*.md` body OR `aliases:` front-matter;
3. any `static/spa/*.js` action-id / `data-cmd` / label;
4. any `parser/*` registry alias;
5. any test assertion;
6. any NPC/mission YAML command ref.
Additionally: assert every command id emitted by `static/spa/*.js` and every `aliases:` entry
in `help/commands/*.md` RESOLVES to a live parser command post-rename (catches the silent
web/help desync). Because there are no aliases, a survivor is a hard break or a wrong on-screen
instruction — the guard is non-negotiable.

## Regeneration command (run before each batch — do NOT trust a stale sweep)

```
# command-shaped refs for a given command across ALL surfaces:
grep -rnE "\`<cmd>\`|\"<cmd>\"|id:\s*'<cmd>'|data-cmd=\"<cmd>\"|^\s*(command|aliases?):.*<cmd>" \
  data/worlds/**/chains.yaml data/worlds/**/tutorial_*.yaml data/worlds/**/npcs*.yaml \
  data/guides/*.md data/help/commands/*.md data/help/topics/*.md data/help_topics.py \
  static/spa/*.js static/*.html parser/*_commands.py tests/
```

## Bottom line for the TODO

The rename pass's TRUE cost is dominated by the REFERENCE update, not the key change. The
catalog (rename targets) + this map (reference surfaces) + the per-batch guard test are the
three prep artifacts. The reference map is the one that must be REGENERATED per batch against
live HEAD — it is the largest and most volatile surface.
