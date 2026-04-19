"""Guard test: every builtin open() in tests/ must specify encoding=.

The Windows default text encoding is cp1252; on Linux/Mac it's utf-8. Any
source or data file under the repo containing a non-ASCII byte (e.g. a
smart quote, em-dash, non-breaking space, or a unicode symbol like → or ✓)
will decode fine on the dev box's CI where the test author ran pytest,
then crash on Brian's Windows machine with a cryptic UnicodeDecodeError.

This test walks every tests/*.py file and flags any `open(...)` call
that's missing an `encoding=` keyword argument. It's AST-based so it
can't be fooled by lines in strings or comments.

Exclusions:
- Method-call opens (`harness.open()`, `self.open()`, `await h.open()`)
- async def open() function definitions
- `open()` inside a string literal or comment (AST handles these)

If this test fails, add `encoding="utf-8"` to the flagged open() call.
If you have a legitimate binary-mode open (mode contains 'b'), the test
allows that because binary mode doesn't decode and can't hit cp1252.
"""
from __future__ import annotations

import ast
import pathlib
import re


TESTS_DIR = pathlib.Path(__file__).resolve().parent


def _iter_builtin_open_calls(tree: ast.AST):
    """Yield every Call node that targets the builtin `open` (Name, not Attr)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Builtin open: the callable is a bare Name "open". Skip Attribute
        # calls (harness.open, self.open, h.open, db.open, etc.).
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            yield node


def _is_binary_mode(call: ast.Call) -> bool:
    """Return True if the call's mode arg contains 'b' (binary mode)."""
    # Mode is positional arg 1 or keyword 'mode'.
    mode_node = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode_node = kw.value
            break
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return "b" in mode_node.value
    return False


def _has_encoding_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "encoding" for kw in call.keywords)


def test_all_open_calls_in_tests_specify_encoding() -> None:
    """Every non-binary builtin open() under tests/ must pass encoding=.

    Rationale: Python's default text-mode encoding is platform-specific
    (cp1252 on Windows, utf-8 elsewhere). Any test that slurps a source
    file to grep its contents with open(path, "r") will blow up on
    Windows the moment that source file gains a non-ASCII character.
    This bit us in S60 regression when `parser/mission_commands.py`
    picked up a smart-quote byte and test_economy_validation.py's bare
    open() couldn't decode it.
    """
    offenders: list[str] = []

    for pyfile in sorted(TESTS_DIR.glob("*.py")):
        # Skip this guard test itself.
        if pyfile.name == "test_encoding_hygiene.py":
            continue
        source = pyfile.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(pyfile))
        except SyntaxError:
            # Another test would catch this; don't mask it here.
            continue

        for call in _iter_builtin_open_calls(tree):
            if _has_encoding_kwarg(call):
                continue
            if _is_binary_mode(call):
                continue
            offenders.append(
                f"{pyfile.name}:{call.lineno}  open(...) is missing "
                f"encoding= — will crash on Windows if the target file "
                f"contains non-ASCII bytes"
            )

    assert not offenders, (
        "The following test-file open() calls are missing encoding=utf-8 "
        "and will fail cp1252 decoding on Windows if their target files "
        "contain any non-ASCII characters. Add encoding=\"utf-8\" "
        "(or encoding=\"ascii\" if you're deliberately ASCII-only):\n\n  "
        + "\n  ".join(offenders)
    )


def test_guard_test_catches_the_pattern_itself() -> None:
    """Meta: prove the guard actually catches an encoding-less open().

    Parse a small synthetic source and verify the helper yields the
    offending call. Without this meta-check the guard could silently
    rot into a no-op (e.g. if the AST traversal stopped matching).
    """
    offender_source = 'with open("parser/foo.py", "r") as f:\n    f.read()\n'
    tree = ast.parse(offender_source)
    calls = list(_iter_builtin_open_calls(tree))
    assert len(calls) == 1, "helper should match a bare open() call"
    assert not _has_encoding_kwarg(calls[0])
    assert not _is_binary_mode(calls[0])

    ok_source = 'with open("parser/foo.py", "r", encoding="utf-8") as f:\n    f.read()\n'
    tree = ast.parse(ok_source)
    calls = list(_iter_builtin_open_calls(tree))
    assert len(calls) == 1
    assert _has_encoding_kwarg(calls[0])

    binary_source = 'with open("foo.bin", "rb") as f:\n    f.read()\n'
    tree = ast.parse(binary_source)
    calls = list(_iter_builtin_open_calls(tree))
    assert _is_binary_mode(calls[0])

    # Method-style open should NOT be matched (harness.open, self.open, etc.).
    method_source = 'await harness.open()\nself.open()\n'
    tree = ast.parse(method_source)
    calls = list(_iter_builtin_open_calls(tree))
    assert len(calls) == 0, (
        "method-style .open() calls must not be flagged — only the "
        "builtin open() is platform-encoding sensitive."
    )
