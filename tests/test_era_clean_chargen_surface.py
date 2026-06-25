"""
test_era_clean_chargen_surface.py
Drop: era-clean-chargen — B3 invariant regression guard.

Asserts that player-facing strings in the chargen + character-sheet
data surfaces contain no GCW-era hardware or faction tokens.
Checked surfaces:
  - data/skill_descriptions.yaml  — template descriptions + skill help text
  - data/skills.yaml              — specialization example arrays
  - data/help/topics/moseisley.md — see_also footer
  - data/help/topics/tatooine.md  — see_also footer
"""

import os
import re
import yaml
import pytest

# ---------------------------------------------------------------------------
# Paths (absolute so tests run from any cwd)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(__file__)
_DATA = os.path.normpath(os.path.join(_HERE, "..", "data"))
_SKILL_DESC = os.path.join(_DATA, "skill_descriptions.yaml")
_SKILLS = os.path.join(_DATA, "skills.yaml")
_HELP_MOSEISLEY = os.path.join(_DATA, "help", "topics", "moseisley.md")
_HELP_TATOOINE = os.path.join(_DATA, "help", "topics", "tatooine.md")

# ---------------------------------------------------------------------------
# Forbidden token pattern — B3 invariant
# Comments, era-mapping keys, and sanctioned surfaces are excluded at the
# grep level: we check only the extracted string values, not raw YAML text.
# ---------------------------------------------------------------------------
# Y-wing is CW-era Republic hardware — excluded from the forbidden list.
# A-wing and B-wing are post-CW (Rebellion era) and are forbidden.
# TIE fighters are Imperial-only — forbidden.
# AT-AT is Imperial Walker — forbidden (CW uses AT-TE/AT-RT).
_FORBIDDEN = re.compile(
    r"\b(empire|imperial|rebel alliance|the rebellion|"
    r"tie fighter|tie bomber|tie interceptor|"
    r"x-wing|a-wing|b-wing|"
    r"at-at|stormtrooper)\b",
    re.IGNORECASE,
)

# GCW-era templates present in skill_descriptions.yaml for the GCW chargen
# path. They are never served to CW players and are exempt from the CW check.
_GCW_TEMPLATE_KEYS = frozenset({"rebel_pilot", "soldier"})


def _collect_strings(obj, path=""):
    """Recursively yield (path, value) for every string leaf in a YAML object."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _collect_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _collect_strings(v, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSkillDescriptionsEraClean:
    """skill_descriptions.yaml — template descriptions and skill help text."""

    @pytest.fixture(scope="class")
    def data(self):
        with open(_SKILL_DESC, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_template_descriptions_no_gcw_tokens(self, data):
        """CW-served template descriptions must be GCW-free.
        GCW-only templates (rebel_pilot) are exempt — they are never
        loaded into the CW chargen path."""
        templates = data.get("templates", {})
        violations = []
        for tmpl_key, tmpl in templates.items():
            if tmpl_key in _GCW_TEMPLATE_KEYS:
                continue  # GCW-only path; not served to CW players
            for field in ("description", "gameplay", "tagline", "label"):
                text = tmpl.get(field, "") or ""
                m = _FORBIDDEN.search(text)
                if m:
                    violations.append(
                        f"templates.{tmpl_key}.{field}: matched '{m.group()}' in: {text[:120]!r}"
                    )
        assert not violations, "\n".join(violations)

    def test_skill_help_text_no_gcw_tokens(self, data):
        """All skill help description/game_use/tip strings must be GCW-free."""
        violations = []
        # skills are nested under attribute groups (dexterity, knowledge, etc.)
        for attr_key, attr_skills in data.items():
            if attr_key == "templates":
                continue
            if not isinstance(attr_skills, dict):
                continue
            for skill_key, skill in attr_skills.items():
                if not isinstance(skill, dict):
                    continue
                for field in ("description", "game_use", "tip"):
                    text = skill.get(field, "") or ""
                    m = _FORBIDDEN.search(text)
                    if m:
                        violations.append(
                            f"{attr_key}.{skill_key}.{field}: matched '{m.group()}' in: {text[:120]!r}"
                        )
        assert not violations, "\n".join(violations)


class TestSkillsYamlEraClean:
    """data/skills.yaml — specialization example arrays must be GCW-free."""

    @pytest.fixture(scope="class")
    def data(self):
        with open(_SKILLS, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_specializations_no_gcw_tokens(self, data):
        violations = []
        for _path, value in _collect_strings(data):
            m = _FORBIDDEN.search(value)
            if m:
                violations.append(
                    f"{_path}: matched '{m.group()}' in: {value!r}"
                )
        assert not violations, "\n".join(violations)


class TestHelpTopicSeeAlsoEraClean:
    """Help topic .md see_also footers must not reference 'empire'."""

    @pytest.mark.parametrize("md_path,label", [
        (_HELP_MOSEISLEY, "moseisley.md"),
        (_HELP_TATOOINE, "tatooine.md"),
    ])
    def test_see_also_no_empire(self, md_path, label):
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        # Extract the see_also line from the YAML frontmatter
        m = re.search(r"^see_also:\s*\[([^\]]*)\]", content, re.MULTILINE)
        assert m, f"{label}: could not find see_also line in frontmatter"
        see_also_text = m.group(1)
        tokens = [t.strip().strip("'\"") for t in see_also_text.split(",")]
        assert "empire" not in tokens, (
            f"{label}: 'empire' still present in see_also: {tokens}"
        )

    @pytest.mark.parametrize("md_path,label", [
        (_HELP_MOSEISLEY, "moseisley.md"),
        (_HELP_TATOOINE, "tatooine.md"),
    ])
    def test_see_also_targets_exist(self, md_path, label):
        """Every see_also key should be a real .md file in the topics dir."""
        topics_dir = os.path.join(_DATA, "help", "topics")
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"^see_also:\s*\[([^\]]*)\]", content, re.MULTILINE)
        if not m:
            return  # already caught above
        tokens = [t.strip().strip("'\"") for t in m.group(1).split(",")]
        missing = [t for t in tokens if not os.path.exists(os.path.join(topics_dir, f"{t}.md"))]
        assert not missing, (
            f"{label}: see_also references missing topic files: {missing}"
        )
