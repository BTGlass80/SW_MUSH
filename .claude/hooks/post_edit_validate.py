#!/usr/bin/env python
"""PostToolUse validation: after any Edit/Write/MultiEdit, syntax-check the
touched file.

  *.py          -> py_compile   (catches Python syntax errors immediately)
  *.yaml/*.yml  -> yaml.safe_load (catches malformed YAML)

This makes the per-edit AST/YAML validation step from the CLAUDE.md testing
protocol deterministic, instead of relying on each agent to remember it after
every write.

On failure: exit 2 with the error on stderr. For PostToolUse, exit 2 surfaces
stderr to Claude and blocks the next model call, so the agent sees the syntax
error and fixes the file on its next turn (the edit itself already happened and
cannot be undone -- this is a fast feedback loop, not a rollback).

On success, on unhandled file types, or on any environment problem: exit 0,
silent. Fail-open is deliberate -- a validation hook must never wedge a session.
"""
import json
import sys


def _fail(msg):
    sys.stderr.write(msg)
    return 2


def _check_py(path):
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        return _fail(
            "POST-EDIT py_compile FAILED for {p}:\n{e}\n"
            "You just introduced a Python syntax error. Fix it before "
            "continuing.\n".format(p=path, e=e)
        )
    except FileNotFoundError:
        return 0
    except Exception:
        return 0  # Unexpected compiler error -> fail open, don't wedge.
    return 0


def _check_yaml(path):
    try:
        import yaml
    except Exception:
        # No YAML parser in this interpreter -> skip (fail open). The committed
        # command prefers venv python, which ships PyYAML, so this is a rare
        # degraded path, not the norm.
        return 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            yaml.safe_load(fh)
    except FileNotFoundError:
        return 0
    except yaml.YAMLError as e:
        return _fail(
            "POST-EDIT YAML validation FAILED for {p}:\n{e}\n"
            "You just introduced malformed YAML. Fix it before continuing.\n".format(
                p=path, e=e
            )
        )
    except Exception:
        return 0  # Non-YAML read error -> fail open.
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    low = path.lower()
    if low.endswith(".py"):
        return _check_py(path)
    if low.endswith((".yaml", ".yml")):
        return _check_yaml(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
