#!/usr/bin/env python3
"""
Star Wars D6 MUSH - Main Entry Point

Usage:
    python main.py [--telnet-port PORT] [--ws-port PORT] [--db PATH]

Starts both the Telnet and WebSocket listeners, initializes the
database, and runs the game loop.
"""
import argparse
import asyncio
import logging
import signal
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.config import Config

# NOTE: `GameServer` is imported INSIDE `main()`, AFTER
# `era_state.set_active_config(cfg)` runs. This deliberate ordering
# matters because importing `GameServer` transitively imports
# `engine/director.py`, whose module-level `VALID_FACTIONS`,
# `DEFAULT_INFLUENCE`, and `_RUNTIME_CFG` are resolved through the
# F.6a.3 seam at import time. The seam reads from `era_state`'s
# ambient `_active_config`, so if we register the config AFTER the
# import, director.py would capture the default (no-era) state and
# the F.6a.6 flag flip would silently no-op.
#
# Pinned by tests/test_f6a6_boot_ordering.py.
# (TYPE_CHECKING-only import for type hints — no runtime import.)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from server.game_server import GameServer


def setup_logging(level: str = "INFO"):
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)-25s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy libraries
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("telnetlib3").setLevel(logging.WARNING)


def parse_args():
    parser = argparse.ArgumentParser(description="Star Wars D6 MUSH Server")
    parser.add_argument(
        "--telnet-port", type=int, default=4000,
        help="Telnet listen port (default: 4000)",
    )
    parser.add_argument(
        "--ws-port", type=int, default=4001,
        help="WebSocket listen port (default: 4001)",
    )
    parser.add_argument(
        "--web-port", type=int, default=8080,
        help="Web client HTTP port (default: 8080)",
    )
    parser.add_argument(
        "--db", type=str, default="sw_mush.db",
        help="SQLite database path (default: sw_mush.db)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    # ── F.6a.6 dev / era flags ─────────────────────────────────────────────
    # The era flags are intentionally dev-only for now. Flipping
    # --use-yaml-director-data on with --era=clone_wars activates the
    # F.6a.{1..4}-int code paths that read from data/worlds/<era>/ YAMLs.
    # NOT yet production-safe — preflight Category B.1 (34 files with
    # hardcoded "imperial"/"rebel"/etc. strings) is the real gate.
    parser.add_argument(
        "--era", type=str, default=None,
        help=(
            "Active era code (e.g. 'gcw', 'clone_wars'). When set, "
            "overrides Config.active_era. Use only on a dev DB; "
            "production gating is preflight B.1."
        ),
    )
    parser.add_argument(
        "--use-yaml-director-data", action="store_true",
        help=(
            "DEV ONLY: read Director / lore / ambient pools from "
            "data/worlds/<era>/ YAMLs instead of the legacy hardcoded "
            "values. Requires --era. Not production-safe — see F.6a.6 "
            "handoff for gating."
        ),
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    setup_logging(args.log_level)

    # Build the Config first. CLI era flags override the dataclass
    # defaults when provided; otherwise the production defaults
    # (active_era="gcw", use_yaml_director_data=False) apply.
    config_kwargs = dict(
        telnet_port=args.telnet_port,
        websocket_port=args.ws_port,
        web_client_port=args.web_port,
        db_path=args.db,
    )
    if args.era is not None:
        config_kwargs["active_era"] = args.era
    if args.use_yaml_director_data:
        config_kwargs["use_yaml_director_data"] = True

    config = Config(**config_kwargs)

    # F.6a.6: register the Config with engine.era_state BEFORE importing
    # GameServer. See the import-ordering comment at the top of this
    # file — director.py resolves its constants at module import time
    # via the F.6a.3 seam, which reads from this ambient config.
    from engine.era_state import set_active_config
    set_active_config(config)

    if args.use_yaml_director_data:
        logging.warning(
            "[boot] F.6a.6: use_yaml_director_data=True (era=%s). "
            "DEV-ONLY mode — preflight B.1 (34 hardcoded faction strings) "
            "is the real production gate. See HANDOFF_APR28_DROP_F6A6.md.",
            config.active_era,
        )

    # Now safe to import GameServer — director.py will resolve through
    # the seam with the era flag honored.
    from server.game_server import GameServer
    server = GameServer(config)

    # Handle shutdown signals gracefully
    loop = asyncio.get_running_loop()

    def signal_handler():
        logging.info("Received shutdown signal.")
        asyncio.create_task(shutdown(server))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await server.start()

    # Keep running until stopped
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()


async def shutdown(server: "GameServer"):
    """Graceful shutdown sequence."""
    await server.stop()

    # Cancel all remaining tasks and AWAIT them so they can handle
    # CancelledError and do any necessary cleanup before the process exits.
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    # gather() waits for all cancellations to complete; return_exceptions
    # prevents a single task's error from aborting the rest.
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    print(r"""
    +==================================================+
    |       ____  _                __    __            |
    |      / ___|| |_ __ _ _ __  / / /\ \ \__ _ _ __  |
    |      \___ \| __/ _` | '__| \ \/  \/ / _` | '__| |
    |       ___) | || (_| | |     \  /\  / (_| | |    |
    |      |____/ \__\__,_|_|      \/  \/ \__,_|_|    |
    |                                                  |
    |            D 6   M U S H   S E R V E R           |
    +==================================================+
    """)
    asyncio.run(main())
