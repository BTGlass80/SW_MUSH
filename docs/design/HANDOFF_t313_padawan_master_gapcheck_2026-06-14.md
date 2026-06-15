# T3.13 Padawan/Master — Gap-check findings

*Main-march session, 2026-06-14 PM. 14-area verification workflow + adversarial
recheck (0 gaps refuted; run wf_ca09510e-2ba) vs `padawan_master_system_design_v1.md`
+ roadmap expansion. Worktree C:/SW_MUSH_live.*

## Headline
The **bond + trials core is solid** (schema, +bond establishment, +master/+padawan,
training cmds, +trials/+endorse/+knight all built). The gaps are the **approval
mechanics, falls, shared-memory, dissolution-completeness**, and the **expansion**
(council / lineage / re-assignment). Less complete than Cities.

## Status (14 areas)
| Area | Overall | Effort | Note |
|------|---------|--------|------|
| P1 bond schema | **DONE** | — | master_padawan_bond + indexes + 1-active constraint |
| P2 bond establishment (+bond/@bond) | **DONE** | — | propose/accept/decline, cap, single-bond, admin |
| P3 shared awareness (+master/+padawan) | PARTIAL | small | **+padawan trials parity SHIPPED**; +who marker + richer status deferred |
| P4 training (+teach/+learn/+spar) | PARTIAL | medium | +spar is a CP-award event, not a real non-lethal combat loop (needs engine/combat.py = **avoid lane**) |
| P5 approval weight (+approve/+deny/+authorize) | MISSING | large | **DESIGN FORK logged** (pending-approval store) |
| P6 shared narrative memory | MISSING | medium | no bond-keyed cross-write |
| P7 trials + knight ceremony | **DONE** | — | (5-trial automation + Trial-of-Spirit deferred post-launch per §11) |
| P8 falls (DSP threshold/stages/mirror) | PARTIAL | medium | partial; redemption deferred per §7.4 |
| P9 dissolution | PARTIAL→ | small | **+leave-master SHIPPED**; master_killed hook deferred (death.py, combat-adjacent) |
| P10 director integration | MISSING | medium | **avoid director lane (Brian)** |
| P11 command surface | PARTIAL | medium | approval trio (P5) + +leave-master (shipped) were the gaps |
| P12 council *(expansion)* | MISSING | large | no Council mechanic |
| P13 lineage trees *(expansion)* | MISSING | medium | no ancestry view |
| P14 re-assignment + waitlist *(expansion)* | MISSING | large | gated on chargen/launch-strategy |

## SHIPPED this session (drop `pm-leave-master`, parser-only)
- **+leave-master** (P9/P11): Padawan-initiated voluntary dissolution — the mirror of `+release` (padawans previously could NOT leave their Master). Reason REQUIRED (design §8 "discourage impulsive breaks"); `dissolve_bond(reason="padawan_voluntary: <text>")`; Master notified + bilateral audit log. Alias `leavemaster`.
- **+padawan trials parity** (P3): the Master's `+padawan` view now shows each Padawan's "Trials passed: N of 5" (was only in `+master`).
- `tests/test_pm_leave_master.py` (13) + PM2 regression (34) green.

## Settled / deferred
- **+forcebond:** Brian 2026-06-14 — KEEP free bond-sensing via +master/+padawan; do NOT add an FP-gated +forcebond. (Not a gap.)
- **DEFERRED to the loop / coordination:**
  - **P5 approval mechanics** (+approve/+deny/+authorize) — large; **needs a design decision first** (where pending approvals are tracked — in-memory vs DB; see logged fork `PM.approval_pending_store`) AND a cross-cutting gating layer (intercept gated Padawan actions). The companion to §5.3.
  - **P4 +spar combat-mode** — wire +spar into engine/combat.py non-lethal mode (**combat lane = avoid**).
  - **P3 +who marker** (builtin_commands.py WhoCommand — audit-adjacent file) + richer +master status (needs combat in-combat flag = avoid lane).
  - **P9 master_killed hook** — engine/death.py on_pc_death → dissolve bonds + trauma (death.py is combat-adjacent).
  - **P6 shared narrative memory**, **P8 falls** — medium engine work.
  - **P10 director integration** — director lane (avoid).
  - **P12 council / P13 lineage / P14 re-assignment+waitlist** — the roadmap expansion (large; council+lineage are net-new systems).
