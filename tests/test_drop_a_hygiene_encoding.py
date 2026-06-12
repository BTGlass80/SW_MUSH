"""Drop A hygiene — pin the SPA node-subprocess UTF-8 contract.

The 2026-06-06 Windows run surfaced 6 failures whose root cause was a
single class of bug: SPA test harnesses launch Node.js with
``subprocess.run(..., text=True)`` but never pass ``encoding="utf-8"``.
With ``text=True`` and no explicit encoding, Python decodes the child's
stdout with ``locale.getpreferredencoding()`` — which is **cp1252** on a
default Windows box. Node always emits UTF-8, so any non-ASCII byte in the
captured output (e.g. the ``×`` in ``WOUNDED ×2``) was mojibake'd on
Windows and the string-equality assertions failed. The same harnesses
pass in the UTF-8 Linux sandbox, which is exactly why these "passed in the
sandbox / failed on the box" splits kept recurring.

The fix is to force ``encoding="utf-8"`` on every node-launching
``subprocess.run`` in the SPA harnesses (and on the one tempfile write
that omitted it). This test pins that contract structurally so the class
cannot silently regress the next time a harness is copied or a new
non-ASCII assertion is added.

This is a TEST-INFRA guard: it asserts nothing about game behaviour, only
that the SPA test harnesses decode child output deterministically.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Every harness that shells out to Node and captures its stdout. If you add
# a new one, add it here — the assertion below will then require it to force
# UTF-8 too.
HARNESS_FILES = [
    REPO_ROOT / "tests" / "spa" / "test_m3_tokens.py",
    REPO_ROOT / "tests" / "spa" / "test_m3_palettes.py",
    REPO_ROOT / "tests" / "spa" / "test_clickwalk_slugjoin.py",
    REPO_ROOT / "tests" / "spa" / "spa_dom_harness.py",
    REPO_ROOT / "tests" / "spa" / "m3_combat_inspector_harness.py",
    REPO_ROOT / "tests" / "test_client_html_inline_script_parses.py",
]


def _is_subprocess_run(call: ast.Call) -> bool:
    """True if this Call node is ``subprocess.run(...)`` or a bare ``run(...)``."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "run":
        val = func.value
        return isinstance(val, ast.Name) and val.id == "subprocess"
    return False


def _kw(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _launches_node(call: ast.Call) -> bool:
    """Heuristic: the first positional arg is a list whose first element is "node"."""
    if not call.args:
        return False
    first = call.args[0]
    if not isinstance(first, ast.List) or not first.elts:
        return False
    head = first.elts[0]
    return isinstance(head, ast.Constant) and head.value == "node"


@pytest.mark.parametrize("path", HARNESS_FILES, ids=lambda p: p.name)
def test_node_subprocess_calls_force_utf8(path: Path) -> None:
    """Every node-launching subprocess.run in an SPA harness sets encoding='utf-8'.

    Guards the Drop A (2026-06-06) fix: without this, captured Node stdout is
    decoded as cp1252 on Windows and non-ASCII assertions (WOUNDED ×2, etc.)
    fail despite the JS being correct.
    """
    assert path.exists(), f"harness moved/renamed: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_run(node):
            continue
        if not _launches_node(node):
            continue
        text_kw = _kw(node, "text")
        is_text = isinstance(text_kw, ast.Constant) and text_kw.value is True
        if not is_text:
            continue  # bytes mode is fine — no decode happens
        enc = _kw(node, "encoding")
        ok = isinstance(enc, ast.Constant) and enc.value == "utf-8"
        if not ok:
            offenders.append(getattr(node, "lineno", "?"))

    assert not offenders, (
        f"{path.name}: node subprocess.run(text=True) without "
        f'encoding="utf-8" at line(s) {offenders}. Add encoding="utf-8" so '
        "captured Node stdout decodes deterministically on Windows (cp1252)."
    )


def test_clickwalk_tempfile_write_forces_utf8() -> None:
    """The clickwalk harness writes its .mjs script as UTF-8.

    A bare NamedTemporaryFile("w") would encode the script with the platform
    default (cp1252 on Windows); the .mjs is ASCII today but pinning UTF-8
    keeps it from breaking if a non-ASCII char is ever introduced.
    """
    src = (REPO_ROOT / "tests" / "spa" / "test_clickwalk_slugjoin.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "NamedTemporaryFile":
            found = True
            enc = _kw(node, "encoding")
            assert isinstance(enc, ast.Constant) and enc.value == "utf-8", (
                "clickwalk NamedTemporaryFile must set encoding='utf-8'"
            )
    assert found, "expected a NamedTemporaryFile call in test_clickwalk_slugjoin.py"


def test_nonascii_roundtrips_through_node_harness() -> None:
    """Behavioural proof: a non-ASCII string survives the real SPA harness path.

    Uses the actual _run_js_in_node helper from the m3_tokens suite (the one
    that read WOUNDED ×2). If the encoding fix regresses, this fails on a
    cp1252 box exactly as the original canonical-labels test did.
    """
    if shutil.which("node") is None:
        pytest.skip("node not available")
    import importlib.util

    mod_path = REPO_ROOT / "tests" / "spa" / "test_m3_tokens.py"
    spec = importlib.util.spec_from_file_location("_m3_tokens_for_hygiene", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # WOUNDED ×2 is the real label that failed on Windows; café/✓ add an
    # accented char and a non-Latin glyph for good measure.
    out = mod._run_js_in_node('result = "WOUNDED \\u00d72 caf\\u00e9 \\u2713";')
    assert out == "WOUNDED \u00d72 caf\u00e9 \u2713"
