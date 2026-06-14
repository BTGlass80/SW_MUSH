# -*- coding: utf-8 -*-
"""
tests/test_claude_skills_integrity.py — keep the project's Agent Skills
(`.claude/skills/<name>/SKILL.md`) well-formed and free of phantom references.

Skills are markdown procedures that the harness auto-surfaces by `description`
match. Two ways they rot silently:
  1. Malformed frontmatter → the skill never loads / never auto-triggers.
  2. A referenced validator script / loader / doc gets renamed or deleted →
     the procedure points at a file that no longer exists (the no-phantom-
     consumer invariant, applied to tooling).

This test is the guard for both. It is intentionally light: it does not lint
prose, only structure + reference integrity, so authoring a new skill stays
cheap.
"""
from __future__ import annotations

import os
import re
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills")

# Documented frontmatter `description` cap (shared with `when_to_use`).
DESCRIPTION_MAX = 1536

# Repo-relative path tokens we treat as concrete file references to verify.
_PATH_RE = re.compile(
    r"(?:tools|engine|db|parser|server|docs|data|web|tests|\.claude)"
    r"/[\w./-]+\.(?:py|md|yaml|yml|txt|js|json)"
)
# Glob / set / placeholder chars — a token containing any of these is an
# illustrative pattern (e.g. `npcs_*.yaml`, `{planets,maps}`), not a literal file.
_NOT_LITERAL = set("*{}[]<>,")
# Local-only, gitignored trees that legitimately may be absent on this/any box.
_SKIP_PREFIXES = ("docs/sourcebooks/",)


def _skill_dirs() -> list[str]:
    if not os.path.isdir(SKILLS_DIR):
        return []
    return [
        d for d in sorted(os.listdir(SKILLS_DIR))
        if os.path.isdir(os.path.join(SKILLS_DIR, d))
    ]


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Raises if frontmatter is missing/bad."""
    if not text.startswith("---"):
        raise ValueError("SKILL.md must open with a '---' YAML frontmatter block")
    # Find the closing fence after the opening one.
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError("SKILL.md frontmatter has no closing '---' fence")
    fm_raw = rest[:end]
    body = rest[end + 4:]
    fm = yaml.safe_load(fm_raw)
    if not isinstance(fm, dict):
        raise ValueError("SKILL.md frontmatter did not parse to a mapping")
    return fm, body


class TestSkillsWellFormed(unittest.TestCase):
    def test_skills_dir_present(self) -> None:
        self.assertTrue(
            os.path.isdir(SKILLS_DIR),
            ".claude/skills/ should exist once any skill is added",
        )

    def test_at_least_one_skill(self) -> None:
        self.assertTrue(_skill_dirs(), "expected at least one skill under .claude/skills/")

    def test_each_skill_has_skill_md(self) -> None:
        for d in _skill_dirs():
            with self.subTest(skill=d):
                self.assertTrue(
                    os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md")),
                    f"{d}/ must contain a SKILL.md",
                )

    def test_frontmatter_name_and_description(self) -> None:
        for d in _skill_dirs():
            with self.subTest(skill=d):
                path = os.path.join(SKILLS_DIR, d, "SKILL.md")
                with open(path, encoding="utf-8") as f:
                    fm, _ = _split_frontmatter(f.read())
                name = fm.get("name")
                desc = fm.get("description")
                self.assertEqual(
                    name, d,
                    f"{d}/SKILL.md frontmatter `name` ({name!r}) must equal its directory",
                )
                self.assertIsInstance(desc, str)
                self.assertTrue(desc.strip(), f"{d}: `description` must be non-empty")
                self.assertLessEqual(
                    len(desc), DESCRIPTION_MAX,
                    f"{d}: `description` exceeds the {DESCRIPTION_MAX}-char cap",
                )

    def test_paths_field_is_list_of_str(self) -> None:
        for d in _skill_dirs():
            path = os.path.join(SKILLS_DIR, d, "SKILL.md")
            with open(path, encoding="utf-8") as f:
                fm, _ = _split_frontmatter(f.read())
            if "paths" not in fm:
                continue
            with self.subTest(skill=d):
                self.assertIsInstance(fm["paths"], list, f"{d}: `paths` must be a list")
                for p in fm["paths"]:
                    self.assertIsInstance(p, str, f"{d}: each `paths` entry must be a string")


class TestSkillsNoPhantomReferences(unittest.TestCase):
    """Every concrete repo file a SKILL.md points to must actually exist."""

    def test_referenced_files_exist(self) -> None:
        for d in _skill_dirs():
            path = os.path.join(SKILLS_DIR, d, "SKILL.md")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for token in sorted(set(_PATH_RE.findall(text))):
                if any(c in token for c in _NOT_LITERAL):
                    continue
                if token.endswith("/"):
                    continue
                if token.startswith(_SKIP_PREFIXES):
                    continue
                with self.subTest(skill=d, ref=token):
                    self.assertTrue(
                        os.path.exists(os.path.join(PROJECT_ROOT, token)),
                        f"{d}/SKILL.md references {token!r}, which does not exist "
                        f"(phantom reference — rename/remove it or fix the path)",
                    )


if __name__ == "__main__":
    unittest.main()
