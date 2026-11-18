"""Generate the MSIX / Microsoft Store tile images from proconvert/assets/icon.png (Pillow only).

Usage: python tools/make_store_assets.py
Writes packaging/windows/msix/Assets/*.png. Replace them with designer-made art before submission if you want
a custom look; the sizes below are what the manifest references.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "proconvert" / "assets" / "icon.png"
OUT = ROOT / "packaging" / "windows" / "msix" / "Assets"
# name -> (width, height); the icon is centred on a transparent canvas for non-square tiles
TILES = {
    "StoreLogo.png": (50, 50), "Square44x44Logo.png": (44, 44), "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150), "Square310x310Logo.png": (310, 310), "SmallTile.png": (71, 71),
    "Square44x44Logo.targetsize-24_altform-unplated.png": (24, 24), "Square44x44Logo.targetsize-48_altform-unplated.png": (48, 48),
    "Square44x44Logo.targetsize-256_altform-unplated.png": (256, 256),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(SRC).convert("RGBA")
    for name, (w, h) in TILES.items():
        side = int(min(w, h) * 0.8) if (w, h) != (50, 50) else 50
        icon = src.resize((side, side), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(icon, ((w - side) // 2, (h - side) // 2), icon)
        canvas.save(OUT / name)
    print(f"wrote {len(TILES)} images to {OUT}")


if __name__ == "__main__":
    main()
