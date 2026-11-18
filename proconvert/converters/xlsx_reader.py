"""XLSX -> IR using openpyxl in read-only (streaming) mode.

Values are the *stored* results (workbook opened with ``data_only=True``) formatted with the
cell's number format for common cases. When formulas exist, a second streaming pass detects
formula cells that have no stored result so the user is told instead of receiving blanks
silently. Charts, pivots and images are detected and reported, not converted.
"""
from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from ..core.context import READING, JobContext
from ..core.errors import ConversionError, DependencyMissingError, InvalidFileError, UnsafeFileError
from ..core.ir import DocumentIR, Section, Table
from ..utils.text import clean_inline

_STRIP_LITERALS = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.')
_CURRENCY = re.compile(r"\[\$([^\]\-]*)(?:-[^\]]*)?\]|([$€£¥])")


def _general(v) -> str:
    if isinstance(v, int):
        return str(v)
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.10g}"


def format_number(v, fmt: str | None) -> str:
    """Apply the common Excel number formats; anything exotic falls back to General."""
    if not fmt or fmt in ("General", "@"):
        return _general(v)
    section = fmt.split(";")[0]
    bare = _STRIP_LITERALS.sub("", section)
    if not any(ch in bare for ch in "0#?") or re.search(r"[eE][+-]", bare):
        return _general(v)
    percent = "%" in bare
    m = re.search(r"\.([0#?]+)", bare)
    decimals = len(m.group(1)) if m else 0
    int_part = bare.split(".")[0]
    thousands = bool(re.search(r"[0#?],[0#?]", int_part))
    x = v * 100 if percent else v
    body = f"{abs(x):,.{decimals}f}" if thousands else f"{abs(x):.{decimals}f}"
    sign = "-" if x < 0 and float(body.replace(",", "")) != 0 else ""
    cur = _CURRENCY.search(section)
    symbol = (cur.group(1) or cur.group(2) or "") if cur else ""
    prefix = suffix = ""
    if symbol:
        first_digit = min((section.find(c) for c in "0#?" if c in section), default=0)
        if cur.start() <= first_digit:
            prefix = symbol
        else:
            suffix = " " + symbol
    return f"{sign}{prefix}{body}{'%' if percent else ''}{suffix}"


def format_value(v, fmt: str | None = None) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if v.time() == time(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, timedelta):
        secs = int(v.total_seconds())
        return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    if isinstance(v, (int, float)):
        return format_number(v, fmt)
    return clean_inline(v)


def _has_formulas(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    tail = b""
                    with zf.open(name) as fh:
                        while chunk := fh.read(1 << 20):
                            blob = tail + chunk
                            if b"<f>" in blob or b"<f " in blob:
                                return True
                            tail = blob[-3:]
    except Exception:
        return False
    return False


def _drawing_counts(path: Path) -> tuple[int, int, int]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except Exception:
        return 0, 0, 0
    charts = sum(1 for n in names if n.startswith("xl/charts/chart") and n.endswith(".xml"))
    media = sum(1 for n in names if n.startswith("xl/media/"))
    pivots = sum(1 for n in names if n.startswith("xl/pivotTables/") and n.endswith(".xml"))
    return charts, media, pivots


def read_xlsx(path: Path, ctx: JobContext) -> DocumentIR:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc

    track_formulas = _has_formulas(path)
    wb_v = wb_f = None
    try:
        wb_v = load_workbook(str(path), read_only=True, data_only=True)
        wb_f = load_workbook(str(path), read_only=True, data_only=False) if track_formulas else None
        sheets_v = list(wb_v.worksheets)
        ir = DocumentIR(path.stem, source_format="xlsx")
        hidden = empty = uncached = 0
        truncated: list[str] = []
        cells_left = ctx.limits.max_total_cells
        for si, ws in enumerate(sheets_v):
            ctx.cancel.check()
            ctx.report(READING, si / max(len(sheets_v), 1), f"Sheet '{ws.title}' ({si + 1} of {len(sheets_v)})")
            if getattr(ws, "sheet_state", "visible") != "visible":
                hidden += 1
                continue
            wf = wb_f[ws.title] if wb_f is not None else None
            f_iter = wf.iter_rows(values_only=True) if wf is not None else None
            rows: list[list[str]] = []
            for ri, vrow in enumerate(ws.iter_rows()):
                frow = next(f_iter, None) if f_iter is not None else None
                if ri % 500 == 0:
                    ctx.cancel.check()
                texts: list[str] = []
                for ci, cell in enumerate(vrow):
                    val = cell.value
                    if val is None:
                        if frow is not None and ci < len(frow) and isinstance(frow[ci], str) and frow[ci].startswith("="):
                            uncached += 1
                        texts.append("")
                    else:
                        texts.append(format_value(val, getattr(cell, "number_format", None)))
                while texts and not texts[-1]:
                    texts.pop()
                if not texts:
                    continue
                if len(rows) >= ctx.limits.max_sheet_rows or cells_left <= 0:
                    truncated.append(ws.title)
                    break
                cells_left -= len(texts)
                rows.append(texts)
            if not rows:
                empty += 1
                continue
            width = max(len(r) for r in rows)
            used = [i for i in range(width) if any(i < len(r) and r[i] for r in rows)]
            grid = [[(r[i] if i < len(r) else "") for i in used] for r in rows]
            ir.sections.append(Section("sheet", ws.title, [Table(grid)]))
    except ConversionError:
        raise
    except Exception as exc:
        name = type(exc).__name__
        if "Entit" in name or "Forbidden" in name or "DTD" in name:
            raise UnsafeFileError("The workbook contains disallowed XML constructs.", technical=f"{name}: {exc}") from exc
        raise InvalidFileError("The Excel file is damaged or uses an unsupported structure.", technical=f"{name}: {exc}") from exc
    finally:
        for wb in (wb_v, wb_f):
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    if truncated:
        ctx.warn(f"Sheet(s) {', '.join(sorted(set(truncated)))} exceeded the row/cell safety limit; only the first part was converted.")
    if uncached:
        ctx.warn(f"{uncached} formula cell(s) have no stored result (the workbook was not calculated and saved by a spreadsheet application) and appear empty.")
    if hidden:
        ctx.warn(f"{hidden} hidden sheet(s) were skipped.")
    if empty:
        ctx.warn(f"{empty} empty sheet(s) were skipped.")
    charts, media, pivots = _drawing_counts(path)
    if charts:
        ctx.warn(f"{charts} chart(s) are not converted.")
    if media:
        ctx.warn(f"{media} image(s) in the workbook are not converted.")
    if pivots:
        ctx.warn(f"{pivots} pivot table(s) are converted as plain values only.")
    return ir
