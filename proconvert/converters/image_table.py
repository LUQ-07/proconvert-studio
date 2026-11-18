"""Images -> Excel: find the table in a photo or scan and read its cells with Tesseract (local, no upload).

Pipeline per image: load -> straighten (small skew) -> find ruled lines -> OCR the whole picture once (words + boxes)
-> put every word into the cell it lies in -> repair obvious digit confusions -> one sheet per image.

Three table styles are understood:
  * ruled        horizontal AND vertical lines (a classic grid)
  * h-rules      horizontal lines only (common in financial tables); columns come from the gaps between words
  * borderless   no lines; rows and columns come from the word positions (approximate)
Limits: ONE table per image, merged cells are not reconstructed (the text lands in the cell that holds its centre),
handwriting and very blurry photos are not supported. OCR can misread characters: the result must be reviewed.
Only numpy (BSD), Pillow (HPND), pytesseract and Tesseract (Apache-2.0) are used.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Callable, Sequence

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ..core.context import CancelToken, JobContext
from ..core.errors import (ConversionError, DependencyMissingError, InvalidFileError, InvalidOptionsError,
                           ResourceLimitError)
from ..core.ir import DocumentIR, Section, Table
from ..core.options import ConversionOptions, Limits
from ..core.security import validate_target
from ..pdftools.ops import _atomic
from . import ocr
from .image_tools import MAX_IMAGES, MAX_PIXELS, ImageResult, _flatten, check_image_file

MAX_SIDE = 3200            # longest side used for analysis; bigger pictures are scaled down (with a warning)
MIN_WORDS = 4              # fewer recognised words than this = "no table"
MIN_CONF = 25              # Tesseract word confidence below this is ignored

Progress = Callable[[float, str], None]


@dataclass
class _Word:
    text: str
    x0: int
    y0: int
    x1: int
    y1: int
    conf: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> int:
        return max(self.y1 - self.y0, 1)


@dataclass
class TableResult:
    rows: list[list[str]]
    style: str                       # "ruled" | "h-rules" | "borderless"
    confidence: float                # mean Tesseract word confidence 0..100
    repaired: int = 0                # cells fixed by the digit repair
    skew_deg: float = 0.0
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ image preparation
def _prepare(path: Path, warnings: list[str]) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    check_image_file(path)
    try:
        with Image.open(path) as im:
            if im.width * im.height > MAX_PIXELS:
                raise ResourceLimitError(f"'{path.name}' is larger than {MAX_PIXELS // 1_000_000} megapixels.")
            if getattr(im, "n_frames", 1) > 1 and im.format == "TIFF":
                im.seek(0)
                warnings.append(f"'{path.name}': only the first TIFF page is scanned.")
            im.load()
            im = ImageOps.exif_transpose(im)
            gray = _flatten(im, Image).convert("L")
    except ConversionError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidFileError(f"'{path.name}' is not a readable image.", technical=f"{type(exc).__name__}: {exc}") from exc
    side = max(gray.size)
    if side > MAX_SIDE:
        k = MAX_SIDE / side
        gray = gray.resize((max(1, round(gray.width * k)), max(1, round(gray.height * k))), Image.LANCZOS)
        warnings.append(f"'{path.name}': scaled down for analysis; very small print may be misread.")
    elif side < 1400:                                    # Tesseract reads small text much better when enlarged
        k = min(2.0, MAX_SIDE / side)
        gray = gray.resize((round(gray.width * k), round(gray.height * k)), Image.LANCZOS)
    return gray


def _dark_mask(gray: Image.Image) -> np.ndarray:
    """Pixels clearly darker than their surroundings (robust against uneven lighting)."""
    radius = max(15, min(gray.size) // 25)
    local = np.asarray(gray.filter(ImageFilter.BoxBlur(radius)), dtype=np.int16)
    return np.asarray(gray, dtype=np.int16) < local - 28


def estimate_skew(dark: np.ndarray) -> float:
    """Angle (degrees, counter-clockwise rotation that straightens the page) from -5 to 5, found by maximising
    the variance of the row profile of the rotated picture."""
    small = Image.fromarray((dark[::2, ::2] * 255).astype(np.uint8))

    def score(angle: float) -> float:
        rot = small.rotate(angle, resample=Image.NEAREST, fillcolor=0)
        return float(np.var(np.asarray(rot, dtype=np.float32).sum(axis=1)))

    coarse = max(np.arange(-5.0, 5.01, 0.5), key=score)
    fine = max(np.arange(coarse - 0.4, coarse + 0.41, 0.1), key=score)
    return 0.0 if abs(fine) < 0.25 else round(float(fine), 1)


# ------------------------------------------------------------------ line detection
def _forward_run(m: np.ndarray) -> np.ndarray:
    cum = np.cumsum(m, axis=1, dtype=np.int16)
    last_zero = np.maximum.accumulate(np.where(m, np.int16(0), cum), axis=1)
    return cum - last_zero


def _long_strokes(mask: np.ndarray, min_len: int) -> np.ndarray:
    """Pixels that belong to a horizontal run of at least *min_len* dark pixels (2-pixel gaps are bridged)."""
    bridged = mask.copy()
    bridged[:, 1:] |= mask[:, :-1]
    bridged[:, :-1] |= mask[:, 1:]
    run = _forward_run(bridged) + _forward_run(bridged[:, ::-1])[:, ::-1] - 1
    return (run >= min_len) & mask


def _centres(profile: np.ndarray, rel: float = 0.55) -> list[int]:
    """Centres of the bands (thick lines) where *profile* reaches *rel* of its maximum."""
    if profile.max() <= 0:
        return []
    on = profile >= profile.max() * rel
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start + i - 1) // 2)
            start = None
    if start is not None:
        out.append((start + len(on) - 1) // 2)
    merged: list[int] = []
    for c in out:                                         # drop near-duplicates (a doubled border)
        if not merged or c - merged[-1] > 6:
            merged.append(c)
    return merged


@dataclass
class _Grid:
    hlines: list[int]
    vlines: list[int]
    stroke_mask: np.ndarray            # pixels of the detected lines (to erase before OCR)


def detect_grid(dark: np.ndarray) -> _Grid:
    h, w = dark.shape
    hmask = _long_strokes(dark, max(40, int(0.12 * w)))
    vmask = _long_strokes(dark.T, max(40, int(0.08 * h))).T
    hlines = _centres(hmask.sum(axis=1))
    vlines = _centres(vmask.sum(axis=0))
    strokes = hmask | vmask
    # grow by 2 px so the anti-aliased edge of every line disappears with it
    grown = strokes.copy()
    for dy in (-2, -1, 1, 2):
        grown[max(dy, 0):h + min(dy, 0)] |= strokes[max(-dy, 0):h + min(-dy, 0)]
    g2 = grown.copy()
    for dx in (-2, -1, 1, 2):
        g2[:, max(dx, 0):w + min(dx, 0)] |= grown[:, max(-dx, 0):w + min(-dx, 0)]
    return _Grid(hlines, vlines, g2)


# ------------------------------------------------------------------ OCR
def _ocr_words(gray: Image.Image, language: str, psm: int = 6) -> list[_Word]:
    import pytesseract

    if not ocr.valid_language(language):
        language = "eng"
    pytesseract.pytesseract.tesseract_cmd = ocr.tesseract_path() or "tesseract"
    try:
        data = pytesseract.image_to_data(gray, lang=language, config=f"--psm {psm} -c preserve_interword_spaces=1",
                                         output_type=pytesseract.Output.DICT, timeout=180)
    except pytesseract.TesseractError as exc:
        if "load" in str(exc).lower() or "language" in str(exc).lower():
            raise DependencyMissingError(f"The OCR language data for '{language}' is not installed.", technical=str(exc)) from exc
        raise ConversionError("The text could not be recognised.", technical=str(exc)) from exc
    except RuntimeError as exc:                            # pytesseract timeout
        raise ConversionError("Text recognition took too long and was stopped.", technical=str(exc)) from exc
    words = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < MIN_CONF:
            continue
        x0, y0, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(_Word(text, x0, y0, x0 + w, y0 + h, conf))
    return words


# ------------------------------------------------------------------ assigning words to cells
def _row_groups(words: list[_Word], thr: float) -> list[list[_Word]]:
    rows: list[list[_Word]] = []
    for w in sorted(words, key=lambda w: w.yc):
        if rows and abs(w.yc - sum(x.yc for x in rows[-1]) / len(rows[-1])) <= thr:
            rows[-1].append(w)
        else:
            rows.append([w])
    return rows


def _column_bands(words: list[_Word], gap: float) -> list[tuple[float, float]]:
    bands: list[list[float]] = []
    for w in sorted(words, key=lambda w: w.x0):
        if bands and w.x0 - bands[-1][1] <= gap:
            bands[-1][1] = max(bands[-1][1], w.x1)
        else:
            bands.append([w.x0, w.x1])
    return [(a, b) for a, b in bands]


def _join_cell(words: list[_Word], med_h: float) -> str:
    lines = _row_groups(words, 0.6 * med_h)
    return " ".join(" ".join(w.text for w in sorted(line, key=lambda w: w.x0)) for line in lines).strip(" |_")


def _fill(words: list[_Word], row_of: Callable[[_Word], int | None], col_of: Callable[[_Word], int | None],
          n_rows: int, n_cols: int) -> list[list[str]]:
    cells: dict[tuple[int, int], list[_Word]] = {}
    for w in words:
        r, c = row_of(w), col_of(w)
        if r is not None and c is not None:
            cells.setdefault((r, c), []).append(w)
    med_h = median(w.h for w in words) if words else 10
    return [[_join_cell(cells.get((r, c), []), med_h) for c in range(n_cols)] for r in range(n_rows)]


def _bucket(bounds: list[float]) -> Callable[[float], int | None]:
    def f(v: float) -> int | None:
        i = bisect_right(bounds, v) - 1
        return i if 0 <= i < len(bounds) - 1 else None
    return f


def build_table(words: list[_Word], grid: _Grid, width: int, height: int) -> tuple[list[list[str]], str] | None:
    """Rows of cell texts and the detected style, or None when there is no usable table."""
    if len(words) < MIN_WORDS:
        return None
    med_h = median(w.h for w in words)
    hl, vl = grid.hlines, grid.vlines
    ruled_h, ruled_v = len(hl) >= 3 or (len(hl) == 2 and len(vl) >= 2), len(vl) >= 3 or (len(vl) == 2 and len(hl) >= 2)
    if ruled_h and ruled_v:
        top, bottom, left, right = hl[0] - 4, hl[-1] + 4, vl[0] - 4, vl[-1] + 4
        words = [w for w in words if top <= w.yc <= bottom and left <= w.xc <= right]
        row_idx = _bucket([float(v) for v in hl])
    if ruled_h and ruled_v:
        col_idx = _bucket([float(v) for v in vl])
        rows = _fill(words, lambda w: row_idx(w.yc), lambda w: col_idx(w.xc), len(hl) - 1, len(vl) - 1)
        return rows, "ruled"
    style = "borderless"
    if ruled_h:                                                        # horizontal rules only: they bound the table, they do not
        words = [w for w in words if hl[0] - 4 <= w.yc <= hl[-1] + 4]  # separate every row (e.g. header rule + closing rule)
        style = "h-rules"
    # borderless: rows and columns purely from the word positions
    row_groups = _row_groups(words, 0.6 * med_h)
    row_centre = [sum(w.yc for w in g) / len(g) for g in row_groups]
    bands = _column_bands(words, max(1.2 * med_h, 14))
    if len(row_groups) < 2 or len(bands) < 2:
        return None
    bounds = [-1e9] + [(a2 + b1) / 2 for (_a1, b1), (a2, _b2) in zip(bands, bands[1:])] + [1e9]
    col_idx = _bucket(bounds)
    row_bounds = [-1e9] + [(row_centre[i] + row_centre[i + 1]) / 2 for i in range(len(row_centre) - 1)] + [1e9]
    row_idx = _bucket(row_bounds)
    return _fill(words, lambda w: row_idx(w.yc), lambda w: col_idx(w.xc), len(row_groups), len(bands)), style


# ------------------------------------------------------------------ cleaning
_NUMERIC_LOOKING = re.compile(r"^[\dOolI|\s.,%\u20ac$\u00a3+\-]+$")
_HAS_DIGIT = re.compile(r"\d")
_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1"})


def repair_digits(rows: list[list[str]]) -> int:
    """In a mostly numeric column, read O/o as 0 and l/I/| as 1 inside cells that are otherwise numeric.
    Returns the number of cells changed. Text columns are never touched."""
    changed = 0
    n_cols = max((len(r) for r in rows), default=0)
    for c in range(n_cols):
        cells = [(r, row[c]) for r, row in enumerate(rows) if c < len(row) and row[c].strip()]
        numeric = [t for _, t in cells if _NUMERIC_LOOKING.match(t) and _HAS_DIGIT.search(t)]
        body = cells[1:] if len(cells) > 2 else cells                  # skip a likely header cell
        if len(body) < 2 or len(numeric) < 0.7 * len(cells):
            continue
        for r, t in body:
            if _NUMERIC_LOOKING.match(t):
                fixed = t.translate(_FIX)
                if fixed != t and _HAS_DIGIT.search(fixed):
                    rows[r][c] = fixed
                    changed += 1
    return changed


def _trim(rows: list[list[str]]) -> list[list[str]]:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return rows
    keep = [c for c in range(max(len(r) for r in rows)) if any(c < len(r) and r[c].strip() for r in rows)]
    return [[r[c] if c < len(r) else "" for c in keep] for r in rows]


# ------------------------------------------------------------------ public API
def read_table(path: str | Path, language: str = "eng", *, warnings: list[str] | None = None,
               cancel: CancelToken | None = None) -> TableResult | None:
    """Scan one image. Returns None when no table is found."""
    warnings = warnings if warnings is not None else []
    token = cancel or CancelToken()
    path = Path(path)
    gray = _prepare(path, warnings)
    token.check()
    dark = _dark_mask(gray)
    skew = estimate_skew(dark)
    if skew:
        gray = gray.rotate(skew, resample=Image.BICUBIC, expand=False, fillcolor=255)
        dark = _dark_mask(gray)
    token.check()
    grid = detect_grid(dark)
    # Tesseract input: ruling erased (it would be read as "|", "_" or "—"), binarised and de-speckled.
    # Measured on synthetic noisy/shaded/rotated tables: 20/20 cells right vs 11-18/20 for the plain grey picture.
    ink = dark & ~grid.stroke_mask
    ocr_img = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3))
    words = _ocr_words(ocr_img, language)
    token.check()
    built = build_table(words, grid, *gray.size)
    if built is None:
        return None
    rows, style = built
    rows = _trim(rows)
    if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
        return None
    repaired = repair_digits(rows)
    conf = sum(w.conf for w in words) / max(len(words), 1)
    res = TableResult(rows, style, round(conf, 1), repaired, skew)
    if skew:
        res.notes.append(f"'{path.name}': the picture was straightened by {skew}\u00b0.")
    if style == "borderless":
        res.notes.append(f"'{path.name}': no table lines were found; rows and columns were guessed from the text positions.")
    elif style == "h-rules":
        res.notes.append(f"'{path.name}': only horizontal lines were found; columns were guessed from the gaps between words.")
    if repaired:
        res.notes.append(f"'{path.name}': {repaired} number(s) were corrected (letters read as digits).")
    if conf < 70:
        res.notes.append(f"'{path.name}': low recognition confidence ({conf:.0f} %). Check every value.")
    return res


def convert_images_to_xlsx(images: Sequence[str | Path], out: str | Path, language: str = "eng", *, overwrite: bool = False,
                           cancel: CancelToken | None = None, progress: Progress | None = None) -> ImageResult:
    """One worksheet per image holding the recognised table. Needs Tesseract; never modifies the sources."""
    if not images:
        raise InvalidOptionsError("Add at least one image.")
    if len(images) > MAX_IMAGES:
        raise InvalidOptionsError(f"At most {MAX_IMAGES} images can be converted at once.")
    if not ocr.is_available():
        raise DependencyMissingError("Reading a table from a picture needs the OCR engine (Tesseract), which was not found.")
    if not ocr.valid_language(language):
        raise InvalidOptionsError("The OCR language must look like 'eng' or 'fra+eng'.")
    paths = [check_image_file(p) for p in images]
    target = validate_target(out, None, "xlsx", overwrite=overwrite)
    for p in paths:
        if p.resolve() == target:
            raise InvalidOptionsError("The output file must be different from the source images.")
    token = cancel or CancelToken()
    warnings = ["Tables read from pictures are an experimental feature: text is recognised automatically and can contain mistakes. "
                "Review the result."]

    def report(frac: float, text: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)), text)

    ir = DocumentIR("tables", source_format="image")
    for i, p in enumerate(paths):
        token.check()
        report(0.05 + 0.8 * i / len(paths), p.name)
        res = read_table(p, language, warnings=warnings, cancel=token)
        if res is None:
            warnings.append(f"'{p.name}': no table was found in this picture.")
            continue
        warnings.extend(res.notes)
        ir.sections.append(Section("sheet", p.stem, [Table(res.rows, header=True)]))
    if not ir.sections:
        raise InvalidFileError("No table was found in the picture(s). Use a sharp, straight and evenly lit picture in which the "
                               "whole table is visible.")
    ctx = JobContext(ConversionOptions(ocr_language=language), Limits())
    from .xlsx_writer import write_xlsx
    with _atomic(target) as tmp:
        report(0.9, "writing")
        write_xlsx(ir, tmp, ctx)
        _verify(tmp, len(ir.sections))
    report(1.0, "done")
    return ImageResult(target, len(ir.sections), warnings + ctx.warnings)


def _verify(path: Path, sheets: int) -> None:
    try:
        import io

        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(path.read_bytes()))      # by content: the temporary file has no .xlsx extension
        count = len(wb.worksheets)
        cells = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value not in (None, ""))
    except Exception as exc:
        raise ConversionError("The result could not be verified and was discarded.", technical=f"{type(exc).__name__}: {exc}") from exc
    if count != sheets or cells == 0:
        raise ConversionError("The result is incomplete and was discarded.", technical=f"sheets={count}/{sheets} cells={cells}")
