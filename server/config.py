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

    # ── Display ──
    default_terminal_width: int = 80
    default_terminal_height: int = 24
    game_name: str = "Star Wars D6 MUSH"
    welcome_banner: str = (
        "\r\n"
        "\033[93m"
        "     ____________  ___    ____       _       _____    ____   _____ \r\n"
        "    / ___/_ __/   |   \\  / _  \\     | |     / /   |  / _  \\ / ___/ \r\n"
        "    \\__ \\ | | / /| |  / / /_| |     | | /| / / /| | / /_| / \\__ \\  \r\n"
        "   ___/ / | |/ ___ | / /  _   |     | |/ |/ / ___ |/  _  /___/ /  \r\n"
        "  /____/  |_/_/  |_|/_/  | |  |     |__/|__/_/  |_/_/ | | /____/   \r\n"
        "                         |_|                           |_|          \r\n"
        "\033[0m"
        "\r\n"
        "\033[2m\033[96m"
        "         ╔═══════════════════════════════════════════════╗\r\n"
        "         ║\033[0m \033[1m\033[97m  D 6   R E V I S E D   &   E X P A N D E D \033[0m \033[2m\033[96m║\r\n"
        "         ╚═══════════════════════════════════════════════╝\r\n"
        "\033[0m"
        "\r\n"
        "\033[2m  A long time ago in a galaxy far, far away...\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "\033[33m  Mos Eisley Spaceport.\033[0m\r\n"
        "\033[2m  You will never find a more wretched hive of scum and\r\n"
        "  villainy.  Smugglers, bounty hunters, and Imperial patrols\r\n"
        "  fill its dusty streets.  Your story begins here.\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "  \033[92mconnect\033[0m \033[2m<username> <password>\033[0m   \033[2m— Log in to an existing account\033[0m\r\n"
        "  \033[92mcreate\033[0m  \033[2m<username> <password>\033[0m   \033[2m— Register a new account\033[0m\r\n"
        "  \033[92mquit\033[0m                          \033[2m— Disconnect\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
    )
