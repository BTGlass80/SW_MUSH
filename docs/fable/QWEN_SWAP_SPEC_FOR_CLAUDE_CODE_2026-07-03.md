# QWEN SWAP SPEC — Ollama model migration: `mistral` → `qwen3.5:9b` (Fable, 2026-07-03)

**Consumption contract:** same as `FINDINGS_FOR_CLAUDE_CODE_2026-07-02.md` — verify every symbol at your HEAD before writing code (tree pinned here = Brian's 2026-07-02 22:04 zip). Brian has picked **Qwen3.5-9B** (official Ollama tag). This doc is the implementation tweak-list only; impact narrative lives in the chat thread.

**Architecture facts that make this cheap (verified live):**
- Transport is `/api/chat` with a messages array (`ai/providers.py:191-212`); **zero `[INST]` tokens anywhere** in ai/engine — Ollama applies each model's own template server-side, so Mistral→Qwen chat-template compatibility is a non-issue.
- Runtime era guard already fences generated text on **both** paths: barks per-line via `is_era_clean` (`engine/idle_queue.py:121`, drop-log at ~124-128) and talk via `era_violations` → canned in-era fallback that is **never persisted to NPC memory** (`ai/npc_brain.py:333-350`). Qwen's richer SW knowledge therefore changes the *drop rate*, never the leak surface.
- Provider abstraction + mock provider mean the test suite is model-agnostic; no test churn expected beyond the new slices below.

---

## 1 · Config touchpoints (the actual swap)

`ai/providers.py` — four strings:
- `:49  default_model: str = "mistral:latest"` → `"qwen3.5:9b"`
- `:60  tier1_model: str = "mistral:latest"`
- `:61  tier2_model: str = "mistral:latest"`  ← comment on this line already says to upgrade it when a bigger model exists — **use the seam**
- `:114 default_model: str = "mistral:7b"` (OllamaProvider ctor default)

**Staged rollout (recommended):** Drop A flips **tier2 only** (premium story NPCs) → live A/B against tier1 Mistral for a day of talk traffic; Drop B flips tier1 + both defaults. Keep `mistral:latest` pulled and honored via an env override (`OLLAMA_MODEL`-style) for one release as rollback.

Also update the standing invariant line ("Mistral 7B only, RTX 3070 8GB") in **CLAUDE.md** and the architecture doc §AI in the same drop as Drop B, per house rules.

---

## 2 · 🔴 The landmine: Ollama drops `format:"json"` for qwen3.5 when thinking is off

- Qwen3.5 **Small** models (0.8B–9B, incl. this one) ship with **thinking disabled by default** (Unsloth model docs: https://unsloth.ai/docs/models/qwen3.5). Good for us — no `<think>` preambles.
- **But** ollama/ollama **#14645** (repro'd on 0.17.6, Mar 2026): with the qwen3.5 series, the JSON grammar mask is only engaged after an end-of-thinking token — which the non-thinking template never emits — so **`format:"json"` is silently ignored when `think=false`**. Companion issue #14617 covers modelfile-level thinking control being ineffective.
- **Blast radius at HEAD — all three `json_mode=True` call sites** (each becomes `payload["format"]="json"` at `providers.py:204-205`):
  1. `engine/idle_queue.py:96` — ambient-bark task (the 33-NPC pool refresh)
  2. `engine/idle_queue.py:372` — the second JSON-array task (5-string output, prompt built at `:364`)
  3. `ai/intent_parser.py:129` — intent/tactical parsing
- **Failure mode is silent starvation, not an error:** parse fails → task returns → bark pools go stale/empty; only trace is the existing log line.

**Required actions:**
1. **Install-time verification** (the bug may be fixed by the current Ollama — check before hardening assumptions):
   ```
   curl -s http://localhost:11434/api/chat -d '{
     "model":"qwen3.5:9b","stream":false,"format":"json",
     "messages":[{"role":"user","content":"List three colors as a JSON array of strings, nothing else."}]}'
   ```
   Content must be valid JSON. Record the Ollama version + result in the drop's CHANGELOG entry.
2. **Harden the bark parser regardless** (`engine/idle_queue.py` ~102-125, and mirror at the `:372` task's parse): the fence-strip exists; add a fallback that extracts the **first balanced `[` … `]` substring** and `json.loads` that before giving up. Keep the length/era filters unchanged downstream.
3. `ai/intent_parser.py`: confirm its parse path tolerates non-JSON-constrained output the same way (fence-strip + substring fallback); add if absent.

**Suggested test slice** (`tests/test_qwen_json_parse_hardening_*.py`): pure-function cases against the parse helper — clean array; fenced ```json array; prose-then-array ("Here are five lines: [ … ]"); array-then-prose; `<think>…</think>` preamble then array (future-proofs thinking-enabled configs); malformed → returns empty without raising; era filter still applied post-parse.

---

## 3 · Provider extension (required by §4 and §5 — the options block is too narrow today)

`ai/providers.py:198-201` currently sends **only** `temperature` + `num_predict`. The swap needs:
- **`options` passthrough:** accept an optional `options: dict` on `generate()` and merge into the payload's `options` (explicit args win). Needed keys immediately: `num_ctx`, `top_p`, `top_k`, `presence_penalty`.
- **`keep_alive` passthrough:** top-level payload key (e.g. `"keep_alive": "30m"`), config-defaulted, so the 9B doesn't cold-load (~longer than 7B) after idle gaps between queue ticks.
- Thread a per-call `options` from the idle-queue tasks and `npc_brain` (both already pass `temperature`/`max_tokens`; extend the signature, default `None` = today's behavior). Mock provider: accept-and-ignore.

**Suggested tests:** payload-shape unit tests on `OllamaProvider` (monkeypatch the session): json_mode ⇒ `format:"json"` present; options merge precedence; keep_alive present when configured; absent-options ⇒ byte-identical payload to today (regression pin).

---

## 4 · VRAM plan (8GB 3070, and why context caps are mandatory)

- The official Ollama qwen3.5 tag bundles the vision projector (~1.4GB fixed overhead for our text-only workload), and the text-only-GGUF escape hatch is **currently closed**: Unsloth's docs state qwen3.5 GGUFs don't work in Ollama because of the separate mmproj vision files (llama.cpp-backend only) — and our provider targets the Ollama API, so we eat the overhead. Budget ≈ 5.7-6GB weights (Q4) + ~1.4GB mmproj + KV.
- Therefore set **per-lane `num_ctx`** via the §3 passthrough (any 32K-context benchmark numbers you've seen are the non-Ollama text-only path and will not fit here):
  - barks (`idle_queue.py:96` and `:372` tasks): **2048**
  - talk (`npc_brain`): **4096**
  - scene summaries: **8192** (design caps pose input at ~3000 tokens — headroom, not 32K)
  - Director rewrite / housing desc: 2048
- **Acceptance:** steady-state VRAM < **7.8GB** with the talk lane warm (watch `nvidia-smi` during the A/B day). If it thrashes/offloads: fallback path is `qwen3.5:4b` at higher quant (thinking-off default too; community reports also note 9B-Q4 tool-use flakiness where 4B-Q8 is clean — barks don't use tools, but it's a data point for the fallback's credibility).

---

## 5 · Sampling retune (Mistral-tuned values won't carry)

- Both JSON-array tasks hardcode `temperature=0.85` (`idle_queue.py:95` and `:371`) — tuned to Mistral's flatness. Qwen3.5-9B has community-documented repetition/looping tendencies without a presence penalty.
- Qwen's recommended **non-thinking general** sampling: `temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5` (Unsloth docs / HF discussions). Adopt as the new bark/task defaults via the §3 options passthrough; leave per-NPC `ai_config.temperature` overrides functional (they already exist and flow through `npc_brain.py:325-329`).
- Put the four values in **tunables** (e.g. `ai.bark_temperature`, `ai.bark_top_p`, `ai.bark_top_k`, `ai.bark_presence_penalty`) with the code defaults above — matches the T3.19 pattern and gives Brian the retune lever without a drop.

---

## 6 · Era-guard drop-rate: make it a dashboard number

- Existing instruments: `[idle_queue] Dropped %d off-era bark(s) …` (idle_queue ~124-128) and `[npc_brain] %s dialogue dropped (off-era) …` (npc_brain ~336-339). Today they're log-only.
- Add matching **telemetry emits** (T3.19 style, async/non-blocking) and a small line on the relevant `@balance` board (barks_generated / barks_dropped_era / talk_dropped_era). Capture one Mistral baseline day before Drop A if convenient; otherwise just monitor post-swap — the guard makes either direction safe, this is a quality/pool-size signal, not a safety one.

---

## 7 · Cutover mechanics + acceptance gate

Order: §3 provider extension (own drop, model-agnostic, fully testable under Mistral) → §2 parse hardening (+ curl verification) → Drop A tier2 flip w/ §4 ctx caps + §5 sampling + §6 telemetry → 1-day A/B → Drop B full flip + invariant/doc updates + fallback env retained.

**Acceptance (Drops A/B):**
- curl JSON check recorded; bark **parse-success rate ≥ Mistral baseline** over one full 4-hour refresh cycle (telemetry from §6)
- era-drop rates logged for the same cycle; spot-read ≥3 barks × ≥10 NPCs across factions/zones (era, persona, brevity, no CJK/refusal artifacts — reject-list the latter two in the bark filter if any appear)
- VRAM < 7.8GB steady-state; talk latency sampled (expect ~2× tok/s vs ~30 baseline)
- full suite green on Windows (provider payload-pin tests prove no behavior drift for non-Qwen configs)
- CHANGELOG + TODO same-drop; CLAUDE.md invariant line updated at Drop B; scene-summary before/after pair pasted into the drop entry (it's the surface with the biggest visible jump — worth showing).

**Explicitly out of scope (log to TODO, don't build):** world-state-aware barks (territory controller / world-event injection into the bark prompt — the 2× throughput funds it later), shorter refresh cycle, any Haiku→Ollama task migration beyond the housing-desc cache that already exists.

— Fable. Sources for the post-cutoff specifics: ollama/ollama issues #14645 and #14617; https://unsloth.ai/docs/models/qwen3.5 (thinking-off default for Small series, sampling recommendations, GGUF/mmproj limitation); HF Qwen3.5-9B discussions (repetition reports, enable_thinking client kwarg). Re-verify #14645 against the installed Ollama version at cutover — it's the one item that decides how much §2 matters.
