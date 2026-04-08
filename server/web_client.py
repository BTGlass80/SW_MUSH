"""
Web Client - serves the browser-based MUSH client.

Adds an HTTP server (aiohttp) that serves the static client.html file.
Runs alongside the WebSocket server on a separate port (default 8080).

Usage in game_server.py:
    from server.web_client import WebClient
    self.web_client = WebClient()
    await self.web_client.start(host, port, static_dir)
"""
import logging
import os
from pathlib import Path

from aiohttp import web

log = logging.getLogger(__name__)


class WebClient:
    """Serves the browser client and related static files."""

    def __init__(self):
        self._runner = None
        self._app = None

    async def start(self, host: str = "0.0.0.0", port: int = 8080,
                    static_dir: str = None):
        """
        Start the HTTP server that serves the web client.

        Args:
            host: Bind address.
            port: HTTP port for the client (default 8080).
            static_dir: Path to the static/ directory. If None, auto-detects
                        relative to the project root.
        """
        if static_dir is None:
            # Assume project layout: server/web_client.py -> project_root/static/
            project_root = Path(__file__).resolve().parent.parent
            static_dir = str(project_root / "static")

        if not os.path.isdir(static_dir):
            log.warning("Static directory not found: %s — web client disabled.",
                        static_dir)
            return

        client_html = os.path.join(static_dir, "client.html")
        if not os.path.isfile(client_html):
            log.warning("client.html not found in %s — web client disabled.",
                        static_dir)
            return

        self._app = web.Application()

        # Root route serves client.html
        async def serve_client(request):
            return web.FileResponse(client_html)

        self._app.router.add_get("/", serve_client)

        # Serve any other static files (future: CSS, JS, images)
        self._app.router.add_static("/static/", static_dir, show_index=False)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, host, port)
        await site.start()

        log.info("Web client serving at http://%s:%d/", host, port)

    async def stop(self):
        """Shut down the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            log.info("Web client server stopped.")
