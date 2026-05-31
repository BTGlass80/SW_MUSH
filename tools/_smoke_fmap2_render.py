# -*- coding: utf-8 -*-
"""Quick visual smoke for F.MAP.2 integration: serve client.html via
a tiny aiohttp app (matches the real server's /static/ route), inject
a faked HUD payload (matching what the server would send), and verify
the minimap SVG was rendered by MapView (not the legacy renderer).

This is a sandbox-only check — not part of the test suite. The real
end-to-end test happens when Brian boots the server and walks Kel
through Mos Eisley.
"""
import asyncio
import json
import socket
import sys
import threading
from pathlib import Path

from aiohttp import web
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_server(port: int) -> threading.Thread:
    """Run an aiohttp app in a background thread that mirrors the real
    server's /static/ route + a / handler that serves client.html."""
    static_dir = str(ROOT / "static")
    client_html = str(ROOT / "static" / "client.html")
    ready = threading.Event()

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()

        async def serve_client(request):
            return web.FileResponse(client_html)
        app.router.add_get("/", serve_client)
        app.router.add_static("/static/", static_dir, show_index=False)

        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", port)
        loop.run_until_complete(site.start())
        ready.set()
        loop.run_forever()

    th = threading.Thread(target=run, daemon=True)
    th.start()
    ready.wait(timeout=5.0)
    return th


def main():
    sys.path.insert(0, str(ROOT))
    from engine.area_loader import AreaGeometryRegistry
    reg = AreaGeometryRegistry.load_era("clone_wars")
    payload = reg.get_payload("tatooine.mos_eisley")
    bay94 = reg.lookup("docking_bay_94_pit")
    assert payload is not None and bay94 is not None

    port = _free_port()
    _start_server(port)
    url = f"http://127.0.0.1:{port}/"

    hud = {
        "type": "hud_update",
        "area_geometry": payload,
        "player_position": {
            "area_key":        bay94.area_key,
            "render_room_id": bay94.render_room_id,
            "x":               bay94.x,
            "y":               bay94.y,
        },
    }

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        errors = []
        page.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
        page.on("console", lambda m: errors.append((m.type, m.text)) if m.type in ("error","warning") else None)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1500)

        has_mv = page.evaluate("() => typeof window.MapView === 'object'")
        has_render = page.evaluate("() => typeof window.renderMapV2 === 'function'")
        svg_present = page.evaluate("() => !!document.getElementById('g-area-map-svg')")
        print(f"window.MapView loaded:    {has_mv}")
        print(f"window.renderMapV2 exposed: {has_render}")
        print(f"g-area-map-svg present:    {svg_present}")

        result = page.evaluate("""(payload) => {
            window._sw_areaGeom = payload.area_geometry;
            window._sw_areaGeom.player = {
              room_id: payload.player_position.render_room_id,
              x: payload.player_position.x,
              y: payload.player_position.y,
            };
            window.renderMapV2();
            const svg = document.getElementById('g-area-map-svg');
            return {
              children: svg.children.length,
              rects:    svg.querySelectorAll('rect').length,
              paths:    svg.querySelectorAll('path').length,
              circles:  svg.querySelectorAll('circle').length,
              texts:    svg.querySelectorAll('text').length,
              viewBox:  svg.getAttribute('viewBox'),
            };
        }""", hud)
        print("Render counts:", result)

        # Capture a focused screenshot of the minimap region for visual review
        svg_box = page.locator("#g-area-map-svg").bounding_box()
        if svg_box:
            page.screenshot(
                path="/tmp/fmap2_minimap.png",
                clip={
                    "x":      max(0, svg_box["x"] - 8),
                    "y":      max(0, svg_box["y"] - 8),
                    "width":  svg_box["width"] + 16,
                    "height": svg_box["height"] + 16,
                },
            )
            print("Screenshot: /tmp/fmap2_minimap.png")

        browser.close()
    print("\nErrors observed:", errors[:5] if errors else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())

