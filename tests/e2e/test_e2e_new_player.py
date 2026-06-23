# -*- coding: utf-8 -*-
"""
tests/e2e/test_e2e_new_player.py — real-browser web-client regression gate.

Wraps the Playwright PoC (playwright_new_player_poc.py) as a runnable pytest gate.
It boots a live server on a free port + a throwaway DB and drives Chromium through
the WHOLE new-player flow in a real browser: portal -> chargen wizard -> login ->
character select -> in-game -> `look` -> click-to-move via the mini-map exit strip
(which also exercises the click-to-move fix). This closes the one QA axis the
in-process break-it sweeps and the jsdom unit tests structurally can't reach: the
actual rendered SPA + the WebSocket round-trip + click handling.

SKIP-GUARDED: it boots a real server + browser (~30-60s, needs Chromium), so it's
marked `slow` + `e2e` AND only runs when RUN_E2E=1 is set -- it never boots a
browser inside the default dev run, the threaded triage, or run_all_tests.bat.

Run it as the web-client regression gate:
    RUN_E2E=1 python -m pytest tests/e2e -m e2e
or directly:
    NODE_OPTIONS=--use-system-ca python tests/e2e/playwright_new_player_poc.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
POC = REPO / "tests" / "e2e" / "playwright_new_player_poc.py"

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

_GUARD = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="real-browser E2E is opt-in: set RUN_E2E=1 (boots a live server + Chromium)",
)


@_GUARD
def test_new_player_flow_in_a_real_browser():
    assert POC.exists(), f"E2E PoC missing: {POC}"
    env = dict(os.environ)
    # Norton TLS-scan analogue: make Playwright's bundled Node trust the Windows
    # cert store (see the anthropic-api-box-blockers memory).
    env.setdefault("NODE_OPTIONS", "--use-system-ca")
    proc = subprocess.run(
        [sys.executable, str(POC)],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=420,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # Surface the PoC's own log on failure so the gate is self-diagnosing.
    assert proc.returncode == 0, f"E2E flow failed (exit {proc.returncode}):\n{out[-3000:]}"
    assert "E2E FLOW PASSED" in out, f"missing PASS marker:\n{out[-3000:]}"
    # The click-to-move path must actually have fired (the regression we shipped).
    assert "map exit fired" in out, f"click-to-move did not fire:\n{out[-3000:]}"
