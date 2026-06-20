#!/usr/bin/env python3
"""tools/_grid_probe.py — draw the room-coordinate grid + current labels over a
painted interior substrate so I (Opus) can SEE which painted space each room's
coordinate currently lands on, and reason about correct placement.

Same north-up projector as make_interior_overlay / the live registration:
    fx = (wx - x_min)/dx ;  fy = (y_max - wy)/dy

Usage: python tools/_grid_probe.py <live-map-yaml> <substrate.png> <out.png>
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml
from PIL import Image, ImageDraw, ImageFont


def _font(sz, bold=False):
    cands = ([r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
             if bold else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"])
    for c in cands:
        try:
            return ImageFont.truetype(c, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    yp, sub, out = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = yaml.safe_load(Path(yp).read_text(encoding="utf-8"))
    b = raw["bounds"]
    x0, y0 = float(b.get("x_min", 0)), float(b.get("y_min", 0))
    x1, y1 = float(b["x_max"]), float(b["y_max"])
    dx, dy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    long_edge = 1100
    aspect = dx / dy
    if aspect >= 1.0:
        W, H = long_edge, round(long_edge / aspect)
    else:
        H, W = long_edge, round(long_edge * aspect)

    def P(wx, wy):
        return ((wx - x0) / dx * W, (y1 - wy) / dy * H)

    art = Image.open(sub).convert("RGB").resize((W, H), Image.LANCZOS)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fS = _font(max(13, W // 60))
    fB = _font(max(15, W // 52), bold=True)

    # faint world gridlines every 0.6 units
    step = 0.6
    n = 0.0
    while n <= x1 + 0.001:
        px, _ = P(n, y0)
        d.line([(px, 0), (px, H)], fill=(255, 255, 255, 40), width=1)
        n += step
    n = 0.0
    while n <= y1 + 0.001:
        _, py = P(x0, n)
        d.line([(0, py), (W, py)], fill=(255, 255, 255, 40), width=1)
        n += step

    # each room: dot + "(x,y) Name"
    for r in raw.get("rooms") or []:
        rx, ry = float(r["x"]), float(r["y"])
        px, py = P(rx, ry)
        rr = max(5, W // 130)
        d.ellipse([px - rr, py - rr, px + rr, py + rr],
                  fill=(255, 90, 70, 255), outline=(20, 18, 14, 255), width=2)
        label = f"({rx:.1f},{ry:.1f}) {r.get('name','')}"
        d.text((px + rr + 3, py - fS.size // 2), label, font=fS, fill=(255, 255, 255),
               stroke_width=3, stroke_fill=(10, 10, 14))

    out_img = Image.alpha_composite(art.convert("RGBA"), ov).convert("RGB")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    out_img.save(out)
    print(f"grid probe -> {out} ({W}x{H})")


if __name__ == "__main__":
    main()
