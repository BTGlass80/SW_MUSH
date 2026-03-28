"""
ANSI color codes for terminal output.

Provides a clean API for colorizing text sent to Telnet clients.
WebSocket clients receive the raw codes; the browser client can
strip or interpret them.
"""

# Reset
RESET = "\033[0m"

# Standard colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

# Bright colors
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

# Styles
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# ── Convenience functions ──


def color(text: str, code: str) -> str:
    """Wrap text in a color code with auto-reset."""
    return f"{code}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def red(text: str) -> str:
    return color(text, RED)


def green(text: str) -> str:
    return color(text, GREEN)


def yellow(text: str) -> str:
    return color(text, YELLOW)


def blue(text: str) -> str:
    return color(text, BLUE)


def cyan(text: str) -> str:
    return color(text, CYAN)


def magenta(text: str) -> str:
    return color(text, MAGENTA)


def bright_white(text: str) -> str:
    return color(text, BRIGHT_WHITE)


def dim(text: str) -> str:
    return color(text, DIM)


def header(text: str) -> str:
    """Format a section header."""
    return f"{BOLD}{BRIGHT_CYAN}{text}{RESET}"


def error(text: str) -> str:
    """Format an error message."""
    return f"{BRIGHT_RED}Error: {text}{RESET}"


def success(text: str) -> str:
    """Format a success message."""
    return f"{BRIGHT_GREEN}{text}{RESET}"


def system_msg(text: str) -> str:
    """Format a system message."""
    return f"{YELLOW}[SYSTEM] {text}{RESET}"


def combat_msg(text: str) -> str:
    """Format a combat message."""
    return f"{BRIGHT_RED}[COMBAT] {text}{RESET}"


def force_msg(text: str) -> str:
    """Format a Force-related message."""
    return f"{BRIGHT_BLUE}[THE FORCE] {text}{RESET}"


def room_name(text: str) -> str:
    """Format a room name."""
    return f"{BOLD}{BRIGHT_WHITE}{text}{RESET}"


def exit_color(text: str) -> str:
    """Format an exit direction."""
    return f"{BRIGHT_GREEN}{text}{RESET}"


def npc_name(text: str) -> str:
    """Format an NPC name."""
    return f"{BRIGHT_YELLOW}{text}{RESET}"


def player_name(text: str) -> str:
    """Format a player name."""
    return f"{BOLD}{CYAN}{text}{RESET}"


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape codes from text."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)
