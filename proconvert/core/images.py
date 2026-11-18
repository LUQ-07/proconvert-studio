"""Safe image decoding and normalisation into IR pictures."""
from __future__ import annotations

import io
import warnings

from .context import JobContext
from .ir import Picture


def normalize_image(data: bytes, ctx: JobContext, *, min_edge: int = 1,
                    display_w_pt: float | None = None, display_h_pt: float | None = None) -> Picture | None:
    """Decode ``data`` defensively and return a PNG/JPEG picture, or ``None`` if unusable.

    Applies the pixel limit (decompression-bomb guard), the quality preset (downscaling /
    JPEG quality) and the per-job total image budget.
    """
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = ctx.limits.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            src_fmt = (img.format or "").upper()
            img.load()
    except Exception:
        ctx.warn("One or more images could not be decoded and were skipped.")
        return None

    w, h = img.size
    if min(w, h) < min_edge:
        return None

    max_px = ctx.options.image_max_px
    resized = False
    if max_px and max(w, h) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        resized = True
        w, h = img.size

    try:
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        if src_fmt == "JPEG" and not has_alpha:
            if not resized and img.mode in ("RGB", "L"):
                out, fmt = data, "jpeg"
            else:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=ctx.options.jpeg_quality, optimize=True)
                out, fmt = buf.getvalue(), "jpeg"
        else:
            if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
                img = img.convert("RGBA" if has_alpha else "RGB")
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=False)
            out, fmt = buf.getvalue(), "png"
    except Exception:
        ctx.warn("One or more images could not be converted and were skipped.")
        return None

    ctx.image_bytes += len(out)
    if ctx.image_bytes > ctx.limits.max_total_image_bytes:
        ctx.warn("The total size of embedded images exceeded the safety budget; remaining images were skipped.")
        return None
    return Picture(out, fmt, w, h, display_w_pt, display_h_pt)
