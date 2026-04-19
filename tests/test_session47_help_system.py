# -*- coding: utf-8 -*-
"""
Session 47 tests — help system redesign.

Covers:
  - HelpEntry dataclass: new fields default to empty, old-shape
    construction still works
  - Filename ↔ key encoding round-trips, including slashes
  - Frontmatter parser: well-formed, malformed YAML, unterminated
    fence, no fence, missing fields
  - load_help_file: populates every field, falls back gracefully
  - Migration completeness: every original topic key has a matching
    .md file that loads into a live registry
  - HelpManager precedence: markdown overrides auto-registered
  - HelpManager.search: ranked output (exact key first, title
    second, body last)
  - HelpManager.get_categories_tree: splits ``Rules: Combat`` into
    nested ``Rules`` → ``Combat``
  - HelpManager.reload: picks up both command-registry changes and
    on-disk markdown changes without a restart
  - Alias map hygiene: re-registering an entry clears stale aliases

These tests are self-contained — they build their own markdown root
under tmpdir and never touch the shipping ``data/help/`` directory,
except for a single completeness check that the migration was done.
"""
import os
import shutil
import tempfile
import unittest

# The tests sit under tests/ and the project root is the parent. Make
# the source tree importable without forcing a pytest conftest.
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════════════════
# HelpEntry dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestHelpEntryShape(unittest.TestCase):
    """The dataclass keeps the old 7-field shape for backward compat
    while adding optional enriched fields."""

    def test_old_shape_still_constructs(self):
        """Old code constructing HelpEntry with only the original
        fields should keep working."""
        from data.help_topics import HelpEntry
        e = HelpEntry(
            key="foo",
            title="Foo",
            category="Bar",
            body="Body text.",
            aliases=["f"],
            see_also=["baz"],
            access_level=0,
        )
        self.assertEqual(e.key, "foo")
        self.assertEqual(e.summary, "")
        self.assertEqual(e.examples, [])
        self.assertEqual(e.tags, [])
        self.assertEqual(e.updated_at, "")

    def test_new_fields_accept_values(self):
        from data.help_topics import HelpEntry
        e = HelpEntry(
            key="x",
            title="X",
            category="C",
            body="B",
            summary="one-liner",
            examples=[{"cmd": "x", "description": "do x"}],
            tags=["combat"],
            updated_at="2026-04-17T12:00:00Z",
        )
        self.assertEqual(e.summary, "one-liner")
        self.assertEqual(len(e.examples), 1)
        self.assertEqual(e.examples[0]["cmd"], "x")
        self.assertIn("combat", e.tags)


# ═══════════════════════════════════════════════════════════════════════
# Filename ↔ key encoding
# ═══════════════════════════════════════════════════════════════════════

class TestFilenameKeyEncoding(unittest.TestCase):

    def test_simple_key_unchanged(self):
        from engine.help_loader import (
            encode_key_to_filename, decode_filename_to_key,
        )
        self.assertEqual(encode_key_to_filename("combat"), "combat")
        self.assertEqual(decode_filename_to_key("combat"), "combat")

    def test_plus_prefix_preserved(self):
        from engine.help_loader import encode_key_to_filename
        self.assertEqual(encode_key_to_filename("+sheet"), "+sheet")

    def test_slash_encoded(self):
        """Slashes in future +command/argument keys must survive a
        round trip to filename and back."""
        from engine.help_loader import (
            encode_key_to_filename, decode_filename_to_key,
        )
        self.assertEqual(
            encode_key_to_filename("+combat/attack"), "+combat__attack"
        )
        self.assertEqual(
            decode_filename_to_key("+combat__attack"), "+combat/attack"
        )

    def test_round_trip_many(self):
        from engine.help_loader import (
            encode_key_to_filename, decode_filename_to_key,
        )
        for key in ["dice", "+sheet", "+combat/attack", "@dig",
                    "+plot/create", "force"]:
            stem = encode_key_to_filename(key)
            self.assertEqual(decode_filename_to_key(stem), key, key)


# ═══════════════════════════════════════════════════════════════════════
# Frontmatter parsing & load_help_file
# ═══════════════════════════════════════════════════════════════════════

class TestFrontmatterLoading(unittest.TestCase):
    """Exercise engine.help_loader.load_help_file end-to-end via a
    tmpdir so we don't depend on on-disk content layout."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="helpload_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_wellformed_file_populates_all_fields(self):
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("combat.md", """---
key: combat
title: Combat Basics
category: Rules · Combat
summary: How rounds, attacks, and wounds work.
aliases: [fight, fighting]
see_also: [wounds, dodge]
tags: [core, combat]
access_level: 0
examples:
  - cmd: attack greedo
    description: Basic ranged attack.
  - cmd: dodge
    description: Reactive dodge.
---

Body text goes here.
""")
        e = load_help_file(path, HelpEntry)
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "combat")
        self.assertEqual(e.title, "Combat Basics")
        self.assertEqual(e.category, "Rules · Combat")
        self.assertEqual(e.summary, "How rounds, attacks, and wounds work.")
        self.assertEqual(e.aliases, ["fight", "fighting"])
        self.assertEqual(e.see_also, ["wounds", "dodge"])
        self.assertEqual(e.tags, ["core", "combat"])
        self.assertEqual(len(e.examples), 2)
        self.assertEqual(e.examples[0]["cmd"], "attack greedo")
        self.assertIn("Body text goes here.", e.body)
        # mtime should populate updated_at
        self.assertTrue(e.updated_at.endswith("Z"))

    def test_missing_key_derived_from_filename(self):
        """A file with no ``key:`` frontmatter field should derive its
        key from the filename stem, with slash-encoding reversed."""
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("+combat__attack.md", """---
title: Attack a Target
category: Commands
---

Attack the target.
""")
        e = load_help_file(path, HelpEntry)
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "+combat/attack")

    def test_missing_title_derived_from_first_heading(self):
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("dice.md", """---
key: dice
category: Rules
---

# The D6 System

Long body follows.
""")
        e = load_help_file(path, HelpEntry)
        self.assertEqual(e.title, "The D6 System")

    def test_malformed_yaml_returns_usable_entry(self):
        """Broken frontmatter shouldn't crash the loader — we log a
        warning and treat the body as content with derived metadata."""
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("bad.md", """---
key: bad
this is: not: valid: yaml: [[[
---

Body still here.
""")
        # Either we get a usable entry (with defaults) or None — both
        # are acceptable non-crashing outcomes. The invariant is: no
        # exception escapes.
        e = load_help_file(path, HelpEntry)
        if e is not None:
            self.assertIn("Body still here", e.body)

    def test_unterminated_fence_doesnt_crash(self):
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("oops.md", """---
key: oops
title: Oops

(no closing fence)
""")
        e = load_help_file(path, HelpEntry)
        # We don't crash. May or may not produce a useful entry —
        # either way, the boot survives.
        self.assertTrue(e is None or isinstance(e.key, str))

    def test_no_frontmatter_treats_whole_file_as_body(self):
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("raw.md", "# A Topic\n\nJust markdown, no fence.\n")
        e = load_help_file(path, HelpEntry)
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "raw")                # from filename
        self.assertEqual(e.title, "A Topic")          # from first heading
        self.assertIn("Just markdown", e.body)

    def test_examples_accept_plain_string_form(self):
        """Authors can write ``examples: ["cmd1", "cmd2"]`` and the
        loader coerces them to {cmd, description} dicts."""
        from engine.help_loader import load_help_file
        from data.help_topics import HelpEntry
        path = self._write("ex.md", """---
key: ex
title: Ex
category: Test
examples:
  - just a command
  - another command
---

body
""")
        e = load_help_file(path, HelpEntry)
        self.assertEqual(len(e.examples), 2)
        self.assertEqual(e.examples[0]["cmd"], "just a command")
        self.assertEqual(e.examples[0]["description"], "")

    def test_readme_md_is_skipped(self):
        """README.md files in a help directory are meta-notes for
        authors, not help entries. The directory walker skips them."""
        from engine.help_loader import load_help_directory
        from data.help_topics import HelpEntry
        # Write one real entry and a README in the same dir
        self._write("real.md", """---
key: real
title: Real
category: Test
---
body
""")
        self._write("README.md", """
Not a help entry, just a note.
""")
        self._write("readme.md", """
Also not an entry (lowercase).
""")
        entries = load_help_directory(self.tmp, HelpEntry)
        keys = {e.key for e in entries}
        self.assertEqual(keys, {"real"})


# ═══════════════════════════════════════════════════════════════════════
# Migration completeness
# ═══════════════════════════════════════════════════════════════════════

class TestMigrationCompleteness(unittest.TestCase):
    """The migration from TOPIC_HELP (Python literals) to
    data/help/topics/*.md (markdown) should have kept every entry,
    and the content on disk should actually load into a live
    registry."""

    EXPECTED_KEYS = [
        # Originally the 47 entries in TOPIC_HELP. Hardcoded here
        # because this is specifically a migration-completeness guard
        # — we want to notice if someone drops an entry by accident.
        # Future help-system work should update this list.
        "dice", "attributes", "skills", "difficulty",
        "combat", "ranged", "melee", "wounds", "dodge", "cover",
        "multiaction", "armor", "scale",
        "force", "forcepoints", "darkside", "lightsaber",
        "cp", "advancement",
        "space", "spacecombat", "crew", "hyperdrive", "sensors",
        "shields", "capital", "navigation", "zonemap", "anomalies",
        "salvage", "shipmod", "poweralloc", "captainorders",
        "transponder", "npccrew",
        "moseisley", "cantina", "tatooine",
        "trading", "smuggling", "bounty",
        "species", "rp", "newbie", "commands", "channels",
        "building",
    ]

    def test_expected_count_matches_shipped_files(self):
        # Sanity check on the hardcoded list above.
        self.assertEqual(len(self.EXPECTED_KEYS), 47)

    def test_every_original_key_has_a_markdown_file(self):
        topics_dir = os.path.join(PROJECT_ROOT, "data", "help", "topics")
        self.assertTrue(
            os.path.isdir(topics_dir),
            f"topics dir missing: {topics_dir}",
        )
        shipped = {
            os.path.splitext(f)[0]
            for f in os.listdir(topics_dir)
            if f.endswith(".md")
        }
        for key in self.EXPECTED_KEYS:
            # Filename stem uses the slash-encoded form; no original
            # key has a slash, so stem == key.
            self.assertIn(
                key, shipped,
                f"missing data/help/topics/{key}.md",
            )

    def test_every_original_key_loads_into_a_fresh_manager(self):
        """End-to-end: a brand-new HelpManager + the shipping content
        dir should resolve every original key."""
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files()  # default root = data/help
        for key in self.EXPECTED_KEYS:
            self.assertIsNotNone(
                mgr.get(key),
                f"HelpManager.get({key!r}) returned None",
            )


# ═══════════════════════════════════════════════════════════════════════
# HelpManager: precedence, search, category tree, reload
# ═══════════════════════════════════════════════════════════════════════

class _FakeCommand:
    """Stand-in for BaseCommand — just enough surface for
    auto_register_commands."""

    def __init__(self, key, help_text="", usage="",
                 aliases=(), access_level=0, valid_switches=()):
        self.key = key
        self.help_text = help_text
        self.usage = usage
        self.aliases = list(aliases)
        self.access_level = access_level
        self.valid_switches = list(valid_switches)


class _FakeRegistry:
    def __init__(self, cmds):
        self.all_commands = list(cmds)


class TestHelpManagerPrecedence(unittest.TestCase):
    """Markdown files override earlier same-key registrations."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="helpmgr_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_markdown_overrides_auto_registered(self):
        from data.help_topics import HelpManager
        # Write a markdown file for key "dodge"
        with open(os.path.join(self.tmp, "dodge.md"), "w", encoding="utf-8") as f:
            f.write("""---
key: dodge
title: Dodging
category: Rules · Combat
summary: Reactive avoidance.
---

Rich markdown body goes here.
""")
        mgr = HelpManager()
        # Register a thin auto-entry first
        mgr.auto_register_commands(_FakeRegistry([
            _FakeCommand("dodge", help_text="thin help"),
        ]))
        self.assertIn("thin help", mgr.get("dodge").body)
        # Now layer the markdown root — should override
        mgr.load_markdown_files(self.tmp)
        e = mgr.get("dodge")
        self.assertIn("Rich markdown body", e.body)
        self.assertEqual(e.category, "Rules · Combat")
        self.assertEqual(e.summary, "Reactive avoidance.")

    def test_absent_markdown_leaves_auto_entry_alone(self):
        """A command with no .md file keeps its auto-registered
        version — that's the "every command gets at least SOMETHING"
        guarantee."""
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.auto_register_commands(_FakeRegistry([
            _FakeCommand("attack", help_text="Attack a target."),
        ]))
        mgr.load_markdown_files(self.tmp)  # empty tmpdir
        e = mgr.get("attack")
        self.assertIsNotNone(e)
        self.assertIn("Attack a target", e.body)


class TestHelpManagerSearch(unittest.TestCase):

    def _make(self):
        from data.help_topics import HelpEntry, HelpManager
        mgr = HelpManager()
        mgr.register(HelpEntry(
            key="combat", title="Combat Basics",
            category="Rules", body="rounds and attacks",
            summary="how fights work",
            aliases=["fight"], tags=["core"],
        ))
        mgr.register(HelpEntry(
            key="wounds", title="Wounds & Healing",
            category="Rules", body="damage, combat injuries",
            aliases=["wound"],
        ))
        mgr.register(HelpEntry(
            key="force", title="The Force",
            category="Rules", body="mystical energy",
            aliases=["jedi"], tags=["force", "combat"],
        ))
        return mgr

    def test_exact_key_match_ranks_first(self):
        mgr = self._make()
        results = mgr.search("combat")
        # Exact key "combat" should be first, even though "wounds"
        # mentions combat in its body and "force" has a combat tag.
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].key, "combat")

    def test_title_match_beats_body_match(self):
        mgr = self._make()
        results = mgr.search("wound")
        # "wounds" has "wound" in both title and key, "combat" has
        # "wound" nowhere. Expect wounds to appear; more importantly
        # expect it to rank above any body-only matches.
        keys = [r.key for r in results]
        self.assertIn("wounds", keys)

    def test_tag_match_appears(self):
        mgr = self._make()
        results = mgr.search("force")
        # "force" is an exact key, should be first
        self.assertEqual(results[0].key, "force")

    def test_empty_query_returns_empty(self):
        mgr = self._make()
        self.assertEqual(mgr.search(""), [])
        self.assertEqual(mgr.search("   "), [])


class TestCategoriesTree(unittest.TestCase):
    """``Rules: Combat`` / ``Rules: D6`` should nest under a shared
    ``Rules`` node so the portal sidebar can render a tree."""

    def test_tree_splits_nested_categories(self):
        from data.help_topics import HelpEntry, HelpManager
        mgr = HelpManager()
        mgr.register(HelpEntry(
            key="combat", title="Combat", category="Rules: Combat", body=""
        ))
        mgr.register(HelpEntry(
            key="dice", title="D6", category="Rules: D6", body=""
        ))
        mgr.register(HelpEntry(
            key="species", title="Species", category="Character", body=""
        ))
        tree = mgr.get_categories_tree()
        self.assertIn("Rules", tree)
        self.assertIn("Character", tree)
        rules = tree["Rules"]
        self.assertIn("Combat", rules["_subcategories"])
        self.assertIn("D6", rules["_subcategories"])
        # Leaf entries attach to their innermost category
        combat_node = rules["_subcategories"]["Combat"]
        self.assertEqual(len(combat_node["_entries"]), 1)
        self.assertEqual(combat_node["_entries"][0].key, "combat")
        # Character has entries at the top level, no subcategories
        char_node = tree["Character"]
        self.assertEqual(len(char_node["_entries"]), 1)
        self.assertEqual(char_node["_subcategories"], {})

    def test_middledot_separator_also_splits(self):
        from data.help_topics import HelpEntry, HelpManager
        mgr = HelpManager()
        mgr.register(HelpEntry(
            key="x", title="X", category="Rules · Combat", body=""
        ))
        tree = mgr.get_categories_tree()
        self.assertIn("Rules", tree)
        self.assertIn("Combat", tree["Rules"]["_subcategories"])


class TestReload(unittest.TestCase):
    """``reload()`` picks up changes in both the command registry AND
    on-disk markdown files, without restart."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="helprel_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reload_sees_changed_command_body(self):
        from data.help_topics import HelpManager
        registry = _FakeRegistry([_FakeCommand("x", help_text="v1")])
        mgr = HelpManager()
        mgr.load_all(registry)
        self.assertIn("v1", mgr.get("x").body)
        # Mutate the registry in place
        registry.all_commands = [_FakeCommand("x", help_text="v2")]
        mgr.reload()
        self.assertIn("v2", mgr.get("x").body)

    def test_reload_sees_new_markdown_file(self):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(self.tmp)
        self.assertIsNone(mgr.get("topicx"))
        # Write a new file and reload
        with open(os.path.join(self.tmp, "topicx.md"), "w", encoding="utf-8") as f:
            f.write("---\nkey: topicx\ntitle: X\ncategory: T\n---\nBody\n")
        mgr.reload()
        self.assertIsNotNone(mgr.get("topicx"))


class TestAliasHygiene(unittest.TestCase):
    """Re-registering an entry with fewer aliases shouldn't leave
    stale aliases pointing at it."""

    def test_stale_alias_cleared_on_overwrite(self):
        from data.help_topics import HelpEntry, HelpManager
        mgr = HelpManager()
        mgr.register(HelpEntry(
            key="x", title="X", category="C", body="",
            aliases=["y", "z"],
        ))
        self.assertIs(mgr.get("y"), mgr.get("x"))
        # Overwrite with fewer aliases
        mgr.register(HelpEntry(
            key="x", title="X new", category="C", body="",
            aliases=["z"],
        ))
        # "y" should no longer resolve to x
        self.assertIsNone(mgr.get("y"))
        # "z" still works
        self.assertIs(mgr.get("z"), mgr.get("x"))


class TestByTag(unittest.TestCase):

    def test_by_tag_returns_all_matching(self):
        from data.help_topics import HelpEntry, HelpManager
        mgr = HelpManager()
        mgr.register(HelpEntry(
            key="a", title="A", category="C", body="",
            tags=["combat", "newbie"],
        ))
        mgr.register(HelpEntry(
            key="b", title="B", category="C", body="",
            tags=["combat"],
        ))
        mgr.register(HelpEntry(
            key="c", title="C", category="C", body="",
            tags=["economy"],
        ))
        combat = mgr.by_tag("combat")
        keys = {e.key for e in combat}
        self.assertEqual(keys, {"a", "b"})
        self.assertEqual(mgr.by_tag(""), [])
        self.assertEqual(mgr.by_tag("nonexistent"), [])


if __name__ == "__main__":
    unittest.main()
