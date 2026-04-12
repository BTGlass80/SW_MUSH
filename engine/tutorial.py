"""
Tutorial system — guided onboarding for new players.

A scripted NPC interaction sequence triggered on first login.
A guide droid (R5-K3) walks the player through core commands.

State machine per character:
    0 = not started
    1 = greeted at spawn, taught look/talk
    2 = walked to cantina, taught movement
    3 = met bartender, taught ask/NPC dialogue
    4 = given starter delivery mission
    5 = delivered package, taught complete
    6 = fought training NPC, taught combat
    7 = complete (pointed to mission board / ships)

Files:
    engine/tutorial.py      (this file)
    Column: characters.tutorial_step INTEGER DEFAULT 0

The guide NPC sends targeted messages ONLY to the tutorial player's
session. No Ollama dependency — all canned dialogue.
"""
import asyncio
import logging
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.session import Session
    from db.database import Database

log = logging.getLogger(__name__)

# ── Constants ──

GUIDE_NAME = "R5-K3"
GUIDE_PREFIX = f"\x1b[33m{GUIDE_NAME}\x1b[0m"  # yellow

# The tutorial guide "speaks" via targeted messages
def _guide(text: str) -> str:
    """Format a guide message."""
    return f"  {GUIDE_PREFIX} beeps: \x1b[37m{text}\x1b[0m"

def _guide_action(text: str) -> str:
    """Format a guide action/emote."""
    return f"  \x1b[33m*{GUIDE_NAME} {text}*\x1b[0m"

def _hint(text: str) -> str:
    """Format a hint/instruction."""
    return f"  \x1b[36m[TUTORIAL]\x1b[0m {text}"


# Room indices in build_mos_eisley.py layout
# We reference rooms by name to find them at runtime
SPAWN_ROOM_NAME = "Landing Pad"
CANTINA_ROOM_NAME = "Chalmun's Cantina"
MARKET_ROOM_NAME = "Market Row"


class TutorialManager:
    """
    Manages tutorial state for all players.

    Called from game_server after character enters the game.
    Checks tutorial_step and drives the state machine.
    """

    def __init__(self):
        self._active: dict[int, int] = {}  # char_id -> current step
        self._training_npcs: dict[int, int] = {}  # char_id -> training NPC id

    async def on_enter_game(self, session: "Session", db: "Database",
                            session_mgr=None):
        """
        Called when a character enters the game world.
        Starts or resumes the tutorial if incomplete.
        """
        char = session.character
        if not char:
            return

        char_id = char["id"]
        step = char.get("tutorial_step", 0)

        if step >= 7:
            return  # Tutorial complete

        self._active[char_id] = step

        if step == 0:
            # First login — start tutorial
            await self._start(session, db, session_mgr)
        else:
            # Resuming — remind where they left off
            await self._resume(session, step, db, session_mgr)

    async def on_command(self, session: "Session", command: str, args: str,
                         db: "Database", session_mgr=None) -> bool:
        """
        Called after a command executes during tutorial.
        Returns True if the tutorial handled it (to suppress normal output).

        Should be called from the main input loop.
        """
        char = session.character
        if not char:
            return False

        char_id = char["id"]
        step = self._active.get(char_id)

        if step is None or step >= 7:
            return False

        return await self._advance(session, step, command, args, db, session_mgr)

    async def skip(self, session: "Session", db: "Database"):
        """Player typed 'skip tutorial'."""
        char = session.character
        if not char:
            return

        char_id = char["id"]
        self._active[char_id] = 7
        await db.save_character(char_id, tutorial_step=7)
        await session.send_line(
            _guide("Understood! Tutorial skipped. Good luck out there!")
        )
        await session.send_line(
            _hint("Type 'help' for a list of commands, or 'missions' to find work.")
        )
        # Clean up training NPC if it exists
        await self._cleanup_training_npc(char_id, db)

    # ── Internal state machine ──

    async def _start(self, session, db, session_mgr):
        """Step 0 → 1: Greet the player."""
        char = session.character
        char_id = char["id"]

        await asyncio.sleep(1.5)  # Brief pause for immersion

        await session.send_line("")
        await session.send_line(
            _guide_action("rolls up to you, antenna spinning excitedly")
        )
        await session.send_line(
            _guide("Welcome to Mos Eisley! I'm R5-K3, your orientation droid.")
        )
        await session.send_line(
            _guide("Let me show you around. First, try looking at your "
                   "surroundings.")
        )
        await session.send_line("")
        await session.send_line(_hint("Type: look"))
        await session.send_line(
            _hint("(Type 'skip tutorial' at any time to skip.)")
        )
        await session.send_line("")

        self._active[char_id] = 1
        await db.save_character(char_id, tutorial_step=1)

    async def _resume(self, session, step, db, session_mgr):
        """Resuming an incomplete tutorial."""
        await session.send_line("")
        await session.send_line(
            _guide_action("rolls up to you, beeping a greeting")
        )
        await session.send_line(
            _guide("Welcome back! Let's pick up where we left off.")
        )

        prompts = {
            1: "Try typing: look",
            2: "Head to the cantina! Try moving north, then follow the exits.",
            3: "Talk to Wuher the bartender. Type: talk wuher",
            4: "Check your missions. Type: missions",
            5: "Go complete your delivery mission! Type: complete when you arrive.",
            6: "Time for some combat training!",
        }
        hint = prompts.get(step, "")
        if hint:
            await session.send_line(_hint(hint))
        await session.send_line(
            _hint("(Type 'skip tutorial' at any time to skip.)")
        )
        await session.send_line("")

    async def _advance(self, session, step, command, args, db, session_mgr):
        """Check if the command advances the tutorial."""
        char = session.character
        char_id = char["id"]
        cmd = command.lower().strip()

        if step == 1 and cmd in ("look", "l"):
            # Player looked — advance to step 2
            await asyncio.sleep(0.5)
            await session.send_line("")
            await session.send_line(
                _guide("See those exits listed at the bottom? That's how you "
                       "get around.")
            )
            await session.send_line(
                _guide("The cantina is the heart of Mos Eisley. Let's head "
                       "there — it's north of here, then follow the streets.")
            )
            await session.send_line("")
            await session.send_line(
                _hint("Move by typing a direction, e.g.: north")
            )

            self._active[char_id] = 2
            await db.save_character(char_id, tutorial_step=2)
            return False  # Don't suppress the look output

        if step == 2:
            # Check if the player reached the cantina
            room = await db.get_room(char["room_id"])
            if room and "cantina" in room["name"].lower():
                await asyncio.sleep(0.5)
                await session.send_line("")
                await session.send_line(
                    _guide_action("follows you in, dome spinning")
                )
                await session.send_line(
                    _guide("This is Chalmun's Cantina — the best place for "
                           "information and work.")
                )
                await session.send_line(
                    _guide("See the NPCs here? You can talk to them. Try "
                           "talking to the bartender.")
                )
                await session.send_line("")
                await session.send_line(
                    _hint("Type: talk wuher")
                )

                self._active[char_id] = 3
                await db.save_character(char_id, tutorial_step=3)
            return False

        if step == 3 and cmd in ("talk", "ask"):
            # Player talked to someone — advance
            await asyncio.sleep(1.0)
            await session.send_line("")
            await session.send_line(
                _guide("NPCs remember conversations and have their own "
                       "personalities.")
            )
            await session.send_line(
                _guide("Now let's get you some credits. Check the mission "
                       "board for available work.")
            )
            await session.send_line("")
            await session.send_line(
                _hint("Type: missions")
            )

            self._active[char_id] = 4
            await db.save_character(char_id, tutorial_step=4)
            return False

        if step == 4 and cmd in ("missions", "mb", "jobs", "board"):
            # Player checked missions — advance
            await asyncio.sleep(0.5)
            await session.send_line("")
            await session.send_line(
                _guide("Pick a delivery mission to start — they're easy and "
                       "safe. Use 'accept <id>' to take one.")
            )
            await session.send_line(
                _guide("Once accepted, type 'mission' to see your objective, "
                       "then go to the destination and type 'complete'.")
            )
            await session.send_line("")
            await session.send_line(
                _hint("Type: accept <mission id>")
            )

            self._active[char_id] = 5
            await db.save_character(char_id, tutorial_step=5)
            return False

        if step == 5 and cmd in ("complete",):
            # Player completed a mission — advance to combat
            await asyncio.sleep(0.5)
            await session.send_line("")
            await session.send_line(
                _guide("Credits earned! You're a natural.")
            )
            await session.send_line(
                _guide("One more thing — combat. Mos Eisley can be dangerous. "
                       "Type 'score' to see your character sheet, and "
                       "'help combat' for combat commands.")
            )
            await session.send_line("")
            await session.send_line(
                _guide("When you're ready, check the bounty board for targets, "
                       "or explore — some NPCs are hostile and will attack "
                       "on sight!")
            )

            self._active[char_id] = 6
            await db.save_character(char_id, tutorial_step=6)
            return False

        if step == 6 and cmd in ("attack", "score", "help", "bounties",
                                  "bboard", "bountyboard"):
            # Player engaged with combat/score — complete tutorial
            await asyncio.sleep(0.5)
            await session.send_line("")
            await session.send_line(
                _guide_action("spins its dome happily")
            )
            await session.send_line(
                _guide("You're ready! Here's what's available:")
            )
            await session.send_line(
                _hint("'missions' — Find work on the mission board")
            )
            await session.send_line(
                _hint("'bounties' — Hunt targets for credits")
            )
            await session.send_line(
                _hint("'ships' — View ships in the docking bays")
            )
            await session.send_line(
                _hint("'who' — See who's online")
            )
            await session.send_line(
                _hint("'help' — Full command list")
            )
            await session.send_line("")
            await session.send_line(
                _guide("May the Force be with you! "
                       "*R5-K3 beeps cheerfully and rolls away.*")
            )
            await session.send_line("")

            self._active[char_id] = 7
            await db.save_character(char_id, tutorial_step=7)
            return False

        return False

    async def _cleanup_training_npc(self, char_id: int, db):
        """Remove any training NPC spawned for this player."""
        npc_id = self._training_npcs.pop(char_id, None)
        if npc_id:
            try:
                await db.delete_npc(npc_id)
            except Exception:
                log.warning("_cleanup_training_npc: unhandled exception", exc_info=True)
                pass
