# -*- coding: utf-8 -*-
"""Capture SPA UI screenshots for the Claude Design UI/UX review handoff package.

Drives the system Edge via Playwright (chromium download is blocked by the
corporate TLS proxy; channel='msedge' uses the installed browser instead).

Server model
------------
This tool boots the REAL game server (``main.py``) with ``ANTHROPIC_API_KEY=""``
(cost-safe: the paid Director is disabled) and captures every surface against it,
then tears it down. The live backend is required because the pre-login funnel
(chargen) fetches ``/api/chargen/*`` — a plain static file server 404s those and
chargen renders "Failed to load game data". The in-game surfaces don't log in, so
no authenticated WebSocket pushes data: the injected MOCK_* state is authoritative
and is never clobbered. If a server is already listening on ``WEB_PORT`` the tool
reuses it (and leaves it running).

Strategy per surface
---------------------
  - Standalone pages (landing/login/chargen/map preview) are loaded directly;
    chargen is additionally driven one step deeper for the attributes view (03b).
  - The integrated GROUND client view is driven by injecting a representative
    ``hud_update`` (+ reputation) plus the mail/achievements/places sidebar
    messages and a batch of comms events — through window-exposed handlers on a
    temp instrumented copy of client.html.
  - The galaxy/region navigator overlay is mounted from M3MapNavigator at its
    self-contained GALAXY tier (no backend round-trip).
  - The in-game component modals/panels are built from each module's OWN demo
    fixture and screenshotted.

Each surface is wrapped so one failure doesn't abort the run; we save what works
and report what didn't.
"""
import os
import sys
import json
import time
import subprocess
import urllib.request

WEB_PORT = 8097
WS_PORT = 4017
TELNET_PORT = 4018
BASE = "http://localhost:%d" % WEB_PORT
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "docs", "design", "ui_screenshots")
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
    # FACTION STANDING panel (renders via handleHudUpdate -> renderReputation;
    # shape per server/session.py _hud_reputation -> organizations.get_all_faction_reps).
    "reputation": {
        "republic": {"rep": 62, "tier_key": "trusted", "tier_name": "Trusted",
                     "rank": "Lieutenant", "rank_level": 4, "is_member": True},
        "bounty_hunters_guild": {"rep": 41, "tier_key": "friendly", "tier_name": "Friendly",
                                 "rank": None, "rank_level": None, "is_member": False},
        "cis": {"rep": -15, "tier_key": "wary", "tier_name": "Wary",
                "rank": None, "rank_level": None, "is_member": False},
        "hutt_cartel": {"rep": -28, "tier_key": "disliked", "tier_name": "Disliked",
                        "rank": None, "rank_level": None, "is_member": False},
    },
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
    # exits are objects {dir,label} per server/session.py _hud_exits (not bare strings).
    "exits": [
        {"dir": "north", "label": "Watto's Parts Row"},
        {"dir": "south", "label": "Med Quarter"},
        {"dir": "east", "label": "Cantina Row"},
        {"dir": "west", "label": "Landing Bays"},
    ],
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

# Sidebar messages that arrive as their OWN WebSocket message types (NOT inside
# hud_update). Shapes match the server producers in server/session.py.
MOCK_MAIL = {  # _hud_sidebar_mail
    "unread": 2,
    "messages": [
        {"id": 1, "from_name": "Republic Quartermaster", "subject": "Requisition approved — DC-15A rifle", "is_read": False},
        {"id": 2, "from_name": "Teemo the Hutt", "subject": "Your debt comes due, off-worlder", "is_read": False},
        {"id": 3, "from_name": "Guild Dispatch", "subject": "New bounty posted: Vex Drago", "is_read": True},
    ],
}
MOCK_ACH = {  # _hud_sidebar_achievements
    "completed": 2, "total": 5,
    "achievements": [
        {"key": "first_blood", "name": "First Blood", "icon": "⚔️",
         "description": "Win your first ground engagement.", "progress": 1, "target": 1, "completed": True, "locked": False},
        {"key": "spacer", "name": "Spacer", "icon": "\U0001f680",
         "description": "Complete a hyperspace jump.", "progress": 1, "target": 1, "completed": True, "locked": False},
        {"key": "gunsmith", "name": "Gunsmith", "icon": "\U0001f527",
         "description": "Craft five weapons.", "progress": 3, "target": 5, "completed": False, "locked": False},
        {"key": "guild_contract", "name": "Contract Fulfilled", "icon": "\U0001f4b0",
         "description": "Collect on a Guild bounty.", "progress": 0, "target": 3, "completed": False, "locked": False},
        {"key": "ace", "name": "Ace Pilot", "icon": "\U0001f31f",
         "description": "Win ten dogfights.", "progress": 0, "target": 10, "completed": False, "locked": True},
    ],
}
MOCK_PLACES = {  # _hud_sidebar_places
    "places": [
        {"id": 1, "name": "Chalmun's Cantina Bar", "occupants": ["Kael Dorne", "Sera Vane"]},
        {"id": 2, "name": "Sabacc Table", "occupants": ["Temo Drask"]},
        {"id": 3, "name": "Docking Gantry", "occupants": []},
    ],
}
# Comms pane events (client-internal shape read by buildCommsRow:
# t / channel / who / text). t in comm-in|ooc|sys-event|sys-ok|sys-arrival.
MOCK_COMMS = [
    {"t": "comm-in", "channel": "open", "who": "Sera Vane", "text": "Anyone got eyes on the east landing pad?"},
    {"t": "comm-in", "channel": "squad", "who": "Temo Drask", "text": "Two speeders inbound, flying Hutt colors."},
    {"t": "sys-arrival", "text": "Korri Bask has arrived from the Spaceport."},
    {"t": "ooc", "who": "Brian", "text": "brb, refilling caf"},
    {"t": "comm-in", "channel": "open", "who": "Sera Vane", "text": "Copy. Moving to intercept."},
    {"t": "sys-event", "text": "A dust storm is building over the Dune Sea."},
    {"t": "ooc", "who": "Mira", "text": "nice pose — love the detail"},
    {"t": "sys-ok", "text": "Channel encryption handshake complete."},
]

# A representative ground combat_state for the combat-strip (the combat HUD).
MOCK_COMBAT = {
    "active": True, "round": 2, "phase": "declaration", "theatre": "ground",
    "combatants": [
        {"id": 1, "name": "Tey Voss", "is_player": True, "wound_level": 0,
         "wound_name": "Healthy", "initiative": 17, "declared": True,
         "action_summary": "attack Jawa Scrap Boss", "cover": 1, "aim_bonus": 0, "is_fleeing": False},
        {"id": 2, "name": "Jawa Scrap Boss", "is_player": False, "wound_level": 2,
         "wound_name": "Wounded", "initiative": 10, "declared": False,
         "action_summary": None, "cover": 0, "aim_bonus": 0, "is_fleeing": False},
        {"id": 3, "name": "Gamorrean Thug", "is_player": False, "wound_level": 1,
         "wound_name": "Stunned", "initiative": 8, "declared": True,
         "action_summary": "attack Tey Voss", "cover": 2, "aim_bonus": 0, "is_fleeing": False},
    ],
    "your_actions": ["attack Jawa Scrap Boss with blaster"],
    "waiting_for": ["Jawa Scrap Boss"],
    "pose_deadline": None,
    "events": [
        {"attacker": "Tey Voss", "target": "Jawa Scrap Boss", "result": "hit", "wound": "Wounded", "weapon": "blaster"},
        {"attacker": "Gamorrean Thug", "target": "Tey Voss", "result": "parried", "wound": "", "weapon": "vibro-axe"},
        {"attacker": "Tey Voss", "target": "Gamorrean Thug", "result": "hit", "wound": "Stunned", "weapon": "blaster"},
    ],
}


# ── Live-server lifecycle ────────────────────────────────────────────────────
def _server_up():
    try:
        with urllib.request.urlopen(BASE + "/api/chargen/species", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _start_server():
    """Boot main.py cost-safe. Returns (proc_or_None, started_here_bool, logpath)."""
    if _server_up():
        print("  (reusing live server already on %s)" % BASE)
        return None, False, None
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""  # disable paid Director — zero API cost
    logpath = os.path.join(ROOT, "logs", "_capture_server.log")
    os.makedirs(os.path.dirname(logpath), exist_ok=True)
    logf = open(logpath, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "main.py",
         "--web-port", str(WEB_PORT), "--ws-port", str(WS_PORT), "--telnet-port", str(TELNET_PORT)],
        cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT,
    )
    print("  booting live server (pid %d) on %s ..." % (proc.pid, BASE))
    for _ in range(60):  # up to ~60s for world-load
        if proc.poll() is not None:
            raise RuntimeError("server exited during boot (rc=%s); see %s" % (proc.returncode, logpath))
        if _server_up():
            print("  server ready")
            return proc, True, logpath
        time.sleep(1)
    raise RuntimeError("server did not become ready within 60s; see %s" % logpath)


def _stop_server(proc):
    if proc is None:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except Exception as e:
        print("  (warn: taskkill on capture server pid %s failed: %s)" % (proc.pid, e))
    try:
        proc.kill()
    except Exception as e:
        print("  (warn: proc.kill on capture server failed: %s)" % e)


def _make_instrumented_client():
    """Write a temp client copy that ALSO exposes the handlers the production
    client only reaches via a live WebSocket — so we can drive the ground-combat
    HUD, the comms pane, and the mail/achievements/places sidebar panels."""
    src = open(os.path.join(ROOT, "static", "client.html"), encoding="utf-8").read()
    needle = "window.handleHudUpdate = handleHudUpdate;"
    assert needle in src, "exposure anchor not found in client.html"
    extra = (needle
             + "\n  window.handleCombatState = handleCombatState;"
             + "\n  window.appendEvent = appendEvent;"
             + "\n  window.handleMailStatus = handleMailStatus;"
             + "\n  window.handleAchievementsStatus = handleAchievementsStatus;"
             + "\n  window.handlePlacesStatus = handlePlacesStatus;")
    src = src.replace(needle, extra, 1)
    out = os.path.join(ROOT, "static", "_client_instrumented.html")
    open(out, "w", encoding="utf-8", newline="").write(src)
    return "/static/_client_instrumented.html"


def _shoot(page, name, full=True):
    path = os.path.join(OUT, name + ".png")
    page.screenshot(path=path, full_page=full)
    print("  saved %s.png" % name)


# JS: populate the ground sidebar panels + comms pane on the instrumented client.
_ENRICH_GROUND_JS = r"""
(p) => {
  var out = {};
  try { window.handleMailStatus(p.mail); } catch (e) { out.mail = String(e); }
  try { window.handleAchievementsStatus(p.ach); } catch (e) { out.ach = String(e); }
  try { window.handlePlacesStatus(p.places); } catch (e) { out.places = String(e); }
  try {
    var pane = document.getElementById('comms-pane-ground');
    if (pane && pane.classList.contains('collapsed') && window.toggleCommsPane) {
      window.toggleCommsPane('ground');
    }
    (p.comms || []).forEach(function(m) { window.appendEvent(m); });
  } catch (e) { out.comms = String(e); }
  return out;
}
"""

# JS: mount the galaxy/region navigator at its self-contained GALAXY tier.
_GALAXY_JS = r"""
(spec) => {
  try {
    document.body.innerHTML = '';
    document.body.style.cssText =
      'margin:0;background:#000;min-height:100vh;display:flex;align-items:center;justify-content:center;';
    if (!(window.M3MapNavigator && window.M3MapNavigator.create)) return 'M3MapNavigator not loaded';
    if (!(window.M3TierRegistry && window.M3TierRegistry.getTierRenderer)) return 'M3TierRegistry not loaded';
    var pal = (window.M3Palettes && window.M3Palettes.getPalette)
                ? window.M3Palettes.getPalette('tatooine') : null;
    if (!pal) return 'palette not found';
    var w = Math.min(1280, (window.innerWidth || 1280));
    var h = Math.min(900, (window.innerHeight || 900));
    var handle = window.M3MapNavigator.create(pal, {
      width: w, height: h, getTierRenderer: null,
      region: null, regionKey: null, data: null,
      startTier: (spec && spec.tier) || '4c', time: 'day', weather: 'clear',
    });
    if (!handle || !handle.element) return 'create() returned no element';
    var c = document.createElement('div');
    c.style.cssText = 'position:relative;width:' + w + 'px;height:' + h + 'px;';
    c.appendChild(handle.element);
    document.body.appendChild(c);
    return 'ok';
  } catch (e) { return 'exc: ' + e; }
}
"""


def run():
    from playwright.sync_api import sync_playwright
    results = {"ok": [], "fail": []}
    proc = None
    inst_written = False
    try:
        proc, _started, _log = _start_server()
        inst_url = _make_instrumented_client()
        inst_written = True

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                      device_scale_factor=2)

            # ── Standalone pages ──
            standalone = [
                ("01_landing_portal", "/static/portal.html"),
                ("02_login_boot", "/static/client.html"),
                ("09_map_preview", "/static/map_v2_preview.html"),
            ]
            for name, url in standalone:
                try:
                    page = ctx.new_page()
                    page.goto(BASE + url, wait_until="networkidle", timeout=25000)
                    page.wait_for_timeout(1500)
                    _shoot(page, name, full=(name != "02_login_boot"))
                    results["ok"].append(name); page.close()
                except Exception as e:
                    results["fail"].append("%s: %s" % (name, str(e)[:120]))

            # ── Chargen (LIVE backend): step 1 PATH (03) then step 3 ATTRS (03b) ──
            try:
                page = ctx.new_page()
                page.goto(BASE + "/static/chargen.html", wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)
                _shoot(page, "03_chargen", full=True)
                results["ok"].append("03_chargen")
                # Pick a template (auto-sets species) then advance to the attributes step.
                page.evaluate(r"""() => {
                  var cards = Array.from(document.querySelectorAll('*')).filter(function(e){
                    return /Smuggler/i.test(e.textContent || '') && e.children.length > 0 && (e.className || '').length; });
                  var card = cards.sort(function(a,b){ return (a.textContent||'').length - (b.textContent||'').length; })[0];
                  if (card) card.click();
                }""")
                page.wait_for_timeout(600)
                page.evaluate(r"""() => {
                  var nx = Array.from(document.querySelectorAll('button,a,div')).find(function(e){
                    return e.children.length === 0 && /^\s*NEXT/i.test(e.textContent || ''); });
                  if (nx) nx.click();
                }""")
                page.wait_for_timeout(1800)
                _shoot(page, "03b_chargen_attributes", full=True)
                results["ok"].append("03b_chargen_attributes"); page.close()
            except Exception as e:
                results["fail"].append("03_chargen/03b: %s" % str(e)[:120])

            # ── Integrated ground client (instrumented: hud + sidebar + comms) ──
            try:
                page = ctx.new_page()
                page.goto(BASE + inst_url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(800)
                page.evaluate(
                    "(hud) => { try { window.handleHudUpdate(hud); } catch(e){ window.__hudErr = String(e); } }",
                    MOCK_HUD)
                page.wait_for_timeout(500)
                enrich = page.evaluate(_ENRICH_GROUND_JS,
                    {"mail": MOCK_MAIL, "ach": MOCK_ACH, "places": MOCK_PLACES, "comms": MOCK_COMMS})
                page.wait_for_timeout(1000)
                err = page.evaluate("() => window.__hudErr || null")
                if err:
                    results["fail"].append("04_ground_play: handleHudUpdate threw: %s" % err[:100])
                if enrich:
                    results["fail"].append("04_ground_play enrich partial: %s" % json.dumps(enrich)[:140])
                _shoot(page, "04_ground_play", full=False)
                results["ok"].append("04_ground_play"); page.close()
            except Exception as e:
                results["fail"].append("04_ground_play: %s" % str(e)[:120])

            # ── Galaxy/region navigator overlay (self-contained GALAXY tier) ──
            try:
                page = ctx.new_page()
                page.goto(BASE + "/static/client.html", wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(700)
                status = page.evaluate(_GALAXY_JS, {"tier": "4c"})
                page.wait_for_timeout(900)
                if status == "ok":
                    _shoot(page, "10_galaxy_navigator", full=False); results["ok"].append("10_galaxy_navigator")
                else:
                    results["fail"].append("10_galaxy_navigator: %s" % str(status)[:140])
                page.close()
            except Exception as e:
                results["fail"].append("10_galaxy_navigator: %s" % str(e)[:120])

            # ── In-game component modals/panels from each module's demo fixture ──
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
                  var c = document.createElement('div');
                  c.style.cssText = 'width:1180px;max-width:96vw;';
                  document.body.appendChild(c);
                  if (spec.stage !== undefined) fn(c, fixture, spec.stage, noop);
                  else fn(c, fixture, noop);
                  return 'ok';
                }
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
                ("11_space_cockpit", {"ns": "M3Cockpit", "fn": "buildCockpitView", "fixtureKey": None, "mode": "build"}),
                ("12_skill_check", {"ns": "M3SkillCheck", "fn": "buildSkillCheckShowcase", "fixtureKey": None, "mode": "build"}),
                ("13_holocron", {"ns": "M3Holocron", "fn": "buildHolocronModal", "fixtureKey": None, "mode": "build"}),
                ("15_craft", {"ns": "M3Craft", "fn": "render", "data": {
                    "resources": [{"name": "Durasteel", "qty": 4, "quality": 62},
                                  {"name": "Power Cell", "qty": 3, "quality": 80},
                                  {"name": "Fiberplast", "qty": 2, "quality": 55}],
                    "schematics": [
                        {"key": "dl44", "name": "DL-44 Heavy Blaster", "tier": 1, "difficulty": 12, "can_craft": True,
                         "skill": "blaster repair", "materials": [{"name": "durasteel", "have": 4, "need": 3}, {"name": "power_cell", "have": 3, "need": 2}]},
                        {"key": "blast_vest", "name": "Blast Vest", "tier": 1, "difficulty": 10, "can_craft": True,
                         "skill": "armor repair", "materials": [{"name": "fiberplast", "have": 2, "need": 2}]},
                        {"key": "vibroblade", "name": "Vibroblade", "tier": 2, "difficulty": 15, "can_craft": False,
                         "skill": "melee repair", "materials": [{"name": "phrik", "have": 0, "need": 1}]}],
                    "last_result": {"success": True, "item": "DL-44 Heavy Blaster", "quality": 71}}, "mode": "container"}),
                ("16_board", {"ns": "M3Board", "fn": "render", "data": {
                    "claimed_id": None,
                    "contracts": [
                        {"id": 1, "target": "Vex Drago", "faction": "Hutt Cartel", "reward": 18000, "tier": "veteran",
                         "desc": "Sullustan smuggler wanted alive for double-crossing Jabba on the Kessel run.", "status": "open"},
                        {"id": 2, "target": "Renta Voss", "faction": "Bounty Guild", "reward": 6500, "tier": "standard",
                         "desc": "Skipped bail in Mos Espa. Last seen near the podracing arena.", "status": "open"},
                        {"id": 3, "target": "The Whisper", "faction": "Independent", "reward": 32000, "tier": "deadly",
                         "desc": "Information broker. Dead or alive. Approach with extreme caution.", "status": "open"}]}, "mode": "container"}),
            ]
            for name, spec in modals:
                try:
                    page = ctx.new_page()
                    page.goto(BASE + "/static/client.html", wait_until="networkidle", timeout=25000)
                    page.wait_for_timeout(600)
                    status = page.evaluate(modal_js, spec)
                    page.wait_for_timeout(700)
                    if status == "ok":
                        _shoot(page, name, full=True); results["ok"].append(name)
                    else:
                        results["fail"].append("%s: %s" % (name, str(status)[:140]))
                    page.close()
                except Exception as e:
                    results["fail"].append("%s: %s" % (name, str(e)[:120]))

            # ── Ground combat HUD (instrumented client: hud_update then combat_state) ──
            try:
                page = ctx.new_page()
                page.goto(BASE + inst_url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(700)
                page.evaluate("(hud) => { try { window.handleHudUpdate(hud); } catch(e){} }", MOCK_HUD)
                page.wait_for_timeout(400)
                err = page.evaluate(
                    "(cs) => { try { window.handleCombatState(cs); return null; } catch(e){ return String(e); } }",
                    MOCK_COMBAT)
                page.wait_for_timeout(900)
                if err:
                    results["fail"].append("14_ground_combat: handleCombatState threw: %s" % err[:100])
                _shoot(page, "14_ground_combat", full=False)
                results["ok"].append("14_ground_combat"); page.close()
            except Exception as e:
                results["fail"].append("14_ground_combat: %s" % str(e)[:120])

            browser.close()
    finally:
        if inst_written:
            try:
                os.remove(os.path.join(ROOT, "static", "_client_instrumented.html"))
            except Exception as e:
                print("  (warn: could not remove temp instrumented client: %s)" % e)
        _stop_server(proc)

    print("\n=== CAPTURE SUMMARY ===")
    print("OK  :", ", ".join(results["ok"]))
    print("FAIL:", "\n       ".join(results["fail"]) if results["fail"] else "(none)")
    return results


if __name__ == "__main__":
    run()
