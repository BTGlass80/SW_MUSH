"""Proactive credit-velocity alerting — pure logic + a recent-alert buffer.

Closes economy-audit finding **#17** (scorecard: "data collected, no alerts")
and the "add velocity alerts" clause of **R1** in `SW_MUSH_Economy_Audit_FINAL.md`.
Before this, `@economy velocity` / `@economy alerts` could *read* credit flow
on demand, but nothing proactively flagged when the server-wide flow ran hot.
A tick handler (`server.tick_handlers_economy.credit_velocity_alert_tick`)
calls `evaluate_velocity_alert` each hour, records breaches here, logs them,
and pages online staff; `@economy alerts` then surfaces the recent buffer.

Kept deliberately server-free (no aiohttp / session imports) so the band
logic is unit-testable in isolation — the tick handler does the I/O.

**Bidirectional by design.** `economy_audit_v2.md` warns that the existing
farming detection only watches *positive* deltas, so deflation never trips an
alert even though a wage-heavy server can quietly contract. We band on the
*magnitude* of net flow and label the direction, so both runaway inflation
(net ≫ 0) and runaway deflation (net ≪ 0) page staff.

**Thresholds are initial defaults, meant to be tuned against live data.** The
operator has `@economy velocity` (the flow) and `@economy throttle` (the
NPC-faucet valve) to calibrate against; these bands are a starting point, not
a tuned constant. They're module-level so a future tuning pass (or a config
surface) can move them without touching the tick. Scale reference: the
existing on-demand alerts treat a single 50,000 cr move as a "whale" and a
sustained 5,000 cr/hr *per character* as farming; these are server-wide
*net* hourly bands, a different and larger scale.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

# ── Tunable bands: server-wide |net| credit flow over a 1-hour window ──────
# net = faucet_total + sink_total (sink is negative); net > 0 is creation
# (inflation pressure), net < 0 is destruction (deflation pressure).
VELOCITY_CAUTION_NET_1H: int = 50_000
VELOCITY_CRITICAL_NET_1H: int = 150_000

# How many recent alerts to retain for the @economy alerts readout.
_ALERT_BUFFER_MAX: int = 50
_RECENT_ALERTS: "deque[dict]" = deque(maxlen=_ALERT_BUFFER_MAX)


def evaluate_velocity_alert(
    v1h: dict,
    v24h: Optional[dict] = None,
    *,
    caution: int = VELOCITY_CAUTION_NET_1H,
    critical: int = VELOCITY_CRITICAL_NET_1H,
) -> Optional[dict]:
    """Return an alert dict if the 1-hour net credit flow breaches a band,
    else ``None``.

    `v1h` / `v24h` are `Database.get_credit_velocity(...)` results, i.e. dicts
    with at least ``net``, ``faucet_total``, ``sink_total``, plus optional
    ``top_faucets`` / ``top_sinks``. The trigger is the 1-hour |net|; the
    24-hour figure (if given) is carried along as context only.

    Fails safe: a malformed/empty `v1h` yields ``None`` (no false alarm).
    """
    if not isinstance(v1h, dict):
        return None
    try:
        net = int(v1h.get("net", 0) or 0)
    except (TypeError, ValueError):
        return None

    mag = abs(net)
    if mag >= critical:
        severity = "critical"
    elif mag >= caution:
        severity = "caution"
    else:
        return None

    direction = "inflation" if net > 0 else "deflation"
    # The "driving side" is faucets for inflation, sinks for deflation.
    if direction == "inflation":
        drivers = list(v1h.get("top_faucets") or [])[:3]
    else:
        drivers = list(v1h.get("top_sinks") or [])[:3]

    net_24h = None
    if isinstance(v24h, dict):
        try:
            net_24h = int(v24h.get("net", 0) or 0)
        except (TypeError, ValueError):
            net_24h = None

    return {
        "ts": time.time(),
        "severity": severity,           # "caution" | "critical"
        "direction": direction,         # "inflation" | "deflation"
        "net_1h": net,
        "net_24h": net_24h,
        "faucet_1h": int(v1h.get("faucet_total", 0) or 0),
        "sink_1h": int(v1h.get("sink_total", 0) or 0),
        "txn_count_1h": int(v1h.get("txn_count", 0) or 0),
        "drivers": drivers,             # [(source, total), ...]
    }


# ── P2P trade-velocity alert (ECON.p2p_cap_review = a, 2026-06-11) ──────
# The S51/audit-v2 hard cap (1,500 cr per rolling 24h per sender) is
# REMOVED — under vendor segmentation (a), crafters are the supply chain
# and a single quality item legitimately trades above the old cap. The
# threshold survives as TELEMETRY: cross it and an alert lands in the
# ring buffer for @economy review; nothing is ever blocked. Alt-funneling
# is fought at the faucet throttle + admin action, not by capping trade.
# Thresholds are tunables (fold into T3.19's per-domain config pass).
P2P_VELOCITY_CAUTION_24H: int = 1_500    # the old cap value
P2P_VELOCITY_CRITICAL_24H: int = 7_500   # 5× — sustained funneling shape


def evaluate_p2p_velocity_alert(
    sender: str,
    sender_id: int,
    recipient: str,
    rolling_24h: int,
    amount: int = 0,
    *,
    caution: int = P2P_VELOCITY_CAUTION_24H,
    critical: int = P2P_VELOCITY_CRITICAL_24H,
) -> Optional[dict]:
    """Return an alert dict if a sender's rolling 24-hour outgoing P2P
    credit volume breaches a band, else ``None``.

    `rolling_24h` is `db.get_daily_p2p_outgoing(...)` INCLUDING the trade
    that just completed. Fails safe: malformed input yields ``None`` —
    telemetry must never disturb a trade.

    The dict carries the generic severity/direction/net fields so the
    existing `@economy` readouts render it without changes, plus
    `kind: "p2p_velocity"` for the dedicated `format_alert_line` branch.
    """
    try:
        total = int(rolling_24h)
    except (TypeError, ValueError):
        return None
    if total >= critical:
        severity = "critical"
    elif total >= caution:
        severity = "caution"
    else:
        return None
    try:
        amt = int(amount)
    except (TypeError, ValueError):
        amt = 0
    return {
        "ts": time.time(),
        "kind": "p2p_velocity",
        "severity": severity,            # "caution" | "critical"
        "direction": "p2p-volume",       # renders sanely in generic readouts
        "net_1h": total,                 # generic-field compatibility
        "sender": str(sender or "?"),
        "sender_id": sender_id,
        "recipient": str(recipient or "?"),
        "rolling_24h": total,
        "amount": amt,
        "drivers": [],
    }


def format_alert_line(alert: dict) -> str:
    """One-line human-readable summary for logs, staff pages, and the
    ``@economy alerts`` readout."""
    if alert.get("kind") == "p2p_velocity":
        # ECON.p2p_cap_review = a (2026-06-11): per-sender trade-volume
        # alert — the old hard cap's threshold, repurposed as telemetry.
        sev = str(alert.get("severity", "?")).upper()
        return (f"{sev} p2p-volume: {alert.get('sender', '?')} has sent "
                f"{alert.get('rolling_24h', 0):,} cr in 24h "
                f"(latest {alert.get('amount', 0):,} cr → "
                f"{alert.get('recipient', '?')})")
    sev = str(alert.get("severity", "?")).upper()
    direction = alert.get("direction", "?")
    net = alert.get("net_1h", 0)
    drivers = alert.get("drivers") or []
    driver_txt = ""
    if drivers:
        top = ", ".join(f"{src} {total:+,}" for src, total in drivers[:2])
        label = "faucets" if direction == "inflation" else "sinks"
        driver_txt = f" — top {label}: {top}"
    n24 = alert.get("net_24h")
    n24_txt = f" (24h net {n24:+,} cr)" if isinstance(n24, int) else ""
    return (f"{sev} {direction}: net {net:+,} cr/hr"
            f"{n24_txt}{driver_txt}")


def record_alert(alert: dict) -> None:
    """Append an alert to the recent-alert ring buffer (capped)."""
    if isinstance(alert, dict):
        _RECENT_ALERTS.append(alert)


def recent_alerts(limit: int = 10) -> list:
    """Most-recent alerts first (up to `limit`)."""
    if limit <= 0:
        return []
    items = list(_RECENT_ALERTS)
    items.reverse()
    return items[:limit]


def clear_alerts() -> None:
    """Drop all buffered alerts (used by tests; harmless in production)."""
    _RECENT_ALERTS.clear()
