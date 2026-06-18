# -*- coding: utf-8 -*-
"""
Server configuration - all tunables in one place.
"""
from dataclasses import dataclass, field


@dataclass
class Config:
    """Server-wide configuration. Load from YAML or override in code."""

    # ── Network ──
    telnet_host: str = "0.0.0.0"
    telnet_port: int = 4000
    websocket_host: str = "0.0.0.0"
    websocket_port: int = 4001
    web_client_host: str = "0.0.0.0"
    web_client_port: int = 8080

    # ── Database ──
    db_path: str = "sw_mush.db"

    # ── Accounts ──
    min_username_len: int = 3
    max_username_len: int = 20
    min_password_len: int = 6
    max_login_attempts: int = 5
    login_lockout_seconds: int = 300  # 5 minutes

    # ── Game ──
    starting_room_id: int = 1
    tick_interval: float = 1.0  # seconds per game tick
    idle_timeout: int = 3600  # disconnect after 1 hour idle
    max_sessions_per_account: int = 1
    max_characters_per_account: int = 3

    # ── Era (F.6a.5 / F.6a.6 scaffolding; CW pivot completed May 18 2026) ──
    # active_era selects which `data/worlds/<era>/` content set the game
    # uses. May 18 2026: Clone Wars is now the live launch era; GCW is
    # deprecated reference content kept on disk for dual-era infrastructure
    # validation and historical reference, but no longer the boot default.
    #
    # use_yaml_director_data is the F.6a.6 feature flag: when True, the
    # world_lore / Director / ambient_events systems read from the
    # era YAML via the F.6a.{1..4} loaders / seams. When False, they use
    # the legacy hardcoded constants. Default flipped to True in May 2026
    # alongside the era pivot — the YAML pipeline is the production path
    # going forward.
    #
    # Per design doc §3.x: these flags were historically the gating switch
    # for "GCW byte-equivalent on YAML" and "Clone Wars era live." Both
    # are now flipped on for production.
    active_era: str = "clone_wars"
    use_yaml_director_data: bool = True

    # ── Display ──
    default_terminal_width: int = 80
    default_terminal_height: int = 24
    game_name: str = "Parsec"
    welcome_banner: str = (
        "\r\n"
        "\033[93m"
        "    ██████   █████  ██████  ███████ ███████  ██████ \r\n"
        "    ██   ██ ██   ██ ██   ██ ██      ██      ██      \r\n"
        "    ██████  ███████ ██████  ███████ █████   ██      \r\n"
        "    ██      ██   ██ ██  ██       ██ ██      ██      \r\n"
        "    ██      ██   ██ ██   ██ ███████ ███████  ██████ \r\n"
        "\033[0m"
        "\r\n"
        "\033[2m\033[96m"
        "         ╔═══════════════════════════════════════════════╗\r\n"
        "         ║\033[0m \033[1m\033[97m  D 6   R E V I S E D   &   E X P A N D E D \033[0m \033[2m\033[96m║\r\n"
        "         ╚═══════════════════════════════════════════════╝\r\n"
        "\033[0m"
        "\r\n"
        "\033[2m  The Clone Wars rage across a galaxy at the brink.\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "\033[33m  Mos Eisley Spaceport.\033[0m\r\n"
        "\033[2m  A sun-blasted den of smugglers, bounty hunters, and\r\n"
        "  cartel enforcers on the galaxy's ragged frontier.  Your\r\n"
        "  story begins here.\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "  \033[92mconnect\033[0m \033[2m<username> <password>\033[0m   \033[2m— Log in to an existing account\033[0m\r\n"
        "  \033[92mcreate\033[0m  \033[2m<username> <password>\033[0m   \033[2m— Register a new account\033[0m\r\n"
        "  \033[92mquit\033[0m                          \033[2m— Disconnect\033[0m\r\n"
        "\r\n"
        "\033[2m  New? Try the visual character creator:\033[0m \033[4m\033[96m/chargen\033[0m\r\n"
        "\033[2m  Browse the portal:\033[0m \033[4m\033[96mhttp://localhost:8080/\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
    )
