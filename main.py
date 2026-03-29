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
        "--db", type=str, default="sw_mush.db",
        help="SQLite database path (default: sw_mush.db)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    setup_logging(args.log_level)

    config = Config(
        telnet_port=args.telnet_port,
        websocket_port=args.ws_port,
        db_path=args.db,
    )

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


async def shutdown(server: GameServer):
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
