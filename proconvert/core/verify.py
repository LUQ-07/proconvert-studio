"""Post-conversion verification: re-open the produced file with an independent parser."""
from __future__ import annotations

from pathlib import Path

from .errors import ConversionError


class OutputVerificationError(ConversionError):
    code = "verification_failed"
    default_message = "The converter produced a file that failed validation, so it was discarded."
    troubleshooting = "Try the conversion again. If it fails repeatedly, attach a diagnostics report to a bug report on the project page."


def verify_output(path: Path, fmt: str) -> dict:
    """Return basic structural facts about the output or raise OutputVerificationError."""
    if not path.exists() or path.stat().st_size == 0:
        raise OutputVerificationError("The converter did not create an output file.")
    try:
        if fmt == "pdf":
            from pypdf import PdfReader
            r = PdfReader(str(path))
            n = len(r.pages)
            if n < 1:
                raise ValueError("PDF has no pages")
            return {"pages": n}
        if fmt == "docx":
            from docx import Document
            d = Document(str(path))
            n = len(d.paragraphs) + len(d.tables)
            if n < 1:
                raise ValueError("DOCX has no content")
            return {"paragraphs": len(d.paragraphs), "tables": len(d.tables)}
        if fmt == "pptx":
            from pptx import Presentation
            p = Presentation(str(path))
            n = len(p.slides)
            if n < 1:
                raise ValueError("PPTX has no slides")
            return {"slides": n}
        if fmt == "xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(str(path), read_only=True)
            try:
                if not wb.sheetnames:
                    raise ValueError("XLSX has no sheets")
                return {"sheets": len(wb.sheetnames)}
            finally:
                wb.close()
    except OutputVerificationError:
        raise
    except Exception as exc:  # any parser failure means the output is not trustworthy
        raise OutputVerificationError(technical=f"{type(exc).__name__}: {exc}") from exc
    raise OutputVerificationError(technical=f"unknown format {fmt}")
