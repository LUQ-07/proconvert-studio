"""PDF operations built on pypdf (BSD), reportlab (BSD), Pillow (HPND) and optionally pypdfium2.

Rules shared by every operation: the source is never modified; the output path is validated
(`validate_target`: never the source, never overwritten without consent); output is written to a
temporary file next to the target and moved into place atomically; every failure is a ConversionError.
"""
from __future__ import annotations

import io
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..core.errors import (ConversionError, DependencyMissingError, InvalidFileError, InvalidOptionsError,
                           OutputPathError, PasswordProtectedError)
from ..core.security import validate_target
from ..utils.ranges import parse_page_ranges

__all__ = ["pdf_info", "merge_pdfs", "split_pdf", "extract_pages", "delete_pages", "reorder_pages", "rotate_pages",
           "duplicate_pages", "add_watermark", "add_page_numbers", "set_metadata", "protect_pdf", "unprotect_pdf",
           "compress_pdf", "images_to_pdf", "pdf_to_images"]

Progress = Callable[[float, str], None]
MAX_PAGES = 5000
MAX_MERGE_INPUTS = 200
_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"


# ------------------------------------------------------------------ helpers
def _pypdf():
    try:
        import pypdf
        return pypdf
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc


def _open(path: str | Path, password: str | None = None):
    """Open and sanity-check a PDF; returns a pypdf PdfReader (decrypted when a password is given)."""
    pypdf = _pypdf()
    p = Path(path)
    if not p.is_file():
        raise InvalidFileError(f"'{p.name}' was not found.")
    if p.suffix.lower() != ".pdf":
        raise InvalidFileError(f"'{p.name}' is not a PDF file.")
    try:
        with p.open("rb") as fh:
            head = fh.read(1024)
    except OSError as exc:
        raise InvalidFileError(f"'{p.name}' cannot be read.", technical=str(exc)) from exc
    if b"%PDF-" not in head:
        raise InvalidFileError(f"'{p.name}' is not a valid PDF (missing PDF header).")
    try:
        reader = pypdf.PdfReader(str(p), strict=False)
        if reader.is_encrypted:
            if not password:
                raise PasswordProtectedError(f"'{p.name}' is password protected.")
            if not reader.decrypt(password):
                raise PasswordProtectedError("The password is not correct.")
        n = len(reader.pages)
    except ConversionError:
        raise
    except Exception as exc:
        raise InvalidFileError(f"'{p.name}' is damaged or uses an unsupported structure.",
                               technical=f"{type(exc).__name__}: {exc}") from exc
    if n == 0:
        raise InvalidFileError(f"'{p.name}' has no pages.")
    if n > MAX_PAGES:
        raise InvalidOptionsError(f"'{p.name}' has {n:,} pages; the limit is {MAX_PAGES:,}.")
    return reader


@contextmanager
def _atomic(target: Path):
    """Yield a temp path beside *target*; move into place only if the block succeeds."""
    fd, tmp = tempfile.mkstemp(prefix=".pdftool-", suffix=".part", dir=str(target.parent))
    os.close(fd)
    tmp_p = Path(tmp)
    try:
        yield tmp_p
        os.replace(tmp_p, target)
    finally:
        tmp_p.unlink(missing_ok=True)


def _target(out: str | Path, src: Path | None, overwrite: bool) -> Path:
    return validate_target(out, src, "pdf", overwrite=overwrite)


def _save(writer, target: Path) -> None:
    with _atomic(target) as tmp:
        try:
            with tmp.open("wb") as fh:
                writer.write(fh)
        except OSError as exc:
            raise OutputPathError("The output file could not be written.", technical=str(exc)) from exc


def _pages(spec: str | Sequence[int] | None, total: int) -> list[int]:
    """Zero-based indexes from a range string ('1-3,7') or a list of 1-based numbers (order kept)."""
    if spec is None or isinstance(spec, str):
        return parse_page_ranges(spec or "", total)
    out = []
    for n in spec:
        if not isinstance(n, int) or not 1 <= n <= total:
            raise InvalidOptionsError(f"Page {n} does not exist; the document has {total} page(s).")
        out.append(n - 1)
    return out


def _report(progress: Progress | None, frac: float, msg: str) -> None:
    if progress:
        progress(frac, msg)


def _new_writer(reader=None):
    pypdf = _pypdf()
    w = pypdf.PdfWriter(clone_from=reader) if reader is not None else pypdf.PdfWriter()
    return w


# ------------------------------------------------------------------ info
def pdf_info(path: str | Path, password: str | None = None) -> dict:
    reader = _open(path, password)
    meta = reader.metadata or {}
    first = reader.pages[0].mediabox
    return {
        "pages": len(reader.pages),
        "title": str(meta.get("/Title", "") or ""), "author": str(meta.get("/Author", "") or ""),
        "subject": str(meta.get("/Subject", "") or ""), "keywords": str(meta.get("/Keywords", "") or ""),
        "creator": str(meta.get("/Creator", "") or ""), "producer": str(meta.get("/Producer", "") or ""),
        "page1_size_pt": (float(first.width), float(first.height)),
        "encrypted": bool(reader.is_encrypted), "size_bytes": Path(path).stat().st_size,
    }


# ------------------------------------------------------------------ page operations
def merge_pdfs(inputs: Sequence[str | Path], out: str | Path, *, overwrite: bool = False,
               passwords: dict[str, str] | None = None, progress: Progress | None = None) -> Path:
    if len(inputs) < 2:
        raise InvalidOptionsError("Choose at least two PDF files to merge.")
    if len(inputs) > MAX_MERGE_INPUTS:
        raise InvalidOptionsError(f"At most {MAX_MERGE_INPUTS} files can be merged at once.")
    target = _target(out, None, overwrite)
    for i in inputs:
        if Path(i).resolve() == target:
            raise OutputPathError("The output file must be different from the source files.")
    w, total = _new_writer(), 0
    for k, src in enumerate(inputs):
        _report(progress, k / len(inputs), f"Adding {Path(src).name}")
        reader = _open(src, (passwords or {}).get(str(src)))
        total += len(reader.pages)
        if total > MAX_PAGES:
            raise InvalidOptionsError(f"The merged document would exceed {MAX_PAGES:,} pages.")
        w.append(reader)
    _save(w, target)
    _report(progress, 1.0, "Done")
    return target


def _select(src, out, spec, overwrite, password, *, keep: bool) -> Path:
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    chosen = set(_pages(spec if isinstance(spec, str) else None, len(reader.pages)))
    if not keep:
        chosen = set(range(len(reader.pages))) - chosen
    if not chosen:
        raise InvalidOptionsError("That selection would leave a PDF with no pages.")
    w = _new_writer()
    for i in sorted(chosen):
        w.add_page(reader.pages[i])
    _save(w, target)
    return target


def extract_pages(src, out, pages: str, *, overwrite=False, password=None) -> Path:
    if not (pages or "").strip():
        raise InvalidOptionsError("Enter the pages to extract, for example 1-3,7.")
    return _select(src, out, pages, overwrite, password, keep=True)


def delete_pages(src, out, pages: str, *, overwrite=False, password=None) -> Path:
    if not (pages or "").strip():
        raise InvalidOptionsError("Enter the pages to delete, for example 2,5-6.")
    return _select(src, out, pages, overwrite, password, keep=False)


def reorder_pages(src, out, order: Sequence[int], *, overwrite=False, password=None) -> Path:
    """*order* lists 1-based page numbers in their new order; pages left out are dropped, repeats are allowed."""
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    idx = _pages(list(order), len(reader.pages))
    if not idx:
        raise InvalidOptionsError("The new page order is empty.")
    w = _new_writer()
    for i in idx:
        w.add_page(reader.pages[i])
    _save(w, target)
    return target


def duplicate_pages(src, out, pages: str, *, overwrite=False, password=None) -> Path:
    """Insert a copy of each chosen page directly after the original."""
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    chosen = set(_pages(pages, len(reader.pages)))
    if not (pages or "").strip():
        raise InvalidOptionsError("Enter the pages to duplicate.")
    w = _new_writer()
    for i, page in enumerate(reader.pages):
        w.add_page(page)
        if i in chosen:
            w.add_page(page)
    if len(w.pages) > MAX_PAGES:
        raise InvalidOptionsError(f"The result would exceed {MAX_PAGES:,} pages.")
    _save(w, target)
    return target


def rotate_pages(src, out, degrees: int, pages: str = "", *, overwrite=False, password=None) -> Path:
    if degrees not in (90, 180, 270, -90, -180, -270):
        raise InvalidOptionsError("Rotation must be 90, 180 or 270 degrees.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    chosen = set(_pages(pages, len(reader.pages)))
    w = _new_writer()
    for i, page in enumerate(reader.pages):
        if i in chosen:
            page.rotate(degrees % 360)
        w.add_page(page)
    _save(w, target)
    return target


def split_pdf(src, out_dir: str | Path, *, every: int = 1, ranges: Sequence[str] | None = None,
              overwrite=False, password=None, progress: Progress | None = None) -> list[Path]:
    """Split into files of *every* pages, or one file per entry of *ranges* (e.g. ["1-3", "4-"])."""
    reader = _open(src, password)
    d = Path(out_dir)
    if not d.is_dir():
        raise OutputPathError("The output folder does not exist.")
    total = len(reader.pages)
    if ranges:
        groups = [_pages(r, total) for r in ranges]
    else:
        if every < 1:
            raise InvalidOptionsError("Pages per file must be at least 1.")
        groups = [list(range(s, min(s + every, total))) for s in range(0, total, every)]
    if len(groups) > 1000:
        raise InvalidOptionsError("That split would create more than 1,000 files.")
    stem, outs = Path(src).stem, []
    width = len(str(len(groups)))
    targets = [_target(d / f"{stem}_part{n:0{width}d}.pdf", Path(src), overwrite) for n in range(1, len(groups) + 1)]
    for n, (g, tgt) in enumerate(zip(groups, targets)):
        _report(progress, n / len(groups), f"Writing part {n + 1} of {len(groups)}")
        w = _new_writer()
        for i in g:
            w.add_page(reader.pages[i])
        _save(w, tgt)
        outs.append(tgt)
    _report(progress, 1.0, "Done")
    return outs


# ------------------------------------------------------------------ overlays
def _font_name(canvas_mod, text: str) -> str:
    """Helvetica for plain Latin-1 text, bundled DejaVu (OFL-like Bitstream Vera license) otherwise."""
    try:
        text.encode("latin-1")
        return "Helvetica"
    except UnicodeEncodeError:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        if "PCDejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("PCDejaVu", str(_FONT)))
        return "PCDejaVu"


def _overlay(width: float, height: float, draw: Callable) -> object:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    draw(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return _pypdf().PdfReader(buf).pages[0]


def add_watermark(src, out, text: str, *, opacity: float = 0.15, size: int = 60, angle: int = 45,
                  pages: str = "", overwrite=False, password=None, progress: Progress | None = None) -> Path:
    text = (text or "").strip()
    if not text or len(text) > 100:
        raise InvalidOptionsError("Enter watermark text of 1 to 100 characters.")
    if not 0.02 <= opacity <= 1.0 or not 8 <= size <= 200:
        raise InvalidOptionsError("Opacity must be 2%-100% and size 8-200 pt.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    chosen = set(_pages(pages, len(reader.pages)))
    w = _new_writer()
    font = _font_name(None, text)
    n = len(reader.pages)
    for i, page in enumerate(reader.pages):
        if i % 20 == 0:
            _report(progress, i / n, f"Watermarking page {i + 1} of {n}")
        if i in chosen:
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)

            def draw(c, pw=pw, ph=ph):
                c.saveState()
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.setFillAlpha(opacity)
                c.setFont(font, size)
                c.translate(pw / 2, ph / 2)
                c.rotate(angle)
                c.drawCentredString(0, -size / 3, text)
                c.restoreState()
            page.merge_page(_overlay(pw, ph, draw))
        w.add_page(page)
    _save(w, target)
    return target


def add_page_numbers(src, out, *, fmt: str = "{n} / {total}", position: str = "bottom-center", start: int = 1,
                     overwrite=False, password=None, progress: Progress | None = None) -> Path:
    positions = {"bottom-center", "bottom-right", "bottom-left", "top-center", "top-right", "top-left"}
    if position not in positions:
        raise InvalidOptionsError("Unknown page-number position.")
    if "{n}" not in fmt or len(fmt) > 40:
        raise InvalidOptionsError("The number format must contain {n}, for example 'Page {n} of {total}'.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    total = len(reader.pages)
    w = _new_writer()
    for i, page in enumerate(reader.pages):
        if i % 20 == 0:
            _report(progress, i / total, f"Numbering page {i + 1} of {total}")
        label = fmt.replace("{n}", str(start + i)).replace("{total}", str(start + total - 1))
        pw, ph = float(page.mediabox.width), float(page.mediabox.height)
        font = _font_name(None, label)

        def draw(c, label=label, pw=pw, ph=ph, font=font):
            c.setFont(font, 9)
            c.setFillGray(0.2)
            y = 24 if position.startswith("bottom") else ph - 30
            if position.endswith("center"):
                c.drawCentredString(pw / 2, y, label)
            elif position.endswith("right"):
                c.drawRightString(pw - 36, y, label)
            else:
                c.drawString(36, y, label)
        page.merge_page(_overlay(pw, ph, draw))
        w.add_page(page)
    _save(w, target)
    return target


# ------------------------------------------------------------------ metadata / security / size
def set_metadata(src, out, *, title=None, author=None, subject=None, keywords=None,
                 overwrite=False, password=None) -> Path:
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    w = _new_writer(reader)
    fields = {"/Title": title, "/Author": author, "/Subject": subject, "/Keywords": keywords}
    for k, v in fields.items():
        if v is not None and len(v) > 500:
            raise InvalidOptionsError("Metadata values are limited to 500 characters.")
    w.add_metadata({k: v for k, v in fields.items() if v is not None})
    _save(w, target)
    return target


def protect_pdf(src, out, user_password: str, owner_password: str | None = None, *, overwrite=False,
                password=None) -> Path:
    """AES-256 encryption. Anyone with the user password can open the file; there is no recovery if it is lost."""
    if len(user_password or "") < 4:
        raise InvalidOptionsError("Use a password of at least 4 characters.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    w = _new_writer(reader)
    try:
        w.encrypt(user_password, owner_password or user_password, algorithm="AES-256")
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc
    _save(w, target)
    return target


def unprotect_pdf(src, out, password: str, *, overwrite=False) -> Path:
    """Save an unencrypted copy. Requires the correct password; this is not a password-recovery tool."""
    if not password:
        raise PasswordProtectedError("Enter the document password.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    w = _new_writer(reader)
    _save(w, target)
    return target


def compress_pdf(src, out, *, level: str = "medium", overwrite=False, password=None) -> tuple[Path, int, int]:
    """Structural compression (deflate streams, merge identical objects; images are re-encoded at
    'medium'/'high' reduction when Pillow can decode them). Returns (path, size_before, size_after).
    The result can be LARGER for already-optimised files; in that case the caller is told via the sizes."""
    if level not in ("low", "medium", "high"):
        raise InvalidOptionsError("Compression level must be low, medium or high.")
    reader = _open(src, password)
    target = _target(out, Path(src), overwrite)
    w = _new_writer(reader)
    for page in w.pages:
        page.compress_content_streams()
        if level != "low":
            quality = 70 if level == "medium" else 45
            try:
                for img in page.images:
                    try:
                        img.replace(img.image, quality=quality)   # re-encodes as JPEG at the given quality
                    except Exception:
                        continue                                  # unsupported colour space etc.: leave as is
            except Exception:
                pass
    try:
        w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception:
        pass
    _save(w, target)
    return target, Path(src).stat().st_size, target.stat().st_size


# ------------------------------------------------------------------ images <-> PDF
def images_to_pdf(images: Sequence[str | Path], out, *, overwrite=False, progress: Progress | None = None) -> Path:
    if not images:
        raise InvalidOptionsError("Choose at least one image.")
    if len(images) > 500:
        raise InvalidOptionsError("At most 500 images can be combined at once.")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc
    target = _target(out, None, overwrite)
    Image.MAX_IMAGE_PIXELS = 100_000_000
    prepared = []
    for k, p in enumerate(images):
        _report(progress, k / len(images), f"Reading {Path(p).name}")
        try:
            with Image.open(p) as im:
                im.load()
                im = im.convert("RGB") if im.mode not in ("RGB", "L") else im.copy()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise InvalidFileError(f"'{Path(p).name}' is not a readable image.", technical=str(exc)) from exc
        prepared.append(im)
    with _atomic(target) as tmp:
        prepared[0].save(str(tmp), "PDF", save_all=True, append_images=prepared[1:], resolution=150.0)
    return target


def pdf_to_images(src, out_dir: str | Path, *, fmt: str = "png", dpi: int = 150, pages: str = "",
                  overwrite=False, password=None, progress: Progress | None = None) -> list[Path]:
    """Render pages with pypdfium2 (Apache-2.0/BSD). Output: <stem>_page<N>.<fmt>."""
    if fmt not in ("png", "jpg"):
        raise InvalidOptionsError("Image format must be png or jpg.")
    if not 36 <= dpi <= 600:
        raise InvalidOptionsError("Resolution must be between 36 and 600 dpi.")
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise DependencyMissingError("Exporting pages as images needs the pypdfium2 package.", technical=str(exc)) from exc
    reader = _open(src, password)                         # validates, and tells us about passwords
    d = Path(out_dir)
    if not d.is_dir():
        raise OutputPathError("The output folder does not exist.")
    idx = _pages(pages, len(reader.pages))
    outs: list[Path] = []
    try:
        doc = pdfium.PdfDocument(str(src), password=password)
    except Exception as exc:
        raise InvalidFileError("The PDF could not be rendered.", technical=str(exc)) from exc
    try:
        for k, i in enumerate(idx):
            _report(progress, k / len(idx), f"Rendering page {i + 1}")
            tgt = d / f"{Path(src).stem}_page{i + 1}.{fmt}"
            if tgt.exists() and not overwrite:
                raise OutputPathError(f"'{tgt.name}' already exists.")
            bmp = doc[i].render(scale=dpi / 72)
            img = bmp.to_pil()
            with _atomic(tgt) as tmp:
                img.convert("RGB").save(str(tmp), "PNG" if fmt == "png" else "JPEG")
            outs.append(tgt)
    finally:
        doc.close()
    return outs
