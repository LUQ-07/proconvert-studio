"""IR -> PPTX using python-pptx with an automatic, deliberately plain 16:9 layout.

Pagination is computed from estimated text height so text never silently overflows a slide:
content that does not fit continues on a new slide ("continued"). Headings of level 1-2 start
a new slide; tables are split by rows (header repeated) and by columns (first column repeated).
"""
from __future__ import annotations

import io
from math import ceil
from pathlib import Path

from ..core.context import WRITING, JobContext
from ..core.ir import DocumentIR, Paragraph, Picture, Section, Table
from ..utils.text import truncate, xml_safe

SLIDE_W, SLIDE_H = 13.333, 7.5   # inches
MARGIN = 0.6
TITLE_TOP, TITLE_H = 0.35, 0.9
BODY_TOP = 1.45
BODY_H = SLIDE_H - BODY_TOP - 0.45
BODY_W = SLIDE_W - 2 * MARGIN
MAX_COLS = 7
BODY_PT = 14.0     # dense converted documents: small enough to keep a section on few slides, still readable
SPACE_PT = 4


class _Deck:
    def __init__(self, ctx: JobContext) -> None:
        from pptx import Presentation
        from pptx.util import Inches

        self.ctx = ctx
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
        self.slide = None
        self.used_h = 0.0
        self.text_buf: list[Paragraph] = []
        self.title = ""
        self.cont = False
        self.capped = False
        self.cut_cells = 0
        self.rows_left = ctx.limits.max_pptx_table_rows
        self.rows_cut = False
        self.running_text = ""      # the source document's running header/footer, shown small at the bottom of each slide

    # -- slide management
    def new_slide(self, title: str, continued: bool = False) -> bool:
        from pptx.util import Inches, Pt

        self.flush_text()
        if len(self.prs.slides) >= self.ctx.limits.max_pptx_slides:
            self.capped = True
            self.slide = None
            return False
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[5])  # "Title Only"
        t = self.slide.shapes.title
        t.left, t.top, t.width, t.height = Inches(MARGIN), Inches(TITLE_TOP), Inches(BODY_W), Inches(TITLE_H)
        text = xml_safe(title or "Untitled")
        t.text_frame.text = text + (" (continued)" if continued else "")
        t.text_frame.word_wrap = True
        for p in t.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(28 if len(text) <= 50 else 22 if len(text) <= 90 else 18)
                r.font.bold = True
        self.title, self.used_h = title, 0.0
        if self.running_text:
            from pptx.dml.color import RGBColor
            box = self.slide.shapes.add_textbox(Inches(MARGIN), Inches(SLIDE_H - 0.4), Inches(BODY_W), Inches(0.3))
            run = box.text_frame.paragraphs[0].add_run()
            run.text = self.running_text
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x70, 0x70, 0x70)
        return True

    @property
    def is_empty(self) -> bool:
        """The current slide has a title but no content yet."""
        return self.slide is not None and self.used_h == 0.0 and not self.text_buf

    def remaining(self) -> float:
        return BODY_H - self.used_h

    def ensure_slide(self) -> bool:
        if self.slide is None:
            return self.new_slide(self.title, continued=True)
        return True

    # -- text
    @staticmethod
    def para_height(p: Paragraph, fsize: float) -> float:
        chars_per_line = max(20, int(BODY_W * 72 / (fsize * 0.52)))
        lines = max(1, ceil(max(len(p.text), 1) / chars_per_line))
        return (lines * fsize * 1.25 + SPACE_PT) / 72

    def add_paragraph(self, p: Paragraph) -> None:
        fsize = BODY_PT
        for chunk in self._split(p, fsize):
            h = self.para_height(chunk, fsize)
            if self.slide is None or h > self.remaining():
                if not self.new_slide(self.title, continued=True):
                    return
            self.text_buf.append(chunk)
            self.used_h += h

    def _split(self, p: Paragraph, fsize: float):
        limit_lines = int((BODY_H * 0.9 * 72) / (fsize * 1.25))
        chars_per_line = max(20, int(BODY_W * 72 / (fsize * 0.52)))
        max_chars = limit_lines * chars_per_line
        if len(p.text) <= max_chars:
            yield p
            return
        words, cur = p.text.split(" "), ""
        for w in words:
            if len(cur) + len(w) + 1 > max_chars:
                yield Paragraph.plain(cur.strip(), bullet=p.bullet, level=p.level, number=p.number)
                cur = ""
            cur += w + " "
        if cur.strip():
            yield Paragraph.plain(cur.strip(), bullet=p.bullet, level=p.level, number=p.number)

    def flush_text(self) -> None:
        from pptx.util import Inches, Pt

        if not self.text_buf or self.slide is None:
            self.text_buf = []
            return
        used_before = self.used_h - sum(self.para_height(p, BODY_PT) for p in self.text_buf)
        top = BODY_TOP + max(used_before, 0.0)
        height = max(sum(self.para_height(p, BODY_PT) for p in self.text_buf), 0.4)
        box = self.slide.shapes.add_textbox(Inches(MARGIN), Inches(top), Inches(BODY_W), Inches(height))
        tf = box.text_frame
        tf.word_wrap = True
        for i, p in enumerate(self.text_buf):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            indent = "    " * p.level
            prefix = f"{p.number}. " if p.number is not None else "\u2022 " if p.bullet else ""
            if indent or prefix:
                r0 = para.add_run()
                r0.text = indent + prefix
                r0.font.size = Pt(BODY_PT)
            for r in p.runs:
                run = para.add_run()
                run.text = xml_safe(r.text)
                run.font.size = Pt(BODY_PT)
                run.font.bold = r.bold or None
                run.font.italic = r.italic or None
            para.space_after = Pt(SPACE_PT)
        self.text_buf = []

    # -- tables
    def add_table(self, tbl: Table) -> None:
        from pptx.util import Inches, Pt

        rows = tbl.rows
        if len(rows) > self.rows_left:
            rows, self.rows_cut = rows[: self.rows_left], True
        self.rows_left -= len(rows)
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        col_groups = [list(range(ncols))] if ncols <= MAX_COLS else None
        if col_groups is None:
            rest = list(range(1, ncols))
            step = MAX_COLS - 1
            col_groups = [[0] + rest[i:i + step] for i in range(0, len(rest), step)]
        fsize = 12 if max(len(g) for g in col_groups) <= 5 else 10
        row_h = (fsize * 2.1) / 72
        header = rows[0] if tbl.header else None
        body = rows[1:] if tbl.header else rows
        for g_i, cols in enumerate(col_groups):
            idx = 0
            first = True
            while idx < len(body) or (first and not body):
                self.flush_text()
                min_h = row_h * (3 if header else 2)
                if self.slide is None or self.remaining() < min_h:
                    if not self.new_slide(self.title, continued=True):
                        return
                fit = int(self.remaining() / row_h) - (1 if header else 0)
                fit = max(fit, 1)
                chunk = body[idx: idx + fit]
                data = ([header] if header else []) + chunk
                tbl_h = row_h * len(data)
                shape = self.slide.shapes.add_table(len(data), len(cols), Inches(MARGIN), Inches(BODY_TOP + self.used_h),
                                                    Inches(BODY_W), Inches(tbl_h))
                t = shape.table
                for ri, row in enumerate(data):
                    for ci, col in enumerate(cols):
                        text = xml_safe(row[col]) if col < len(row) else ""
                        if len(text) > self.ctx.limits.max_cell_chars_pptx:
                            text = truncate(text, self.ctx.limits.max_cell_chars_pptx)
                            self.cut_cells += 1
                        cell = t.cell(ri, ci)
                        cell.text = text
                        for p in cell.text_frame.paragraphs:
                            for r in p.runs:
                                r.font.size = Pt(fsize)
                                r.font.bold = True if (header and ri == 0) else None
                    t.rows[ri].height = Inches(row_h)
                self.used_h += tbl_h + 0.15
                idx += len(chunk)
                first = False
                if idx < len(body):
                    self.slide = None  # remaining rows continue on a fresh slide
            if g_i < len(col_groups) - 1:
                self.slide = None

    # -- pictures
    def add_picture(self, pic: Picture) -> None:
        from pptx.util import Inches

        self.flush_text()
        w = (pic.display_w_pt or pic.width_px * 0.75) / 72
        h = (pic.display_h_pt or pic.height_px * 0.75) / 72
        if w <= 0 or h <= 0:
            return
        if self.slide is None or self.remaining() < min(h, BODY_H) * 0.6 or self.remaining() < 1.0:
            if not self.new_slide(self.title, continued=True):
                return
        avail_h = self.remaining()
        s = min(1.0, BODY_W / w, avail_h / h)
        w, h = w * s, h * s
        try:
            self.slide.shapes.add_picture(io.BytesIO(pic.data), Inches(MARGIN + (BODY_W - w) / 2), Inches(BODY_TOP + self.used_h), Inches(w), Inches(h))
            self.used_h += h + 0.15
        except Exception:
            self.ctx.warn("An image could not be added to the presentation.")


def write_pptx(ir: DocumentIR, path: Path, ctx: JobContext) -> None:
    deck = _Deck(ctx)
    deck.running_text = " - ".join(t for t in (ir.header, ir.footer) if t)[:150]
    doc_title = ir.title.replace("_", " ").strip() or ir.title
    n = max(len(ir.sections), 1)
    for si, sec in enumerate(ir.sections):
        ctx.cancel.check()
        ctx.report(WRITING, si / n, f"Building slides for {sec.label}")
        if deck.capped:
            break
        if sec.kind == "page" and si > 0:
            started = deck.slide is not None      # PDF pages are not slides: the text flows on under the last heading
        else:
            deck.title = doc_title if sec.kind in ("flow", "page") else sec.label
            deck.slide = None   # sheets, slides and the first page start a fresh slide
            started = False
        for bi, b in enumerate(sec.blocks):
            if bi % 100 == 0:
                ctx.cancel.check()
            if deck.capped:
                break
            if isinstance(b, Paragraph) and b.text.strip():
                if b.heading and b.heading <= 2:
                    if started and deck.is_empty:
                        # a heading straight after a heading (e.g. title + subtitle on a cover): no empty slide
                        deck.add_paragraph(Paragraph([type(b.runs[0])(b.text.strip(), bold=True)]))
                        continue
                    if not deck.new_slide(b.text.strip()):
                        break
                    started = True
                    continue
                if b.heading:  # level 3 -> bold body text
                    b = Paragraph([type(b.runs[0])(b.text, bold=True)])
                if not started and deck.slide is None:
                    if not deck.new_slide(deck.title):
                        break
                    started = True
                deck.add_paragraph(b)
            elif isinstance(b, Table):
                if not started and deck.slide is None:
                    if not deck.new_slide(deck.title):
                        break
                    started = True
                deck.add_table(b)
            elif isinstance(b, Picture):
                if not started and deck.slide is None:
                    if not deck.new_slide(deck.title):
                        break
                    started = True
                deck.add_picture(b)
        deck.flush_text()
    deck.flush_text()
    if len(deck.prs.slides) == 0:
        deck.new_slide(ir.title)
    if deck.capped:
        ctx.warn(f"Output was limited to {ctx.limits.max_pptx_slides} slides.")
    if deck.rows_cut:
        ctx.warn(f"Table output was limited to {ctx.limits.max_pptx_table_rows} rows.")
    if deck.cut_cells:
        ctx.warn(f"{deck.cut_cells} long table cell(s) were shortened to fit on slides.")
    ctx.report(WRITING, 0.95, "Saving presentation")
    deck.prs.save(str(path))
