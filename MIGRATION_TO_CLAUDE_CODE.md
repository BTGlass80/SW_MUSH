# SW_MUSH — Migration to Claude Code

**Date:** 2026-06-12
**What this is:** The transition plan from the claude.ai Project workflow (sandbox → zip → Expand-Archive → test) to Claude Code working directly on your Windows tree, plus the new day-to-day workflow.

---

## 1. The mental model — what actually changes

Today's loop: Claude works in a throwaway sandbox, packages a root-mirrored zip, you extract it over your tree, you run the 7,700-test suite, and the next session starts blind until it re-greps everything. Three of your standing failure modes — phantom delivery, phantom-undelivered, and sandbox divergence — exist *only because* the model never touches the real tree.

Claude Code inverts that: the agent works **in** `SW_MUSH`, on the real HEAD, with git as the safety net and `run_all_tests.bat` runnable on demand. The zip discipline, the transfer step, and most of the verification-against-HEAD ritual dissolve into ordinary git workflow. That's the genuine win. The things that **don't** change: you still review every drop, the full suite is still the merge gate, and the invariants still need enforcing — they just move from chat memory into files in the repo (`CLAUDE.md`, `.claude/agents/`).

What replaces what:

| Old (claude.ai Project) | New (Claude Code) |
|---|---|
| Sandbox at `/home/claude/head` | Your actual working tree |
| Atomic root-mirrored zips + `Expand-Archive` | Git branches + commits |
| Project memory (userMemories) | `CLAUDE.md` at repo root (in this kit) |
| Project knowledge search over design docs | `docs/design/` in the repo, grep/read by the agent (in this kit) |
| Handoff docs for cross-session continuity | Handoff docs still useful + `claude --resume` + git log |
| "Grep HEAD before claiming" ritual | Agent greps the real tree natively |
| Targeted tests in sandbox, full suite on your box | Targeted tests in-loop, full suite as your merge gate (unchanged) |

## 2. Installation (pick your surface)

You're on Windows with VS Code. Recommended primary surface: **the Claude Code VS Code extension** — it gives you plan review, inline diffs, @-file mentions, and conversation tabs inside the editor you already use. Install: VS Code → Extensions (`Ctrl+Shift+X`) → search "Claude Code" → Install (publisher: Anthropic) → sign in with your claude.ai account on first launch. Any paid Claude subscription works; no API key needed. Docs: https://code.claude.com/docs/en/vs-code

Secondary surface: **the desktop app's Code tab** — what you already found. Code tab → Local → Select folder → `SW_MUSH`. The desktop app bundles Claude Code (no Node/CLI install needed), and on Windows it requires Git to be installed for local sessions. Good for sessions where you don't want the IDE open. Docs: https://code.claude.com/docs/en/desktop-quickstart

Optional: **the CLI** (`claude` in a terminal at the repo root) — the most scriptable surface; the VS Code extension bundles it anyway. The desktop app also offers Remote (cloud) sessions, which you should ignore for now: your suite and your SQLite DB are local.

## 3. Apply this kit

From the SW_MUSH project root, same as every drop:

```powershell
Expand-Archive -Path SW_MUSH_claude_code_migration_kit.zip -DestinationPath . -Force
```

It adds (and only adds — nothing in your engine is touched):

- `CLAUDE.md` — repo-root project memory. Every Claude Code session auto-loads it. This is the ported version of the standing invariants (funnel functions, era cleanness, phantom discipline, testing protocol, drop workflow, your communication style). **If you already have a CLAUDE.md (e.g., from running `/init`), diff before overwriting.**
- `docs/design/` — all 156 documents from the claude.ai Project (guides, handoffs, extractions, design docs, audits, the architecture doc, the systems-reference docx, the map HTML, the Mos Eisley PNG), plus a categorized `INDEX.md` with the authority-order rules at the top.
- `.claude/agents/` — three project subagents: `invariant-auditor` (read-only, checks every drop against the standing invariants), `test-runner` (targeted pytest + triage, keeps raw output out of the main context), `design-reviewer` (pinned to Opus, reviews economy/design changes against the doc corpus).

Deliberately **excluded**: `WEG40092.pdf` and `WEG40120.pdf`. Keep sourcebook PDFs out of the git repo (size + copyright, especially if the repo is or ever becomes public). The per-book `*_extraction_v1.md` files are the working references; if a session genuinely needs a PDF, keep them in a local gitignored folder and point the agent at them.

Then commit the kit as a meta-drop:

```powershell
git checkout -b chore/claude-code-migration
git add CLAUDE.md docs/design .claude
git commit -m "chore: Claude Code migration kit — CLAUDE.md, design doc corpus, project subagents"
```

One thing to check: if your hygiene tests assert anything about repo-root file inventory, run the full suite once after this commit before merging.

## 4. First session — a deliberate hello-world

Open the repo in VS Code, open Claude Code, and give it a real but bounded task that exercises the whole new loop:

> Read CLAUDE.md. Add a CHANGELOG.md entry and TODO.json note recording the Claude Code migration kit (docs corpus moved into docs/design/, project subagents added). Then run the targeted hygiene tests and confirm they pass.

This verifies in one shot: CLAUDE.md is being loaded, the agent can edit your real files, it follows the CHANGELOG+TODO-in-same-change rule, and it can run pytest on your box. Review the diff, run `run_all_tests.bat` yourself, merge. That's the new drop loop in miniature.

## 5. The new drop workflow

1. **Branch per drop.** `git checkout -b drop/<name>`. This replaces "atomic zip" as the unit of delivery — same atomicity, better rollback (`git checkout main` instead of restoring from backup).
2. **Plan first for anything non-trivial.** Press `Shift+Tab` to enter plan mode — the agent reads code and proposes a plan with read-only tools before touching anything. This is where your "Fable architects, others implement" vision actually lives day-to-day: plan on a strong model, review/edit the plan, then approve execution.
3. **Implement.** Default permission mode asks before edits/commands — keep that until trust is established. The agent runs targeted tests and AST validation in-loop; delegate to `test-runner` to keep its context clean.
4. **Audit.** "Use the invariant-auditor subagent on this diff." It returns PASS/FAIL per invariant with file:line evidence.
5. **Gate.** You run `run_all_tests.bat`. Green → CHANGELOG/TODO already in the commit (the agent knows the rule from CLAUDE.md) → merge.
6. **Design forks** still go to `design_calls_pending_brian` — the rule survives in CLAUDE.md.

Sessions persist: `--resume` (or the extension's history) picks up prior conversations, and because state lives in git + CHANGELOG + TODO.json, a *fresh* session re-orients itself by reading the repo — the handoff-doc habit becomes optional rather than load-bearing.

## 6. Model strategy (and the Fable question)

Claude Code lets you switch the main model mid-session with `/model`, and each subagent pins its own model in frontmatter (`haiku` / `sonnet` / `opus` / `fable` or a full model ID).

**The Fable economics you need to know:** Fable 5 is included in Pro/Max/Team plan limits only **until June 22, 2026** — after that it shifts to pay-as-you-go usage credits at API rates ($10/$50 per million tokens, roughly double Opus). Even inside the free window it burns plan limits about 2× as fast as Opus. So:

- **Now → June 22:** use Fable freely for the highest-leverage work — plan-mode sessions on big design questions (T3.19 telemetry catalog expansion, crafting integration pass, Kamino arc planning, economy reviews). This is a 10-day window to bank your hardest thinking cheaply.
- **After June 22:** default architecture/design reviews to **Opus**, implementation to **Sonnet**, mechanical chores to **Haiku**. Reserve Fable for occasional credit-funded sessions where the problem genuinely warrants it. (The `design-reviewer` subagent ships pinned to `opus` for exactly this reason; flip it to `fable` for special occasions.)
- Don't run long agentic implementation loops on Fable — that's paying architect rates for typing.

Practical default: **Sonnet as the main session model, plan mode + design-reviewer escalating to Opus, Fable by deliberate exception.**

## 7. Subagents vs. agent teams — your hierarchy vision, honestly assessed

Your vision (architect model → implementer models → an orchestrator managing it) maps to two real features:

**Subagents (stable — use these).** Markdown-defined specialists in `.claude/agents/`, each with its own system prompt, tool allowlist, and model. The main session delegates to them automatically when a task matches their description, or explicitly ("use the design-reviewer on this"). They run inside your session and report back; they don't talk to each other. Manage with `/agents`. This kit ships three; add more only when a role keeps recurring.

**Agent teams (experimental — wait, mostly).** Multiple full Claude Code sessions with a team lead, a shared task list, and peer-to-peer messaging — the literal version of your org chart. It exists behind a flag (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json or env, Claude Code v2.1.32+), with documented rough edges around session resumption and shutdown, and token costs that scale linearly per teammate (~3–5× a single session). Your codebase is also a poor fit for wide parallelism: one SQLite schema, one engine with tight seams, one extend-don't-add policy — parallel writers create merge conflicts, not speed. Where it *could* earn its cost later: read-heavy fan-out like the architecture-v52 reconciliation (one teammate per subsystem auditing docs vs. code) or bulk test triage. Treat it as a tool to revisit after a month of single-session fluency, not the foundation.

**The honest critique of the four-tier vision:** Claude Code isn't a separate "manager" you staff with a model — the main session *is* the orchestrator, running whatever model you picked. Stacking Fable-orchestrates-Opus-implements adds cost and loses context at every handoff (subagents return summaries, not their full reasoning). For a solo developer with strict invariants, the leaner mapping wins: strong model in plan mode = your architect; main session on Sonnet = your implementer; pinned subagents = your specialists; you = the actual orchestrator, same as now.

## 8. What stays in claude.ai (the hybrid)

Don't delete the Project. Keep claude.ai for:

- **Long-form design conversations** — the kind that produced the economy audits and the enrichment roadmap. Reading two WEG sourcebook PDFs side-by-side and arguing about faucet rates is chat-shaped work, and the Project's memory of *why* decisions were made doesn't transfer.
- **The sourcebook PDFs** live there already and shouldn't enter the repo.
- **Mobile/away-from-desk** thinking.
- **Archive** — past chats and the existing knowledge base remain searchable.

The discipline that makes the hybrid work: **the repo is now the single source of truth for documents.** New design docs get written by Claude Code into `docs/design/` (or produced in claude.ai and committed by you). The claude.ai Project knowledge is a frozen snapshot as of 2026-06-12 — don't update both. If a design conversation in claude.ai needs current repo state, paste the relevant files, or check Settings → Connectors for the GitHub connector so chats can read the repo directly.

When a claude.ai design session ends, its output is a `.md` you commit — the "drop" for design work is a document, exactly as it's been.

## 9. Risks and safety rails

- **Don't run with permissions bypassed** (`--dangerously-skip-permissions` / "YOLO mode") on this tree. Default ask-mode plus branch-per-drop is the right setting for a stateful game with a live SQLite DB.
- **Protect the database.** Add `*.db` / `*.sqlite*` (and any save-state) to `.gitignore` if not already, and tell the agent in-session before any task that touches migrations. Schema/state migration is your declared launch-risk area — keep those drops small and reviewed line-by-line.
- **Context rot in long sessions.** A multi-hour session can drift from the invariants as its context fills. Mitigations: CLAUDE.md reloads every session (keep it current — it's the new memory), prefer more shorter sessions over one marathon, and run the invariant-auditor before every handback.
- **Eager-agent risk.** Agentic Claude will sometimes "helpfully" refactor adjacent code. The extend-don't-add and additive-YAML rules are in CLAUDE.md, but review diffs for scope creep — `git diff --stat` first, every time.
- **The full suite is still yours.** Nothing in this migration moves the 7,700-test gate onto the agent by default. In-loop = targeted; gate = you. (Later, if you want, a stop-hook can auto-run smoke tests — see `SMOKE_CI_INTEGRATION_GUIDE.md` — but earn trust first.)
- **Usage limits are real.** Long agentic sessions consume plan limits much faster than chat. If you hit walls on your current plan, that's the signal to evaluate Max — measure a week of real usage first.

## 10. Day-one checklist

- [ ] Install Claude Code VS Code extension, sign in with your claude.ai account
- [ ] Confirm Git for Windows installed (desktop app Code tab requires it)
- [ ] Extract this kit at repo root; diff CLAUDE.md if one already exists
- [ ] `git checkout -b chore/claude-code-migration`, commit the kit
- [ ] Run the hello-world task from §4; review diff; run `run_all_tests.bat`; merge
- [ ] Try `/agents` and confirm the three subagents loaded
- [ ] Run one real drop (UI-5 bounty board is the queued candidate) through the §5 loop, in plan mode, on Sonnet
- [ ] Before June 22: spend the free Fable window on the T3.19 telemetry-catalog re-examination and/or the crafting integration design pass
- [ ] Decide nothing about agent teams for at least a month
