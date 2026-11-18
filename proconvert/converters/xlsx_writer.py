"""IR -> XLSX using openpyxl.

Security: every text value is stored as a *string cell* so text beginning with "=", "+", "-"
or "@" can never be evaluated as a formula by a spreadsheet application. Only unambiguous
plain numbers are written as numbers.
"""
from __future__ import annotations

import io
import re
from math import ceil
from pathlib import Path

from ..core.context import WRITING, JobContext
from ..core.ir import DocumentIR, Paragraph, Picture, Section, Table
from ..utils.text import parse_plain_number, xml_safe

_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")


def sheet_name(raw: str, used: set[str]) -> str:
    name = _BAD_SHEET.sub("_", xml_safe(raw)).strip().strip("'") or "Sheet"
    name = name[:31]
    base, n = name, 1
    while name.lower() in used:
        n += 1
        suffix = f" ({n})"
        name = base[: 31 - len(suffix)] + suffix
    used.add(name.lower())
    return name


def _put(ws, row: int, col: int, text: str, *, numbers: bool = True):
    text = xml_safe(text)[:32767]
    cell = ws.cell(row=row, column=col)
    num = parse_plain_number(text) if numbers else None
    if num is not None:
        cell.value = num
    else:
        cell.value = text
        cell.data_type = "s"  # never a formula, even when the text starts with "="
    return cell


def write_xlsx(ir: DocumentIR, path: Path, ctx: JobContext) -> None:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E3E8F2")
    wrap = Alignment(wrap_text=True, vertical="top")

    def write_table(ws, start_row: int, tbl: Table) -> int:
        r = start_row
        for ri, row in enumerate(tbl.rows):
            for ci, text in enumerate(row, 1):
                if not text:
                    continue
                cell = _put(ws, r, ci, text)
                if tbl.header and ri == 0:
                    cell.font, cell.fill = head_font, head_fill
            r += 1
        return r

    def write_blocks(ws, blocks, *, table_note_sheets: dict[int, str] | None = None) -> bool:
        r = 1
        wrote_table_first = bool(blocks) and isinstance(blocks[0], Table)
        max_para = 0
        for bi, b in enumerate(blocks):
            if isinstance(b, Paragraph):
                if not b.text.strip():
                    continue
                prefix = f"{b.number}. " if b.number is not None else "\u2022 " if b.bullet else ""
                c = _put(ws, r, 1, prefix + b.text, numbers=False)
                if b.heading or any(x.bold for x in b.runs):
                    c.font = Font(bold=True, size=13 if b.heading == 1 else 11)
                c.alignment = wrap
                max_para = max(max_para, len(b.text))
                r += 1
            elif isinstance(b, Table):
                if table_note_sheets is not None:
                    c = _put(ws, r, 1, f"[Table - see sheet '{table_note_sheets[id(b)]}']", numbers=False)
                    c.font = Font(italic=True)
                    r += 1
                else:
                    r = write_table(ws, r, b) + 1
            elif isinstance(b, Picture):
                try:
                    img = XLImage(io.BytesIO(b.data))
                    s = min(1.0, 600 / max(img.width, 1))
                    img.width, img.height = int(img.width * s), int(img.height * s)
                    ws.add_image(img, f"A{r}")
                    r += ceil(img.height / 20) + 1
                except Exception:
                    ctx.warn("An image could not be added to the workbook.")
        if max_para:
            ws.column_dimensions["A"].width = 90 if not wrote_table_first else 40
        return wrote_table_first

    n = max(len(ir.sections), 1)
    for si, sec in enumerate(ir.sections):
        ctx.cancel.check()
        ctx.report(WRITING, si / n, f"Writing {sec.label}")
        if sec.kind == "flow":
            tables = [b for b in sec.blocks if isinstance(b, Table)]
            names: dict[int, str] = {}
            for t_i, t in enumerate(tables, 1):
                names[id(t)] = sheet_name(f"Table {t_i}", used)
            text_blocks = [b for b in sec.blocks if not isinstance(b, Table) or tables]
            has_text = any((isinstance(b, Paragraph) and b.text.strip()) or isinstance(b, Picture) for b in sec.blocks)
            if has_text or not tables:
                ws = wb.create_sheet(sheet_name("Document", used))
                write_blocks(ws, sec.blocks, table_note_sheets=names)
            for t in tables:
                ws = wb.create_sheet(names[id(t)])
                write_table(ws, 1, t)
                if t.header:
                    ws.freeze_panes = "A2"
            del text_blocks
        else:
            ws = wb.create_sheet(sheet_name(sec.label, used))
            first_table = write_blocks(ws, sec.blocks)
            if first_table and isinstance(sec.blocks[0], Table) and sec.blocks[0].header:
                ws.freeze_panes = "A2"
    if not wb.sheetnames:
        wb.create_sheet("Sheet1")
    for ws in wb.worksheets:
        widths: dict[int, int] = {}
        for row in ws.iter_rows(max_row=min(ws.max_row, 300)):
            for c in row:
                if isinstance(c.value, str):
                    widths[c.column] = max(widths.get(c.column, 0), min(len(c.value), 60))
                elif c.value is not None:
                    widths[c.column] = max(widths.get(c.column, 0), min(len(str(c.value)), 20))
        for col, w in widths.items():
            letter = ws.cell(row=1, column=col).column_letter
            if ws.column_dimensions[letter].width in (None, 13) or ws.column_dimensions[letter].width < w + 2:
                ws.column_dimensions[letter].width = max(8, min(w + 2, 90))
    ctx.report(WRITING, 0.95, "Saving workbook")
    wb.save(str(path))
