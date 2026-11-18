"""IR -> PDF using ReportLab Platypus (BSD) and the bundled DejaVu Sans fonts.

Real progress: ReportLab reports each laid-out flowable through ``afterFlowable``, which is
used for both the progress fraction and cancellation checks. Characters the bundled font
cannot draw are replaced with "?" and *counted in a warning*; right-to-left text is detected
and reported because ReportLab does not perform bidirectional shaping.
"""
from __future__ import annotations

import io
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

from ..core.context import WRITING, JobContext
from ..core.ir import DocumentIR, Paragraph, Picture, Table
from ..utils.paths import resource_path
from ..utils.text import xml_safe

_FONTS_READY = False
FONT = "PCSans"


def register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    base = resource_path("assets/fonts")
    for name, file in (("PCSans", "DejaVuSans.ttf"), ("PCSans-Bold", "DejaVuSans-Bold.ttf"),
                       ("PCSans-Italic", "DejaVuSans-Oblique.ttf"), ("PCSans-BoldItalic", "DejaVuSans-BoldOblique.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(base / file)))
    pdfmetrics.registerFontFamily("PCSans", normal="PCSans", bold="PCSans-Bold",
                                  italic="PCSans-Italic", boldItalic="PCSans-BoldItalic")
    _FONTS_READY = True


class _Sanitizer:
    """Replace characters the PDF font cannot render; remember what happened."""

    def __init__(self) -> None:
        from reportlab.pdfbase import pdfmetrics

        self.cmap = pdfmetrics.getFont(FONT).face.charToGlyph
        self.replaced = 0
        self.saw_rtl = False

    def __call__(self, text: str) -> str:
        text = xml_safe(text)
        if text.isascii():
            return text
        out = []
        for ch in text:
            o = ord(ch)
            if o in self.cmap or ch in "\t\n":
                if unicodedata.bidirectional(ch) in ("R", "AL"):
                    self.saw_rtl = True
                out.append(ch)
                continue
            cat = unicodedata.category(ch)
            if cat == "Cf":
                continue
            if cat == "Zs":
                out.append(" ")
                continue
            self.replaced += 1
            out.append("?")
        return "".join(out)


def _markup(runs, san: _Sanitizer) -> str:
    parts = []
    for r in runs:
        t = escape(san(r.text))
        if not t:
            continue
        if r.bold:
            t = f"<b>{t}</b>"
        if r.italic:
            t = f"<i>{t}</i>"
        parts.append(t)
    return "".join(parts)


def write_pdf(ir: DocumentIR, path: Path, ctx: JobContext) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, LETTER, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Image, KeepTogether, LongTable, PageBreak
    from reportlab.platypus import Paragraph as RLParagraph
    from reportlab.platypus import SimpleDocTemplate, Spacer
    from reportlab.platypus import Table as RLTable
    from reportlab.platypus import TableStyle

    register_fonts()
    san = _Sanitizer()
    size = LETTER if ctx.options.page_size == "Letter" else A4
    wide = any(isinstance(b, Table) and b.n_cols > 8 for b in ir.iter_blocks())
    pw, ph = landscape(size) if wide else size
    margin = 48.0
    frame_w, frame_h = pw - 2 * margin, ph - 2 * margin

    body = ParagraphStyle("body", fontName=FONT, fontSize=10, leading=14, spaceAfter=6, splitLongWords=1)
    heads = {
        1: ParagraphStyle("h1", parent=body, fontName="PCSans-Bold", fontSize=20, leading=25, spaceBefore=10, spaceAfter=10, keepWithNext=1),
        2: ParagraphStyle("h2", parent=body, fontName="PCSans-Bold", fontSize=16, leading=20, spaceBefore=8, spaceAfter=8, keepWithNext=1),
        3: ParagraphStyle("h3", parent=body, fontName="PCSans-Bold", fontSize=12.5, leading=16, spaceBefore=6, spaceAfter=6, keepWithNext=1),
    }
    caption = ParagraphStyle("cap", parent=body, fontSize=8, textColor=colors.Color(0.4, 0.4, 0.4), spaceAfter=4)

    story: list = []
    table_rows_left = ctx.limits.max_pdf_table_rows
    trimmed_cells = 0
    row_cut = False

    def table_flow(tbl: Table):
        nonlocal table_rows_left, trimmed_cells, row_cut
        rows = tbl.rows
        if len(rows) > table_rows_left:
            rows = rows[:table_rows_left]
            row_cut = True
        table_rows_left -= len(rows)
        if not rows:
            return None
        ncols = max(len(r) for r in rows)
        fsize = 9 if ncols <= 6 else 8 if ncols <= 10 else 7 if ncols <= 14 else 6
        leading = fsize * 1.25
        sample = rows[:200]
        weights = []
        for c in range(ncols):
            longest = max((len(r[c]) for r in sample if c < len(r)), default=1)
            weights.append(min(max(longest, 4), 40))
        total_w = sum(weights)
        widths = [max(frame_w * w / total_w, 30.0) for w in weights]
        scale = frame_w / sum(widths)
        widths = [w * scale for w in widths]
        cell_style = ParagraphStyle("cell", parent=body, fontSize=fsize, leading=leading, spaceAfter=0)
        head_style = ParagraphStyle("head", parent=cell_style, fontName="PCSans-Bold")
        data = []
        for ri, row in enumerate(rows):
            out = []
            for ci in range(ncols):
                text = san(row[ci] if ci < len(row) else "")
                max_chars = max(20, int((frame_h * 0.7 / leading) * ((widths[ci] - 8) / (fsize * 0.52))))
                max_chars = min(max_chars, ctx.limits.max_cell_chars_pdf)
                if len(text) > max_chars:
                    text = text[: max_chars - 1] + "\u2026"
                    trimmed_cells += 1
                is_head = tbl.header and ri == 0
                plain_limit = int((widths[ci] - 8) / (fsize * 0.58))
                if is_head or len(text) > plain_limit or "\n" in text:
                    out.append(RLParagraph(escape(text), head_style if is_head else cell_style))
                else:
                    out.append(text)
            data.append(out)
        cls = LongTable if len(data) > 100 else RLTable
        t = cls(data, colWidths=widths, repeatRows=1 if tbl.header else 0)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), fsize),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.65, 0.68, 0.72)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ROWBACKGROUNDS", (0, 1 if tbl.header else 0), (-1, -1), [colors.white, colors.Color(0.96, 0.97, 0.98)]),
        ]
        if tbl.header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.91, 0.96)))
        t.setStyle(TableStyle(style))
        return t

    def picture_flow(pic: Picture):
        w = pic.display_w_pt or pic.width_px * 0.75
        h = pic.display_h_pt or pic.height_px * 0.75
        if w <= 0 or h <= 0:
            return None
        s = min(1.0, frame_w * 0.98 / w, frame_h * 0.85 / h)
        img = Image(io.BytesIO(pic.data), width=w * s, height=h * s)
        img.hAlign = "CENTER"
        return KeepTogether([img, Spacer(1, 6)])

    n_sections = max(len(ir.sections), 1)
    for si, sec in enumerate(ir.sections):
        ctx.cancel.check()
        ctx.report(WRITING, 0.3 * si / n_sections, f"Preparing {sec.label}")
        if si > 0:
            story.append(PageBreak())
        if sec.kind == "sheet":
            story.append(RLParagraph(escape(san(sec.label)), heads[2]))
        elif sec.kind == "slide" and not any(isinstance(b, Paragraph) and b.heading for b in sec.blocks):
            story.append(RLParagraph(escape(san(sec.label)), caption))
        for block in sec.blocks:
            if isinstance(block, Paragraph):
                markup = _markup(block.runs, san)
                if not markup.strip():
                    continue
                if block.heading:
                    story.append(RLParagraph(markup, heads[min(block.heading, 3)]))
                elif block.number is not None:
                    st = ParagraphStyle("ol", parent=body, leftIndent=22 + 14 * block.level, bulletIndent=2 + 14 * block.level, spaceAfter=3)
                    story.append(RLParagraph(markup, st, bulletText=f"{block.number}."))
                elif block.bullet:
                    st = ParagraphStyle("li", parent=body, leftIndent=16 + 14 * block.level, bulletIndent=4 + 14 * block.level, spaceAfter=3)
                    story.append(RLParagraph(markup, st, bulletText="\u2022"))
                else:
                    story.append(RLParagraph(markup, body))
            elif isinstance(block, Table):
                flow = table_flow(block)
                if flow is not None:
                    story.append(flow)
                    story.append(Spacer(1, 8))
            elif isinstance(block, Picture):
                flow = picture_flow(block)
                if flow is not None:
                    story.append(flow)
    if not story:
        story.append(RLParagraph(" ", body))

    class _Doc(SimpleDocTemplate):
        n = 0

        def afterFlowable(self, flowable):  # noqa: N802 (ReportLab hook name)
            _Doc.n += 1
            if _Doc.n % 25 == 0:
                ctx.cancel.check()
                ctx.report(WRITING, 0.3 + 0.7 * _Doc.n / max(len(story), 1), f"Laying out page {self.page}")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillGray(0.45)
        canvas.drawCentredString(pw / 2, 26, str(doc.page))
        if ir.header:
            canvas.drawString(margin, ph - margin + 18, san(ir.header)[:150])
        if ir.footer:
            canvas.drawString(margin, 26, san(ir.footer)[:150])
        canvas.restoreState()

    doc = _Doc(str(path), pagesize=(pw, ph), leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
               title=san(ir.title)[:200], author="", creator="ProConvert Studio", subject="")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    if san.replaced:
        ctx.warn(f"{san.replaced} character(s) cannot be drawn with the built-in PDF font (for example CJK) and were replaced with '?'.")
    if san.saw_rtl:
        ctx.warn("Right-to-left text (Arabic/Hebrew) is not shaped correctly in PDF output; it may appear reversed or disconnected.")
    if trimmed_cells:
        ctx.warn(f"{trimmed_cells} very long table cell(s) were shortened to fit on a page.")
    if row_cut:
        ctx.warn(f"Table output was limited to {ctx.limits.max_pdf_table_rows:,} rows.")
