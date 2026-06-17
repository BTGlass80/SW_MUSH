# -*- coding: utf-8 -*-
"""Capture SPA UI screenshots for the Claude Design UI/UX review handoff package.

Drives the system Edge via Playwright (chromium download is blocked by the
corporate TLS proxy; channel='msedge' uses the installed browser instead). A
plain `python -m http.server` over the repo root serves the SPA so the
`/static/spa/m3_*.js` modules load exactly as in production.

Strategy:
  - Standalone HTML pages (landing/login/chargen/map preview) are loaded directly.
  - The integrated GROUND client view is driven by injecting a representative
    hud_update through the window-exposed handleHudUpdate.
  - The in-game component modals/panels (holonet, sheet, shop, inventory, combat
    inspector) are built from each module's OWN demo fixture and screenshotted.

Each surface is wrapped so one failure doesn't abort the run; we save what works
and report what didn't (those are the surfaces that need a live-game capture).
"""
import os
import sys
import json

BASE = "http://localhost:8090"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "design", "ui_screenshots")
os.makedirs(OUT, exist_ok=True)

# A representative hud_update to populate the integrated ground view.
MOCK_HUD = {
    "character_id": 1, "name": "Tey Voss", "species": "Twi'lek",
    "zone_name": "Mos Eisley Spaceport", "zone_type": "secured",
    "room_name": "Docking Bay 94", "room_id": 101,
    "room_description": ("A cavernous durasteel hangar, scarred by decades of "
        "scorching ion exhaust. A battered light freighter rests on its landing "
        "struts, loading ramp lowered. Spice-haze drifts under the sodium lamps."),
    "security_level": "secured",
    "room_services": ["vendor", "cantina", "docking", "mechanic"],
    "nearby_services": [
        {"type": "vendor", "name": "Watto's Parts", "distance": 1, "direction": "north"},
        {"type": "cantina", "name": "Chalmun's Cantina", "distance": 2, "direction": "east"},
        {"type": "medical", "name": "Med-Bay 3", "distance": 3, "direction": "south"},
    ],
    "zone_influence": {"republic": 45, "hutt_cartel": 33, "independent": 22},
    "room_contents": {
        "npcs": [{"name": "Watto", "role": "vendor", "wound_level": 0},
                 {"name": "Republic Sentry", "role": "guard", "wound_level": 0}],
        "players": [{"name": "Kael Dorne", "role": "player", "online": True}],
        "vendor_droids": [],
    },
    "active_jobs": [
        {"type": "bounty", "label": "Wanted: Vex Drago", "reward": "18,000 cr", "target": "Vex Drago"},
        {"type": "delivery", "label": "Deliver med-supplies to Anchorhead", "reward": "1,200 cr"},
    ],
    "exits": ["north", "south", "east", "west"],
    "credits": 1250, "force_points": 2, "character_points": 8,
    "condition": "healthy", "wound_level": 0, "wound_name": "Healthy",
    "loadout": {
        "weapon": {"name": "DL-44 Heavy Blaster", "damage": "5D"},
        "armor": {"name": "Blast Vest", "location": "torso", "bonus": "+1D"},
        "consumables": [{"name": "Medpac", "count": 3, "type": "healing"},
                        {"name": "Stimpack", "count": 1, "type": "boost"}],
    },
    "objective": "Find passage off-world before the Hutts collect on your debt.",
    "cp_progress": {"current": 8, "this_week": 35, "cap": 400},
}


def _shoot(page, name, full=True):
    path = os.path.join(OUT, name + ".png")
    page.screenshot(path=path, full_page=full)
    print(f"  saved {name}.png")


def run():
    from playwright.sync_api import sync_playwright
    results = {"ok": [], "fail": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  device_scale_factor=2)

        # ── Standalone pages ──
        standalone = [
            ("01_landing_portal", "/static/portal.html"),
            ("02_login_boot", "/static/client.html"),
            ("03_chargen", "/static/chargen.html"),
            ("09_map_preview", "/static/map_v2_preview.html"),
        ]
        for name, url in standalone:
            try:
                page = ctx.new_page()
                page.goto(BASE + url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(1500)
                _shoot(page, name, full=(name != "02_login_boot"))
                results["ok"].append(name); page.close()
            except Exception as e:
                results["fail"].append(f"{name}: {str(e)[:120]}")

        # ── Integrated ground client (inject hud_update) ──
        try:
            page = ctx.new_page()
            page.goto(BASE + "/static/client.html", wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(800)
            page.evaluate(
                "(hud) => { try { if (window.handleHudUpdate) window.handleHudUpdate(hud); } catch(e){ window.__hudErr = String(e); } }",
                MOCK_HUD)
            page.wait_for_timeout(1200)
            err = page.evaluate("() => window.__hudErr || null")
            if err:
                results["fail"].append(f"04_ground_play: handleHudUpdate threw: {err[:100]}")
            _shoot(page, "04_ground_play", full=False)
            results["ok"].append("04_ground_play"); page.close()
        except Exception as e:
            results["fail"].append(f"04_ground_play: {str(e)[:120]}")

        # ── In-game component modals/panels from each module's demo fixture ──
        # (built in a clean full-viewport container on a fresh client.html page)
        modal_js = r"""
        (spec) => {
          try {
            document.body.innerHTML = '';
            document.body.style.cssText = 'margin:0;background:#0c0a08;min-height:100vh;display:flex;align-items:flex-start;justify-content:center;padding:24px;';
            var pal = (window.M3Palettes && window.M3Palettes.getPalette) ? window.M3Palettes.getPalette('tatooine') : {};
            var ns = window[spec.ns];
            if (!ns) return 'namespace ' + spec.ns + ' not loaded';
            var fn = ns[spec.fn];
            if (typeof fn !== 'function') return 'fn ' + spec.ns + '.' + spec.fn + ' not found; keys=' + Object.keys(ns).slice(0,24).join(',');
            var fixture = spec.fixtureKey ? ns[spec.fixtureKey] : (spec.data || undefined);
            var noop = function(){};
            if (spec.mode === 'container') {
              // render(container, data, onCommand) — renders INTO a container.
              var c = document.createElement('div');
              c.style.cssText = 'width:1180px;max-width:96vw;';
              document.body.appendChild(c);
              fn(c, fixture, noop);
              return 'ok';
            }
            // build(p, data, hooks) → returns an element (or HTML string).
            var el;
            try { el = fn(pal, fixture, {}); } catch(e1) {
              try { el = fn(pal, fixture); } catch(e2) {
                try { el = fn(fixture, pal); } catch(e3) { return 'build sigs failed: ' + e1; }
              }
            }
            if (!el) return 'build returned nothing';
            if (typeof el === 'string') { document.body.innerHTML = el; }
            else { document.body.appendChild(el); }
            return 'ok';
          } catch (e) { return 'exc: ' + e; }
        }
        """
        _shop_data = {"mode": "browse", "focused_id": 1, "droids": [
            {"id": 1, "name": "Watto's Parts Droid", "tier": "general", "item_count": 4,
             "desc": "Salvaged WED Treadwell hawking blasters and field gear.",
             "inventory": [
                {"key": "dl44", "name": "DL-44 Heavy Blaster", "cost": 1500, "slot": "weapon", "stat": "5D dmg"},
                {"key": "blast_vest", "name": "Blast Vest", "cost": 600, "slot": "armor", "stat": "+1D phys"},
                {"key": "medpac", "name": "Medpac", "cost": 100, "slot": "consumable", "stat": "heal 1 wound"},
                {"key": "comlink", "name": "Comlink", "cost": 25, "slot": "misc", "stat": "comms"}]},
            {"id": 2, "name": "Spice Trader", "tier": "contraband", "item_count": 2,
             "desc": "Keeps the good stuff under the counter.", "inventory": [
                {"key": "glitterstim", "name": "Glitterstim", "cost": 2200, "slot": "misc", "stat": "contraband"},
                {"key": "scope", "name": "Targeting Scope", "cost": 450, "slot": "mod", "stat": "+1D aim"}]}]}
        _inv_data = {"credits": 1250, "equipped": {
                "weapon": {"name": "DL-44 Heavy Blaster", "stat": "5D", "condition": 92},
                "armor": {"name": "Blast Vest", "stat": "+1D torso", "condition": 80}},
            "carried": [
                {"key": "medpac", "name": "Medpac", "count": 3, "type": "healing"},
                {"key": "stimpack", "name": "Stimpack", "count": 1, "type": "boost"},
                {"key": "thermal", "name": "Thermal Detonator", "count": 1, "type": "ordnance"},
                {"key": "comlink", "name": "Comlink", "count": 1, "type": "misc"},
                {"key": "datapad", "name": "Datapad", "count": 1, "type": "misc"}]}
        modals = [
            ("05_holonet", {"ns": "M3Holonet", "fn": "buildHolonetBrowserModal", "fixtureKey": "HOLONET_DATA_FIXTURE", "mode": "build"}),
            ("06_sheet",   {"ns": "M3Sheet",   "fn": "buildCharacterSheetModal", "fixtureKey": "TEY_V2_FIXTURE", "mode": "build"}),
            ("07_shop",    {"ns": "M3Shop",    "fn": "render", "data": _shop_data, "mode": "container"}),
            ("08_inventory", {"ns": "M3Inventory", "fn": "render", "data": _inv_data, "mode": "container"}),
        ]
        for name, spec in modals:
            try:
                page = ctx.new_page()
                page.goto(BASE + "/static/client.html", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(600)
                status = page.evaluate(modal_js, spec)
                page.wait_for_timeout(700)
                if status == "ok":
                    _shoot(page, name, full=True); results["ok"].append(name)
                else:
                    results["fail"].append(f"{name}: {status[:140]}")
                page.close()
            except Exception as e:
                results["fail"].append(f"{name}: {str(e)[:120]}")

        browser.close()
    print("\n=== CAPTURE SUMMARY ===")
    print("OK  :", ", ".join(results["ok"]))
    print("FAIL:", "\n       ".join(results["fail"]) if results["fail"] else "(none)")
    return results


if __name__ == "__main__":
    run()
