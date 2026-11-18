"""Independent plain-text extraction from the four formats (used for verification and tests)."""
from __future__ import annotations

from pathlib import Path


def extract_text(path: str | Path, fmt: str | None = None) -> str:
    path = Path(path)
    fmt = fmt or path.suffix.lower().lstrip(".")
    if fmt == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if fmt == "docx":
        from docx import Document
        d = Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            parts += [c.text for row in t.rows for c in row.cells]
        return "\n".join(parts)
    if fmt == "pptx":
        from pptx import Presentation
        parts: list[str] = []
        for s in Presentation(str(path)).slides:
            for sh in s.shapes:
                if sh.has_text_frame:
                    parts.append(sh.text_frame.text)
                if getattr(sh, "has_table", False) and sh.has_table:
                    parts += [c.text for r in sh.table.rows for c in r.cells]
        return "\n".join(parts)
    if fmt == "xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(str(path), read_only=True)
        try:
            return "\n".join(str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        finally:
            wb.close()
    raise ValueError(fmt)
