"""HelpEntry schema fix — guard against regression of the
`engine/help_loader.py` ↔ `data/help_topics.py:HelpEntry` contract.

The loader passes four kwargs (`summary`, `examples`, `tags`,
`updated_at`) when constructing a HelpEntry from a markdown file's
frontmatter. If any of these four fields disappear from the dataclass,
every help-loader call site fails with a TypeError on
`HelpEntry.__init__() got an unexpected keyword argument <field>`,
which on the v88 baseline took down 35 tests across
`test_session57b_space_umbrellas.py` and the help-file class in
`test_session57a_ship_expansion.py`.

These tests are deliberately minimal — they guard the contract, not
the loader's behavior. Behavior tests live in the session test files
that previously exercised the loader against real markdown files.
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _help_entry_cls():
    """Late-import so a missing module reports as a clean test failure
    rather than a collection error."""
    from data.help_topics import HelpEntry
    return HelpEntry


# ───────────────────────────────────────────────────────────────────────
# Schema contract — every loader-required field is present with the
# right type and a sensible default.
# ───────────────────────────────────────────────────────────────────────


class TestHelpEntrySchema:

    def test_helpentry_is_a_dataclass(self):
        cls = _help_entry_cls()
        assert dataclasses.is_dataclass(cls), (
            "HelpEntry must remain a dataclass — loader uses kwarg init"
        )

    def test_summary_field_present(self):
        """summary: str = ''"""
        fields = {f.name: f for f in dataclasses.fields(_help_entry_cls())}
        assert 'summary' in fields, (
            "HelpEntry.summary missing — loader at engine/help_loader.py:247 "
            "passes summary= and TypeError will fire on every markdown load"
        )
        f = fields['summary']
        # Default is empty string (not MISSING)
        assert f.default == "" or f.default_factory is not dataclasses.MISSING, (
            "HelpEntry.summary must have a default — code-constructed "
            "entries (data/help_topics.py register_topics) don't pass it"
        )

    def test_examples_field_present(self):
        """examples: list[dict] = field(default_factory=list)"""
        fields = {f.name: f for f in dataclasses.fields(_help_entry_cls())}
        assert 'examples' in fields, "HelpEntry.examples missing"
        f = fields['examples']
        assert f.default_factory is not dataclasses.MISSING, (
            "HelpEntry.examples must use default_factory=list — mutable "
            "defaults are a dataclass bug magnet"
        )

    def test_tags_field_present(self):
        """tags: list[str] = field(default_factory=list)"""
        fields = {f.name: f for f in dataclasses.fields(_help_entry_cls())}
        assert 'tags' in fields, "HelpEntry.tags missing"
        f = fields['tags']
        assert f.default_factory is not dataclasses.MISSING, (
            "HelpEntry.tags must use default_factory=list"
        )

    def test_updated_at_field_present(self):
        """updated_at: str = ''"""
        fields = {f.name: f for f in dataclasses.fields(_help_entry_cls())}
        assert 'updated_at' in fields, "HelpEntry.updated_at missing"
        f = fields['updated_at']
        assert f.default == "" or f.default_factory is not dataclasses.MISSING, (
            "HelpEntry.updated_at must have a default"
        )

    def test_legacy_required_fields_intact(self):
        """The original 7 fields (key/title/category/body/aliases/
        see_also/access_level) must remain — code-constructed entries
        depend on them by name."""
        fields = {f.name for f in dataclasses.fields(_help_entry_cls())}
        for required in ('key', 'title', 'category', 'body',
                         'aliases', 'see_also', 'access_level'):
            assert required in fields, (
                f"HelpEntry.{required} missing — legacy contract broken"
            )


# ───────────────────────────────────────────────────────────────────────
# End-to-end — a synthesized HelpEntry constructor call mirroring the
# loader's call site. If this fails the loader path is broken.
# ───────────────────────────────────────────────────────────────────────


class TestHelpLoaderCallSite:

    def test_loader_kwargs_construct_cleanly(self):
        """Mirror the exact kwarg list from
        `engine/help_loader.py:243-256` and confirm it succeeds."""
        cls = _help_entry_cls()
        entry = cls(
            key="test-topic",
            title="Test Topic",
            category="Testing",
            body="Body text here.\n",
            aliases=["test", "tt"],
            see_also=["other-topic"],
            access_level=0,
            summary="A short summary.",
            examples=[{"cmd": "test foo", "description": "do the thing"}],
            tags=["meta", "test"],
            updated_at="2026-04-25T12:00:00Z",
        )
        # Sanity: every kwarg landed on the right attribute
        assert entry.key == "test-topic"
        assert entry.summary == "A short summary."
        assert entry.examples == [
            {"cmd": "test foo", "description": "do the thing"}
        ]
        assert entry.tags == ["meta", "test"]
        assert entry.updated_at == "2026-04-25T12:00:00Z"

    def test_legacy_kwargs_only_still_work(self):
        """Code paths in `data/help_topics.py:register_topics()` and
        `register_command_help()` construct HelpEntry without the new
        fields. They must still succeed."""
        cls = _help_entry_cls()
        entry = cls(
            key="legacy",
            title="Legacy Entry",
            category="Commands",
            body="Body.\n",
            aliases=["leg"],
            access_level=0,
        )
        # New fields default cleanly
        assert entry.summary == ""
        assert entry.examples == []
        assert entry.tags == []
        assert entry.updated_at == ""
        # Each entry's mutable defaults are independent (default_factory test)
        other = cls(key="other", title="Other", category="X", body="b\n")
        other.examples.append({"cmd": "x", "description": ""})
        assert entry.examples == [], (
            "examples mutable default leaked across instances — "
            "default_factory regression"
        )
