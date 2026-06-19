"""
Regression guards for TD.TUTORIAL_V1_DEAD_CODE removal.

engine/tutorial.py (v1 TutorialManager) was instantiated in game_server
but never driven — superseded by the chain-tutorial system at chargen.
Removal landed in drop tech-debt-tutorial-v1-removal (2026-06-19).
"""
import os
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def test_tutorial_v1_file_deleted():
    assert not (PROJECT_ROOT / "engine" / "tutorial.py").exists(), (
        "engine/tutorial.py (v1 TutorialManager) was supposed to be deleted "
        "— it has re-appeared; ensure the v1 dead code stays removed."
    )


def test_game_server_does_not_import_tutorial_manager():
    src = _read("server/game_server.py")
    assert "TutorialManager" not in src, (
        "server/game_server.py still references TutorialManager — "
        "the v1 tutorial import/instantiation must stay removed."
    )


def test_no_import_of_engine_tutorial_v1():
    """No live source file should import from engine.tutorial (the v1 module)."""
    skip_dirs = {"tests", ".git", "__pycache__"}
    hits = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "from engine.tutorial import" in text or "import engine.tutorial" in text:
            # Exclude references to tutorial_v2 / tutorial_chains
            lines = [
                ln for ln in text.splitlines()
                if ("from engine.tutorial import" in ln or "import engine.tutorial" in ln)
                and "tutorial_v2" not in ln
                and "tutorial_chains" not in ln
            ]
            if lines:
                hits.append((str(path.relative_to(PROJECT_ROOT)), lines))
    assert not hits, (
        "Live source files import engine.tutorial (v1) — should be removed:\n"
        + "\n".join(f"  {f}: {ls}" for f, ls in hits)
    )
