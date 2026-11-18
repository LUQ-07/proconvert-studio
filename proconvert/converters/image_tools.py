"""Images -> PDF / Word (DOCX) / PowerPoint (PPTX) / Excel table scan. Qt-free, one image per page or slide, no distortion, no silent overwrite.

* PDF is written with reportlab. JPEG files are embedded as the ORIGINAL JPEG data (no re-compression);
  every other format is embedded losslessly (Flate). Images are never stretched: the aspect ratio is always kept.
* DOCX is written with python-docx: one section (= one page) per image so each page can have its own size and
  orientation; the picture is embedded as the original JPEG/PNG bytes.
* PPTX: one slide per image on a fixed-size slide (16:9, or A4/Letter), the picture centred and never stretched.
* XLSX: the table in each picture is read with OCR (see image_table.py); experimental.
* Supported inputs: PNG, JPG/JPEG, BMP, TIFF (multi-page TIFF -> one page per frame) and WebP (first frame).
* Every limit is explicit and every failure is a ConversionError. The source files are only ever read.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ..core.context import CancelToken
from ..core.errors import (ConversionError, DependencyMissingError, InvalidFileError, InvalidOptionsError,
                           ResourceLimitError)
from ..core.security import validate_target
from ..pdftools.ops import _atomic

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
MAX_IMAGES = 300                 # files per job
MAX_PAGES = 600                  # pages per job (multi-page TIFF counts every frame)
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PIXELS = 100_000_000         # per image; larger files are refused instead of exhausting memory
MAX_TIFF_FRAMES = 200
PAGE_SIZES_PT = {"A4": (595.2756, 841.8898), "Letter": (612.0, 792.0)}   # portrait, points
FIT = "Fit"                      # page takes the size of the image
MAX_PAGE_PT = 14400.0            # PDF/Word practical maximum (200 inches)
MIN_AREA_PT = 36.0

Progress = Callable[[float, str], None]


@dataclass
class ImageLayout:
    page_size: str = "A4"            # "A4" | "Letter" | "Fit"
    orientation: str = "auto"        # "auto" (follow each image) | "portrait" | "landscape"; ignored for "Fit"
    margin_mm: float = 10.0          # 0..50
    position: str = "center"         # "center" | "top"
    allow_upscale: bool = True       # False: small images stay at their native size instead of being enlarged

    def validate(self) -> None:
        if self.page_size not in (*PAGE_SIZES_PT, FIT):
            raise InvalidOptionsError("Page size must be A4, Letter or Fit to image.")
        if self.orientation not in ("auto", "portrait", "landscape"):
            raise InvalidOptionsError("Orientation must be auto, portrait or landscape.")
        if self.position not in ("center", "top"):
            raise InvalidOptionsError("Image position must be center or top.")
        if not isinstance(self.margin_mm, (int, float)) or not 0 <= self.margin_mm <= 50:
            raise InvalidOptionsError("Margins must be between 0 and 50 mm.")


@dataclass
class ImageResult:
    output_path: Path
    pages: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Frame:
    data: bytes
    kind: str          # "jpeg" | "png"
    width_px: int
    height_px: int
    dpi: float
    name: str


# ------------------------------------------------------------------ inputs
def _pil():
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        return Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc


def check_image_file(path: str | Path) -> Path:
    """Cheap validation used by the UI when files are added (no pixel decoding)."""
    p = Path(path)
    if not p.is_file():
        raise InvalidFileError(f"'{p.name}' was not found.")
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InvalidFileError(f"'{p.name}' is not a supported image type (PNG, JPG, BMP, TIFF, WebP).")
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise InvalidFileError(f"'{p.name}' cannot be read.", technical=str(exc)) from exc
    if size == 0:
        raise InvalidFileError(f"'{p.name}' is empty.")
    if size > MAX_FILE_BYTES:
        raise ResourceLimitError(f"'{p.name}' is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return p


def image_info(path: str | Path) -> dict:
    """Size/format for the preview list. Decodes only the header."""
    Image, _, Unidentified = _pil()
    p = check_image_file(path)
    try:
        with Image.open(p) as im:
            frames = getattr(im, "n_frames", 1) if im.format == "TIFF" else 1
            return {"width": im.width, "height": im.height, "format": im.format, "frames": frames}
    except (Unidentified, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise InvalidFileError(f"'{p.name}' is not a readable image.", technical=f"{type(exc).__name__}: {exc}") from exc


def make_thumbnail(path: str | Path, max_px: int = 160) -> bytes:
    """PNG bytes of a small preview (EXIF rotation applied). Never modifies the source."""
    Image, ImageOps, Unidentified = _pil()
    p = check_image_file(path)
    if not 16 <= max_px <= 1024:
        raise InvalidOptionsError("Thumbnail size must be between 16 and 1024 pixels.")
    try:
        with Image.open(p) as im:
            im.draft("RGB", (max_px * 2, max_px * 2))      # fast JPEG downscale; ignored by other formats
            im = ImageOps.exif_transpose(im)
            im.thumbnail((max_px, max_px))
            im = _flatten(im, Image)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()
    except (Unidentified, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise InvalidFileError(f"'{p.name}' is not a readable image.", technical=f"{type(exc).__name__}: {exc}") from exc


def _flatten(im, Image):
    """Bring any mode to RGB or L. Transparency is composited on white (document pages are white)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    if im.mode in ("I;16", "I;16L", "I;16B", "I"):
        return im.point(lambda v: v / 256).convert("L")
    if im.mode in ("RGB", "L"):
        return im
    return im.convert("RGB")


def _dpi_of(im) -> float:
    try:
        d = im.info.get("dpi")
        val = float(d[0]) if d else 0.0
    except (TypeError, ValueError, IndexError):
        val = 0.0
    return val if 36 <= val <= 1200 else 96.0


def _load_frames(path: Path, warnings: list[str]) -> list[_Frame]:
    Image, ImageOps, Unidentified = _pil()
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    check_image_file(path)
    frames: list[_Frame] = []
    try:
        with Image.open(path) as im:
            fmt = im.format
            n = min(getattr(im, "n_frames", 1), MAX_TIFF_FRAMES) if fmt == "TIFF" else 1
            if fmt == "TIFF" and getattr(im, "n_frames", 1) > MAX_TIFF_FRAMES:
                warnings.append(f"'{path.name}': only the first {MAX_TIFF_FRAMES} TIFF pages were used.")
            for i in range(n):
                if fmt == "TIFF":
                    im.seek(i)
                if im.width * im.height > MAX_PIXELS:
                    raise ResourceLimitError(f"'{path.name}' is larger than {MAX_PIXELS // 1_000_000} megapixels.")
                if im.width < 1 or im.height < 1:
                    raise InvalidFileError(f"'{path.name}' has no image data.")
                im.load()
                oriented = ImageOps.exif_transpose(im)
                rotated = _exif_rotated(im)
                dpi = _dpi_of(im)
                label = path.name if n == 1 else f"{path.name} (page {i + 1})"
                if fmt == "JPEG" and not rotated and im.mode in ("RGB", "L"):
                    data = path.read_bytes()                      # original JPEG, byte for byte
                    frames.append(_Frame(data, "jpeg", im.width, im.height, dpi, label))
                    continue
                flat = _flatten(oriented, Image)
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    warnings.append(f"'{label}': transparency was replaced by a white background.")
                buf = io.BytesIO()
                if fmt == "JPEG":                                  # EXIF-rotated or CMYK JPEG must be re-encoded
                    flat.save(buf, "JPEG", quality=95, subsampling=0, dpi=(dpi, dpi))
                    kind = "jpeg"
                    warnings.append(f"'{label}': re-encoded as high-quality JPEG (rotation/colour fix).")
                else:
                    flat.save(buf, "PNG")                          # lossless
                    kind = "png"
                frames.append(_Frame(buf.getvalue(), kind, flat.width, flat.height, dpi, label))
    except ConversionError:
        raise
    except (Unidentified, OSError, Image.DecompressionBombError, ValueError, EOFError, SyntaxError) as exc:
        raise InvalidFileError(f"'{path.name}' is not a readable image.", technical=f"{type(exc).__name__}: {exc}") from exc
    return frames


def _exif_rotated(im) -> bool:
    try:
        return int(im.getexif().get(0x0112, 1)) not in (0, 1)
    except Exception:
        return False


# ------------------------------------------------------------------ layout maths
def place(frame_w_px: int, frame_h_px: int, dpi: float, layout: ImageLayout) -> tuple[float, float, float, float, float, float]:
    """Return (page_w, page_h, x, y_top, w, h) in points. The image keeps its aspect ratio (no distortion)."""
    layout.validate()
    margin = layout.margin_mm * 72.0 / 25.4
    nat_w, nat_h = frame_w_px * 72.0 / dpi, frame_h_px * 72.0 / dpi        # native size at the image's own dpi
    if layout.page_size == FIT:
        pw, ph = nat_w + 2 * margin, nat_h + 2 * margin
        big = max(pw, ph)
        if big > MAX_PAGE_PT:
            k = MAX_PAGE_PT / big
            pw, ph = pw * k, ph * k
        scale = (pw - 2 * margin) / nat_w
        w, h = nat_w * scale, nat_h * scale
        return pw, ph, margin, margin, w, h
    base_w, base_h = PAGE_SIZES_PT[layout.page_size]
    landscape = (frame_w_px > frame_h_px) if layout.orientation == "auto" else layout.orientation == "landscape"
    pw, ph = (max(base_w, base_h), min(base_w, base_h)) if landscape else (min(base_w, base_h), max(base_w, base_h))
    x, y, w, h = fit_rect(pw, ph, nat_w, nat_h, layout)
    return pw, ph, x, y, w, h


def fit_rect(pw: float, ph: float, nat_w: float, nat_h: float, layout: ImageLayout) -> tuple[float, float, float, float]:
    """Place a picture of native size nat_w x nat_h (points) inside a pw x ph page: (x, y_top, w, h), aspect kept."""
    margin = layout.margin_mm * 72.0 / 25.4
    area_w, area_h = pw - 2 * margin, ph - 2 * margin
    if area_w < MIN_AREA_PT or area_h < MIN_AREA_PT:
        raise InvalidOptionsError("The margins are too large for this page size.")
    scale = min(area_w / nat_w, area_h / nat_h)
    if not layout.allow_upscale:
        scale = min(scale, 1.0)
    w, h = nat_w * scale, nat_h * scale
    x = margin + (area_w - w) / 2
    y = margin + ((area_h - h) / 2 if layout.position == "center" else 0.0)
    return x, y, w, h


# ------------------------------------------------------------------ writers
def _write_pdf(frames: list[_Frame], layout: ImageLayout, tmp: Path, step: Callable[[int], None]) -> None:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(tmp), pageCompression=1)
    c.setTitle("Images")
    c.setCreator("ProConvert Studio")
    for i, fr in enumerate(frames):
        pw, ph, x, y_top, w, h = place(fr.width_px, fr.height_px, fr.dpi, layout)
        c.setPageSize((pw, ph))
        c.drawImage(ImageReader(io.BytesIO(fr.data)), x, ph - y_top - h, width=w, height=h)
        c.showPage()
        step(i)
    c.save()


def _write_docx(frames: list[_Frame], layout: ImageLayout, tmp: Path, step: Callable[[int], None]) -> None:
    try:
        from docx import Document
        from docx.enum.section import WD_ORIENT, WD_SECTION
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc
    doc = Document()
    doc.core_properties.author = "ProConvert Studio"
    doc.core_properties.title = "Images"
    margin_pt = layout.margin_mm * 72.0 / 25.4
    for i, fr in enumerate(frames):
        pw, ph, x, y_top, w, h = place(fr.width_px, fr.height_px, fr.dpi, layout)
        sec = doc.sections[0] if i == 0 else doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.LANDSCAPE if pw > ph else WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = Pt(pw), Pt(ph)
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Pt(margin_pt)
        sec.header_distance = sec.footer_distance = Pt(min(margin_pt / 2, 18))
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = para.paragraph_format
        # Vertical centring through space-before (honoured by Word AND LibreOffice, unlike section vAlign).
        pf.space_before = Pt(max(0.0, y_top - margin_pt))
        pf.space_after = Pt(0)
        pf.line_spacing = 1.0
        # 1 % safety so the picture's line never overflows its page because of rounding
        para.add_run().add_picture(io.BytesIO(fr.data), width=Pt(w * 0.99), height=Pt(h * 0.99))
        step(i)
    doc.save(str(tmp))


SLIDE_16_9_PT = (960.0, 540.0)      # 13.333 x 7.5 in, the PowerPoint widescreen default


def slide_size(layout: ImageLayout) -> tuple[float, float]:
    """One size for the whole deck: widescreen for "Fit", otherwise A4/Letter (landscape unless portrait is chosen)."""
    if layout.page_size == FIT:
        return SLIDE_16_9_PT
    base_w, base_h = PAGE_SIZES_PT[layout.page_size]
    if layout.orientation == "portrait":
        return min(base_w, base_h), max(base_w, base_h)
    return max(base_w, base_h), min(base_w, base_h)


def _write_pptx(frames: list[_Frame], layout: ImageLayout, tmp: Path, step: Callable[[int], None]) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc
    pw, ph = slide_size(layout)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(round(pw * 12700)), Emu(round(ph * 12700))
    prs.core_properties.author = "ProConvert Studio"
    prs.core_properties.title = "Images"
    blank = prs.slide_layouts[6]
    for i, fr in enumerate(frames):
        nat_w, nat_h = fr.width_px * 72.0 / fr.dpi, fr.height_px * 72.0 / fr.dpi
        x, y, w, h = fit_rect(pw, ph, nat_w, nat_h, layout)
        slide = prs.slides.add_slide(blank)
        pic = slide.shapes.add_picture(io.BytesIO(fr.data), Emu(round(x * 12700)), Emu(round(y * 12700)), Emu(round(w * 12700)), Emu(round(h * 12700)))
        pic._element.nvPicPr.cNvPr.set("descr", fr.name)           # alternative text for screen readers
        step(i)
    prs.save(str(tmp))


def _verify(fmt: str, tmp: Path, expected_pages: int) -> None:
    """Re-open the finished file and check it really contains every page/picture."""
    try:
        if fmt == "pdf":
            import pypdf
            r = pypdf.PdfReader(str(tmp))
            pages = len(r.pages)
            images = sum(len(p.images) for p in r.pages)
        elif fmt == "pptx":
            from pptx import Presentation
            prs = Presentation(str(tmp))
            pages = len(prs.slides)
            images = sum(1 for sl in prs.slides for sh in sl.shapes if sh.shape_type == 13)
        else:
            from docx import Document
            d = Document(str(tmp))
            pages, images = len(d.sections), len(d.inline_shapes)
    except Exception as exc:
        raise ConversionError("The result could not be verified and was discarded.", technical=f"{type(exc).__name__}: {exc}") from exc
    if pages != expected_pages or images != expected_pages:
        raise ConversionError("The result is incomplete and was discarded.",
                              technical=f"expected {expected_pages} pages/images, got {pages}/{images}")


# ------------------------------------------------------------------ public API
def convert_images(images: Sequence[str | Path], out: str | Path, fmt: str = "pdf", layout: ImageLayout | None = None, *,
                   overwrite: bool = False, cancel: CancelToken | None = None, progress: Progress | None = None,
                   language: str = "eng") -> ImageResult:
    """Embed *images* (in the given order) into one PDF or DOCX. Sources are never modified; *out* is never
    overwritten unless ``overwrite`` is True; a cancelled or failed job leaves no partial file behind."""
    if fmt not in ("pdf", "docx", "pptx", "xlsx"):
        raise InvalidOptionsError("The output format must be PDF, Word (DOCX), PowerPoint (PPTX) or Excel (XLSX).")
    layout = layout or ImageLayout()
    layout.validate()
    if fmt == "xlsx":                                  # tables are read from the pictures; page options do not apply
        from .image_table import convert_images_to_xlsx
        return convert_images_to_xlsx(images, out, language, overwrite=overwrite, cancel=cancel, progress=progress)
    if not images:
        raise InvalidOptionsError("Add at least one image.")
    if len(images) > MAX_IMAGES:
        raise InvalidOptionsError(f"At most {MAX_IMAGES} images can be converted at once.")
    paths = [check_image_file(p) for p in images]
    target = validate_target(out, None, fmt, overwrite=overwrite)
    for p in paths:
        if p.resolve() == target:
            raise InvalidOptionsError("The output file must be different from the source images.")
    token = cancel or CancelToken()
    warnings: list[str] = []

    def report(frac: float, text: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)), text)

    frames: list[_Frame] = []
    for i, p in enumerate(paths):
        token.check()
        report(0.05 + 0.5 * i / len(paths), p.name)
        frames.extend(_load_frames(p, warnings))
        if len(frames) > MAX_PAGES:
            raise ResourceLimitError(f"The images contain more than {MAX_PAGES} pages in total.")
    for fr in frames:                                           # fail early on bad margins for any frame
        place(fr.width_px, fr.height_px, fr.dpi, layout)

    def step(i: int) -> None:
        token.check()
        report(0.55 + 0.35 * (i + 1) / len(frames), f"{i + 1}/{len(frames)}")

    with _atomic(target) as tmp:
        {"pdf": _write_pdf, "docx": _write_docx, "pptx": _write_pptx}[fmt](frames, layout, tmp, step)
        report(0.92, "verifying")
        _verify(fmt, tmp, len(frames))
    report(1.0, "done")
    return ImageResult(target, len(frames), warnings)
