# -*- coding: utf-8 -*-
"""
engine/titles.py — Drop 3 B3: vanity titles (an aspirational, cosmetic credit sink).

A character buys an honorific *title* — pure social standing, no payout, no
mechanical benefit, nothing to farm. It is one of the high-tier *sinks* the
economy audit calls for (alongside the Kuat ship brokerage B1, the spacedock
yard-repair drain F2, and the home-prestige ladder B2): it gives veteran credit
somewhere to *go*.

Storage (added by ``ensure_schema`` — the housing-style idempotent column path,
**not** the main SCHEMA_MIGRATIONS dict, so there is **no SCHEMA_VERSION bump**
and no concurrent v-number collision with other in-flight drops):
  - ``characters.vanity_titles``  TEXT DEFAULT '[]'  — JSON list of OWNED keys
  - ``characters.display_title``   TEXT DEFAULT ''    — the literal label worn now

``get_character`` is ``SELECT *``, so both columns flow into the live session
dict automatically; the worn-title display surfaces (``+who``, ``+sheet``, the
room "is here" listing) just read ``display_title`` off the character dict — it
is the single source and *is* the render string.

A purchase debits the cost through the ledger chokepoint as ``vanity_title`` (a
pure sink) and appends the key to the owned set, auto-wearing the new title.
``set_worn_title`` / clear move the worn title among already-owned titles with no
credit movement. Refund-safe: the cost is taken before the owned set is
persisted, and a ``vanity_title_refund`` fires if the persist fails.

This module deliberately introduces the *worn-title display layer* that the
earned-status work (design III.2, Drop 4) will later extend — III.2 grants
titles for *deeds* into this very ``vanity_titles`` set / ``display_title``
surface, so the display layer is built once. Purchasable titles here are
mundane prestige honorifics only (wealth / reputation flavour); Jedi rank and
the like remain *earned*, never bought.
"""

import json
import logging

log = logging.getLogger(__name__)

# ── Catalog ──────────────────────────────────────────────────────────────────
# Era-clean (~20 BBY), faction-neutral, no canon figures, no Empire/Rebel/Jedi
# references (B3 era-cleanness). A price spread for collector sink depth; the
# headline tier is a genuine money-burn for the wealthy (cf. B2's 250k top tier).
VANITY_TITLES = [
    {"key": "wayfarer",       "label": "the Wayfarer",            "cost":   2_000,
     "blurb": "A traveller of the lanes, known in a dozen ports."},
    {"key": "dealmaker",      "label": "the Dealmaker",           "cost":   5_000,
     "blurb": "Whatever you need, they know where to find it."},
    {"key": "high_roller",    "label": "the High Roller",         "cost":  12_000,
     "blurb": "Sabacc tables go quiet when they sit down."},
    {"key": "socialite",      "label": "Sector Socialite",        "cost":  25_000,
     "blurb": "Their name opens doors across a dozen worlds."},
    {"key": "magnate",        "label": "Sector Magnate",          "cost":  60_000,
     "blurb": "Their holdings are whispered about across the sector."},
    {"key": "void_baron",     "label": "Baron of the Void",       "cost": 120_000,
     "blurb": "Fortunes rise and fall on a word from them."},
    {"key": "philanthropist", "label": "Renowned Philanthropist", "cost": 200_000,
     "blurb": "Their generosity is legend — and so is their wealth."},
    {"key": "luminary",       "label": "Luminary of the Core",    "cost": 400_000,
     "blurb": "A name spoken with reverence from the Rim to the Core."},
]

# ── Earned titles (granted for DEEDS, never purchasable) ─────────────────────
# The design III.2 extension this module's docstring anticipates: titles awarded
# for in-game accomplishments flow into the SAME vanity_titles owned-set /
# display_title worn surface, so the display layer is built once. These are NOT
# in VANITY_TITLES, so they never appear in the +title BUY catalog
# (catalog_lines) — they're granted by grant_earned_title() with no credit
# movement. They ARE folded into _BY_KEY below so worn-title display + set_worn_title
# resolve their proper labels. Era-clean (~20 BBY), faction-neutral, no canon figures.
EARNED_TITLES = [
    # Solo-PvE "hunting log" milestones (engine/hunting_rewards.py).
    {"key": "hunter",          "label": "the Hunter",          "earned": True,
     "blurb": "Has felled enough quarry to be known as a hunter."},
    {"key": "seasoned_hunter", "label": "the Seasoned Hunter", "earned": True,
     "blurb": "A steady hand, a long tally — a hunter of repute."},
    {"key": "master_hunter",   "label": "the Master Hunter",   "earned": True,
     "blurb": "Few things in the wild outmatch them anymore."},
    {"key": "apex_hunter",     "label": "the Apex Hunter",     "earned": True,
     "blurb": "Stands at the very top of the food chain."},
]

_BY_KEY = {t["key"]: t for t in (VANITY_TITLES + EARNED_TITLES)}

# Columns added idempotently by ensure_schema (defined before it for clarity,
# mirroring housing's _PRESTIGE_COL pattern).
_TITLE_COLS = [
    "ALTER TABLE characters ADD COLUMN vanity_titles TEXT DEFAULT '[]';",
    "ALTER TABLE characters ADD COLUMN display_title TEXT DEFAULT '';",
]


# ── Telemetry (T3.19): the vanity-title prestige lifecycle ───────────────────
def _emit_title_telemetry(action, char_id, amount, **extra):
    """Emit one fail-open, sample-tunable ``vanity_title`` lifecycle event.

    The purchase debit already rides the ledger as ``vanity_title`` (a pure
    prestige sink), but that isolated credit row can't be rejoined offline into
    the *prestige* lifecycle — which price tiers actually sell, how purchased
    prestige compares to earned prestige, and how much veteran credit the sink
    soaks up against take-up. Each transition emits ONE event tagged by action:
    ``purchase`` (the sink — a title bought) or ``grant`` (an EARNED title
    awarded for a deed; no credit movement). The signal for tuning the 8-tier
    ``VANITY_TITLES`` cost curve (2k→400k): a dead top tier means it is priced
    past reach; everyone parked on the cheap tiers means the sink is too shallow.

      action : ``"purchase"`` / ``"grant"``
      char_id: the acting character (coerced to int when it parses, so a str-id
               system and an int-id system join on the same player)
      amount : the signed credit delta — ``-cost`` for a purchase, ``0`` for a
               (creditless) earned grant
      extra  : action-specific fields (key, tier, owned); ``None`` dropped so
               the record stays clean.

    Sampling honours ``telemetry.title_sample`` (default 1.0 — buying/earning a
    title is a deliberate, low-frequency act, so full capture by default).
    Buffer-only + offline-flushed → can NEVER disturb the buy/grant it observes.
    """
    try:
        try:
            cid = int(char_id)
        except (TypeError, ValueError):
            cid = char_id
        fields = {"action": action, "char_id": cid, "amount": int(amount)}
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        from engine.telemetry import emit as _tele_emit
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.title_sample", 1.0))
        except Exception:
            sample = 1.0
        _tele_emit("vanity_title", fields, sample=sample)
    except Exception:
        log.debug("title telemetry emit failed", exc_info=True)


# ── Pure helpers ─────────────────────────────────────────────────────────────
def title_by_key(key):
    """Return the catalog entry dict for `key`, or None."""
    if not key:
        return None
    return _BY_KEY.get(str(key).strip().lower())


def _parse_owned(char):
    """Safely parse the owned-title key list off a character dict."""
    raw = (char or {}).get("vanity_titles")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(k) for k in raw]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(k) for k in data]
    except (TypeError, ValueError):
        log.warning("[titles] bad vanity_titles blob for char %s",
                    (char or {}).get("id"), exc_info=True)
    return []


def owned_title_keys(char):
    """Owned title keys for `char`, order-preserving and deduped."""
    seen, out = set(), []
    for k in _parse_owned(char):
        kl = k.strip().lower()
        if kl and kl not in seen:
            seen.add(kl)
            out.append(kl)
    return out


def is_owned(char, key):
    """True if `char` owns the title `key`."""
    return str(key or "").strip().lower() in set(owned_title_keys(char))


def worn_title(char):
    """The literal worn-title label for `char`, or None.

    ``display_title`` stores the render string directly, so this is trivial — it
    is the single source the ``+who`` / room / ``+sheet`` surfaces read.
    """
    val = (char or {}).get("display_title")
    val = val.strip() if isinstance(val, str) else ""
    return val or None


def title_status_lines(char):
    """Plain-text status block for the +title command (the command styles it)."""
    lines = []
    worn = worn_title(char)
    lines.append("  Worn title: " + (worn if worn else "(none)"))
    owned = owned_title_keys(char)
    if owned:
        labels = []
        for k in owned:
            t = title_by_key(k)
            labels.append(t["label"] if t else k)
        lines.append("  Owned: " + ", ".join(labels))
    else:
        lines.append("  Owned: (none yet)")
    return lines


def catalog_lines(char):
    """Catalog rows with an owned/affordable/locked marker per title.

    Returns a list of dicts (the command applies colour); pure + testable.
    """
    try:
        balance = int((char or {}).get("credits") or 0)
    except (TypeError, ValueError):
        balance = 0
    rows = []
    for t in VANITY_TITLES:
        if is_owned(char, t["key"]):
            mark = "owned"
        elif balance >= t["cost"]:
            mark = "buy"
        else:
            mark = "locked"
        rows.append({"key": t["key"], "label": t["label"], "cost": t["cost"],
                     "blurb": t["blurb"], "mark": mark})
    return rows


# ── Schema (idempotent, no SCHEMA_VERSION bump) ──────────────────────────────
async def ensure_schema(db):
    """Idempotently add the two title columns to ``characters``.

    Mirrors housing's own column-loop (B2): a per-column ALTER guarded by
    try/except so a re-run on an already-migrated DB is a harmless no-op. NOT
    part of the main SCHEMA_MIGRATIONS dict — so no SCHEMA_VERSION bump and no
    concurrent v-number collision risk with other in-flight drops.
    """
    for col_sql in _TITLE_COLS:
        try:
            await db.execute(col_sql)
        except Exception:
            pass  # column already present
    try:
        await db.commit()
    except Exception:
        log.debug("titles: commit after column-add failed (non-fatal)",
                  exc_info=True)


# ── The sink: buy a title ────────────────────────────────────────────────────
async def purchase_title(db, char: dict, key) -> dict:
    """Buy the vanity title `key` for `char`.

    Debits the cost through the ledger chokepoint as ``vanity_title`` (a pure
    sink), appends the key to the owned set, and auto-wears the new title.
    Refund-safe: the cost is taken before the owned set is persisted, and a
    ``vanity_title_refund`` fires if the persist fails. Returns a result dict
    the command renders.
    """
    t = title_by_key(key)
    if t is None:
        return {"ok": False, "reason": "unknown"}
    if is_owned(char, t["key"]):
        return {"ok": False, "reason": "owned", "label": t["label"]}

    cost = int(t["cost"])
    try:
        balance = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        balance = 0
    if balance < cost:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - balance, "label": t["label"]}

    # Debit FIRST (the sink), then persist; refund on failure so a failed buy
    # never eats credits.
    # allow_negative=False refuses a concurrent overdraw atomically; None return
    # means insufficient funds — treat identically to the balance pre-check above.
    try:
        new_balance = await db.adjust_credits(
            char["id"], -cost, "vanity_title", allow_negative=False)
    except Exception:
        log.warning("[titles] vanity debit failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "charge_failed"}
    if new_balance is None:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - int(char.get("credits") or 0), "label": t["label"]}
    char["credits"] = new_balance

    owned = owned_title_keys(char)
    owned.append(t["key"])
    try:
        await db.save_character(
            char["id"],
            vanity_titles=json.dumps(owned),
            display_title=t["label"],          # auto-wear the freshly-bought title
        )
        char["vanity_titles"] = json.dumps(owned)
        char["display_title"] = t["label"]
    except Exception:
        log.warning("[titles] vanity persist failed for char %s; refunding",
                    char.get("id"), exc_info=True)
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], cost, "vanity_title_refund")
        except Exception:
            log.error("[titles] vanity REFUND FAILED for char %s",
                      char.get("id"), exc_info=True)
        return {"ok": False, "reason": "persist_failed"}

    # Telemetry only after the buy has genuinely landed (debit + persist both
    # succeeded). A failed-and-refunded buy emits nothing — never a phantom
    # prestige signal. ``tier`` is the price-tier index in VANITY_TITLES.
    _tier = next((i for i, vt in enumerate(VANITY_TITLES)
                  if vt["key"] == t["key"]), None)
    _emit_title_telemetry("purchase", char["id"], -cost,
                          key=t["key"], tier=_tier, owned=len(owned))
    return {"ok": True, "key": t["key"], "label": t["label"], "cost": cost}


# ── Earned grant (no credit movement) ────────────────────────────────────────
async def grant_earned_title(db, char: dict, key) -> bool:
    """Grant an EARNED title (a deed reward) to `char` — no credit movement,
    does NOT auto-wear (the player chooses via `+title wear <key>`). Returns
    True iff it was newly granted (False if already owned or unknown key).

    Appends the key to the owned `vanity_titles` set and persists; mirrors the
    purchase persist (minus the debit). The label is resolved from the EARNED_TITLES
    catalog via title_by_key, so worn-title display reads cleanly.
    """
    t = title_by_key(key)
    if t is None:
        return False
    if is_owned(char, t["key"]):
        return False
    owned = owned_title_keys(char)
    owned.append(t["key"])
    try:
        await db.save_character(char["id"], vanity_titles=json.dumps(owned))
        char["vanity_titles"] = json.dumps(owned)
    except Exception:
        log.warning("[titles] earned-title persist failed for char %s",
                    char.get("id"), exc_info=True)
        return False
    # The deed-reward grant — no credit movement (amount 0), but a prestige
    # progression signal worth rejoining against the purchased tiers offline.
    _emit_title_telemetry("grant", char["id"], 0, key=t["key"])
    return True


# ── Selection (no credit movement) ───────────────────────────────────────────
async def set_worn_title(db, char: dict, key) -> dict:
    """Wear an already-owned title, or clear it. No credit movement.

    `key` may be falsy / "none" / "clear" / "off" to remove the worn title.
    """
    clearing = (not key) or str(key).strip().lower() in ("none", "clear", "off")
    if clearing:
        try:
            await db.save_character(char["id"], display_title="")
            char["display_title"] = ""
        except Exception:
            log.warning("[titles] clear-title persist failed for char %s",
                        char.get("id"), exc_info=True)
            return {"ok": False, "reason": "persist_failed"}
        return {"ok": True, "cleared": True}

    # Accept any owned key. For B3 the catalog supplies the label; an unknown but
    # owned key (a future III.2 earned title) falls back to its key as the label.
    if not is_owned(char, key):
        t = title_by_key(key)
        return {"ok": False, "reason": "not_owned",
                "label": (t["label"] if t else str(key))}
    t = title_by_key(key)
    label = t["label"] if t else str(key).strip()
    try:
        await db.save_character(char["id"], display_title=label)
        char["display_title"] = label
    except Exception:
        log.warning("[titles] set-title persist failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "persist_failed"}
    return {"ok": True, "label": label}
