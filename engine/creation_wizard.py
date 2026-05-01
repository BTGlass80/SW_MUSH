# -*- coding: utf-8 -*-
"""
Guided character creation wizard.

Walks players through D6 character creation step-by-step with
rich descriptions sourced from the WEG R&E rulebook, while
retaining the ability to undo, go back, or drop into free-form
editing at any point.

Steps:
  1. Welcome & path choice (template vs scratch)
  2a. Template selection (with gameplay descriptions)
  2b. Species selection (scratch path)
  3. Attributes (scratch path)
  4. Skills
  5. Force Sensitivity
  6. Background (free text)
  7. Review & confirm
"""
import os
import logging
import textwrap
from typing import Optional

import yaml

from engine.dice import DicePool
from engine.character import ATTRIBUTE_NAMES, SkillRegistry
from engine.species import SpeciesRegistry
from engine.creation import CreationEngine, TEMPLATES
from server.ansi import (
    BOLD, RESET, CYAN, YELLOW, GREEN, RED, DIM, WHITE,
    BRIGHT_WHITE, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN,
    BRIGHT_RED, BRIGHT_BLUE, BRIGHT_MAGENTA,
)
from engine.text_format import Fmt

log = logging.getLogger(__name__)

DEFAULT_WIDTH = 72  # Fallback; actual width comes from Fmt


# ── Helpers ──

def _bar(char="=", color=BRIGHT_CYAN, width=DEFAULT_WIDTH):
    return f"{color}{char * width}{RESET}"

def _hdr(text):
    return f"{BOLD}{BRIGHT_WHITE}{text}{RESET}"

def _dim(text):
    return f"{DIM}{text}{RESET}"

def _yl(text):
    return f"{BRIGHT_YELLOW}{text}{RESET}"

def _gr(text):
    return f"{BRIGHT_GREEN}{text}{RESET}"

def _cy(text):
    return f"{CYAN}{text}{RESET}"

def _mg(text):
    return f"{BRIGHT_MAGENTA}{text}{RESET}"

def _bl(text):
    return f"{BRIGHT_BLUE}{text}{RESET}"

def _wrap(text, indent=2, width=DEFAULT_WIDTH-4):
    """Word-wrap text with consistent indent."""
    lines = []
    for para in text.strip().split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        for line in textwrap.wrap(para, width=width):
            lines.append(" " * indent + line)
    return lines


def _load_skill_descriptions(data_dir="data"):
    """Load skill_descriptions.yaml. Returns dict or empty on failure."""
    path = os.path.join(data_dir, "skill_descriptions.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.warning("Could not load skill_descriptions.yaml: %s", e)
        return {}


# ── Step Constants ──

STEP_WELCOME = "welcome"
STEP_TEMPLATE_SELECT = "template_select"
STEP_SPECIES = "species"
STEP_ATTRIBUTES = "attributes"
STEP_SKILLS = "skills"
STEP_FORCE = "force"
STEP_BACKGROUND = "background"
STEP_TUTORIAL_CHAIN = "tutorial_chain"  # F.8.c.1: CW-only step
STEP_REVIEW = "review"
STEP_FREEFORM = "freeform"

# ── F.8.c.1 (Apr 30 2026) — Tutorial-chain selection step ────────────────
# Inserted between STEP_BACKGROUND and STEP_REVIEW for the CW era ONLY.
# GCW chargen uses the legacy `engine/tutorial_v2.py` 8-elective tutorial
# model; CW chargen uses the new chain-based tutorial seam from
# `engine/tutorial_chains.py` (delivered F.8 Phase 1) plus the 24
# tutorial-zone rooms from F.8.b.
#
# The chain step is era-conditional via _build_step_lists() at __init__
# time. Eras without a chains.yaml file (GCW) get the legacy step
# lists; CW gets the chain step inserted before review.

# Ordered step list for back/forward navigation
SCRATCH_STEPS_LEGACY = [
    STEP_WELCOME, STEP_SPECIES, STEP_ATTRIBUTES,
    STEP_SKILLS, STEP_FORCE, STEP_BACKGROUND, STEP_REVIEW,
]
TEMPLATE_STEPS_LEGACY = [
    STEP_WELCOME, STEP_TEMPLATE_SELECT,
    STEP_SKILLS, STEP_FORCE, STEP_BACKGROUND, STEP_REVIEW,
]
# CW step lists with chain selection slotted before review
SCRATCH_STEPS_CW = [
    STEP_WELCOME, STEP_SPECIES, STEP_ATTRIBUTES,
    STEP_SKILLS, STEP_FORCE, STEP_BACKGROUND,
    STEP_TUTORIAL_CHAIN, STEP_REVIEW,
]
TEMPLATE_STEPS_CW = [
    STEP_WELCOME, STEP_TEMPLATE_SELECT,
    STEP_SKILLS, STEP_FORCE, STEP_BACKGROUND,
    STEP_TUTORIAL_CHAIN, STEP_REVIEW,
]

# Module-level aliases preserve the pre-F.8.c.1 names for any external
# imports. These default to the legacy lists; CreationWizard switches
# at __init__ time via `self.scratch_steps` / `self.template_steps`.
SCRATCH_STEPS = SCRATCH_STEPS_LEGACY
TEMPLATE_STEPS = TEMPLATE_STEPS_LEGACY


class CreationWizard:
    """
    Step-by-step character creation that wraps CreationEngine.

    Call get_initial_display() for the first screen, then
    process_input(text) for each line of player input.
    Returns (display_text, prompt, is_done) from process_input.
    """

    def __init__(self, species_reg: SpeciesRegistry, skill_reg: SkillRegistry,
                 data_dir: str = "data", width: int = DEFAULT_WIDTH):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.engine = CreationEngine(species_reg, skill_reg)
        self.descs = _load_skill_descriptions(data_dir)
        self.step = STEP_WELCOME
        self.path = "undecided"  # "template" or "scratch"
        self.background = ""
        self._force_sensitive = False
        self.fmt = Fmt(width=width)

        # ── F.8.c.1: Era-conditional tutorial chain selection ──
        # The wizard detects whether the active era has chain-based
        # tutorials. CW does (via data/worlds/clone_wars/tutorials/
        # chains.yaml); GCW falls through to the legacy elective-module
        # tutorial in engine/tutorial_v2.py. The seam in
        # engine/tutorial_chains.load_tutorial_chains() returns None
        # for eras without a chains.yaml — that's the signal to use the
        # legacy step lists.
        self._chains_corpus = None
        self._selected_chain_id: Optional[str] = None
        self.scratch_steps = SCRATCH_STEPS_LEGACY
        self.template_steps = TEMPLATE_STEPS_LEGACY
        try:
            from engine.tutorial_chains import load_tutorial_chains
            corpus = load_tutorial_chains()  # uses active era
            if corpus is not None and corpus.ok and corpus.chains:
                self._chains_corpus = corpus
                self.scratch_steps = SCRATCH_STEPS_CW
                self.template_steps = TEMPLATE_STEPS_CW
        except Exception as e:
            log.warning(
                "[creation_wizard] Tutorial chains corpus unavailable "
                "(%s); falling back to legacy step lists.", e,
            )

    # ══════════════════════════════════════════════
    #  PUBLIC API
    # ══════════════════════════════════════════════

    def get_initial_display(self) -> tuple[str, str]:
        """Show the welcome screen."""
        return self._render_step(), self._prompt()

    def process_input(self, text: str) -> tuple[str, str, bool]:
        """Process one line of input. Returns (display, prompt, done)."""
        text = text.strip()
        if not text:
            return "", self._prompt(), False

        low = text.lower()

        # ── Freeform mode: pass everything to engine ──
        if self.step == STEP_FREEFORM:
            if low == "guided":
                self.step = STEP_REVIEW
                return (f"  {_gr('Returning to guided mode at review step.')}\n\n"
                        + self._render_step()), self._prompt(), False
            display, prompt, done = self.engine.process_input(text)
            return display, prompt or "create> ", done

        # ── Global commands available at any step ──
        if low == "help":
            return self._global_help(), self._prompt(), False
        if low in ("sheet", "review") and self.step != STEP_REVIEW:
            return self._show_sheet(), self._prompt(), False
        if low == "undo":
            return self._cmd_undo(), self._prompt(), False
        if low == "free":
            return self._enter_freeform(), "create> ", False
        if low == "back":
            return self._go_back(), self._prompt(), False

        # ── Step-specific handling ──
        handler = {
            STEP_WELCOME: self._handle_welcome,
            STEP_TEMPLATE_SELECT: self._handle_template_select,
            STEP_SPECIES: self._handle_species,
            STEP_ATTRIBUTES: self._handle_attributes,
            STEP_SKILLS: self._handle_skills,
            STEP_FORCE: self._handle_force,
            STEP_BACKGROUND: self._handle_background,
            STEP_TUTORIAL_CHAIN: self._handle_tutorial_chain,
            STEP_REVIEW: self._handle_review,
        }.get(self.step)

        if handler:
            return handler(text)

        return f"  Unknown state. Type 'help'.", self._prompt(), False

    def get_character(self):
        """Build final Character from state (delegates to engine)."""
        char = self.engine.get_character()
        if self._force_sensitive:
            char.force_sensitive = True
            char.force_points = 2   # R&E: Force-sensitive start with 2 FP
        if self.background:
            char.description = self.background
        return char

    def get_background(self) -> str:
        """Return the player's background text."""
        return self.background

    def is_force_sensitive(self) -> bool:
        return self._force_sensitive

    # ══════════════════════════════════════════════
    #  STEP RENDERERS
    # ══════════════════════════════════════════════

    def _render_step(self) -> str:
        """Render the current step's display."""
        renderers = {
            STEP_WELCOME: self._render_welcome,
            STEP_TEMPLATE_SELECT: self._render_template_select,
            STEP_SPECIES: self._render_species,
            STEP_ATTRIBUTES: self._render_attributes,
            STEP_SKILLS: self._render_skills,
            STEP_FORCE: self._render_force,
            STEP_BACKGROUND: self._render_background,
            STEP_TUTORIAL_CHAIN: self._render_tutorial_chain,
            STEP_REVIEW: self._render_review,
        }
        renderer = renderers.get(self.step, self._render_welcome)
        return renderer()

    def _render_welcome(self):
        lines = [
            "",
            self.fmt.bar("="),
            "",
            f"  {_hdr('S T A R   W A R S')}",
            f"  {_dim('The Roleplaying Game — Character Creation')}",
            "",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            "Welcome to Mos Eisley, the most wretched hive of scum and "
            "villainy in the galaxy. Before you step into its dusty streets, "
            "you need a character — someone to BE in this world."
        ))
        lines.append("")
        lines.extend(self.fmt.wrap(
            "You have two paths:"
        ))
        lines.append("")
        lines.append(f"  {_yl('1')} — {_hdr('Pick a Template')}  "
                     f"{_dim('(Quick start — choose an archetype and customize)')}")
        lines.append(f"  {_yl('2')} — {_hdr('Build from Scratch')}  "
                     f"{_dim('(Full control — choose species, set every stat)')}")
        lines.append("")
        lines.append(f"  {_dim('Type')} {_yl('1')} {_dim('or')} "
                     f"{_yl('2')} {_dim('to choose, or')} "
                     f"{_yl('help')} {_dim('for navigation commands.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        lines.append("")
        return "\n".join(lines)

    def _render_template_select(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 1: Choose a Template')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            "Templates are pre-built archetypes — a starting point you can "
            "customize. Each one has attributes, skills and a backstory "
            "already set. You can change anything after selecting."
        ))
        lines.append("")

        tmpl_descs = self.descs.get("templates", {})
        for i, (key, tmpl) in enumerate(TEMPLATES.items(), 1):
            desc_data = tmpl_descs.get(key, {})
            tagline = desc_data.get("tagline", tmpl["label"])
            gameplay = desc_data.get("gameplay", "")
            key_skills = desc_data.get("key_skills", [])

            lines.append(f"  {_yl(str(i))}. {_hdr(tmpl['label'])} — {_cy(tagline)}")

            if gameplay:
                # Show first two sentences of gameplay desc
                gp_short = ". ".join(gameplay.strip().split(".")[:2]) + "."
                for gl in self.fmt.wrap(gp_short, indent=5, width=self.fmt.prose_width - 4):
                    lines.append(gl)

            if key_skills:
                sk_str = ", ".join(s.title() for s in key_skills[:6])
                lines.append(f"     {_dim('Key skills:')} {_gr(sk_str)}")
            lines.append("")

        lines.append(f"  {_dim('Type a number (1-'+ str(len(TEMPLATES)) +') or template name to select.')}")
        lines.append(f"  {_dim('Type')} {_yl('back')} {_dim('to return to the previous step.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _render_species(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 1: Choose Your Species')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            "Your species determines your attribute ranges — the minimum "
            "and maximum you can set each attribute to — as well as any "
            "special abilities. Most species get 18D to distribute among "
            "six attributes and 7D for skills."
        ))
        lines.append("")

        for sp in self.species_reg.list_all():
            lines.append(f"  {_hdr(sp.name)} — {_dim(sp.homeworld)}")
            # One-line description
            desc_text = sp.description.strip()
            # Show full first sentence, word-wrapped (no truncation)
            first_sentence = desc_text.split(".")[0] + "."
            for dl in self.fmt.wrap(first_sentence, indent=4):
                lines.append(f"{_cy('')}{dl}")

            # Attribute range summary (compact)
            ranges = []
            for attr in ATTRIBUTE_NAMES:
                r = sp.attributes.get(attr)
                if r:
                    abbr = attr[:3].upper()
                    ranges.append(f"{abbr} {r.min_pool}-{r.max_pool}")
            lines.append(f"    {_dim(' | '.join(ranges))}")

            # Special abilities on one line
            if sp.special_abilities:
                abs_str = ", ".join(a.name for a in sp.special_abilities)
                lines.append(f"    {_mg('Abilities:')} {abs_str}")

            lines.append("")

        lines.append(f"  {_dim('Type a species name to select (e.g.')} "
                     f"{_yl('human')}{_dim('), or')} {_yl('info <species>')} "
                     f"{_dim('for full details.')}")
        lines.append(f"  {_dim('Then type')} {_yl('next')} {_dim('to proceed to attributes.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _render_attributes(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 2: Set Your Attributes')}",
            self.fmt.bar("-", DIM),
            "",
        ]

        sp = self.engine.state.species
        sp_name = sp.name if sp else "Unknown"
        attr_total = self.engine._attr_pips_total()
        attr_spent = self.engine._attr_pips_spent()
        attr_left = attr_total - attr_spent
        pips_str = self._pips_display(attr_left)

        lines.extend(self.fmt.wrap(
            f"As a {sp_name}, you have {self._pips_to_dice(attr_total)} to distribute "
            f"among six attributes. Each has a minimum and maximum set by your "
            f"species. You have {self._pips_to_dice(attr_left)} remaining."
        ))
        lines.append("")

        attr_descs = self.descs.get("attributes", {})
        for attr in ATTRIBUTE_NAMES:
            ad = attr_descs.get(attr, {})
            r = sp.attributes.get(attr) if sp else None
            current = self.engine.state.attributes.get(attr, DicePool(0, 0))
            short_desc = ad.get("short", "")
            gameplay = ad.get("gameplay_note", "")

            range_str = f"{r.min_pool}-{r.max_pool}" if r else "2D-4D"
            lines.append(f"  {_hdr(attr.upper())} "
                         f"{_yl(str(current))} "
                         f"{_dim('(range: ' + range_str + ')')}")
            if short_desc:
                lines.append(f"    {_cy(short_desc)}")
            if gameplay:
                # First sentence of gameplay note
                gp = gameplay.strip().split(".")[0] + "."
                lines.append(f"    {_dim(gp)}")
            lines.append("")

        lines.append(f"  {_dim('Remaining:')} {pips_str}")
        lines.append("")
        lines.append(f"  {_dim('Commands:')} {_yl('set <attr> <dice>')} "
                     f"{_dim('(e.g.')} {_yl('set dex 3D+1')}{_dim(')')}")
        lines.append(f"  {_dim('Type')} {_yl('next')} {_dim('when done, or')} "
                     f"{_yl('back')} {_dim('to change species.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _render_skills(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 3: Choose Your Skills')}",
            self.fmt.bar("-", DIM),
            "",
        ]

        skill_total = self.engine._skill_pips_total()
        skill_spent = self.engine._skill_pips_spent()
        skill_left = skill_total - skill_spent
        pips_str = self._pips_display(skill_left)

        lines.extend(self.fmt.wrap(
            f"You have {self._pips_to_dice(skill_total)} to spend on skills. "
            f"Skills are a bonus on top of your attribute — if your Dexterity "
            f"is 3D and you put +1D in Blaster, you roll 4D to shoot. "
            f"You have {self._pips_to_dice(skill_left)} remaining."
        ))
        lines.append("")
        lines.append(f"  {_dim('Skills marked')} {_yl('*')} {_dim('are especially important in this game.')}")
        lines.append("")

        skill_descs = self.descs.get("skills", {})
        for attr in ATTRIBUTE_NAMES:
            pool = self.engine.state.attributes.get(attr, DicePool(0, 0))
            lines.append(f"  {_hdr(attr.upper())} {_dim('(' + str(pool) + ')')}")

            attr_skills = skill_descs.get(attr, {})
            for sd in self.skill_reg.skills_for_attribute(attr):
                current = self.engine.state.skills.get(sd.key)
                # Normalize key for YAML lookup
                yaml_key = sd.key.replace(" ", "_").replace("/", "_")
                sk_desc = attr_skills.get(yaml_key, {})
                priority = sk_desc.get("priority", "low")
                star = f" {_yl('*')}" if priority == "high" else ""

                if current:
                    total = pool + current
                    lines.append(f"    {_gr(sd.name):27s} +{current} = {_yl(str(total))}{star}")
                elif priority in ("high", "medium"):
                    # Show recommended unallocated skills with short hint
                    game_use = sk_desc.get("game_use", "")
                    hint = game_use.strip().split(".")[0] + "." if game_use else ""
                    lines.append(f"    {_dim(sd.name):27s} {_dim(hint)}{star}")

            lines.append("")

        lines.append(f"  {_dim('Remaining:')} {pips_str}")
        lines.append("")
        lines.append(f"  {_yl('skill <name> <dice>')} {_dim('— add dice (e.g.')} "
                     f"{_yl('skill blaster 2D')}{_dim(')')}")
        lines.append(f"  {_yl('unskill <name>')} {_dim('— remove |')} "
                     f"{_yl('list <attr>')} {_dim('— browse all |')} "
                     f"{_yl('explain <skill>')} {_dim('— details')}")
        lines.append(f"  {_dim('Type')} {_yl('next')} {_dim('when done, or')} "
                     f"{_yl('back')} {_dim('to change attributes.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _render_force(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 4: The Force')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            '"The Force is what gives a Jedi his power. It\'s an energy field '
            'created by all living things. It surrounds us and penetrates us. '
            'It binds the galaxy together." — Obi-Wan Kenobi'
        ))
        lines.append("")
        lines.extend(self.fmt.wrap(
            "Only a rare few are sensitive to the Force. This choice affects "
            "your starting Force Points and whether you can learn Force "
            "powers (Control, Sense, Alter) during play."
        ))
        lines.append("")
        lines.append(f"  {_yl('yes')} — {_hdr('Force-Sensitive')}")
        lines.append(f"    {_cy('Start with 2 Force Points. Can learn Force powers.')}")
        lines.append(f"    {_cy('Must follow the Jedi Code: act with honor and restraint.')}")
        lines.append(f"    {_cy('Dark Side Points track your choices — at 6 DSP, you may fall.')}")
        lines.append(f"    {_cy('Control governs your inner Force. Sense detects the world')}")
        lines.append(f"    {_cy('around you. Alter lets you manipulate the Force externally.')}")
        lines.append("")
        lines.append(f"  {_yl('no')}  — {_hdr('Not Force-Sensitive')} {_dim('(default)')}")
        lines.append(f"    {_cy('Start with 1 Force Point. Cannot learn Force powers.')}")
        lines.append(f"    {_cy('No behavioral restrictions. You can be as mercenary as')}")
        lines.append(f"    {_cy('Han Solo at the start of A New Hope.')}")
        lines.append("")
        lines.append(f"  {_dim('Type')} {_yl('yes')} {_dim('or')} "
                     f"{_yl('no')}{_dim(', or')} {_yl('next')} {_dim('to default to No.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _render_background(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('STEP 5: Name & Background')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            "Every character has a story. What brings you to Mos Eisley? "
            "Are you running from something? Looking for work? Chasing a "
            "bounty? Hiding from the Empire?"
        ))
        lines.append("")
        lines.extend(self.fmt.wrap(
            "Write a sentence or two about your character's history and "
            "personality. This helps other players understand who you are "
            "and gives depth to roleplay interactions."
        ))
        lines.append("")

        name = self.engine.state.name
        lines.append(f"  {_dim('Name:')} {_yl(name or '(not set)')}")
        if self.background:
            lines.append(f"  {_dim('Background:')}")
            for bl in self.fmt.wrap(self.background, indent=4):
                lines.append(bl)
        lines.append("")
        lines.append(f"  {_yl('name <n>')} {_dim('— set your character name')}")
        lines.append(f"  {_dim('Just type your background text to set it.')}")
        lines.append(f"  {_dim('Type')} {_yl('next')} {_dim('to proceed to final review.')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    # ── F.8.c.1: Tutorial chain selection (CW only) ──────────────────────
    def _render_tutorial_chain(self):
        """Render the tutorial-chain selection screen.

        Shows the player a numbered list of available chains, with
        locked chains marked. Players pick a chain by number or by
        chain_id, or skip with `next`.

        Locked-chain rejection (F.8.c.1):
          - jedi_path is locked at chargen because the design's
            Force-policy gates Jedi behind the Village quest chain.
            The chain's locked_message is shown inline, but the chain
            cannot be selected.
          - Other chains may have prereq-blocks (e.g. faction_intent
            mismatches) that make them unavailable; those are filtered
            out of the menu.
        """
        if self._chains_corpus is None:
            # Should never reach this if the step is in the list, but
            # belt-and-suspenders.
            self.step = STEP_REVIEW
            return self._render_step()

        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('TUTORIAL CHAIN')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        lines.extend(self.fmt.wrap(
            "Pick a profession path. Each chain walks you through 4-6 "
            "tutorial steps with NPCs of that profession, then drops "
            "you into the live galaxy with a starter package and "
            "faction reputation. You can complete other chains later, "
            "but you'll start with this one."
        ))
        lines.append("")

        # Build the player-attrs dict for prereq checks. At chargen
        # we don't have a full character yet, so we synthesize:
        char_attrs = self._chargen_attrs_for_chain_check()

        # List unlocked chains numbered, locked chains marked
        from engine.tutorial_chains import is_chain_locked_for_character
        self._menu_chains = []  # ordered list of selectable chain_ids
        idx = 1
        for chain in self._chains_corpus.chains:
            is_locked, reason = is_chain_locked_for_character(chain, char_attrs)
            if is_locked:
                # Show locked entry but greyed-out, no number
                lines.append(
                    f"  {_dim('—')}  {_dim(chain.chain_name)}  "
                    f"{_dim('(' + chain.archetype_label + ')')}"
                )
                # Word-wrap the locked-reason as a sub-line
                for sub in self.fmt.wrap(reason, indent=6):
                    lines.append(f"     {_dim(sub.lstrip())}")
            else:
                lines.append(
                    f"  {_yl(str(idx))}  {_hdr(chain.chain_name)}  "
                    f"{_dim('(' + chain.archetype_label + ')')}"
                )
                for sub in self.fmt.wrap(chain.description, indent=6):
                    lines.append(f"     {sub.lstrip()}")
                if chain.duration_minutes:
                    lines.append(f"     {_dim('~' + str(chain.duration_minutes) + ' minutes')}")
                self._menu_chains.append(chain.chain_id)
                idx += 1
            lines.append("")

        lines.append(f"  {_yl('1-' + str(len(self._menu_chains)))}  "
                     f"{_dim('— pick a chain by number')}")
        lines.append(f"  {_yl('next')}  {_dim('— skip the tutorial (drops you straight into the galaxy)')}")
        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    def _handle_tutorial_chain(self, text):
        """Process tutorial-chain step input."""
        low = text.lower().strip()

        if low in ("next", "skip"):
            # Skip the tutorial chain entirely; advance to review
            self._selected_chain_id = None
            self.step = self._next_step_after(STEP_TUTORIAL_CHAIN)
            return (f"  {_dim('Tutorial chain skipped — you will start in the live galaxy.')}\n\n"
                    + self._render_step()), self._prompt(), False

        # Numeric selection
        if low.isdigit():
            n = int(low)
            menu = getattr(self, "_menu_chains", [])
            if 1 <= n <= len(menu):
                chain_id = menu[n - 1]
                return self._select_chain_by_id(chain_id)
            return (f"  {BRIGHT_RED}No chain numbered {n}.{RESET}\n"
                    f"  {_dim('Pick 1-' + str(len(menu)) + ' or')} "
                    f"{_yl('next')} {_dim('to skip.')}"), \
                   self._prompt(), False

        # Direct chain_id selection (handy for power users)
        if self._chains_corpus:
            chain = self._chains_corpus.by_id().get(low)
            if chain is not None:
                return self._select_chain_by_id(low)

        return (f"  {_dim('Pick a chain by number, or type')} "
                f"{_yl('next')} {_dim('to skip.')}"), \
               self._prompt(), False

    def _select_chain_by_id(self, chain_id: str):
        """Internal: store the chain selection and advance to review."""
        if self._chains_corpus is None:
            self.step = STEP_REVIEW
            return self._render_step(), self._prompt(), False
        chain = self._chains_corpus.by_id().get(chain_id)
        if chain is None:
            return (f"  {BRIGHT_RED}No chain '{chain_id}'.{RESET}", self._prompt(), False)
        # Re-check locked status against current attrs — this catches the
        # edge case where someone reaches this method via direct chain_id
        # input bypassing the menu filter.
        from engine.tutorial_chains import is_chain_locked_for_character
        attrs = self._chargen_attrs_for_chain_check()
        is_locked, reason = is_chain_locked_for_character(chain, attrs)
        if is_locked:
            return (f"  {BRIGHT_RED}{reason}{RESET}", self._prompt(), False)
        self._selected_chain_id = chain_id
        self.step = self._next_step_after(STEP_TUTORIAL_CHAIN)
        return (f"  {_gr('Path selected: ' + chain.chain_name)}.\n"
                f"  {_dim('You will be routed to')} "
                f"{_yl(chain.starting_room or '(graduation drop_room)')} "
                f"{_dim('after final review.')}\n\n"
                + self._render_step()), self._prompt(), False

    def _chargen_attrs_for_chain_check(self) -> dict:
        """Build the minimal char_attrs dict for chain-prereq checking.

        At chargen we don't have a full character yet, but
        is_chain_locked_for_character() needs:
          - chargen_complete: implicitly True at this step (player has
            finished background already; we're 1 step from done)
          - faction_intent: at chargen, picking a faction-aligned chain
            IS the faction commitment, so we synthesize a permissive
            faction_intent that satisfies any chain's gate. F.8.c.1
            uses a sentinel value "__chargen_any__" that the
            engine.tutorial_chains module treats as "matches any
            faction_intent prereq" (chargen-only override).
            (Actual runtime faction_intent is set post-chargen
            by the chain selection itself.)
          - force_sensitive / jedi_path_unlocked: from wizard state.
            jedi_path remains LOCKED at chargen by design — Jedi unlock
            requires the F.10 Village quest, regardless of force-sensitive
            attribute.
        """
        attrs = {
            "chargen_complete": True,
            "faction_intent": "__chargen_any__",
            "force_sensitive": self._force_sensitive,
            # jedi_path_unlocked is set by the F.10 Village quest, not
            # chargen. Always False at character creation.
            "jedi_path_unlocked": False,
        }
        return attrs

    def get_selected_chain_id(self) -> Optional[str]:
        """Return the player's selected tutorial chain_id, or None if
        skipped / not applicable. Used by game_server.py post-chargen
        to layer the tutorial_chain state into the character's
        attributes JSON before DB save."""
        return self._selected_chain_id

    def get_tutorial_chain_block(self) -> Optional[dict]:
        """Return the tutorial_chain state block to merge into the
        character's attributes JSON, or None if no chain selected.

        Format matches engine/tutorial_chains.select_chain():
            {
                "chain_id": <str>,
                "step": 1,
                "started_at": <unix_ts>,
                "completed_steps": [],
                "completion_state": "active",
            }
        """
        if not self._selected_chain_id or self._chains_corpus is None:
            return None
        import time
        return {
            "chain_id": self._selected_chain_id,
            "step": 1,
            "started_at": time.time(),
            "completed_steps": [],
            "completion_state": "active",
        }

    def get_tutorial_chain_starting_room_slug(self) -> Optional[str]:
        """Return the room slug to teleport the new character into,
        or None if no chain was selected. Returned slug is a
        room slug; game_server.py is responsible for resolving it
        to a room id via DB lookup."""
        if not self._selected_chain_id or self._chains_corpus is None:
            return None
        chain = self._chains_corpus.by_id().get(self._selected_chain_id)
        if chain is None:
            return None
        # Locked-stub chains (jedi_path) have empty starting_room; those
        # shouldn't be selectable anyway, but defend against it.
        return chain.starting_room or None

    def _render_review(self):
        lines = [
            "",
            self.fmt.bar("="),
            f"  {_hdr('FINAL REVIEW')}",
            self.fmt.bar("-", DIM),
            "",
        ]
        sheet_lines = self.engine._sheet_lines()
        lines.extend(sheet_lines)
        lines.append("")

        # Force sensitivity display
        fs_str = "Yes" if self._force_sensitive else "No"
        lines.append(f"  {_hdr('Force Sensitive:')} {_bl(fs_str)}")

        if self.background:
            lines.append(f"  {_hdr('Background:')}")
            for bl in self.fmt.wrap(self.background, indent=4):
                lines.append(bl)
        lines.append("")

        # Validation
        errors = self.engine._validate()

        if errors:
            lines.append(f"  {BRIGHT_RED}Issues to resolve:{RESET}")
            for e in errors:
                lines.append(f"    {BRIGHT_RED}- {e}{RESET}")
            lines.append("")
            lines.append(f"  {_dim('Fix issues, then type')} "
                         f"{_yl('done')} {_dim('to finalize.')}")
        else:
            lines.append(f"  {_gr('Everything looks good!')}")
            lines.append(f"  {_dim('Type')} {_yl('done')} "
                         f"{_dim('to enter the galaxy, or')} "
                         f"{_yl('back')} {_dim('to make changes.')}")

        lines.append("")
        lines.append(self.fmt.bar("="))
        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  STEP HANDLERS
    # ══════════════════════════════════════════════

    def _handle_welcome(self, text):
        low = text.lower().strip()
        if low in ("1", "template", "templates"):
            self.path = "template"
            self.step = STEP_TEMPLATE_SELECT
            return self._render_step(), self._prompt(), False
        elif low in ("2", "scratch", "custom", "build"):
            self.path = "scratch"
            self.step = STEP_SPECIES
            return self._render_step(), self._prompt(), False
        else:
            return (f"  {_dim('Please type')} {_yl('1')} {_dim('for template or')} "
                    f"{_yl('2')} {_dim('for scratch.')}"),\
                   self._prompt(), False

    def _handle_template_select(self, text):
        low = text.lower().strip()
        template_keys = list(TEMPLATES.keys())

        # Try numeric selection
        selected_key = None
        try:
            idx = int(low) - 1
            if 0 <= idx < len(template_keys):
                selected_key = template_keys[idx]
        except ValueError as _e:
            log.debug("silent except in engine/creation_wizard.py:610: %s", _e, exc_info=True)

        # Try name match
        if not selected_key:
            key = low.replace(" ", "_")
            if key in TEMPLATES:
                selected_key = key
            else:
                matches = [k for k in template_keys if k.startswith(key)]
                if len(matches) == 1:
                    selected_key = matches[0]

        if selected_key:
            self.engine.process_input(f"template {selected_key}")
            self.step = STEP_SKILLS
            tmpl_descs = self.descs.get("templates", {})
            desc_data = tmpl_descs.get(selected_key, {})
            description = desc_data.get("description", "")

            result_lines = [f"  {_gr('Template applied:')} "
                            f"{_hdr(TEMPLATES[selected_key]['label'])}",
                            ""]
            if description:
                result_lines.extend(self.fmt.wrap(description, indent=2))
                result_lines.append("")
            result_lines.append(f"  {_dim('You can edit any attribute or skill from here.')}")
            result_lines.append("")
            result_lines.append(self._render_step())
            return "\n".join(result_lines), self._prompt(), False

        return f"  Unknown template: '{text}'. Type a number or name.", \
               self._prompt(), False

    def _handle_species(self, text):
        low = text.lower().strip()
        parts = low.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd == "info" and len(parts) > 1:
            display, _, _ = self.engine.process_input(f"info {parts[1]}")
            return display, self._prompt(), False

        if cmd == "next":
            if not self.engine.state.species:
                return "  You must select a species first.", self._prompt(), False
            self.step = STEP_ATTRIBUTES
            return self._render_step(), self._prompt(), False

        # Try species selection
        display, _, _ = self.engine.process_input(f"species {text}")
        return display, self._prompt(), False

    def _handle_attributes(self, text):
        low = text.lower().strip()
        parts = low.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd == "next":
            attr_left = self.engine._attr_pips_total() - self.engine._attr_pips_spent()
            if attr_left != 0:
                return (f"  You have {self._pips_to_dice(attr_left)} attribute dice "
                        f"remaining. Spend them all before continuing."), \
                       self._prompt(), False
            self.step = STEP_SKILLS
            return self._render_step(), self._prompt(), False

        if cmd == "set":
            display, _, _ = self.engine.process_input(text)
            return display, self._prompt(), False

        # Treat "dex 3D+1" as "set dex 3D+1"
        if len(parts) >= 2:
            display, _, _ = self.engine.process_input(f"set {text}")
            if "Unknown" not in display:
                return display, self._prompt(), False

        return (f"  {_dim('Use')} {_yl('set <attr> <dice>')} {_dim('(e.g.')} "
                f"{_yl('set dex 3D+1')}{_dim('). Type')} "
                f"{_yl('next')} {_dim('when done.')}"), \
               self._prompt(), False

    def _handle_skills(self, text):
        low = text.lower().strip()
        parts = low.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd == "next":
            self.step = STEP_FORCE
            return self._render_step(), self._prompt(), False

        if cmd == "explain" and len(parts) > 1:
            return self._explain_skill(parts[1]), self._prompt(), False

        if cmd in ("list", "skill", "unskill", "set"):
            display, _, _ = self.engine.process_input(text)
            return display, self._prompt(), False

        # Try as implicit skill command: "blaster 2D"
        if len(parts) >= 2:
            display, _, _ = self.engine.process_input(f"skill {text}")
            if "Unknown" not in display:
                return display, self._prompt(), False

        # Try as explain: "blaster"
        if len(parts) == 1:
            result = self._explain_skill(low)
            if "No description found" not in result:
                return result, self._prompt(), False

        return (f"  {_dim('Use')} {_yl('skill <name> <dice>')} "
                f"{_dim('or')} {_yl('explain <skill>')} "
                f"{_dim('or')} {_yl('list <attr>')}{_dim('.')}"), \
               self._prompt(), False

    def _handle_force(self, text):
        low = text.lower().strip()

        if low in ("yes", "y", "force", "sensitive"):
            self._force_sensitive = True
            self.step = STEP_BACKGROUND
            return (f"  {_bl('You are Force-sensitive.')} "
                    f"You will start with 2 Force Points.\n"
                    f"  {_dim('The Force is strong with you... but beware the dark side.')}\n\n"
                    + self._render_step()), self._prompt(), False

        if low in ("no", "n", "skip", "next"):
            self._force_sensitive = False
            self.step = STEP_BACKGROUND
            msg = f"  {_dim('Not Force-sensitive. You start with 1 Force Point.')}\n\n"
            return msg + self._render_step(), self._prompt(), False

        return (f"  {_dim('Type')} {_yl('yes')} {_dim('or')} {_yl('no')}"
                f"{_dim('.')}"), self._prompt(), False

    def _handle_background(self, text):
        low = text.lower().strip()
        parts = low.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd == "next":
            if not self.engine.state.name:
                return (f"  {BRIGHT_RED}You need a name before you can proceed.{RESET}\n"
                        f"  {_dim('Use')} {_yl('name <n>')} {_dim('to set it.')}"), \
                       self._prompt(), False
            self.step = self._next_step_after(STEP_BACKGROUND)
            return self._render_step(), self._prompt(), False

        if cmd == "name":
            display, _, _ = self.engine.process_input(text)
            return display, self._prompt(), False

        # Anything 5+ chars is treated as background text
        if len(text) >= 5:
            self.background = text
            return (f"  {_gr('Background set.')}\n"
                    f"  {_dim('Type')} {_yl('name <n>')} {_dim('if needed, then')} "
                    f"{_yl('next')} {_dim('to review.')}"), \
                   self._prompt(), False
        else:
            return (f"  {_dim('Write at least a short sentence for your background,')}\n"
                    f"  {_dim('or type')} {_yl('next')} {_dim('to skip.')}"), \
                   self._prompt(), False

    def _handle_review(self, text):
        low = text.lower().strip()
        parts = low.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd == "done":
            errors = self.engine._validate()
            if errors:
                lines = [f"  {BRIGHT_RED}Cannot finalize:{RESET}"]
                for e in errors:
                    lines.append(f"    {BRIGHT_RED}- {e}{RESET}")
                return "\n".join(lines), self._prompt(), False
            # Success!
            lines = self.engine._sheet_lines()
            lines.append("")
            lines.append(f"  {_gr('Character complete!')}")
            return "\n".join(lines), "", True

        # Allow editing commands at review
        if cmd in ("name", "set", "skill", "unskill", "species", "template"):
            display, _, _ = self.engine.process_input(text)
            return display + "\n\n" + self._render_review(), self._prompt(), False

        if cmd == "background" and len(parts) > 1:
            self.background = parts[1]
            return f"  {_gr('Background updated.')}\n\n" + self._render_review(), \
                   self._prompt(), False

        return (f"  {_dim('Type')} {_yl('done')} {_dim('to finalize, or edit with')} "
                f"{_yl('name')}{_dim('/')} {_yl('set')}{_dim('/')} "
                f"{_yl('skill')} {_dim('commands.')}"), \
               self._prompt(), False

    # ══════════════════════════════════════════════
    #  NAVIGATION & GLOBAL COMMANDS
    # ══════════════════════════════════════════════

    def _go_back(self):
        """Move to the previous step."""
        steps = self.template_steps if self.path == "template" else self.scratch_steps
        if self.step in steps:
            idx = steps.index(self.step)
            if idx > 0:
                self.step = steps[idx - 1]
                return self._render_step()
        return f"  {_dim('Already at the first step.')}"

    def _next_step_after(self, current_step: str) -> str:
        """Return the step that comes after `current_step` in the active
        step list. Used by step handlers that advance to "the next step"
        rather than naming a destination explicitly. F.8.c.1: lets
        background→next go to tutorial_chain in CW or review in GCW
        without each handler hardcoding the era.
        """
        steps = self.template_steps if self.path == "template" else self.scratch_steps
        try:
            idx = steps.index(current_step)
            if idx + 1 < len(steps):
                return steps[idx + 1]
        except ValueError:
            pass
        return STEP_REVIEW

    def _cmd_undo(self):
        display, _, _ = self.engine.process_input("undo")
        return display

    def _enter_freeform(self):
        """Drop into free-form editing mode."""
        lines = [
            "",
            f"  {_hdr('FREE-FORM MODE')}",
            f"  {_dim('You now have full control. All creation commands work:')}",
            f"  {_dim('name, species, set, skill, unskill, template, undo, sheet, done')}",
            "",
            f"  {_dim('Type')} {_yl('guided')} {_dim('to return to the guided wizard.')}",
            "",
        ]
        sheet_display, _, _ = self.engine.process_input("sheet")
        lines.append(sheet_display)
        self.step = STEP_FREEFORM
        return "\n".join(lines)

    def _show_sheet(self):
        display, _, _ = self.engine.process_input("sheet")
        return display

    def _explain_skill(self, skill_name):
        """Show detailed skill info from the descriptions YAML."""
        skill_descs = self.descs.get("skills", {})
        norm = skill_name.lower().replace("/", "_").replace(" ", "_")

        for attr, skills in skill_descs.items():
            for sk_key, sk_data in skills.items():
                if sk_key == norm or sk_key.replace("_", " ") == skill_name.lower():
                    lines = [""]
                    display_name = sk_key.replace("_", " ").title()
                    # Fix names with slashes
                    if "climbing" in sk_key:
                        display_name = "Climbing/Jumping"
                    if "computer" in sk_key:
                        display_name = "Computer Programming/Repair"
                    lines.append(f"  {_hdr(display_name)} "
                                 f"{_dim('(' + attr.capitalize() + ')')}")
                    lines.append("")
                    desc = sk_data.get("description", "")
                    if desc:
                        lines.extend(self.fmt.wrap(desc))
                        lines.append("")
                    game_use = sk_data.get("game_use", "")
                    if game_use:
                        lines.append(f"  {_hdr('In this game:')}")
                        lines.extend(self.fmt.wrap(game_use, indent=4))
                        lines.append("")
                    tip = sk_data.get("tip", "")
                    if tip:
                        lines.append(f"  {_mg('Tip:')} ")
                        lines.extend(self.fmt.wrap(tip, indent=4))
                        lines.append("")
                    return "\n".join(lines)

        return f"  No description found for '{skill_name}'. Try 'list <attr>' to browse."

    def _global_help(self):
        lines = [
            "",
            f"  {_hdr('NAVIGATION COMMANDS')} {_dim('(available at any step)')}",
            "",
            f"    {_yl('back')}             Go to the previous step",
            f"    {_yl('next')}             Proceed to the next step",
            f"    {_yl('sheet')}            Show your current character sheet",
            f"    {_yl('undo')}             Undo your last change",
            f"    {_yl('free')}             Drop into free-form editing mode",
            f"    {_yl('help')}             Show this help",
            "",
            f"  {_hdr('EDITING COMMANDS')}",
            "",
            f"    {_yl('name <n>')}          Set character name",
            f"    {_yl('set <attr> <dice>')}  Set attribute (e.g. set dex 3D+1)",
            f"    {_yl('skill <n> <dice>')}  Add skill bonus (e.g. skill blaster 2D)",
            f"    {_yl('unskill <n>')}       Remove skill bonus",
            f"    {_yl('list <attr|all>')}   Browse skills by attribute",
            f"    {_yl('explain <skill>')}   Detailed skill description and gameplay tips",
            f"    {_yl('info <species>')}    View full species details",
            "",
        ]
        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  UTILITIES
    # ══════════════════════════════════════════════

    def _prompt(self):
        step_prompts = {
            STEP_WELCOME: "choose> ",
            STEP_TEMPLATE_SELECT: "template> ",
            STEP_SPECIES: "species> ",
            STEP_ATTRIBUTES: "attrs> ",
            STEP_SKILLS: "skills> ",
            STEP_FORCE: "force> ",
            STEP_BACKGROUND: "story> ",
            STEP_REVIEW: "review> ",
            STEP_FREEFORM: "create> ",
        }
        return step_prompts.get(self.step, "create> ")

    def _pips_display(self, pips_left):
        dice_str = self._pips_to_dice(pips_left)
        if pips_left == 0:
            return _gr(f"{dice_str} remaining")
        elif pips_left < 0:
            return f"{BRIGHT_RED}{dice_str} OVERSPENT{RESET}"
        else:
            return _yl(f"{dice_str} remaining")

    @staticmethod
    def _pips_to_dice(pips):
        if pips < 0:
            return f"-{CreationWizard._pips_to_dice(-pips)}"
        d = pips // 3
        p = pips % 3
        return f"{d}D+{p}" if p > 0 else f"{d}D"
