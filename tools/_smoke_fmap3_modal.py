# -*- coding: utf-8 -*-
"""F.MAP.3 modal smoke: open expanded modal at tier 1, flip to tier 2,
capture screenshots of each.

Sandbox-only — not part of the test suite. Real end-to-end is Brian
playing through Mos Eisley with the expanded modal.
"""
import asyncio
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


def _start_server(port: int):
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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        errors = []
        page.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
        page.on("console", lambda m: errors.append((m.type, m.text)) if m.type in ("error","warning") else None)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(800)

        # 1) Send a faux HUD update to dismiss the login overlay
        page.evaluate("if(typeof handleHudUpdate==='function')handleHudUpdate({type:'hud_update',name:'TestPilot',credits:100});")
        page.wait_for_timeout(300)

        # 2) Stamp a cached AreaGeometry on window._sw_areaGeom — same
        #    state the live HUD push would establish — and re-render the
        #    mini so the modal has a source to work from.
        page.evaluate("""(p) => {
          window._sw_areaGeom = p.geom;
          window._sw_areaGeom.player = {
            room_id: p.entry.render_room_id,
            x: p.entry.x, y: p.entry.y
          };
          window.renderMapV2();
        }""", {"geom": payload, "entry": {
            "render_room_id": bay94.render_room_id,
            "x": bay94.x, "y": bay94.y,
        }})
        page.wait_for_timeout(300)

        # 3) Open the modal
        page.evaluate("openMapModal('ground')")
        page.wait_for_timeout(500)

        # Inspect the modal SVG
        info = page.evaluate("""() => {
          const body = document.getElementById('map-modal-body');
          const svg = body ? body.querySelector('svg') : null;
          const rail = document.getElementById('map-modal-tier-rail');
          return {
            modal_open: !!document.getElementById('map-modal-overlay').classList.contains('show'),
            svg_present: !!svg,
            viewBox: svg ? svg.getAttribute('viewBox') : null,
            rail_visible: rail ? rail.style.display : 'unknown',
            tier_buttons: Array.from(document.querySelectorAll('.mm-tier-btn')).map(b => ({
              tier: b.getAttribute('data-tier'),
              active: b.classList.contains('active'),
            })),
            rooms_full: svg ? svg.querySelectorAll('rect').length : 0,
            paths: svg ? svg.querySelectorAll('path').length : 0,
            texts: svg ? svg.querySelectorAll('text').length : 0,
          };
        }""")
        print("Tier 1 (district view):", info)
        page.screenshot(path="/tmp/fmap3_tier1.png", full_page=False)

        # 4) Switch to tier 2
        page.evaluate("setMapModalTier(2)")
        page.wait_for_timeout(400)
        info2 = page.evaluate("""() => {
          const body = document.getElementById('map-modal-body');
          const svg = body ? body.querySelector('svg') : null;
          return {
            viewBox: svg ? svg.getAttribute('viewBox') : null,
            rooms_full: svg ? svg.querySelectorAll('rect').length : 0,
            circles: svg ? svg.querySelectorAll('circle').length : 0,
            texts: svg ? svg.querySelectorAll('text').length : 0,
            tier_buttons: Array.from(document.querySelectorAll('.mm-tier-btn')).map(b => ({
              tier: b.getAttribute('data-tier'),
              active: b.classList.contains('active'),
            })),
          };
        }""")
        print("Tier 2 (city overview):", info2)
        page.screenshot(path="/tmp/fmap3_tier2.png", full_page=False)

        # 5) Switch back to tier 1
        page.evaluate("setMapModalTier(1)")
        page.wait_for_timeout(300)
        info3 = page.evaluate("""() => {
          const buttons = Array.from(document.querySelectorAll('.mm-tier-btn'));
          const active = buttons.find(b => b.classList.contains('active'));
          return {
            active_tier: active ? active.getAttribute('data-tier') : null,
          };
        }""")
        print("After flip back:", info3)

        # 6) Close
        page.evaluate("closeMapModal()")
        page.wait_for_timeout(200)
        closed = page.evaluate("() => !document.getElementById('map-modal-overlay').classList.contains('show')")
        print("Modal closed:", closed)

        browser.close()
    print("\nErrors observed:", errors[:5] if errors else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
