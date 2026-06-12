#!/usr/bin/env python
"""PreToolUse guard: block any Edit/Write/MultiEdit that would DELETE lines from
protected world-map YAML files.

Enforces the SW_MUSH "map safety" invariant (CLAUDE.md): world map YAML edits
must be PURELY ADDITIVE (zero deleted lines). Coordinate/room rows in the
planets and maps files are pinned by
tests/test_geonosis_barracks_and_map_safety.py; a stray deletion silently drops
rooms or coordinates. This hook makes the invariant deterministic instead of
trusting each agent to remember it.

Granularity: this is a LINE-COUNT guard. It blocks edits whose net line delta is
negative (a deletion). It deliberately does NOT police same-line-count rewrites
of existing coordinate rows -- the golden-snapshot test is the backstop for
semantic pinning. A net-zero edit that swaps one line for another therefore
passes here and is caught downstream by the snapshot test.

Blocks via exit code 2 (stderr is surfaced to Claude). Allows (exit 0) for:
  - files outside the protected globs
  - new-file creation (Write to a path that does not exist yet)
  - edits whose net line delta is >= 0 (purely additive / line-neutral)

Fail-open: any unexpected input or read error returns 0 (allow). The hook is a
safety net layered on top of the snapshot test, not the sole guard, so it must
never wedge a session on a parsing hiccup.
"""
import json
import os
import sys

# Protected world-map YAML: deletions here drop pinned rooms/coordinates.
# Matched as forward-slash, lowercased substrings of the normalized file path.
PROTECTED_SUBPATHS = (
    "data/worlds/clone_wars/planets/",
    "data/worlds/clone_wars/maps/",
)
YAML_EXTS = (".yaml", ".yml")


def _norm(p):
    return (p or "").replace("\\", "/").lower()


def _is_protected(file_path):
    n = _norm(file_path)
    if not n.endswith(YAML_EXTS):
        return False
    return any(sub in n for sub in PROTECTED_SUBPATHS)


def _lines(s):
    # Physical line count, trailing-newline-insensitive. "" -> 0.
    return len((s or "").splitlines())


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # Unparseable input -> fail open.

    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path") or ""

    if not _is_protected(file_path):
        return 0

    if tool == "Edit":
        net = _lines(ti.get("new_string")) - _lines(ti.get("old_string"))
    elif tool == "MultiEdit":
        net = 0
        for e in ti.get("edits") or []:
            net += _lines(e.get("new_string")) - _lines(e.get("old_string"))
    elif tool == "Write":
        # New file -> additive by definition; nothing to delete.
        if not os.path.exists(file_path):
            return 0
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                existing = fh.read()
        except Exception:
            return 0  # Can't read current file -> fail open.
        net = _lines(ti.get("content")) - _lines(existing)
    else:
        return 0

    if net < 0:
        sys.stderr.write(
            "BLOCKED by map-safety hook: this {tool} would remove {n} line(s) from "
            "protected world-map YAML\n  {path}\n\n"
            "World map YAML edits must be PURELY ADDITIVE (CLAUDE.md map-safety "
            "invariant; rooms/coordinates are pinned by "
            "tests/test_geonosis_barracks_and_map_safety.py). Redo the edit so it "
            "only ADDS lines (new rooms / new exits) and never deletes or rewrites "
            "existing coordinate rows. If a deletion is genuinely intended, that is "
            "a design fork -- stop and ask Brian.\n".format(
                tool=tool, n=-net, path=file_path
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
