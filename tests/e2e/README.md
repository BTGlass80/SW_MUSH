# Web-client E2E (Playwright)

Closes the one QA axis the in-process **break-it** sweeps and the **jsdom** unit
tests structurally can't reach: the **actual rendered web SPA in a real browser**
— clicks, the WebSocket round-trip, and rendering. break-it drives the parser;
jsdom drives isolated DOM functions; this drives Chromium against a live server.

## Run

```
python tests/e2e/playwright_new_player_poc.py
```

Local + headless, **no API cost**. Exit 0 = the full new-player flow worked.
It boots `main.py` on a free port + a throwaway temp DB (schema + world
auto-create; `ANTHROPIC_API_KEY` cleared so the Director never spends), drives
the real chargen wizard → login → character select → live game → a `look`
command → a click on the mini-map exit strip (which also exercises the
click-to-move fix), and writes a numbered screenshot of every screen to
`tests/e2e/_screens/` (gitignored) plus the server log. Review the screenshots
by eye, or hand them to an Opus vision pass for automated visual QA.

## One-time setup (this box)

```
python -m playwright install chromium chromium-headless-shell
```

If the browser download fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE` /
"unable to verify the first certificate", that's Norton's TLS-scanning CA (see
the `anthropic-api-box-blockers` memory). Make Playwright's bundled Node read the
Windows cert store:

```
NODE_OPTIONS=--use-system-ca python -m playwright install chromium chromium-headless-shell
```

(Same root cause as the Python-side `truststore` fix; this is its Node analogue.)

## Notes / next steps

- This is the PoC. To grow it into the standing suite: parametrize per-screen
  assertions, add a curated screenshot baseline for visual-regression diffing,
  and a pytest wrapper (kept out of the default xdist run — it boots a real
  server + browser).
- Known finding it already surfaced: the **standalone** `/chargen` wizard shows
  *"Failed to load chains (HTTP 401)"* at the CHAIN step — `/api/chargen/chains`
  requires an account token that only the **embedded** (in-client) chargen flow
  has. A new player entering via the portal's "Create Character" link can't pick
  a tutorial chain.
