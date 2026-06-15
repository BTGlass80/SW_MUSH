# SW_MUSH Senior Developer Code Audit

## Verdict

The project is technically impressive and unusually test-heavy for a solo-developed game. The architecture shows a strong habit of identifying invariants and locking them with tests. The codebase is also large, organically grown, and now carries the predictable risks of rapid AI-assisted iteration: monolith files, broad exception handling, documentation drift, command-registry collisions, mixed old/new patterns, and a few high-impact seams where green tests may not mean safe behavior.

The right next move is **not a rewrite**. The right next move is a series of behavior-preserving hardening passes.

## Codebase shape observed

Approximate stripped-upload counts:

| Surface | Count / size |
|---|---:|
| Python files total | 812 |
| App Python files under `engine`, `parser`, `server`, `ai`, `db`, `tools` | 275 |
| App Python lines | ~176k |
| Total Python lines including tests/tools | ~372k |
| `tests/test_*.py` files | 469 |

Largest app files:

| File | Approx. lines | Risk |
|---|---:|---|
| `parser/space_commands.py` | 6,752 | Command/router and state complexity. |
| `parser/builtin_commands.py` | 5,757 | Core command coupling. |
| `db/database.py` | 5,322 | Persistence and schema concentration. |
| `engine/player_cities.py` | 5,044 | Large domain module. |
| `engine/housing.py` | 3,862 | Large domain module. |
| `parser/combat_commands.py` | 3,464 | Combat state mutation concentration. |
| `engine/wilderness_anomalies.py` | 3,526 | Content/mechanics coupling. |

Large files alone are not a bug. But they are where regression risk concentrates.

## Highest-priority findings

### DEV-1 — P0: `@newpassword` appears to write a SHA-256 hash into a bcrypt field.

`parser/mux_commands.py::NewPasswordCommand` uses:

```python
import hashlib
hashed = hashlib.sha256(new_pass.encode()).hexdigest()
UPDATE accounts SET password_hash = ?
```

Normal authentication uses bcrypt:

```python
bcrypt.checkpw(password.encode("utf-8"), account["password_hash"].encode("utf-8"))
```

This likely means an admin password reset makes the target account unable to log in. Depending on bcrypt behavior, it may also produce bad-hash exceptions on login.

**Fix:** use the same bcrypt hashing path as account creation. Add a test:

1. create account,
2. admin resets password,
3. old password fails,
4. new password authenticates,
5. stored hash starts with a bcrypt prefix and is not the raw password or SHA hex.

Also align password length policy: normal account creation appears stricter than reset.

### DEV-2 — P1: Broad `except Exception` use needs a policy.

I counted roughly 1,858 `except Exception` handlers across app code. Many are probably intentional because the game is player-facing and should not crash on flavor failure. But broad exceptions become dangerous when they cover:

- credit movement,
- CP/FP/rep mutation,
- inventory mutation,
- combat result application,
- quest completion,
- migration,
- account/security operations,
- command registration,
- AI output validation.

**Recommendation:** classify exception zones.

| Zone | Policy |
|---|---|
| Optional flavor, ambient AI, non-authoritative UI hints | Fail open, log debug or warning. |
| Player command parsing before mutation | Fail cleanly, no mutation. |
| Value movement/inventory/combat/quest completion | Fail closed, transaction rollback, log error. |
| Account/security/admin | Fail closed, alert admin. |
| Migration/startup/schema | Fail hard. |

Then add an AST guard that flags new broad exceptions in protected directories unless they include an allowlist comment/tag.

### DEV-3 — P1: Command registry collisions should be explicit and allowlisted.

The command registry is simple and useful, but duplicate command keys/aliases can overwrite or create ambiguous partial matches unless managed deliberately. I found multiple duplicate keys/aliases, many likely intentional umbrella commands or smart dispatch cases:

- `accept`,
- `market`,
- `investigate`,
- `listen`,
- `who`,
- `repair`,
- `+bridge`,
- `+ship`,
- various admin/build aliases.

The goal is not to remove all duplicates. The goal is to prevent accidental future collisions.

**Recommendation:** create a command registry collision test:

- enumerate every command key and alias,
- fail on new duplicates,
- maintain an explicit allowlist with reason strings,
- separately test partial-match ambiguity.

### DEV-4 — P1: Session-cache mutation should follow authoritative persistence, not precede it.

Some value paths mutate `ctx.session.character` or local character dicts near/before DB updates. This is common in game code but risky.

**Desired invariant:** all value movement and inventory mutation returns a canonical state, then session cache updates from that state.

Bad pattern:

```python
char["credits"] -= amount
await db.adjust_credits(...)
```

Better pattern:

```python
new_balance = await db.adjust_credits(...)
char["credits"] = new_balance
```

This matters if DB writes fail, if `adjust_credits` later adds tax/seizure/bonus logic, or if multiple sessions touch the same character.

### DEV-5 — P1: The web client has a privileged HTML injection seam.

The client generally escapes text, but message rendering has paths that trust `ev.html` and assign it to `innerHTML`. Even if current server events do not expose user-controlled HTML, this is a future footgun.

**Recommendation:** remove `ev.html` entirely unless absolutely needed. If needed, restrict it to server-generated allowlisted message types and sanitize centrally. Add a regression test that user-originated pose/say/page/channel/whisper text cannot produce HTML execution.

### DEV-6 — P1: Documentation drift will poison future AI-assisted work.

Examples:

- `README.md` says “107 tests” while the project is far larger.
- `pytest.ini` comments about `pytest-timeout` conflict with `requirements.txt`.
- economy guide references policy that architecture says changed.
- architecture header/body/closing notes appear to include count/schema evolution that must be reconciled carefully.

**Recommendation:** add a docs truth pass and make Claude treat architecture/TODO/changelog precedence explicitly.

## Architecture observations

### What is good

- Explicit invariants.
- Large regression suite.
- Schema version discipline.
- Split of pure/runtime in some subsystems.
- Credit ledger chokepoint.
- Vendor and trainer flags instead of implicit room magic.
- Canonical skill-key resolution.
- Era-guard work around LLM outputs.
- Fail-open philosophy for optional LLM/flavor systems.

### What is risky

- Large command modules mix parsing, permissions, business logic, output formatting, and state mutation.
- `db/database.py` concentrates schema, migrations, persistence APIs, and domain-specific helpers.
- Some systems appear to have both legacy and new implementations alive at once.
- Command aliases and partial matching are powerful but fragile.
- Tests are numerous but likely mostly example-based rather than mutation/property/load based.

## Networking and runtime notes

### WebSocket/Telnet dual stack

The dual-client architecture is appropriate for a MUSH-to-web evolution. The risk is inconsistent feature parity and duplicated output assumptions. Every new player-facing mechanic should answer:

- Is this available via telnet?
- Is it visible in the web client?
- Does the web client get structured data or only text?
- Does the command have staged/confirm behavior if dangerous?

### Binding and exposure

The server appears to bind broadly by default. That may be fine for LAN/dev, but before any external test you need a launch profile:

- explicit host binding,
- reverse proxy/TLS plan,
- admin IP/rate limits,
- login rate limiting,
- command spam limits,
- max WebSocket connections,
- backup/restart procedure.

### Token/session behavior

Process-local HMAC token secrets are acceptable for a private local server but should be documented: tokens invalidate on restart. HMAC signature truncation is probably not your biggest risk, but longer signatures are cheap.

## Dependencies and tooling

### Requirements

The Python dependency footprint looks small, which is good. But version ranges using `>=` are a reproducibility risk.

**Recommendation:** for launch/playtest, add a locked environment:

- `requirements-lock.txt` or `uv.lock`/`pip-tools`,
- Python version pin,
- `pip-audit` or equivalent,
- reproducible Windows setup script.

### JavaScript tooling

The package footprint is tiny, but the UI is large. Add minimal JS checks:

- existing jsdom tests,
- lint pass if feasible,
- no-inline-handler target over time,
- DOM XSS regression tests,
- keyboard navigation tests.

## Test strategy recommendations

Local tests passing is a strong signal. The next gains are not more ordinary unit tests; they are blind-spot tests.

### Add these invariant tests

1. **Password reset auth test** — reset and authenticate.
2. **Command collision allowlist** — fail on new unapproved duplicate key/alias.
3. **No privileged client HTML** — user text cannot become `innerHTML`.
4. **Value mutation atomicity** — credit/CP/FP/rep/inventory mutations must use services/logs.
5. **Exception policy AST guard** — no new broad exceptions in authoritative mutation zones.
6. **Docs drift smoke** — README test count/version statements cannot be wildly stale.
7. **Migration rehearsal** — create old schema/save, migrate to current, preserve key fields.
8. **First-session journey** — account creation through first meaningful reward.
9. **Economy simulation** — faucet/sink macro run.
10. **UI staged-command behavior** — risky actions stage/confirm consistently.

### Add these non-unit checks

- `ruff` or equivalent lint.
- `pyright`/`mypy` on selected modules, even if gradual.
- `bandit` focused on auth/file/network issues.
- coverage only for critical modules, not vanity global coverage.
- mutation testing on ledger/registry/auth functions.
- load test: 50–100 idle/active sessions.

## Refactoring strategy

Do not rewrite. Extract seams.

### Phase 1 — service wrappers

For each high-risk monolith, create service functions while preserving command behavior:

- `CreditService`,
- `InventoryService`,
- `CombatEquipmentService`,
- `CommandRegistryAudit`,
- `CharacterProgressionService`,
- `VendorService`,
- `ContrabandService`.

Commands should parse and call services. Services should mutate state and return result objects. UI rendering should format result objects.

### Phase 2 — result objects

Replace ad hoc strings with result structures for important mechanics:

```python
@dataclass
class ActionResult:
    ok: bool
    player_text: str
    structured_event: dict
    mutations: list[Mutation]
    next_actions: list[str]
```

This helps the web client answer “what happened / why / what next.”

### Phase 3 — split UI protocol from text output

The web client should not parse MUSH prose for everything. Keep text for telnet, but send structured events for:

- combat,
- inventory,
- crafting,
- vendors,
- quests,
- factions,
- maps,
- opportunities,
- errors/refusals.

## Specific Claude prompts

### Prompt: fix password reset

> Verify `parser/mux_commands.py::NewPasswordCommand` against `db/database.py::create_account` and `authenticate`. It appears to store SHA-256 while login expects bcrypt. Write a failing regression test first: create account, reset password through the command or command handler, authenticate with new password, ensure old password fails, ensure stored hash is bcrypt. Then fix the command using the same bcrypt helper/path as account creation. Also align password length policy.

### Prompt: command collision audit

> Build an audit of every registered command key and alias in SW_MUSH. Identify duplicates and partial-match ambiguities. Do not assume duplicates are bugs; classify them as intentional umbrella dispatch, smart dispatch, legacy alias, or accidental collision. Add a test that fails on any new duplicate unless it appears in an explicit allowlist with a reason.

### Prompt: exception policy audit

> Audit all broad `except Exception` handlers. Classify each as flavor/UI fail-open, optional AI fail-open, command parse fail-clean, or authoritative mutation fail-closed. Produce a table of high-risk handlers around credits, CP, FP, rep, inventory, combat, quest completion, migration, account/auth, and admin commands. Add an AST guard or lint-style test preventing new broad exceptions in protected mutation zones without an allowlist tag.

### Prompt: privileged HTML seam

> Audit `static/client.html` and SPA modules for every `innerHTML` assignment and every path that accepts `ev.html` or server-provided HTML. Determine which paths can be reached by user-authored text. Replace privileged HTML with escaped text or structured renderers, or add a central sanitizer/allowlist. Add jsdom tests proving say/pose/page/channel/whisper text cannot inject HTML.
