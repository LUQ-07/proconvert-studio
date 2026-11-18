"""PDF -> IR.

Pipeline per page: ruled-table detection (pdfplumber) -> text lines with font metrics
(table regions excluded) -> optional two-column re-ordering -> images (pypdf bytes placed
using pdfplumber coordinates) -> optional OCR for pages without a text layer.
After all pages are read: repeating headers/footers are removed (and reported), the body
font size is estimated, and lines are grouped into headings, bullets and paragraphs.

This is text-and-structure *reconstruction*, not layout reproduction. See the capability matrix.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from statistics import median

from ..core.context import READING, JobContext
from ..core.errors import (
    ConversionError,
    DependencyMissingError,
    EmptyContentError,
    FileTooLargeError,
    InvalidFileError,
    PasswordProtectedError,
)
from ..core.images import normalize_image
from ..core.ir import Block, DocumentIR, Paragraph, Picture, Run, Section, Table
from ..utils.ranges import parse_page_ranges
from ..utils.text import clean_block, clean_inline
from . import ocr

_BOLD = ("bold", "black", "heavy", "semibold", "demi")
_ITALIC = ("italic", "oblique")
_BULLET = re.compile(r"^([•●▪◦‣∙·■□▫–—\-§→➔➢✓❖❑◻◆\uf000-\uf0ff]|o(?=\s+[A-ZÀ-ÖØ-Þ]))\s+(?=\S)")
_PUA = re.compile(r"[\ue000-\uf8ff]")
_NUMBERED = re.compile(r"^(\d{1,3})[.)]\s+(?=\S)")
_X_RATIO = 0.12   # a gap wider than 12% of the font size is a word space
_CID = re.compile(r"\(cid:\d+\)")
_TERMINAL = (".", "!", "?", ":", ";", '"', "\u201d", ")")


@dataclass
class LineInfo:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool
    italic: bool


@dataclass
class PageRaw:
    number: int
    width: float
    height: float
    lines: list[LineInfo] = field(default_factory=list)
    extras: list[tuple[float, Block]] = field(default_factory=list)   # tables / images with y position
    ocr_paragraphs: list[str] = field(default_factory=list)
    scanned: bool = False


# --------------------------------------------------------------------------- line helpers
# Lines are built from pdfplumber *words* (cheap) rather than extract_text_lines(), which retained
# ~4 MB per page. Each word dict carries text, x0, x1, top, bottom, size and fontname.
def _flags(words: list[dict]) -> tuple[float, bool, bool]:
    if not words:
        return 0.0, False, False
    total = sum(len(w["text"]) for w in words) or 1
    size = float(median(float(w.get("size") or 0) for w in words))
    names = [(str(w.get("fontname", "")).lower(), len(w["text"])) for w in words]
    bold = sum(n for f, n in names if any(k in f for k in _BOLD)) / total >= 0.6
    italic = sum(n for f, n in names if any(k in f for k in _ITALIC)) / total >= 0.6
    return size, bold, italic


def _line_from_words(words: list[dict]) -> LineInfo | None:
    if not words:
        return None
    ws = sorted(words, key=lambda w: w["x0"])
    parts = [ws[0]["text"]]
    for prev, cur in zip(ws, ws[1:]):
        size = float(cur.get("size") or prev.get("size") or 10)
        gap = cur["x0"] - prev["x1"]
        # words split only by a font/size change stay joined; a real gap is a word space
        parts.append(cur["text"] if gap < _X_RATIO * size else " " + cur["text"])
    text = clean_inline("".join(parts))
    if not text:
        return None
    size, bold, italic = _flags(ws)
    return LineInfo(text, ws[0]["x0"], max(w["x1"] for w in ws), min(w["top"] for w in ws),
                    max(w["bottom"] for w in ws), size, bold, italic)


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster words into visual lines by vertical overlap."""
    lines: list[list[dict]] = []
    cur: list[dict] = []
    top = bottom = 0.0
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        cy = (w["top"] + w["bottom"]) / 2
        if cur and top - 1.0 <= cy <= bottom + 1.0:
            cur.append(w)
            top, bottom = min(top, w["top"]), max(bottom, w["bottom"])
        else:
            if cur:
                lines.append(cur)
            cur, top, bottom = [w], w["top"], w["bottom"]
    if cur:
        lines.append(cur)
    return lines


def _fix_cids(lines: list[LineInfo]) -> int:
    """Unmapped glyphs appear as "(cid:N)". A leading run is a bullet symbol; others are counted."""
    unmapped = 0
    for ln in lines:
        if "(cid:" not in ln.text:
            continue
        m = re.match(r"^\s*(?:\(cid:\d+\)\s*)+", ln.text)
        if m:
            ln.text = "\u2022 " + ln.text[m.end():].lstrip()
        unmapped += len(_CID.findall(ln.text))
        ln.text = _CID.sub("\ufffd", ln.text)
    return unmapped


def _find_gutter(words: list[dict], width: float) -> tuple[float, float] | None:
    """Return (gutter_center_x, gutter_width) for a two-column page, else None."""
    bins = [0] * (int(width // 2) + 3)
    total = 0
    for w in words:
        weight = len(w["text"])
        total += weight
        for b in range(max(0, int(w["x0"] // 2)), min(len(bins) - 1, int(w["x1"] // 2)) + 1):
            bins[b] += weight
    if total < 150:
        return None
    lo, hi = int(width * 0.30 / 2), int(width * 0.70 / 2)
    limit = max(1, int(total * 0.002))
    best_len, best_start, run, start = 0, 0, 0, 0
    for i in range(lo, hi + 1):
        if bins[i] <= limit:
            if run == 0:
                start = i
            run += 1
            if run > best_len:
                best_len, best_start = run, start
        else:
            run = 0
    gutter_w = best_len * 2.0
    if gutter_w < 10:
        return None
    gx = (best_start + best_len / 2) * 2.0
    left = sum(len(w["text"]) for w in words if w["x1"] <= gx)
    right = sum(len(w["text"]) for w in words if w["x0"] >= gx)
    if min(left, right) < 0.25 * total:
        return None
    return gx, gutter_w


def _gap_straddles(words: list[dict], gx: float, min_gap: float) -> bool:
    ordered = sorted(words, key=lambda w: w["x0"])
    for a, b in zip(ordered, ordered[1:]):
        if a["x1"] <= gx <= b["x0"] and (b["x0"] - a["x1"]) >= min_gap:
            return True
    return False


def _order_columns(lines: list[list[dict]], gx: float, gutter_w: float) -> list[LineInfo]:
    out: list[LineInfo] = []
    left_band: list[LineInfo] = []
    right_band: list[LineInfo] = []

    def flush() -> None:
        out.extend(left_band)
        out.extend(right_band)
        left_band.clear()
        right_band.clear()

    for ws in lines:
        left = [w for w in ws if (w["x0"] + w["x1"]) / 2 < gx]
        right = [w for w in ws if (w["x0"] + w["x1"]) / 2 >= gx]
        if left and right:
            if _gap_straddles(ws, gx, max(6.0, gutter_w * 0.5)):
                for target, group in ((left_band, left), (right_band, right)):
                    li = _line_from_words(group)
                    if li:
                        target.append(li)
            else:  # continuous text crossing the gutter: a full-width line (title, caption)
                flush()
                li = _line_from_words(ws)
                if li:
                    out.append(li)
        else:
            li = _line_from_words(ws)
            if li:
                (left_band if left else right_band).append(li)
    flush()
    return out


# --------------------------------------------------------------------------- tables / images
def _clean_table(rows: list[list]) -> list[list[str]]:
    grid = [[clean_inline(c) for c in (r or [])] for r in rows]
    grid = [r for r in grid if any(r)]
    if not grid:
        return []
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    keep = [i for i in range(width) if any(r[i] for r in grid)]
    return [[r[i] for i in keep] for r in grid]


def _page_tables(page, ctx: JobContext, number: int) -> list[tuple[tuple, list[list[str]]]]:
    if not (page.lines or page.rects or page.curves):
        return []
    try:
        found = page.find_tables()
    except Exception:
        ctx.warn(f"Table detection failed on page {number}; its text was extracted without table structure.")
        return []
    tables = []
    for t in found:
        try:
            rows = _clean_table(t.extract())
        except Exception:
            continue
        if len(rows) >= 2 and len(rows[0]) >= 2:
            tables.append((t.bbox, rows))
    return tables


def _page_images(page, pypdf_page, ctx: JobContext, number: int) -> list[tuple[float, Picture]]:
    if not ctx.options.include_images:
        return []
    from PIL import Image

    try:
        images = list(pypdf_page.images)
    except Exception:
        ctx.warn(f"Images on page {number} could not be read.")
        return []
    placements: dict[tuple[int, int], list[dict]] = {}
    for obj in page.images:
        key = tuple(int(v) for v in (obj.get("srcsize") or (0, 0)))
        placements.setdefault(key, []).append(obj)
    out: list[tuple[float, Picture]] = []
    for img in images[: ctx.limits.max_images_per_page]:
        ctx.cancel.check()
        try:
            data = img.data
            with Image.open(io.BytesIO(data)) as probe:
                src = probe.size
        except Exception:
            ctx.warn("One or more images could not be decoded and were skipped.")
            continue
        if min(src) < 24 or src[0] * src[1] < 2500:
            continue  # decorative rules, bullets, spacer pixels
        slot = placements.get(src)
        obj = slot.pop(0) if slot else None
        pic = normalize_image(
            data, ctx,
            display_w_pt=float(obj["x1"] - obj["x0"]) if obj else None,
            display_h_pt=float(obj["bottom"] - obj["top"]) if obj else None,
        )
        if pic:
            out.append((float(obj["top"]) if obj else float(page.height), pic))
    return out


# --------------------------------------------------------------------------- OCR
def _ocr_page(pdfium_doc, index: int, ctx: JobContext) -> list[str]:
    page = pdfium_doc[index]
    try:
        w, h = page.get_size()
        scale = min(300 / 72, 4000 / max(w, h, 1))
        pil = page.render(scale=scale).to_pil()
    finally:
        page.close()
    text = ocr.recognize(pil, ctx.options.ocr_language)
    paras = [clean_block(p.replace("\n", " ")) for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p]


# --------------------------------------------------------------------------- structure
def _heading_level(line: LineInfo, body: float) -> int:
    if body <= 0 or len(line.text) > 200:
        return 0
    ratio = line.size / body
    if ratio >= 1.6:
        return 1
    if ratio >= 1.3:
        return 2
    if ratio >= 1.15:
        return 3
    return 0


def _join(a: str, b: str) -> str:
    if len(a) > 2 and a.endswith("-") and a[-2].isalpha() and b[:1].islower():
        return a[:-1] + b
    return f"{a} {b}"


def _short_line(prev: LineInfo, col_width: float, ln: LineInfo) -> bool:
    """True when *prev* ends well before the column's right edge and *ln* starts at (or right of) the same x:
    the author pressed Enter there, so *ln* is a new item and not the continuation of a wrapped paragraph."""
    return (prev.x1 - prev.x0) < 0.6 * col_width and ln.x0 >= prev.x0 - 0.5 * ln.size and len(prev.text) < 70


def _build_paragraphs(lines: list[LineInfo], body: float) -> list[tuple[float, Paragraph]]:
    if not lines:
        return []
    def colw_for(l: LineInfo) -> float:
        """Width of the widest line in the same column (lines whose left edge is within 60 pt, so indents count)."""
        return max((o.x1 - o.x0 for o in lines if abs(o.x0 - l.x0) <= 60), default=1.0)

    groups: list[list[LineInfo]] = []
    kinds: list[int] = []
    for ln in lines:
        kind = _heading_level(ln, body)
        if groups:
            prev = groups[-1][-1]
            gap = ln.top - prev.bottom
            same = kind == kinds[-1] and abs(ln.size - prev.size) <= 1.0
            if kind > 0:
                cont = same and -0.5 * prev.size <= gap <= 0.8 * prev.size
            else:
                cont = (
                    same
                    and -0.2 * prev.size <= gap <= 0.75 * prev.size
                    and not _BULLET.match(ln.text)
                    and not _NUMBERED.match(ln.text)
                    and not ((prev.x1 - prev.x0) < 0.7 * colw_for(prev) and prev.text.endswith(_TERMINAL))
                    and not (ln.x0 - prev.x0 > 1.2 * ln.size and prev.text.endswith(_TERMINAL))
                    and abs(ln.x0 - groups[-1][0].x0) <= 3.0 * ln.size      # a much deeper (or shallower) start is a new item, not a wrapped line
                    and not _short_line(prev, colw_for(prev), ln)             # a wrapped line always runs to the margin; a short one ended its item
                )
            if cont:
                groups[-1].append(ln)
                continue
        groups.append([ln])
        kinds.append(kind)

    out: list[tuple[float, Paragraph]] = []
    list_base: float | None = None          # x of the last marked list item: deeper unmarked lines under it are sub-items
    for group, kind in zip(groups, kinds):
        text = group[0].text
        for ln in group[1:]:
            text = _join(text, ln.text)
        bullet = False
        number = None
        level = 0
        m = _BULLET.match(text)
        if m and kind == 0:
            bullet, text = True, text[m.end():]
            list_base = group[0].x0
        elif kind == 0 and (mn := _NUMBERED.match(text)):
            number, text = int(mn[1]), text[mn.end():]
            list_base = group[0].x0
        elif (kind == 0 and list_base is not None and group[0].x0 - list_base > 3.0 * group[0].size
              and not (text.isupper() and len(text) < 60)):      # an indented ALL-CAPS label is a sub-title, not an item
            bullet, level = True, 1                      # indented, unmarked line below a list item = nested item
        else:
            list_base = None
        text = _PUA.sub("", text).strip() or text
        bold = kind == 0 and all(l.bold for l in group)
        italic = kind == 0 and all(l.italic for l in group)
        out.append((group[0].top, Paragraph([Run(text, bold=bold, italic=italic)], heading=kind, bullet=bullet, level=level, number=number)))
    return out


def _interleave(paras: list[tuple[float, Block]], extras: list[tuple[float, Block]]) -> list[Block]:
    result = list(paras)
    for top, blk in sorted(extras, key=lambda x: x[0]):
        idx = next((i for i, (t, _b) in enumerate(result) if t >= top), len(result))
        result.insert(idx, (top, blk))
    return [b for _t, b in result]


def _zone(ln: LineInfo, page: PageRaw, body: float = 0.0) -> str | None:
    """Top/bottom 10 % of the page: where running headers, footers and page numbers live.

    Lines set noticeably larger than the body text are headings (e.g. "Section 3 Overview"), never running headers.
    """
    if body and ln.size > body * 1.12:
        return None
    if ln.top < page.height * 0.10:
        return "top"
    if ln.bottom > page.height * 0.90:
        return "bottom"
    return None


def _strip_repeating(pages: list[PageRaw], body: float = 0.0) -> tuple[int, str, str]:
    """Remove running headers/footers/page numbers that repeat on at least half the pages.

    Returns (lines removed, header text, footer text); a footer that is only a page number gives ''.
    """
    if len(pages) < 3:
        return 0, "", ""
    counts: Counter = Counter()
    samples: dict[tuple[str, str], Counter] = {}
    for p in pages:
        seen = set()
        for ln in p.lines:
            zone = _zone(ln, p, body)
            if zone:
                key = (zone, re.sub(r"\d+", "#", ln.text.lower()))
                seen.add(key)
                samples.setdefault(key, Counter())[ln.text] += 1
        counts.update(seen)
    threshold = max(3, ceil(len(pages) * 0.5))
    drop = {k for k, v in counts.items() if v >= threshold}
    if not drop:
        return 0, "", ""
    removed = 0
    for p in pages:
        kept = []
        for ln in p.lines:
            zone = _zone(ln, p, body)
            if zone and (zone, re.sub(r"\d+", "#", ln.text.lower())) in drop:
                removed += 1
            else:
                kept.append(ln)
        p.lines = kept

    def pick(zone: str) -> str:
        cands = [(counts[k], k) for k in drop if k[0] == zone and re.sub(r"[#\s]", "", k[1])]   # skip pure page numbers
        if not cands:
            return ""
        _n, key = max(cands)
        return clean_inline(samples[key].most_common(1)[0][0])
    return removed, pick("top"), pick("bottom")


def read_pdf(path: Path, ctx: JobContext) -> DocumentIR:
    try:
        import pdfplumber
        from pypdf import PdfReader
        from pypdf.errors import DependencyError
    except ImportError as exc:  # pragma: no cover - packaging problem
        raise DependencyMissingError(technical=str(exc)) from exc

    opts = ctx.options
    password = opts.pdf_password or ""
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(password):
            raise PasswordProtectedError(
                "This PDF is password protected. Enter the password to continue." if not password
                else "The password is not correct."
            )
        total_pages = len(reader.pages)
    except ConversionError:
        raise
    except DependencyError as exc:
        raise DependencyMissingError("This PDF uses encryption that needs an additional component.", technical=str(exc)) from exc
    except Exception as exc:
        raise InvalidFileError("The PDF is damaged or uses an unsupported structure.", technical=f"{type(exc).__name__}: {exc}") from exc
    if total_pages == 0:
        raise EmptyContentError("The PDF has no pages.")

    indexes = parse_page_ranges(opts.pdf_pages, total_pages)
    if len(indexes) > ctx.limits.max_pdf_pages:
        raise FileTooLargeError(f"The PDF has {len(indexes):,} pages; the limit is {ctx.limits.max_pdf_pages:,}. Use a page range.")

    pages: list[PageRaw] = []
    failed = 0
    unmapped_glyphs = 0
    pdfium_doc = None
    ocr_ready = opts.ocr_enabled and ocr.is_available()
    if opts.ocr_enabled and not ocr_ready:
        ctx.warn("OCR was requested but no OCR engine was found, so scanned pages were not recognized.")
    try:
        with pdfplumber.open(str(path), password=password or None) as pdf:
            for k, idx in enumerate(indexes):
                ctx.cancel.check()
                ctx.report(READING, k / len(indexes), f"Page {idx + 1} of {total_pages}")
                number = idx + 1
                try:
                    page = pdf.pages[idx]
                    raw = PageRaw(number, float(page.width), float(page.height))
                    tables = _page_tables(page, ctx, number)
                    words = page.extract_words(x_tolerance_ratio=_X_RATIO, extra_attrs=["size", "fontname"],
                                               keep_blank_chars=False, use_text_flow=False)
                    if tables:
                        boxes = [t[0] for t in tables]
                        words = [w for w in words if not any(
                            b[0] - 1 <= (w["x0"] + w["x1"]) / 2 <= b[2] + 1 and b[1] - 1 <= (w["top"] + w["bottom"]) / 2 <= b[3] + 1
                            for b in boxes)]
                    grouped = _group_lines(words)
                    gutter = _find_gutter(words, raw.width) if opts.detect_columns else None
                    if gutter:
                        raw.lines = _order_columns(grouped, *gutter)
                    else:
                        raw.lines = [li for li in (_line_from_words(g) for g in grouped) if li]
                    for bbox, rows in tables:
                        raw.extras.append((float(bbox[1]), Table(rows)))
                    imgs = _page_images(page, reader.pages[idx], ctx, number)
                    unmapped_glyphs += _fix_cids(raw.lines)
                    raw.scanned = not raw.lines and not tables and bool(imgs)
                    if raw.scanned and ocr_ready:
                        if pdfium_doc is None:
                            import pypdfium2 as pdfium
                            pdfium_doc = pdfium.PdfDocument(str(path), password=password or None)
                        ctx.report(READING, k / len(indexes), f"Recognizing text on page {number}")
                        raw.ocr_paragraphs = _ocr_page(pdfium_doc, idx, ctx)
                        if raw.ocr_paragraphs:
                            imgs = []
                    raw.extras.extend(imgs)
                    page.flush_cache()
                    pages.append(raw)
                except ConversionError:
                    raise
                except Exception:
                    failed += 1
                    ctx.warn(f"Page {number} could not be read and was skipped.")
    except ConversionError:
        raise
    except Exception as exc:
        raise InvalidFileError("The PDF is damaged or uses an unsupported structure.", technical=f"{type(exc).__name__}: {exc}") from exc
    finally:
        if pdfium_doc is not None:
            pdfium_doc.close()
    if failed == len(indexes):
        raise InvalidFileError("None of the pages in this PDF could be read.")

    if unmapped_glyphs:
        ctx.warn(f"{unmapped_glyphs} character(s) could not be mapped to text (unusual PDF font encoding) and appear as '\ufffd'.")
    sizes: Counter = Counter()
    for p in pages:
        for ln in p.lines:
            sizes[round(ln.size, 1)] += len(ln.text)
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    removed, header_text, footer_text = _strip_repeating(pages, body) if opts.strip_headers_footers else (0, "", "")
    if removed:
        ctx.warn(f"{removed} repeating header/footer/page-number line(s) were removed from the text flow"
                 + (" and kept as the document header/footer." if header_text or footer_text else "."))


    scanned = [p.number for p in pages if p.scanned and not p.ocr_paragraphs]
    ocr_pages = [p.number for p in pages if p.ocr_paragraphs]
    if scanned:
        ctx.warn(f"{len(scanned)} page(s) have no selectable text (scanned images); the page images were included instead. Enable OCR to recognize the text.")
    if ocr_pages:
        ctx.warn(f"OCR was used on {len(ocr_pages)} page(s); recognized text may contain errors and tables are not detected.")

    ir = DocumentIR(path.stem, source_format="pdf", header=header_text[:200], footer=footer_text[:200])
    for p in pages:
        if p.ocr_paragraphs:
            blocks: list[Block] = [Paragraph.plain(t) for t in p.ocr_paragraphs]
            blocks.extend(b for _t, b in sorted(p.extras, key=lambda x: x[0]))
        else:
            blocks = _interleave(_build_paragraphs(p.lines, body), p.extras)
        ir.sections.append(Section("page", f"Page {p.number}", blocks))
    return ir
