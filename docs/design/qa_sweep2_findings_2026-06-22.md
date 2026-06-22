# QA break-it sweep #2 — confirmed findings (2026-06-22)

Surfaces: chargen, mail/comms, medical/death/insurance, advancement. **8 of 11** hypotheses independently reproduced. (2 medical_death verifications were cut off by a session limit — unverified, re-run.)

## A. force_sensitive cluster — DEFERRED to design call `FORCE.chargen_sensitivity_representation` (balance/schema fork; do NOT fix piecemeal)

### A1. [BLOCKER] Force-sensitive character loses Force sensitivity on first login after web chargen
- symbol: `?`
- Refutation attempts all failed: (1) the 0D submit path IS reachable from the SPA as a standalone choice, not just via Jedi-path commitment; (2) reload genuinely re-derives force_sensitive=False (not a stale-cache artifact); (3) the lockout fires through the live parser, not just the bare from_db_dict. Affects BOTH chargen endpoints (handle_submit standalone + handle_create_character embedded/alt-char). force_points=2 is still persisted, so the symptom is "has 2 FP and was told they have Force powers, but every Force command rejects them." Root cause is the producer/consumer disagreement: producer stores 0D as the force-sensitive sentinel; consumer treats 0D as not-force-sensitive. Two plausi

### A2. [HIGH] +teach writes Force-skill dice to wrong JSON column — force_sensitive stays False after CP is spent
- symbol: `parser/padawan_master_training_commands.py:_ensure_padawan_skills_one_die (~line 561), engine/character.py:from_db_dict (~lines 877-886), engine/character.py:from_db_dict (~line 900-909 force-failsafe)`
- Severity high (not blocker): it is a credit/CP sink with no payoff (Padawan pays 6 CP per Force skill, gets a power they cannot fire) and the entire Padawan +teach progression path is dead, but it is not data-corrupting and the bonded-Padawan surface is a narrow, opt-in subsystem unlikely to gate launch boot. The fix is a genuine design fork for Brian, NOT a one-line patch: the whole padawan_master_training subsystem (and its tests, and _master_can_attempt_power's `attrs.get(skill_key)` fallback) treats control/sense/alter as SKILLS-column entries, while the rest of the engine (force_commands, character.force_sensitive derivation, get_attribute) treats them as ATTRIBUTES. The two halves disa

### A3. [MEDIUM] train control/sense/alter is a silent dead-end — no player path exists to raise Force attributes
- symbol: `parser/cp_commands.py:143-149 (SkillRegistry.get rejects control/sense/alter), data/skills.yaml (no Force attribute entries)`
- Severity medium (not blocker/high): it's a missing-progression / dead-end, not a crash, data-corruption, or credit-integrity bug — CP is correctly NOT consumed on the failed attempt, so nothing is lost. But it's a genuine launch-quality gap because the entire Jedi class has no advancement loop for its defining stats, and the game's own +powers text points players at a nonexistent mechanism. This is a design fork, not a one-line fix: the right resolution is a decision for Brian (extend `train` to handle control/sense/alter as attributes with a WEG R&E Force-attribute advancement cost, vs. a dedicated `+teach`/meditation/trial path), so it belongs in design_calls_pending_brian rather than an a

### A4. [MEDIUM] test_character.yaml seeds control/sense/alter into the skills JSON column — phantom force entries that are never read for force_sensitive derivation
- symbol: `data/worlds/clone_wars/test_character.yaml (skills: control: 8D, sense: 8D, alter: 7D), engine/character.py:from_db_dict:877-909 (attributes-only force_sensitive derivation)`
- Severity raised from the hypothesis's "low" to MEDIUM: not a latent test-only artifact but a real broken dev account in the production CW build (and the harness inherits the same YAML, so any default-spawned character is non-force regardless of template). Two clean fixes exist (either is a one-liner-class change, design call for Brian): (A) author-side — move the YAML's force dice to TOP-LEVEL `attributes.control/sense/alter` (where from_db_dict reads them); or (B) loader-side — have from_db_dict also honor a `force_skills` nested dict and/or the explicit `force_sensitive` flag. Note the skills-column control/sense/alter (YAML lines 173-175, self-described as "duplicates ... preserved for pa

## B. MECHANICAL — fix now (independent of the force_sensitive decision)

### B1. [MEDIUM] @mail/reply to soft-deleted mail bypasses is_deleted gate — sends reply from trash
- symbol: `parser/mail_commands.py:438-445 (_reply SQL query)`
- repro: 1. Log in as Sender. 2. @mail/quick Recip/Subj = Original body 3. Log in as Recip (second session). 4. @mail  — note the mail_id in the listing. 5. @mail/delete <id>  — 'marked for deletion' confirmed. 6. @mail/reply <id> = I am replying from the trash.  — Expected: 'not found'. Actual: '[MAIL SENT]' — reply delivered despite is_deleted=1. Root cause: parser/mail_commands.py:443 WHERE clause missi
- fix (verified): Severity medium is fair — it is a logic-integrity / UX-trust defect, not a security or economy hole: the reply still goes only to the original sender's own id, no credits move, no cross-character data leaks (the reply re-quotes nothing of the original; it only reuses the sender_id + subject, both of which the recipient legitimately received before deleting). Worst-case impact is sending a "phantom" reply on mail the user believes they trashed, plus the subject of a deleted thread being reusable. No crash, no traceback.

SCOPE NOTE for the fix (relevant, same root-cause class): _forward has the IDENTICAL gap — parser/mail_commands.py:516-522, 'WHERE m.id = ? AND mr.char_id = ?' with no is_deleted gate. I confirmed this by reading the code (did not separately drive it, but it is the same que

### B2. [MEDIUM] Wound recovery tick (tick_handlers_death) silently skips wounded characters whose session-cache is stale
- symbol: `server/tick_handlers_death.py:86-90 — fast-path cache check before DB read`
- repro: 1. Same stale cache setup: on_pc_death sets DB wound_state='wounded' but session cache 'healthy'. 2. Leave the player idle (no commands typed — because typing any command would trigger _execute's refresh). 3. Wait 1 hour. 4. The wound_recovery tick in server/tick_handlers_death.py:86-90 reads `cached_state = char.get('wound_state') or 'healthy'`. If cache='healthy', the tick SKIPS this character (
- fix (verified): Suggested fix (for Brian to adjudicate, not applied — read-only task): add `sess.character["wound_clear_at"] = clear_at` next to the existing `sess.character["wound_state"] = "wounded"` at parser/combat_commands.py:1421 (on_pc_death could return clear_at, or the caller can re-read it), so the tick's line-90 fast-path sees the real clock. Alternatively, make the tick fall through to the authoritative DB read when state is 'wounded' but cached_clear_at<=0 (treat 0 as "unknown, check DB") rather than skipping. Note the existing test suite (tests/test_pg1_death_b_loot_and_recovery.py) only exercises the tick with a fully-correct DB+cache and never simulates the combat->cache-sync gap, which is why it passes while this slips through.

Files of record: server/tick_handlers_death.py:81-102 (tick 

### B3. [LOW] CRASH: @mail/reply to mail with nonexistent-sender_id raises FK IntegrityError
- symbol: `parser/mail_commands.py:359 (_do_send INSERT mail_recipients), triggered from _reply:463`
- repro: Requires admin DB access to set up: 1. Admin creates char A, sends mail to char B, then hard-deletes char A from the characters table. 2. Log in as char B. 3. @mail — see the mail from the now-deleted char. 4. @mail/read <id> — reads fine (LEFT JOIN returns sender_name=NULL). 5. @mail/reply <id> = reply text — Expected: clean error. Actual: 'An error occurred processing your command' with FK const
- fix (verified): Net: the defect class is genuine and I reproduced both the `=`-form generic-error crash AND a worse silent-crash in the open-editor reply path. The fix is trivial and worth doing defensively: in _do_send (parser/mail_commands.py:334) skip/resolve recipients whose char_id has no characters row (or wrap the INSERT loop and report "recipient no longer exists"), and/or have _read/_reply detect sender_name IS NULL (orphaned sender) and refuse to reply with a clean "you can't reply — sender no longer exists." But severity is low, not high: the trigger requires raw DB manipulation, not any in-game action (soft-delete is the only in-game char deletion, and a raw hard-delete is itself FK-blocked by ~30 other tables). If a hard-delete admin tool or a mail-archival/restore feature is ever added, this

### B4. [LOW] LEAK: @mail/reply compose-editor shows 'To: None' when sender character is missing
- symbol: `parser/mail_commands.py:474 (_reply compose-editor display line)`
- repro: Same setup as finding #2 (mail with deleted sender). 1. @mail/reply <id> (no = body) — compose editor opens showing 'To: None'. 2. Type ~q to cancel. The 'To: None' is the Python None repr surfaced to the player; it looks like an internal error. Fix: apply the same fallback used on line 469: orig['sender_name'] or f'#{orig["sender_id"]}'
- fix (verified): Severity confirmed LOW: purely cosmetic. No crash/traceback, no data corruption; the compose state still carries to=[orig sender_id] and the reply can still be sent or cancelled (~q). The user just sees a confusing internal-looking "To: None".

Two corrections to the hypothesis's framing, both making the bug MORE reachable than stated (not less):
1) Effort is NOT "E4 — deep." The realistic trigger is the COMMON case, not a hard-deleted character: any player who replies (with no inline body, to open the editor) to a SYSTEM mail — stipend deposit, BH bounty payout, stale-claim warning — hits it, because send_system_mail uses sender_id=0. This is a first-class, in-production producer. Effort to verify is closer to E1/E2.
2) The fix the hypothesis names is exactly right and minimal: change mai
