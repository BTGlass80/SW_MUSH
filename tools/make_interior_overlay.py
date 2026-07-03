#!/usr/bin/env python3
"""tools/make_interior_overlay.py — composite the NAVIGATION overlay onto a
painted interior substrate, so you can judge how in-game navigation reads on the
new art (room click-targets, movement paths, labeled landmark pins, tier labels).

Uses the SAME north-up projector as tools/make_substrate_seed.py / the live map
registration, so every marker lands where the live map would put it:
    fx = (wx - x_min)/dx ;  fy = (y_max - wy)/dy

This is a preview compositor for the 2026-06-19 Nano interior drafts — it does
NOT wire anything into the live game. Output: <out> PNG = painting + overlay.

Usage:
  python tools/make_interior_overlay.py <area_key> <painting.png> [--out PATH]
      [--root static/tools/_interior_test] [--era clone_wars] [--long 2048]
      [--title "DISPLAY NAME"]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import yaml
from PIL import Image, ImageDraw, ImageFont

# navigation palette (drawn on a translucent overlay, over the art)
PATH_CASING = (18, 16, 12, 180)     # dark casing under movement paths
PATH_LINE   = (255, 236, 188, 165)  # warm movement-path ribbon (click-to-move)
ROOM_FILL   = (255, 255, 255, 32)   # faint click-target fill
ROOM_EDGE   = (250, 248, 240, 200)  # click-target outline
LM_GOLD     = (255, 198, 92, 235)   # landmark pin
LM_RING     = (255, 214, 130, 230)
TXT         = (248, 246, 238)
TXT_STROKE  = (14, 14, 18)
DIST_TXT    = (236, 230, 250)


def _font(sz):
    for cand in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(cand, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_bold(sz):
    for cand in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(cand, sz)
        except OSError:
            continue
    return _font(sz)


def render(area_key, painting_path, out_path, root="static/tools/_interior_test",
           era="clone_wars", long_edge=2048, title=None):
    base = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    yp = Path(root) / era / "maps" / f"{base}.yaml"
    if not yp.exists():
        sys.exit(f"zone-map YAML not found: {yp}")
    raw = yaml.safe_load(yp.read_text(encoding="utf-8"))
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
        return ((wx - x0) / dx * W, (y1 - wy) / dy * H)

    def slen(world_len):
        return world_len * (W / dx)

    # base = painting resized to the canonical seed frame (img2img keeps aspect)
    art = Image.open(painting_path).convert("RGB").resize((W, H), Image.LANCZOS)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # 1) movement paths (click-to-move connectors) — casing then ribbon
    for key, ep in (raw.get("exit_paths") or {}).items():
        path = [P(px, py) for px, py in ep.get("path", [])]
        if len(path) < 2:
            continue
        w = max(5, int(slen(float(ep.get("width", 0.2))) * 0.55))
        d.line(path, fill=PATH_CASING, width=w + max(6, W // 300), joint="curve")
        d.line(path, fill=PATH_LINE, width=w, joint="curve")

    # 2) room click-targets (every room is a tap location)
    lm_ids = {str(lm.get("id")) for lm in (raw.get("landmarks") or [])}
    lm_slugs = set()
    for r in raw.get("rooms") or []:
        cx, cy = float(r["x"]), float(r["y"])
        w, h = float(r["w"]), float(r["h"])
        tl = P(cx - w / 2, cy + h / 2)
        br = P(cx + w / 2, cy - h / 2)
        rad = max(8, W // 90)
        d.rounded_rectangle([tl, br], radius=rad, fill=ROOM_FILL,
                            outline=ROOM_EDGE, width=max(2, W // 640))

    # 3) landmark pins + names (the navigation anchors)
    fL = _font_bold(max(20, W // 52))
    landmark_rooms = set()
    for lm in raw.get("landmarks") or []:
        pos = lm.get("pos")
        if not pos:
            continue
        px, py = P(float(pos[0]), float(pos[1]))
        landmark_rooms.add((round(float(pos[0]), 2), round(float(pos[1]), 2)))
        rr = W // 64
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=LM_GOLD,
                  outline=(20, 18, 14, 255), width=max(2, W // 520))
        ring = rr + max(5, W // 200)
        d.ellipse([px - ring, py - ring, px + ring, py + ring],
                  outline=LM_RING, width=max(2, W // 700))
        name = str(lm.get("name", ""))
        d.text((px + ring + 6, py - fL.size // 2), name, font=fL, fill=TXT,
               stroke_width=max(3, W // 360), stroke_fill=TXT_STROKE)

    # 4) ordinary room names (small) for non-landmark rooms
    fS = _font(max(15, W // 80))
    for r in raw.get("rooms") or []:
        keyxy = (round(float(r["x"]), 2), round(float(r["y"]), 2))
        if keyxy in landmark_rooms:
            continue
        px, py = P(float(r["x"]), float(r["y"]))
        nm = str(r.get("name", ""))
        d.text((px, py), nm, font=fS, fill=TXT, anchor="mm",
               stroke_width=max(2, W // 520), stroke_fill=TXT_STROKE)

    # 5) tier / district labels
    fM = _font_bold(max(16, W // 70))
    for dd in raw.get("districts") or []:
        la = dd.get("label_anchor") or (dd.get("polygon") or [[0, 0]])[0]
        px, py = P(float(la[0]), float(la[1]))
        d.text((px, py), str(dd.get("name", "")), font=fM, fill=DIST_TXT,
               stroke_width=max(3, W // 360), stroke_fill=TXT_STROKE)

    # 6) title bar + N arrow
    ttl = title or str(raw.get("display_name", area_key))
    fT = _font_bold(max(22, W // 40))
    d.rectangle([0, 0, W, int(H * 0.055) + 10], fill=(14, 14, 18, 205))
    d.text((16, 10), f"{ttl}  —  navigation preview", font=fT, fill=(236, 232, 222))
    ax, ay = W - int(W * 0.05), int(H * 0.10)
    d.line([(ax, ay + 28), (ax, ay - 28)], fill=(236, 232, 222, 235), width=4)
    d.polygon([(ax - 9, ay - 16), (ax + 9, ay - 16), (ax, ay - 32)],
              fill=(236, 232, 222, 235))
    d.text((ax - 6, ay + 32), "N", font=fS, fill=(236, 232, 222))

    out = Image.alpha_composite(art.convert("RGBA"), ov).convert("RGB")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    print(f"  overlay -> {out_path}  ({W}x{H})")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("area_key")
    ap.add_argument("painting")
    ap.add_argument("--out", default=None)
    ap.add_argument("--root", default="static/tools/_interior_test")
    ap.add_argument("--era", default="clone_wars")
    ap.add_argument("--long", type=int, default=2048)
    ap.add_argument("--title", default=None)
    a = ap.parse_args()
    out = a.out or f"static/tools/batches/_review/{a.area_key}_nav.png"
    render(a.area_key, a.painting, out, root=a.root, era=a.era,
           long_edge=a.long, title=a.title)
