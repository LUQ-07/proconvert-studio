"""DOCX -> IR using python-docx.

Reads body paragraphs and tables in document order (including content controls),
run-level bold/italic, bullet and numbered lists (numbers restored from numbering.xml),
header/footer text, footnotes/endnotes (appended as a numbered "Notes" list) and
inline/anchored images. Tracked changes are
*accepted* (insertions kept, deletions dropped). Constructs that are not converted
(text boxes, equations, footnotes, headers/footers, nested tables) are detected and
reported as warnings rather than disappearing silently.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.context import READING, JobContext
from ..core.errors import ConversionError, DependencyMissingError, InvalidFileError, UnsafeFileError
from ..core.images import normalize_image
from ..core.ir import Block, DocumentIR, Paragraph, Run, Section, Table
from ..utils.text import clean_block, clean_inline

_HEADING = re.compile(r"(?i)^heading\s*(\d)")


def _local(el) -> str:
    tag = el.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _iter_blocks(parent, qn):
    for child in parent.iterchildren():
        name = _local(child)
        if name in ("p", "tbl"):
            yield name, child
        elif name == "sdt":
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _iter_blocks(content, qn)


class _StyleCache:
    """python-docx resolves styles with a linear scan on every call (very slow on big documents);
    resolve each style id once."""

    def __init__(self, doc) -> None:
        from docx.enum.style import WD_STYLE_TYPE
        self.styles, self.P, self.C = doc.styles, WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER
        self._pname: dict = {}
        self._cflags: dict = {}

    def paragraph_name(self, p_el) -> str:
        ppr = p_el.pPr
        sid = ppr.pStyle.val if ppr is not None and ppr.pStyle is not None else None
        if sid not in self._pname:
            try:
                st = self.styles.get_by_id(sid, self.P) if sid else self.styles.default(self.P)
                self._pname[sid] = (st.name or "") if st is not None else ""
            except Exception:
                self._pname[sid] = ""
        return self._pname[sid]

    def char_flags(self, r_el) -> tuple[bool, bool]:
        rpr = r_el.rPr
        sid = rpr.rStyle.val if rpr is not None and rpr.rStyle is not None else None
        if sid is None:
            return False, False
        if sid not in self._cflags:
            try:
                st = self.styles.get_by_id(sid, self.C)
                self._cflags[sid] = (bool(st.font.bold), bool(st.font.italic)) if st is not None else (False, False)
            except Exception:
                self._cflags[sid] = (False, False)
        return self._cflags[sid]


class _Numbering:
    """Resolves w:numId/w:ilvl to bullet vs ordered and keeps running counters per list."""

    def __init__(self, doc, qn) -> None:
        self.qn = qn
        self.formats: dict[tuple[str, int], tuple[str, int]] = {}   # (numId, ilvl) -> (numFmt, start)
        self.counters: dict[str, list[int]] = {}
        try:
            root = doc.part.numbering_part.element
        except Exception:
            return
        try:
            abstract: dict[str, dict[int, tuple[str, int]]] = {}
            for an in root.findall(qn("w:abstractNum")):
                lv = {}
                for lvl in an.findall(qn("w:lvl")):
                    fmt = lvl.find(qn("w:numFmt"))
                    st = lvl.find(qn("w:start"))
                    lv[int(lvl.get(qn("w:ilvl"), "0"))] = (
                        fmt.get(qn("w:val")) if fmt is not None else "decimal",
                        int(st.get(qn("w:val"))) if st is not None else 1)
                abstract[an.get(qn("w:abstractNumId"))] = lv
            for num in root.findall(qn("w:num")):
                aid = num.find(qn("w:abstractNumId"))
                if aid is None:
                    continue
                for ilvl, v in abstract.get(aid.get(qn("w:val")), {}).items():
                    self.formats[(num.get(qn("w:numId")), ilvl)] = v
        except Exception:
            self.formats = {}

    def next_number(self, num_id: str, ilvl: int) -> int | None:
        """Return the item number for an ordered list item, or None when the level is a bullet."""
        fmt, start = self.formats.get((num_id, ilvl), (None, 1))
        if fmt is None or fmt in ("bullet", "none"):
            return None
        counters = self.counters.setdefault(num_id, [0] * 9)
        ilvl = max(0, min(ilvl, 8))
        counters[ilvl] = (start - 1 if counters[ilvl] == 0 else counters[ilvl]) + 1
        for deeper in range(ilvl + 1, 9):
            counters[deeper] = 0
        return counters[ilvl]


def _part_text(el, qn) -> str:
    return " ".join("".join(t.text or "" for t in p.iter(qn("w:t"))).strip() for p in el.iter(qn("w:p"))).strip()


def _runs(p_el, para, DocxRun, styles: "_StyleCache") -> list[Run]:
    out: list[Run] = []
    for r_el in p_el.xpath(".//w:r[not(ancestor::w:del) and not(ancestor::w:txbxContent)]"):
        run = DocxRun(r_el, para)
        text = run.text
        if not text:
            continue
        text = text.replace("\r", "").replace("\n", " ")
        bold, italic = run.bold, run.italic
        if bold is None or italic is None:
            sb, si = styles.char_flags(r_el)
            bold = sb if bold is None else bold
            italic = si if italic is None else italic
        flags = (bool(bold), bool(italic))
        if out and (out[-1].bold, out[-1].italic) == flags:
            out[-1] = Run(out[-1].text + text, *flags)
        else:
            out.append(Run(text, *flags))
    return out


def _clean_runs(runs: list[Run]) -> list[Run]:
    """Normalise whitespace and control characters while keeping run boundaries."""
    result: list[Run] = []
    for r in runs:
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", r.text)
        t = re.sub(r"[ \t\u00a0]+", " ", t)
        if t:
            result.append(Run(t, r.bold, r.italic))
    if not result:
        return []
    result[0] = Run(result[0].text.lstrip(), result[0].bold, result[0].italic)
    result[-1] = Run(result[-1].text.rstrip(), result[-1].bold, result[-1].italic)
    result = [r for r in result if r.text]
    return result if "".join(r.text for r in result).strip() else []


def read_docx(path: Path, ctx: JobContext) -> DocumentIR:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph as DocxParagraph
        from docx.text.run import Run as DocxRun
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc

    try:
        doc = Document(str(path))
    except ConversionError:
        raise
    except Exception as exc:
        name = type(exc).__name__
        if "Entit" in name or "Forbidden" in name:
            raise UnsafeFileError("The document contains disallowed XML constructs.", technical=f"{name}: {exc}") from exc
        raise InvalidFileError("The Word document is damaged or uses an unsupported structure.", technical=f"{name}: {exc}") from exc

    styles = _StyleCache(doc)
    numbering = _Numbering(doc, qn)
    body = doc.element.body
    elements = list(_iter_blocks(body, qn))
    blocks: list[Block] = []
    cell_budget = ctx.limits.max_total_cells
    nested = 0
    style_counts: dict[str, int] = {}
    total = max(len(elements), 1)

    for i, (kind, el) in enumerate(elements):
        if i % 50 == 0:
            ctx.cancel.check()
            ctx.report(READING, i / total, f"Reading element {i + 1} of {total}")
        if kind == "p":
            para = DocxParagraph(el, doc._body)
            sname = styles.paragraph_name(el)
            low = sname.lower()
            m = _HEADING.match(sname)
            heading = min(int(m[1]), 3) if m else (1 if low == "title" else 2 if low == "subtitle" else 0)
            runs = _clean_runs(_runs(el, para, DocxRun, styles))
            ppr = el.pPr
            num = ppr.numPr if ppr is not None else None
            bullet = (num is not None) or low.startswith("list")
            number = None
            level = 0
            try:
                if num is not None and num.ilvl is not None:
                    level = int(num.ilvl.val)
                elif low[-1:].isdigit() and low.startswith("list"):
                    level = int(low[-1]) - 1
            except Exception:
                level = 0
            if num is not None and num.numId is not None and not heading:
                try:
                    number = numbering.next_number(str(num.numId.val), level)
                except Exception:
                    number = None
            elif low.startswith("list number") and not heading:
                # style-based numbering (no explicit numPr): one running counter per style name
                style_counts[low] = style_counts.get(low, 0) + 1
                number = style_counts[low]
            if runs:
                blocks.append(Paragraph(runs, heading=heading, bullet=bullet and not heading and number is None,
                                        level=max(0, min(level, 2)), number=number))
            if ctx.options.include_images:
                rids = el.xpath(".//a:blip/@r:embed")
                extents = el.xpath(".//wp:extent")
                for n, rid in enumerate(rids):
                    try:
                        part = doc.part.related_parts[rid]
                        w_pt = h_pt = None
                        if n < len(extents):
                            w_pt, h_pt = int(extents[n].get("cx")) / 12700, int(extents[n].get("cy")) / 12700
                        pic = normalize_image(part.blob, ctx, display_w_pt=w_pt, display_h_pt=h_pt)
                        if pic:
                            blocks.append(pic)
                    except (KeyError, ValueError, TypeError, AttributeError):
                        ctx.warn("An image could not be extracted from the document.")
        else:
            table = DocxTable(el, doc._body)
            rows: list[list[str]] = []
            # Walk <w:tr>/<w:tc> directly: python-docx's row.cells rebuilds the table grid per call (quadratic).
            for tr in el.tr_lst:
                cells: list[str] = []
                for tc in tr.tc_lst:
                    texts = []
                    for p_el in tc.p_lst:
                        cp = DocxParagraph(p_el, table)
                        texts.append("".join(r.text for r in _runs(p_el, cp, DocxRun, styles)))
                    cells.append(clean_inline(" ".join(texts)))
                    span = tc.grid_span
                    cells.extend([""] * (span - 1))          # keep the grid aligned for horizontally merged cells
                cell_budget -= len(cells)
                rows.append(cells)
                if cell_budget < 0:
                    ctx.warn("The document has more table cells than the safety limit; later cells were not converted.")
                    break
            if any(c for r in rows for c in r):
                width = max(len(r) for r in rows)
                blocks.append(Table([r + [""] * (width - len(r)) for r in rows]))
            nested += len(el.xpath(".//w:tc//w:tbl"))
            if cell_budget < 0:
                break

    # ---- report constructs that are not converted
    if nested:
        ctx.warn(f"{nested} nested table(s) are not converted (their text is omitted).")
    boxes = len(body.xpath(".//w:txbxContent")) // 2 or len(body.xpath(".//w:txbxContent"))
    if boxes:
        ctx.warn(f"{boxes} text box(es) are not converted.")
    eq = len(body.xpath(".//m:oMath"))
    if eq:
        ctx.warn(f"{eq} equation(s) are not converted.")
    if body.xpath(".//w:ins | .//w:del"):
        ctx.warn("The document contains tracked changes; all changes were accepted in the output.")
    notes = _read_notes(doc, qn)
    if notes:
        blocks.append(Paragraph.plain("Notes", heading=3))
        for i, (label, text) in enumerate(notes, 1):
            blocks.append(Paragraph.plain(text, number=i))
        ctx.warn(f"{len(notes)} footnote/endnote(s) were moved to a numbered 'Notes' list at the end of the document.")
    header = footer = ""
    try:
        for s_ in list(doc.sections)[:20]:
            header = header or _part_text(s_.header._element, qn)
            footer = footer or _part_text(s_.footer._element, qn)
            if header and footer:
                break
    except Exception:
        pass
    header, footer = clean_inline(header)[:200], clean_inline(footer)[:200]
    if header or footer:
        ctx.warn("Header/footer text is kept as running text where the output format supports it (Word, PDF); "
                 "page-number fields are replaced by the output's own page numbers.")

    ir = DocumentIR(path.stem, source_format="docx", header=header, footer=footer)
    ir.sections.append(Section("flow", "Document", blocks))
    return ir


def _read_notes(doc, qn) -> list[tuple[str, str]]:
    """Footnote and endnote text in id order (separators skipped). Never raises."""
    from lxml import etree
    out: list[tuple[str, str]] = []
    try:
        parts = {str(p.partname): p for p in doc.part.package.iter_parts()}
        for name, tag in (("/word/footnotes.xml", "w:footnote"), ("/word/endnotes.xml", "w:endnote")):
            part = parts.get(name)
            if part is None or len(part.blob) > 5_000_000:
                continue
            root = etree.fromstring(part.blob, etree.XMLParser(resolve_entities=False, no_network=True))
            for note in root.findall(qn(tag)):
                if note.get(qn("w:type")) in ("separator", "continuationSeparator", "continuationNotice"):
                    continue
                text = _part_text(note, qn)
                if text:
                    out.append((note.get(qn("w:id"), ""), text))
                if len(out) >= 2000:
                    return out
    except Exception:
        return out
    return out
