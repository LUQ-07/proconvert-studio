"""Lazy reader/writer lookup (keeps application start-up fast)."""
from __future__ import annotations


def get_reader(fmt: str):
    if fmt == "pdf":
        from .pdf_reader import read_pdf as fn
    elif fmt == "docx":
        from .docx_reader import read_docx as fn
    elif fmt == "pptx":
        from .pptx_reader import read_pptx as fn
    elif fmt == "xlsx":
        from .xlsx_reader import read_xlsx as fn
    else:
        raise KeyError(fmt)
    return fn


def get_writer(fmt: str):
    if fmt == "pdf":
        from .pdf_writer import write_pdf as fn
    elif fmt == "docx":
        from .docx_writer import write_docx as fn
    elif fmt == "pptx":
        from .pptx_writer import write_pptx as fn
    elif fmt == "xlsx":
        from .xlsx_writer import write_xlsx as fn
    else:
        raise KeyError(fmt)
    return fn
