#!/usr/bin/env python3
"""
tools/make_substrate_seed.py — render an img2img SEED + a labeled KEYMAP
for any AreaGeometry map YAML, using the EXACT projector the registration
tool / manifest generator use (fx=(wx-x_min)/dx, fy=(y_max-wy)/dy → north-up).

Two outputs per area:
  <out>/<basename>_seed.png    — TEXT-FREE spatial scaffold to feed Nano (img2img).
                                  District color-blocks + street ribbons + room
                                  footprints + landmark markers. No text => nothing
                                  for Gemini to OCR (franchise filter) and nothing
                                  to leak as a label into the painting.
  <out>/<basename>_keymap.png  — the SAME layout WITH labels (district names,
                                  landmark names, N arrow, title). YOUR reference
                                  only — do NOT feed this to Nano.

Usage:
  python tools/make_substrate_seed.py <area_key> [--out dir] [--long 2048]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# distinct, desaturated district hues (cycled) — must read as SEPARATE zones
DISTRICT_HUES = [
    (96, 116, 138),   # slate blue
    (138, 116, 86),   # tan
    (104, 132, 104),  # sage
    (140, 104, 120),  # mauve
    (120, 120, 96),   # olive
    (96, 130, 138),   # teal
    (132, 112, 132),  # heather
]
BG_SEED   = (26, 28, 32)
BG_KEYMAP = (40, 43, 49)
ROOM_FILL = (210, 206, 196)
ROOM_EDGE = (250, 248, 242)
STREET    = (196, 188, 168)
LM_DIST   = (255, 196, 96)    # distinctive landmark (gold)
LM_GEN    = (150, 170, 190)   # generic landmark (cool grey-blue)

# --- TIGHT mode: lock the macro skeleton so Gemini preserves composition ---
TIGHT_ROOM_FILL = (118, 120, 116)   # dark, recessive density texture (NOT per-room prompt)
TIGHT_ROOM_EDGE = (96, 98, 94)
TIGHT_STREET    = (252, 250, 245)   # near-white centerline — unmistakable on any district
ROAD_CASING     = (12, 13, 16)      # dark casing under streets => road network reads


def _load(area_key, era, root):
    base = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    p = Path(root) / era / "maps" / f"{base}.yaml"
    if not p.exists():
        sys.exit(f"map YAML not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return raw, base


def _font(sz):
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(cand, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def render(area_key: str, era="clone_wars", root="data/worlds",
           out="static/tools/seeds", long_edge=2048, tight=False):
    raw, base = _load(area_key, era, root)
    b = raw["bounds"]
    x0, y0, x1, y1 = (float(b["x_min"]), float(b["y_min"]),
                      float(b["x_max"]), float(b["y_max"]))
    dx, dy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    aspect = dx / dy
    if aspect >= 1.0:
        W, H = long_edge, round(long_edge / aspect)
    else:
        H, W = long_edge, round(long_edge * aspect)

    def P(wx, wy):
        fx = (wx - x0) / dx
        fy = (y1 - wy) / dy            # north-up, matches tool + manifest
        return (fx * W, fy * H)

    def scale_len(world_len):
        return world_len * (W / dx)

    def draw_base(draw, overlay_draw, labeled):
        # In TIGHT mode the district fills are near-opaque, so the skeleton
        # (edges, roads, landmarks) must draw on the OVERLAY to sit ABOVE the
        # fill. Rooms stay on the base => recessive density under the fill.
        skel = overlay_draw if tight else draw
        A = (255,)
        # districts (filled polygons w/ alpha on overlay)
        for i, d in enumerate(raw.get("districts") or []):
            pts = [P(px, py) for px, py in d["polygon"]]
            hue = DISTRICT_HUES[i % len(DISTRICT_HUES)]
            if tight:
                overlay_draw.polygon(pts, fill=hue + (205,))
                # crisp dark casing + bright inner edge => hard, distinct borders
                skel.line(pts + [pts[0]], fill=(12, 13, 16) + A, width=max(5, W // 220))
                skel.line(pts + [pts[0]],
                          fill=tuple(min(c + 90, 255) for c in hue) + A, width=max(3, W // 440))
            else:
                overlay_draw.polygon(pts, fill=hue + (150,))
                draw.line(pts + [pts[0]], fill=tuple(min(c + 40, 255) for c in hue),
                          width=max(2, W // 500))
        # rooms (footprints): x,y is CENTER (renderer projects x-w/2,y-h/2)
        # drawn on BASE so the near-opaque tight fill mutes them into texture
        for r in raw.get("rooms") or []:
            cx, cy = float(r["x"]), float(r["y"])
            w, h = float(r["w"]), float(r["h"])
            tl = P(cx - w / 2, cy + h / 2)   # +h/2 because y is up; tl is top-left in image
            br = P(cx + w / 2, cy - h / 2)
            if tight:
                draw.rectangle([tl, br], fill=TIGHT_ROOM_FILL, outline=TIGHT_ROOM_EDGE,
                               width=max(1, W // 1100))
            else:
                draw.rectangle([tl, br], fill=ROOM_FILL, outline=ROOM_EDGE,
                               width=max(1, W // 900))
        # streets (ribbons) — on the skeleton layer so they sit above the fill
        for key, ep in (raw.get("exit_paths") or {}).items():
            path = [P(px, py) for px, py in ep["path"]]
            if len(path) < 2:
                continue
            base_w = max(4, int(scale_len(float(ep.get("width", 0.2)))))
            if tight:
                wpx = int(base_w * 1.7)
                skel.line(path, fill=ROAD_CASING + A, width=wpx + max(6, W // 280),
                          joint="curve")
                skel.line(path, fill=TIGHT_STREET + A, width=wpx, joint="curve")
            else:
                draw.line(path, fill=STREET, width=base_w, joint="curve")
        # landmarks (markers) — on the skeleton layer in tight mode
        for lm in raw.get("landmarks") or []:
            pos = lm.get("pos")
            if not pos:
                continue
            px, py = P(float(pos[0]), float(pos[1]))
            name = str(lm.get("name", ""))
            icon = str(lm.get("icon", "beacon"))
            offmap = any(a in name for a in ("\u2197", "\u2199", "\u2196", "\u2198"))
            distinctive = (not offmap) and icon in {
                "dock", "ship", "wreck", "cantina", "bones", "palace"}
            col = LM_DIST if distinctive else LM_GEN
            if tight:
                if distinctive:
                    # building BLOCK + ring => Gemini plants a real structure here
                    bs = W // 42
                    skel.rectangle([px - bs, py - bs, px + bs, py + bs],
                                   fill=col + A, outline=(20, 20, 24) + A, width=max(2, W // 520))
                    rr = bs + max(5, W // 200)
                    skel.ellipse([px - rr, py - rr, px + rr, py + rr],
                                 outline=col + A, width=max(2, W // 640))
                else:
                    rad = W // 110
                    skel.ellipse([px - rad, py - rad, px + rad, py + rad],
                                 fill=col + A, outline=(20, 20, 24) + A, width=max(2, W // 700))
            else:
                rad = (W // 70) if distinctive else (W // 110)
                draw.ellipse([px - rad, py - rad, px + rad, py + rad],
                             fill=col, outline=(20, 20, 24), width=max(2, W // 600))
                if distinctive:
                    rr = rad + max(4, W // 240)
                    draw.ellipse([px - rr, py - rr, px + rr, py + rr],
                                 outline=col, width=max(2, W // 700))

    # ── SEED (text-free) ────────────────────────────────────────────────
    seed = Image.new("RGB", (W, H), BG_SEED)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_base(ImageDraw.Draw(seed), ImageDraw.Draw(ov), labeled=False)
    seed = Image.alpha_composite(seed.convert("RGBA"), ov).convert("RGB")

    # ── KEYMAP (labeled, reference only) ────────────────────────────────
    km = Image.new("RGB", (W, H), BG_KEYMAP)
    ovk = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_base(ImageDraw.Draw(km), ImageDraw.Draw(ovk), labeled=True)
    km = Image.alpha_composite(km.convert("RGBA"), ovk).convert("RGB")
    d = ImageDraw.Draw(km)
    fL, fM, fS = _font(max(20, W // 36)), _font(max(15, W // 64)), _font(max(12, W // 90))
    # title + N arrow
    title = f'{raw.get("display_name", area_key)}   ·   {area_key}   ·   bounds {dx:g}x{dy:g}  aspect {aspect:.2f}'
    if tight:
        title += "   ·   [TIGHT SEED]"
    d.rectangle([0, 0, W, int(H * 0.06) + 8], fill=(18, 19, 22))
    d.text((16, 10), title, font=fM, fill=(230, 226, 216))
    ax, ay = W - int(W * 0.06), int(H * 0.10)
    d.line([(ax, ay + 30), (ax, ay - 30)], fill=(230, 226, 216), width=4)
    d.polygon([(ax - 9, ay - 18), (ax + 9, ay - 18), (ax, ay - 34)], fill=(230, 226, 216))
    d.text((ax - 6, ay + 34), "N", font=fS, fill=(230, 226, 216))
    # district names
    for i, dd in enumerate(raw.get("districts") or []):
        la = dd.get("label_anchor") or dd["polygon"][0]
        px, py = P(float(la[0]), float(la[1]))
        d.text((px, py), str(dd.get("name", dd.get("id", ""))), font=fM,
               fill=(245, 242, 234), stroke_width=3, stroke_fill=(20, 20, 24))
    # landmark names
    for lm in raw.get("landmarks") or []:
        pos = lm.get("pos")
        if not pos:
            continue
        px, py = P(float(pos[0]), float(pos[1]))
        d.text((px + W // 60, py - W // 120), str(lm.get("name", "")), font=fS,
               fill=(255, 226, 170), stroke_width=3, stroke_fill=(20, 20, 24))

    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    suffix = "_tight" if tight else ""
    sp, kp = outd / f"{base}{suffix}_seed.png", outd / f"{base}{suffix}_keymap.png"
    seed.save(sp); km.save(kp)
    print(f"{area_key:<30} {W}x{H} (aspect {aspect:.3f})  ->  {sp.name}, {kp.name}")
    return sp, kp


# ════════════════════════════════════════════════════════════════════
# WILDERNESS mode (Drop 4.16) — soft terrain blobs + POI gold-blocks +
# faint tracks, from a region OVERVIEW spec (terrain_zones / routes /
# landmarks) rather than a city map (districts / rooms / exit_paths). The
# seed grammar per the painted-wilderness design §4b: terrain reads as
# blended zones (NOT hard districts), distinctive POIs get the same gold
# building-block convention as city landmarks, tracks are faint (NOT bright
# paved causeways). Same projector + tight semantics as the city mode, so
# the unified atlas style clause / reference image apply unchanged.
# ════════════════════════════════════════════════════════════════════
TERRAIN_HUES = {
    "dune":       (152, 130, 96),    # warm sand
    "scrub":      (124, 122, 92),    # olive flats
    "canyon":     (134, 104, 82),    # rock / badlands
    "rock":       (122, 112, 96),
    "ferrocrete": (92, 98, 108),     # cold grey ducrete
    "duracrete":  (98, 102, 108),
    "industrial": (104, 92, 100),    # grey-mauve ruin
    "dark":       (50, 54, 62),      # bottom dark
}
TERRAIN_DEFAULT = (112, 110, 104)


def _load_overview(area_key, era, root):
    stem = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    p = Path(root) / era / "maps" / f"{stem}.yaml"
    if not p.exists():
        sys.exit(f"overview YAML not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    # terrain_zones is optional: a faithful overview generated from real
    # region data may carry zero invented zones (open desert / dark base +
    # POIs + routes only). It MUST, however, look like an overview spec and
    # not a city map — guard against running --wilderness on a districts map.
    if "terrain_zones" not in raw and "landmarks" not in raw:
        sys.exit(f"{p} is not an overview spec (no terrain_zones or landmarks). "
                 f"City maps use the default mode; drop --wilderness.")
    if "districts" in raw or "rooms" in raw or "exit_paths" in raw:
        sys.exit(f"{p} looks like a city map (districts/rooms/exit_paths). "
                 f"Use the default seed mode; drop --wilderness.")
    raw.setdefault("terrain_zones", [])
    return raw, stem


def render_wilderness(area_key: str, era="clone_wars", root="data/worlds",
                      out="static/tools/seeds", long_edge=2048, tight=False):
    raw, stem = _load_overview(area_key, era, root)
    out_base = raw.get("area_key") or stem
    b = raw["bounds"]
    x0, y0, x1, y1 = (float(b["x_min"]), float(b["y_min"]),
                      float(b["x_max"]), float(b["y_max"]))
    dx, dy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    aspect = dx / dy
    if aspect >= 1.0:
        W, H = long_edge, round(long_edge / aspect)
    else:
        H, W = long_edge, round(long_edge * aspect)

    def P(wx, wy):
        # Overview pos is SVG-space (y DOWN, north=top), matching the live
        # renderer (m3_tier_wilderness_body draws POIs at SVG (x,y)) and the
        # gen_wilderness_overview projection. NO y-flip here, so a landmark
        # lands in the same place in the seed, the painting, and the live map.
        return ((wx - x0) / dx * W, (wy - y0) / dy * H)

    base_tone = tuple((raw.get("base_tone") or [22, 22, 26])[:3])
    A = (255,)

    def compose():
        # bg + soft (blurred) terrain blobs + faint routes + POI blocks.
        zones = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        zd = ImageDraw.Draw(zones)
        for z in (raw.get("terrain_zones") or []):
            pts = [P(px, py) for px, py in z["polygon"]]
            hue = TERRAIN_HUES.get(str(z.get("terrain", "")), TERRAIN_DEFAULT)
            if z.get("hazard"):
                # nudge hazard zones warmer + a touch darker so they read apart
                hue = (min(hue[0] + 16, 255), max(hue[1] - 8, 0), max(hue[2] - 8, 0))
            alpha = 215 if tight else 160
            zd.polygon(pts, fill=hue + (alpha,))
        blur = (max(6, W // 120)) if tight else (max(12, W // 60))
        zones = zones.filter(ImageFilter.GaussianBlur(blur))

        img = Image.alpha_composite(
            Image.new("RGBA", (W, H), base_tone + (255,)), zones)
        d = ImageDraw.Draw(img)

        # faint routes — low-contrast tracks, never bright causeways
        for rt in (raw.get("routes") or []):
            path = [P(px, py) for px, py in rt]
            if len(path) < 2:
                continue
            col = (192, 184, 162, 150) if tight else (176, 168, 150, 115)
            d.line(path, fill=col, width=max(3, W // 360), joint="curve")

        # POIs — gold building-block (distinctive) / grey dot (generic)
        for lm in (raw.get("landmarks") or []):
            pos = lm.get("pos")
            if not pos:
                continue
            px, py = P(float(pos[0]), float(pos[1]))
            if bool(lm.get("distinctive")):
                bs = (W // 42) if tight else (W // 54)
                d.rectangle([px - bs, py - bs, px + bs, py + bs],
                            fill=LM_DIST + A, outline=(20, 20, 24) + A,
                            width=max(2, W // 520))
                rr = bs + max(5, W // 200)
                d.ellipse([px - rr, py - rr, px + rr, py + rr],
                          outline=LM_DIST + A, width=max(2, W // 640))
            else:
                rad = W // 110
                d.ellipse([px - rad, py - rad, px + rad, py + rad],
                          fill=LM_GEN + A, outline=(20, 20, 24) + A,
                          width=max(2, W // 700))
        return img

    # ── SEED (text-free) ────────────────────────────────────────────────
    seed = compose().convert("RGB")

    # ── KEYMAP (labeled, reference only) ────────────────────────────────
    km = compose()
    d = ImageDraw.Draw(km)
    fM, fS = _font(max(15, W // 64)), _font(max(12, W // 90))
    title = (f'{raw.get("display_name", out_base)}   ·   {out_base}   ·   '
             f'bounds {dx:g}x{dy:g}  aspect {aspect:.2f}   ·   [WILDERNESS')
    title += " TIGHT]" if tight else "]"
    d.rectangle([0, 0, W, int(H * 0.06) + 8], fill=(18, 19, 22))
    d.text((16, 10), title, font=fM, fill=(230, 226, 216))
    ax, ay = W - int(W * 0.06), int(H * 0.10)
    d.line([(ax, ay + 30), (ax, ay - 30)], fill=(230, 226, 216), width=4)
    d.polygon([(ax - 9, ay - 18), (ax + 9, ay - 18), (ax, ay - 34)], fill=(230, 226, 216))
    d.text((ax - 6, ay + 34), "N", font=fS, fill=(230, 226, 216))
    # zone names at polygon centroids
    for z in (raw.get("terrain_zones") or []):
        poly = z["polygon"]
        cx = sum(pt[0] for pt in poly) / len(poly)
        cy = sum(pt[1] for pt in poly) / len(poly)
        px, py = P(cx, cy)
        d.text((px, py), str(z.get("name", "")), font=fS,
               fill=(238, 234, 224), stroke_width=3, stroke_fill=(20, 20, 24),
               anchor="mm")
    # POI names
    for lm in (raw.get("landmarks") or []):
        pos = lm.get("pos")
        if not pos:
            continue
        px, py = P(float(pos[0]), float(pos[1]))
        d.text((px + W // 60, py - W // 120), str(lm.get("name", "")), font=fS,
               fill=(255, 226, 170), stroke_width=3, stroke_fill=(20, 20, 24))
    km = km.convert("RGB")

    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    suffix = "_tight" if tight else ""
    sp, kp = outd / f"{out_base}{suffix}_seed.png", outd / f"{out_base}{suffix}_keymap.png"
    seed.save(sp); km.save(kp)
    print(f"{out_base:<30} {W}x{H} (aspect {aspect:.3f})  WILDERNESS ->  {sp.name}, {kp.name}")
    return sp, kp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("area_keys", nargs="+")
    ap.add_argument("--era", default="clone_wars")
    ap.add_argument("--root", default="data/worlds")
    ap.add_argument("--out", default="static/tools/seeds")
    ap.add_argument("--long", type=int, default=2048)
    ap.add_argument("--tight", action="store_true",
                    help="lock the macro skeleton (crisp districts, cased roads, "
                         "landmark blocks) for high-fidelity img2img backdrops")
    ap.add_argument("--wilderness", action="store_true",
                    help="region OVERVIEW seed (soft terrain blobs + POI gold-blocks "
                         "+ faint tracks) from a *_overview.yaml spec (Drop 4.16)")
    a = ap.parse_args()
    for k in a.area_keys:
        if a.wilderness:
            render_wilderness(k, era=a.era, root=a.root, out=a.out,
                              long_edge=a.long, tight=a.tight)
        else:
            render(k, era=a.era, root=a.root, out=a.out, long_edge=a.long, tight=a.tight)
