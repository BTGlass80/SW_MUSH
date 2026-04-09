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
        "+----------------------------------------------+\r\n"
        "|          STAR WARS D6 MUSH                   |\r\n"
        "|   A long time ago in a galaxy far, far away.  |\r\n"
        "+----------------------------------------------+\r\n"
        "\r\n"
        "  Type 'connect <username> <password>' to log in.\r\n"
        "  Type 'create <username> <password>' to register.\r\n"
        "  Type 'quit' to disconnect.\r\n"
        "\r\n"
    )
