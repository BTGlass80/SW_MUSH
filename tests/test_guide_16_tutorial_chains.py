"""Guard: Guide_16 Tutorial Chains teaches commands that actually RESOLVE
against the live registry, and its reward / skip-kit / chain-surface claims
match the engine + data at HEAD.

The Opus-owned guides quality pass.  Guide_16 is onboarding-critical — it is the
first thing a brand-new player reads — and it had drifted from HEAD in several
test-INVISIBLE ways (the curated suite never reads guide prose):

* **Phantom faction-rep numbers.**  The guide promised "+50" reputation per
  chain (and a "+30 / +15" split for Smuggler).  The chains award the literal
  ``graduation.faction_rep`` deltas via ``adjust_rep`` — single-digit-to-low-teen
  bumps on the 0-100 scale.  +50 is the *Honored* tier (a mid-game standing), not
  a fresh recruit's.  Removed.

* **Post-F.8.c.2.e command drift.**  Republic Soldier step 4 taught
  ``board`` / ``launch`` — but tutorial rooms have no walkable exits, so that step
  was re-anchored to ``talk`` (Pilot CT-7567).  Step 5's NPC is Sergeant Drix and
  it completes on ``+factions``, not a "duty officer" + ``comlink``.

* **Wrong reward amounts / phantom items.**  Shipwright graduates with 400
  credits (not 500) and grants no "schematics for entry-level items" item.

* **Skip starter kit.**  The guide said skip-chain alts get "no credits, no
  items" — they actually get a small fixed kit (300 cr + medpac + comlink +
  hold-out blaster), but no rep / achievement / chain gear.

* **Stale surfaces.**  ``training skip`` is deprecated (points at the chargen
  skip); chargen selects a chain by NUMBER, not ``chain <name>``; ``chain status``
  prints ``(step N)`` (no "of M" total) + ``Completes when: <type>``.

This test resolves every taught command against the SAME registry
``GameServer.__init__`` builds, pins the corrected claims, and cross-checks the
reward numbers against the live ``chains.yaml`` + ``skip_starter_kit.yaml`` so a
future data retune that desyncs the guide fails loudly here.
"""
import os

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_16_Tutorial_Chains.md")
CHAINS_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                           "tutorials", "chains.yaml")
SKIP_KIT_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                             "skip_starter_kit.yaml")
TUTORIAL_ROOMS_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                                   "tutorials", "rooms.yaml")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def chains_by_id():
    data = yaml.safe_load(_read(CHAINS_PATH))
    return {c["chain_id"]: c for c in data["chains"]}


@pytest.fixture(scope="module")
def skip_kit():
    return yaml.safe_load(_read(SKIP_KIT_PATH))


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__).
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_chainreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every command Guide_16 teaches must resolve against HEAD ──────────────────
# §4/§5 walkthroughs + §7/§8 chain + §11 training + §15 quick-ref.
_TAUGHT_FORMS = [
    "look", "move", "+sheet", "attack", "dodge",
    "+missions", "accept", "complete",
    "talk", "examine", "say", "use", "give",
    "+factions", "+bounties", "scan", "survey", "+craft",
    "chain", "training", "+achievements",
    "ooc", "page", "+who", "+finger",
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _TAUGHT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_16 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    def test_chain_subcommands(self, reg):
        """§7/§8 lean on `chain`, `chain status`, `chain attempt`."""
        from parser.chain_commands import _SUBCOMMANDS
        assert reg.get("chain") is not None
        assert {"attempt", "status"} <= _SUBCOMMANDS

    def test_training_modules(self, reg):
        """§11 names eight training modules — pin them against the engine."""
        from engine.tutorial_v2 import ELECTIVE_LABELS
        for module in ("space", "combat", "economy", "crafting",
                       "force", "bounty", "crew", "factions"):
            assert module in ELECTIVE_LABELS, (
                f"Guide_16 §11 lists `training {module}` but it is not a real "
                f"training module"
            )


# ── The phantom rep numbers must stay dead ────────────────────────────────────
class TestNoPhantomRepNumbers:
    def test_no_plus50_rep(self, guide_text):
        assert "+50" not in guide_text, (
            "Guide_16 must not promise '+50' reputation — chains award the "
            "literal graduation.faction_rep deltas (single digits to low teens), "
            "and +50 is the Honored tier, not a fresh graduate's standing"
        )

    def test_no_smuggler_30_15_split(self, guide_text):
        for tok in ("+30 independent", "+15 Hutt", "+30/+15"):
            assert tok not in guide_text, (
                f"Guide_16 must not carry the phantom Smuggler rep split {tok!r}"
            )

    def test_rep_tiers_pin_50_as_honored(self):
        """The fact the phantom got wrong: 50 is mid-high (Honored), not a
        recruit's foothold.  If the tier bands ever move, re-check the guide."""
        from engine.organizations import get_rep_tier
        assert get_rep_tier(50)[0] == "honored"
        # A graduate's ~10 lands at Recognized or below — a known face, not a
        # vetted veteran.  (Republic Soldier totals 9 across its steps.)
        assert get_rep_tier(9)[0] in ("unknown", "recognized")


# ── §4 Republic Soldier walkthrough must match the chain data ─────────────────
class TestRepublicSoldierRewards:
    def test_graduation_matches_data(self, chains_by_id):
        grad = chains_by_id["republic_soldier"]["graduation"]
        assert grad["credits"] == 500
        assert grad["items"] == [
            "dc15_blaster_rifle", "republic_light_armor", "comlink_basic"]
        assert grad["achievements"] == ["sworn_to_the_republic"]
        # The rep delta is single-digit, NOT 50.
        assert grad["faction_rep"]["republic"] == 3

    def test_step4_teaches_talk_not_board_launch(self, guide_text, chains_by_id):
        """Step 4 was re-anchored to talk_to_npc (Pilot CT-7567) by F.8.c.2.e —
        tutorial rooms have no exits, so board/launch never fire there."""
        step4 = chains_by_id["republic_soldier"]["steps"][3]
        assert step4["completion"]["type"] == "talk_to_npc"
        assert step4["teaches"] == ["talk"]
        assert "Pilot CT-7567" in guide_text
        assert "`board`, `launch`" not in guide_text

    def test_step5_is_sergeant_drix_factions(self, guide_text, chains_by_id):
        step5 = chains_by_id["republic_soldier"]["steps"][4]
        assert step5["completion"]["command"] == "+factions"
        assert "Sergeant Drix" in guide_text


# ── §5 other-chain reward claims must match the data ──────────────────────────
class TestOtherChainRewards:
    def test_shipwright_is_400_credits_no_schematics(self, guide_text,
                                                     chains_by_id):
        grad = chains_by_id["shipwright_trader"]["graduation"]
        assert grad["credits"] == 400, (
            "Shipwright graduates with 400 credits (lowest cash, most gear)"
        )
        assert "schematics for entry-level items" not in guide_text, (
            "Guide_16 must not claim a schematic-item grant — none is awarded"
        )
        assert "400 credits" in guide_text

    def test_bounty_hunter_700_credits(self, guide_text, chains_by_id):
        assert chains_by_id["bounty_hunter"]["graduation"]["credits"] == 700
        assert "700 credits" in guide_text

    def test_smuggler_dual_faction_800(self, guide_text, chains_by_id):
        grad = chains_by_id["smuggler"]["graduation"]
        assert grad["credits"] == 800
        # Dual-faction graduation rep: Independent + Hutt Cartel.
        assert "independent" in grad["faction_rep"]
        assert "hutt_cartel" in grad["faction_rep"]
        assert "800 credits" in guide_text

    def test_republic_intel_item_set(self, guide_text, chains_by_id):
        grad = chains_by_id["republic_intelligence"]["graduation"]
        assert grad["items"] == [
            "concealed_blaster", "civilian_disguise_kit", "encrypted_comlink"]
        # The corrected prose names the real items, not "lockpick toolkit".
        assert "lockpick toolkit" not in guide_text
        assert "concealed blaster" in guide_text


# ── §10 skip starter kit must match skip_starter_kit.yaml ─────────────────────
class TestSkipStarterKit:
    def test_kit_values(self, skip_kit):
        assert skip_kit["credits"] == 300
        keys = {it["key"] for it in skip_kit["items"]}
        assert keys == {"medpac", "comlink", "hold_out_blaster"}
        # No faction rep on the skip path (alts haven't earned standing).
        assert not skip_kit.get("faction_rep")

    def test_guide_states_the_kit_not_nothing(self, guide_text):
        assert "300 credits" in guide_text, (
            "Guide_16 §10 must state the real skip kit (300 cr + items), not "
            "claim skip-chain characters get 'no credits, no items'"
        )
        assert "no credits, no items" not in guide_text


# ── §11 / §15 stale surfaces ──────────────────────────────────────────────────
class TestStaleSurfaces:
    def test_training_skip_is_deprecated(self, guide_text):
        assert "skip the core tutorial" not in guide_text, (
            "`training skip` no longer skips anything; the guide must not "
            "present it as a working skip"
        )

    def test_chargen_selection_is_by_number(self, guide_text):
        # The chargen picker takes a number (see creation_wizard); there is no
        # `chain <name>` set-command at chargen.
        assert "pick a chain by number" in guide_text


# ── §14 / §15 live-world movement teaching must match HEAD ────────────────────
# The first-session-unblock drop (266a6db) made a bare word matching a real
# current-room exit route to MoveCommand (via MoveCommand._match_exit, which
# matches an exit's *name*, not just its compass direction) — and the SPA exit
# chips send `move <dir>`.  Guide_16 is the new-player guide; before that drop it
# never taught how to walk a live-world exit at all (the #1 fun-pass killer:
# graduates stranded in the drop room).  §14's "First Hour" beat + the §15
# quick-ref now teach it.  Pin the prose AND the live behaviors it claims, so a
# future refactor that breaks named-exit movement fails loudly here.
class TestLiveWorldMovementTeaching:
    def test_guide_teaches_moving_by_exit_name(self, guide_text):
        assert "the exit's name" in guide_text, (
            "Guide_16 must teach that you walk a live-world exit by typing its "
            "name (not only a compass direction) — the first-session-unblock "
            "behavior that un-gated the world"
        )
        assert "`corridor`" in guide_text, (
            "Guide_16 should give the concrete named-exit example (`corridor`)"
        )

    def test_guide_teaches_web_client_exit_chip(self, guide_text):
        assert "exit chip" in guide_text or "exit's chip" in guide_text, (
            "Guide_16 should tell web-client players they can click the exit "
            "chip to walk through it"
        )

    def test_move_resolves_against_registry(self, reg):
        assert reg.get("move") is not None, (
            "Guide_16 teaches `move`; it must resolve against the live registry"
        )

    def test_match_exit_still_matches_by_name(self):
        """The guide's 'type the exit's name' claim is only true while
        MoveCommand._match_exit matches against the exit *name*.  Pin it."""
        import inspect
        from parser.builtin_commands import MoveCommand
        src = inspect.getsource(MoveCommand._match_exit)
        assert '.get("name")' in src and 'e["name"]' in src, (
            "MoveCommand._match_exit no longer matches an exit by name — "
            "Guide_16 §14/§15 'type the exit's name' has gone stale"
        )

    def test_spa_exit_chip_sends_move(self):
        """The guide's 'click the exit chip' claim is only true while the SPA
        dispatches `move <dir>` for an exit chip/button."""
        client_html = _read(os.path.join(PROJECT_ROOT, "static", "client.html"))
        assert "'move ' +" in client_html, (
            "The SPA no longer sends `move <dir>` for exit chips — Guide_16's "
            "'click the exit chip' claim has gone stale"
        )


# ── §6 Jedi unlock: "five" Force-sign landmark visits must match the engine ───
class TestForceSignThreshold:
    def test_five_signs_matches_engine(self, guide_text):
        from engine.force_signs import FORCE_SIGNS_FOR_INVITATION
        assert FORCE_SIGNS_FOR_INVITATION == 5, (
            "Guide_16 §6 says the Hermit's invitation triggers after five "
            "Force-resonant landmark visits — keep it in sync with the engine"
        )
        assert "five" in guide_text.lower()


# ── §4 Step 2 + §8 "Failures are forgiving": the combat sim is a SAFE SANDBOX ──
# drop fun3-sim-safety (`5cda2ca`) made tipoca_combat_sim non-lethal for the
# player (CombatInstance.is_simulation caps a PC defender to STUNNED/KO, no
# scars; NPCs still take real damage so the drill stays winnable).  Guide_16
# used to say a player could *die in the combat sim* and respawn — now stale.
# These pin the corrected prose to the live data + engine plumbing so a future
# change that re-arms lethality (or drops the room flag) fails loudly here.
class TestCombatSimSafeSandbox:
    def test_no_stale_die_in_sim_respawn_claim(self, guide_text):
        """The old, now-false claim must stay dead."""
        lowered = guide_text.lower()
        assert "dying in the combat sim" not in lowered, (
            "Guide_16 must not claim a player can die in the combat sim — drop "
            "fun3-sim-safety caps a PC defender to STUNNED/KO (unloseable drill)"
        )

    def test_guide_states_sim_is_non_lethal(self, guide_text):
        lowered = guide_text.lower()
        assert "non-lethal" in lowered or "safe sandbox" in lowered, (
            "Guide_16 §4/§8 should reassure new players the combat sim is a "
            "non-lethal safe sandbox"
        )
        # The claim's exact shape: never wounded/scarred/killed in the drill.
        assert "scarred" in lowered and "killed in the" in lowered, (
            "Guide_16 should spell out that you are never wounded, scarred, or "
            "killed in the sim (only briefly stunned)"
        )

    def test_sim_room_carries_the_is_simulation_flag(self):
        """The load-bearing data fact: tipoca_combat_sim is flagged
        is_simulation, which is what makes the guide's safety claim TRUE."""
        data = yaml.safe_load(_read(TUTORIAL_ROOMS_PATH))
        rooms = data["rooms"]
        entries = rooms.values() if isinstance(rooms, dict) else rooms
        sim = next((r for r in entries
                    if r.get("slug") == "tipoca_combat_sim"), None)
        assert sim is not None, "tipoca_combat_sim room vanished from rooms.yaml"
        assert sim.get("properties", {}).get("is_simulation") is True, (
            "tipoca_combat_sim lost properties.is_simulation:true — Guide_16's "
            "'safe sandbox' claim would no longer hold"
        )

    def test_combat_instance_threads_is_simulation(self):
        """CombatInstance must still accept is_simulation, or the room flag
        never reaches the damage cap."""
        import inspect
        from engine.combat import CombatInstance
        params = inspect.signature(CombatInstance.__init__).parameters
        assert "is_simulation" in params, (
            "CombatInstance no longer accepts is_simulation — the sim safety "
            "guarantee Guide_16 promises is unplumbed"
        )

    def test_damage_cap_protects_pc_defender_only(self):
        """The cap must apply to a PC defender but NOT to NPCs (so the drill
        stays winnable) — pin the guard so a refactor can't silently drop it."""
        import inspect
        from engine.combat import CombatInstance
        src = inspect.getsource(CombatInstance._apply_damage)
        assert "self.is_simulation" in src and "is_npc" in src, (
            "engine/combat.py._apply_damage no longer caps a PC defender in a "
            "simulation while leaving NPCs damageable — Guide_16's dual claim "
            "(you can't be hurt / the droids still take real damage) is stale"
        )


# ── §12 "What If You Get Stuck": the natural-language confusion redirect ───────
# drop NL-confusion-redirect (`19c5765`) made a confused newcomer's most natural
# instinct WORK: typing a plain-English question ("what do i do") at the prompt
# now returns "I didn't catch that" + the active objective + command-to-type +
# a help/look/Ctrl+K pointer, instead of a bare "Huh? Unknown command".  Guide_16
# §12 now teaches this safety net.  These pin the prose to the live dispatcher
# behavior + the onboarding-state ABI both the redirect and the guide rely on,
# so removing the redirect (or its objective/command_to_type fields) fails here.
class TestNLConfusionRedirectTeaching:
    def test_guide_teaches_plain_english_redirect(self, guide_text):
        assert "I didn't catch that" in guide_text, (
            "Guide_16 §12 should quote the natural-language redirect's reply "
            "(\"I didn't catch that\") so a stuck newcomer knows what it means"
        )
        lowered = guide_text.lower()
        assert "plain-english question" in lowered or "plain english question" \
            in lowered, (
            "Guide_16 §12 should tell players they can type a plain-English "
            "question when stuck — the redirect-supported recovery path"
        )

    def test_guide_keeps_the_single_word_huh_distinction(self, guide_text):
        # The redirect is reserved for question-shaped input; a single mistyped
        # command word still gets the crisp error.  The guide must not over-
        # promise that *any* unknown input gets the soft redirect.
        assert "Huh?" in guide_text, (
            "Guide_16 §12 should note that a single mistyped command word still "
            "gets the crisp `Huh?` — the redirect is for question-shaped input"
        )

    def test_dispatcher_still_emits_the_redirect(self):
        """The guide's claim is only true while parse_and_dispatch still does the
        natural-language redirect (the 'I didn't catch that.' branch)."""
        import inspect
        from parser.commands import CommandParser
        src = inspect.getsource(CommandParser.parse_and_dispatch)
        assert "I didn't catch that." in src, (
            "parser/commands.py no longer emits the natural-language confusion "
            "redirect — Guide_16 §12's 'type a plain-English question' teaching "
            "has gone stale"
        )
        assert "build_onboarding_state" in src, (
            "the redirect no longer pulls the active objective via "
            "build_onboarding_state — Guide_16 §12 over-promises the objective hint"
        )
        # The crisp single-word error must survive alongside the redirect.
        assert "Huh? Unknown command" in src, (
            "parser/commands.py dropped the crisp single-word error — Guide_16 "
            "§12's 'a single mistyped word still gets Huh?' distinction is stale"
        )

    def test_onboarding_state_surfaces_objective_and_command(self):
        """The redirect (and the guide) promise the active objective + the exact
        command to type.  Both come from build_onboarding_state's pinned ABI."""
        import inspect
        from engine.chain_events import build_onboarding_state
        src = inspect.getsource(build_onboarding_state)
        assert '"objective"' in src and '"command_to_type"' in src, (
            "build_onboarding_state no longer surfaces objective/command_to_type "
            "— Guide_16 §12's 'your current objective + the exact command to "
            "type next' promise is unbacked"
        )
