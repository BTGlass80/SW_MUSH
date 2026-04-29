"""
F.1c+d follow-up — fix inline onclick handlers blocked by IIFE wrapper.

ROOT CAUSE
----------
At commit `big_update_2`, static/client.html's main script was wrapped in
`(function(){ 'use strict'; ... })();`. This made all top-level function
declarations (setSheetTab, closeMapModal, beginSheetEdit, setCommsFilter, etc.)
LOCAL to the IIFE closure. HTML inline handlers like
    onclick="setSheetTab('full')"
run in *global* scope, so they can't see the closure-local functions and throw
    Uncaught ReferenceError: setSheetTab is not defined

The user's symptom was the sheet panel tabs failing, but every inline handler
in the file is silently broken.

FIX
---
Add a single export block near the end of the IIFE (just before the
DOMContentLoaded bootstrap) that copies the closure-local function references
onto `window`. Function declarations are hoisted within the IIFE, so
referencing them by name at the export site works even though the declarations
are physically later in the file.

This patch is idempotent — running it twice produces the same file.
"""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path("static/client.html")

EXPORT_MARKER = "/* INLINE-HANDLER EXPORTS"

EXPORT_BLOCK = """\
/* INLINE-HANDLER EXPORTS — see notes at the IIFE wrapper at the top of this
   script. The HTML uses `onclick="setSheetTab('full')"` etc., which run in
   global scope; the script body runs inside an IIFE, so we have to lift the
   handler functions onto `window` explicitly. Function declarations are
   hoisted within the IIFE, so naming them here is fine even though the
   declarations are later in the file textually. Keep this list in sync with
   `grep -oE 'on(click|change|input)="[^"]*"' static/client.html`. */
window.setSheetTab              = setSheetTab;
window.closeSheetPanel          = closeSheetPanel;
window.sheetPanelBackdropClick  = sheetPanelBackdropClick;
window.beginSheetEdit           = beginSheetEdit;
window.cancelSheetEdit          = cancelSheetEdit;
window.saveSheetEdit            = saveSheetEdit;
window.openMapModal             = openMapModal;
window.closeMapModal            = closeMapModal;
window.mapModalBackdropClick    = mapModalBackdropClick;
window.setCommsFilter           = setCommsFilter;
window.toggleCommsPane          = toggleCommsPane;
/* Already exported above; re-asserted here as a single source of truth. */
window.toggleSidePanel          = toggleSidePanel;
window.scrollPoseLogToBottom    = scrollPoseLogToBottom;
window.reconnectClick           = reconnectClick;
"""

ANCHOR = """\
  connect();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();"""

REPLACEMENT = """\
  connect();
}

""" + EXPORT_BLOCK + """
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();"""


def main() -> int:
    if not CLIENT.exists():
        print(f"ERROR: {CLIENT} not found. Run from project root.", file=sys.stderr)
        return 2

    src = CLIENT.read_text(encoding="utf-8")

    if EXPORT_MARKER in src:
        print(f"[SKIP] {CLIENT}: export block already present (idempotent re-run).")
        return 0

    if ANCHOR not in src:
        print(f"ERROR: anchor not found in {CLIENT}.", file=sys.stderr)
        print("       The end-of-IIFE bootstrap block must match exactly.", file=sys.stderr)
        return 1

    if src.count(ANCHOR) != 1:
        print(f"ERROR: anchor appears {src.count(ANCHOR)} times; need exactly 1.", file=sys.stderr)
        return 1

    out = src.replace(ANCHOR, REPLACEMENT)
    CLIENT.write_text(out, encoding="utf-8")

    # Quick sanity: count handler-targeted symbols in window.* assignments.
    expected = [
        "setSheetTab", "closeSheetPanel", "sheetPanelBackdropClick",
        "beginSheetEdit", "cancelSheetEdit", "saveSheetEdit",
        "openMapModal", "closeMapModal", "mapModalBackdropClick",
        "setCommsFilter", "toggleCommsPane",
    ]
    after = CLIENT.read_text(encoding="utf-8")
    for name in expected:
        if f"window.{name}" not in after:
            print(f"ERROR: expected `window.{name}` not found post-write.", file=sys.stderr)
            return 1

    print(f"[OK] {CLIENT}: inserted {len(expected) + 3} window.* exports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
