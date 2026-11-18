"""Generate the ProConvert Studio app icon (PNG, ICO, SVG) with Pillow + numpy. Original artwork, no third-party assets.

Design: deep-indigo to violet rounded square; two overlapping document sheets (the front one with a folded corner and
text lines); a teal circular badge with two opposing arrows (= conversion) in the lower right corner.
Run:  python tools/make_icons.py   (then python tools/make_store_assets.py for the Microsoft Store tiles)
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "proconvert" / "assets"
S = 2048  # supersample, downscaled for crisp edges


def f(x: float) -> int:
    return int(round(x * S))


def diagonal_gradient(c0, c1) -> Image.Image:
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    t = (x + y) / (2 * (S - 1))
    arr = np.empty((S, S, 3), dtype=np.float32)
    for i in range(3):
        arr[..., i] = c0[i] + (c1[i] - c0[i]) * t
    # soft light from the top-left corner
    d = np.sqrt((x - S * 0.15) ** 2 + (y - S * 0.05) ** 2) / (S * 0.9)
    glow = np.clip(1.0 - d, 0, 1) ** 2 * 38
    arr += glow[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def shadow(shape: Image.Image, offset=(0, 0.012), blur=0.02, alpha=90) -> Image.Image:
    a = shape.getchannel("A").point(lambda v: v * alpha // 255)
    sh = Image.new("RGBA", shape.size, (10, 8, 60, 0))
    sh.putalpha(a)
    sh = ImageChops.offset(sh, f(offset[0]), f(offset[1]))
    return sh.filter(ImageFilter.GaussianBlur(f(blur)))


def sheet(w: float, h: float, fold: float, body, foldc, lines=None) -> Image.Image:
    """A page with a folded top-right corner, drawn on its own transparent layer (centred)."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = f(0.5 - w / 2), f(0.5 - h / 2), f(0.5 + w / 2), f(0.5 + h / 2)
    r, fd = f(0.03), f(fold)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=body)
    # cut the corner, then paint the fold
    cut = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cut).polygon([(x1 - fd, y0 - 2), (x1 + 2, y0 - 2), (x1 + 2, y0 + fd)], fill=255)
    layer.paste((0, 0, 0, 0), (0, 0), cut)
    d.polygon([(x1 - fd, y0), (x1 - fd, y0 + fd - r // 2), (x1 - r // 2, y0 + fd)], fill=foldc)
    d.rounded_rectangle([x1 - fd, y0 + fd - r, x1, y0 + fd], radius=r // 2, fill=foldc) if False else None
    if lines:
        lh, lx = f(0.026), x0 + f(0.045)
        for i, frac in enumerate(lines):
            ly = y0 + f(0.115) + i * f(0.062)
            d.rounded_rectangle([lx, ly, lx + int((x1 - x0 - f(0.09)) * frac), ly + lh], radius=lh // 2, fill=(74, 85, 201, 255))
    return layer


def arc_arrow(d: ImageDraw.ImageDraw, c, r, a0, a1, width, fill) -> None:
    """Clockwise arc from a0 to a1 degrees (PIL convention) with an arrow head at the end."""
    cx, cy = c
    d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1 - 9, fill=fill, width=width)
    for ang in (a0,):
        x, y = cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)      # round start cap
    th = math.radians(a1)
    px, py = cx + r * math.cos(th), cy + r * math.sin(th)
    tx, ty = -math.sin(th), math.cos(th)            # tangent (direction of travel)
    nx, ny = math.cos(th), math.sin(th)             # normal (radial)
    hl, hw = width * 1.7, width * 1.45
    d.polygon([(px + tx * hl, py + ty * hl), (px + nx * hw, py + ny * hw), (px - nx * hw, py - ny * hw)], fill=fill)


def render() -> Image.Image:
    base = diagonal_gradient((38, 40, 140), (128, 92, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=f(0.225), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    # --- back sheet (tilted, translucent) and front sheet
    back = sheet(0.33, 0.45, 0.085, (214, 222, 255, 235), (170, 182, 240, 255))
    back = back.rotate(9, resample=Image.BICUBIC, center=(S // 2, S // 2))
    back = ImageChops.offset(back, -f(0.095), -f(0.005))
    front = sheet(0.36, 0.50, 0.095, (255, 255, 255, 255), (205, 214, 250, 255), lines=(0.92, 0.92, 0.92, 0.55))
    front = ImageChops.offset(front, -f(0.025), f(0.025))
    for layer in (back, front):
        icon = Image.alpha_composite(icon, shadow(layer, blur=0.018, alpha=80))
        icon = Image.alpha_composite(icon, layer)

    # --- conversion badge (lower right)
    bx, by, br = f(0.675), f(0.70), f(0.215)
    badge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gb = diagonal_gradient((22, 205, 170), (30, 150, 235)).crop((0, 0, S, S))
    circ = Image.new("L", (S, S), 0)
    ImageDraw.Draw(circ).ellipse([bx - br, by - br, bx + br, by + br], fill=255)
    badge.paste(gb, (0, 0), circ)
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([bx - br, by - br, bx + br, by + br], outline=(255, 255, 255, 255), width=f(0.014))
    badge = Image.alpha_composite(badge, ring)
    d = ImageDraw.Draw(badge)
    w = f(0.040)
    arc_arrow(d, (bx, by), int(br * 0.52), 200, 325, w, (255, 255, 255, 255))
    arc_arrow(d, (bx, by), int(br * 0.52), 20, 145, w, (255, 255, 255, 255))
    icon = Image.alpha_composite(icon, shadow(badge, offset=(0, 0.014), blur=0.022, alpha=110))
    icon = Image.alpha_composite(icon, badge)

    # keep everything inside the rounded square
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(icon, (0, 0), mask)
    return out


def svg() -> str:
    """The same artwork as scalable vector graphics (1024 x 1024), kept in sync by hand with render()."""
    k = 1024.0

    def page(w, h, fold, body, foldc, lines=None, extra=""):
        x0, y0, x1, y1 = (0.5 - w / 2) * k, (0.5 - h / 2) * k, (0.5 + w / 2) * k, (0.5 + h / 2) * k
        r, fd = 0.03 * k, fold * k
        path = (f"M{x0 + r:.1f} {y0:.1f}H{x1 - fd:.1f}L{x1:.1f} {y0 + fd:.1f}V{y1 - r:.1f}Q{x1:.1f} {y1:.1f} {x1 - r:.1f} {y1:.1f}"
                f"H{x0 + r:.1f}Q{x0:.1f} {y1:.1f} {x0:.1f} {y1 - r:.1f}V{y0 + r:.1f}Q{x0:.1f} {y0:.1f} {x0 + r:.1f} {y0:.1f}Z")
        out = f'<path d="{path}" fill="{body}"/><path d="M{x1 - fd:.1f} {y0:.1f}V{y0 + fd:.1f}H{x1:.1f}Z" fill="{foldc}"/>'
        for i, frac in enumerate(lines or []):
            ly = y0 + 0.115 * k + i * 0.062 * k
            out += f'<rect x="{x0 + 0.045 * k:.1f}" y="{ly:.1f}" width="{(x1 - x0 - 0.09 * k) * frac:.1f}" height="{0.026 * k:.1f}" rx="{0.013 * k:.1f}" fill="#4A55C9"/>'
        return out

    bx, by, br = 0.675 * k, 0.70 * k, 0.215 * k
    rr, sw = br * 0.52, 0.040 * k

    def arc(a0, a1):
        p0 = (bx + rr * math.cos(math.radians(a0)), by + rr * math.sin(math.radians(a0)))
        pe = (bx + rr * math.cos(math.radians(a1 - 9)), by + rr * math.sin(math.radians(a1 - 9)))
        th = math.radians(a1)
        px, py = bx + rr * math.cos(th), by + rr * math.sin(th)
        tx, ty, nx, ny = -math.sin(th), math.cos(th), math.cos(th), math.sin(th)
        hl, hw = sw * 1.7, sw * 1.45
        head = f"{px + tx * hl:.1f},{py + ty * hl:.1f} {px + nx * hw:.1f},{py + ny * hw:.1f} {px - nx * hw:.1f},{py - ny * hw:.1f}"
        return (f'<path d="M{p0[0]:.1f} {p0[1]:.1f}A{rr:.1f} {rr:.1f} 0 0 1 {pe[0]:.1f} {pe[1]:.1f}" fill="none" stroke="#fff" '
                f'stroke-width="{sw:.1f}" stroke-linecap="round"/><polygon points="{head}" fill="#fff"/>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="ProConvert Studio">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#262890"/><stop offset="1" stop-color="#805CFF"/></linearGradient>
    <linearGradient id="bd" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#16CDAA"/><stop offset="1" stop-color="#1E96EB"/></linearGradient>
    <filter id="sh" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#0A083C" flood-opacity=".35"/></filter>
    <clipPath id="clip"><rect width="1024" height="1024" rx="230"/></clipPath>
  </defs>
  <g clip-path="url(#clip)">
    <rect width="1024" height="1024" fill="url(#bg)"/>
    <g filter="url(#sh)" transform="translate(-97.3 -5.1) rotate(-9 512 512)">{page(0.33, 0.45, 0.085, "#D6DEFF", "#AAB6F0")}</g>
    <g filter="url(#sh)" transform="translate(-25.6 25.6)">{page(0.36, 0.50, 0.095, "#FFFFFF", "#CDD6FA", lines=(0.92, 0.92, 0.92, 0.55))}</g>
    <g filter="url(#sh)"><circle cx="{bx:.1f}" cy="{by:.1f}" r="{br:.1f}" fill="url(#bd)" stroke="#fff" stroke-width="{0.014 * k:.1f}"/></g>
    {arc(200, 325)}
    {arc(20, 145)}
  </g>
</svg>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(svg(), encoding="utf-8")
    big = render()
    big.resize((1024, 1024), Image.LANCZOS).save(OUT / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon_256.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico", sizes=sizes)
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
