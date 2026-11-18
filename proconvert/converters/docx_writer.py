"""IR -> DOCX using python-docx (default template styles)."""
from __future__ import annotations

import io
from pathlib import Path

from ..core.context import WRITING, JobContext
from ..core.ir import DocumentIR, Paragraph, Picture, Table
from ..utils.text import xml_safe


def _shade(cell, hex_fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def write_docx(ir: DocumentIR, path: Path, ctx: JobContext) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Inches, Pt
    from docx.table import _Cell

    doc = Document()
    doc.core_properties.title = xml_safe(ir.title)[:200]
    doc.core_properties.author = ""
    doc.core_properties.comments = "Created with ProConvert Studio"
    wide = any(isinstance(b, Table) and b.n_cols > 8 for b in ir.iter_blocks())
    sec0 = doc.sections[0]
    if wide:
        sec0.orientation = WD_ORIENT.LANDSCAPE
        sec0.page_width, sec0.page_height = sec0.page_height, sec0.page_width
    for side in ("left_margin", "right_margin"):
        setattr(sec0, side, Inches(0.8))
    if ir.header:
        sec0.header.paragraphs[0].text = xml_safe(ir.header)
    if ir.footer:
        sec0.footer.paragraphs[0].text = xml_safe(ir.footer)
    max_w = (sec0.page_width - sec0.left_margin - sec0.right_margin)
    rows_left = ctx.limits.max_docx_table_rows
    row_cut = False
    n = max(len(ir.sections), 1)

    for si, sec in enumerate(ir.sections):
        ctx.cancel.check()
        ctx.report(WRITING, si / n, f"Writing {sec.label}")
        if si > 0 and sec.kind in ("slide", "sheet"):
            doc.add_page_break()
        has_heading = any(isinstance(b, Paragraph) and b.heading for b in sec.blocks)
        if sec.kind == "sheet" or (sec.kind == "slide" and not has_heading):
            doc.add_heading(xml_safe(sec.label)[:200], level=2 if sec.kind == "slide" else 1)
        for bi, block in enumerate(sec.blocks):
            if bi % 200 == 0:
                ctx.cancel.check()
            if isinstance(block, Paragraph):
                if block.heading:
                    doc.add_heading(xml_safe(block.text), level=min(block.heading, 3))
                    continue
                style = None
                if block.bullet:
                    style = "List Bullet" if block.level == 0 else f"List Bullet {block.level + 1}"
                p = doc.add_paragraph(style=style)
                if block.number is not None:
                    # explicit numbers: python-docx's template shares one counter across all "List Number" paragraphs
                    p.paragraph_format.left_indent = Pt(18 + 14 * block.level)
                    p.paragraph_format.first_line_indent = Pt(-18)
                    p.add_run(f"{block.number}.\t")
                for r in block.runs:
                    run = p.add_run(xml_safe(r.text))
                    run.bold = r.bold or None
                    run.italic = r.italic or None
            elif isinstance(block, Table):
                rows = block.rows
                if len(rows) > rows_left:
                    rows, row_cut = rows[:rows_left], True
                rows_left -= len(rows)
                if not rows:
                    continue
                ncols = max(len(r) for r in rows)
                t = doc.add_table(rows=len(rows), cols=ncols)
                t.style = "Table Grid"
                fsize = Pt(10 if ncols <= 5 else 8.5 if ncols <= 8 else 7.5)
                # python-docx's row.cells rebuilds the whole grid per call (quadratic); address <w:tc> directly.
                trs = list(t._tbl.tr_lst)
                for ri, row in enumerate(rows):
                    tcs = trs[ri].tc_lst
                    for ci in range(ncols):
                        cell = _Cell(tcs[ci], t)
                        text = xml_safe(row[ci]) if ci < len(row) else ""
                        para = cell.paragraphs[0]
                        run = para.add_run(text)
                        run.font.size = fsize
                        if block.header and ri == 0:
                            run.bold = True
                            _shade(cell, "E3E8F2")
                doc.add_paragraph()
            elif isinstance(block, Picture):
                w_emu = int((block.display_w_pt or block.width_px * 0.75) * 12700)
                w_emu = min(w_emu, int(max_w))
                try:
                    doc.add_picture(io.BytesIO(block.data), width=w_emu)
                except Exception:
                    ctx.warn("An image could not be added to the Word document.")
    if row_cut:
        ctx.warn(f"Table output was limited to {ctx.limits.max_docx_table_rows:,} rows.")
    ctx.report(WRITING, 0.95, "Saving document")
    doc.save(str(path))
