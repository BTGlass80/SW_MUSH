"""
spa_dom_harness.py — shared test helper for SPA modules that touch the DOM.

Drop 4.1b · Tier 1 #4 · May 26 2026.

Per Q1 (Playwright in CI), the long-term plan is Playwright. For 4.1b
through 4.1d the modules are DOM-rendering but the tests don't need a
full browser stack — jsdom is sufficient and 50× faster than Playwright.
We move to Playwright in 4.1c when interaction (click, keydown) needs to
be exercised, or in 4.1e when the composition engine's full render needs
visual diffing.

Pattern:
  result = run_with_dom([
      'static/spa/m3_tokens.js',
      'static/spa/m3_palettes.js',
      'static/spa/m3_assets_styles.js',
  ], '''
      var g = window.M3AssetsStyles.STYLE_PRIMITIVES.dock(
          window.M3Palettes.getPalette('tatooine')
      );
      result = { tag: g.tagName, childCount: g.childNodes.length };
  ''')
  assert result['tag'] == 'g'
  assert result['childCount'] == 5  # dock has 5 SVG children

The harness uses jsdom from /tmp/node_modules (installed by Drop 4.1b).
In production CI, this gets baked into the test image.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import pytest


# Path to jsdom. drop 26 (2026-06-13): resolve dynamically instead of
# hardcoding /tmp/node_modules — the repo root carries its own
# node_modules (installed by the VSCode extension's npm) which is where
# jsdom actually lives on a dev box, so the SPA DOM tests now run for
# anyone with the repo deps installed, no manual /tmp setup. Candidates
# are tried in order; the first whose `jsdom/` exists wins. Forward
# slashes throughout (the path is interpolated into a JS require()).
def _resolve_node_modules() -> str:
    repo_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        repo_root / "node_modules",   # repo-local deps (preferred)
        Path("/tmp/node_modules"),    # legacy 4.1b drop-setup location
    ]
    for c in candidates:
        if (c / "jsdom").exists():
            return c.as_posix()
    # None resolved — return the repo-local path for the skip message.
    return (repo_root / "node_modules").as_posix()


NODE_MODULES = _resolve_node_modules()


def require_node_and_jsdom() -> None:
    """Skip the calling test if node or jsdom isn't available."""
    if shutil.which("node") is None:
        pytest.skip("node not available; install Node.js to run SPA DOM tests")
    if not Path(NODE_MODULES, "jsdom").exists():
        pytest.skip(
            f"jsdom not installed at {NODE_MODULES}/jsdom. "
            "Run `npm install jsdom` in the repo root (or /tmp/node_modules)."
        )


def run_with_dom(script_paths: Iterable[Path | str], setup_js: str) -> dict:
    """Load each script under jsdom and run setup_js; return parsed JSON output.

    The scripts are loaded into an empty <html><body></body></html> document
    in order; each one sees `window` set to the jsdom window so that
    `window.M3<X> = ...` assignments accumulate correctly.

    setup_js runs after all scripts are loaded. It must set `result` to a
    JSON-serializable value (numbers, strings, arrays, plain objects).
    DOM elements aren't directly JSON-serializable — extract `.tagName`,
    `.childNodes.length`, `.getAttribute(...)`, `.textContent` etc.
    """
    require_node_and_jsdom()

    paths = [str(Path(p)) for p in script_paths]
    paths_json = json.dumps(paths)

    wrapper = f"""
        var {{ JSDOM }} = require('{NODE_MODULES}/jsdom');
        var fs = require('fs');

        var dom = new JSDOM('<!doctype html><html><body></body></html>', {{
            runScripts: 'outside-only',
            pretendToBeVisual: true
        }});
        var window = dom.window;
        var document = window.document;

        // Load each SPA script in order.
        var scriptPaths = {paths_json};
        scriptPaths.forEach(function(path) {{
            var src = fs.readFileSync(path, 'utf8');
            window.eval(src);
        }});

        // Run the test setup script. It must set `result`.
        var result;
        (function() {{
            {setup_js}
        }}).call(window);

        process.stdout.write(JSON.stringify(result));
    """

    proc = subprocess.run(
        ["node", "-e", wrapper],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"node exited {proc.returncode}\n"
            f"stderr:\n{proc.stderr}\n"
            f"stdout:\n{proc.stdout}"
        )
    return json.loads(proc.stdout)
