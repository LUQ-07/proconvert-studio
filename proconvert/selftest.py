"""Built-in self-test: builds tiny sample documents and runs all 12 routes end to end.

Works from source and from a frozen (PyInstaller) build, so the packaging scripts can prove
that every library and font really made it into the bundle. Qt is not required.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .core.capabilities import all_routes
from .core.extract import extract_text
from .core.pipeline import convert_file

TOKEN = {"pdf": "SELFTESTPDF", "docx": "SELFTESTDOCX", "pptx": "SELFTESTPPTX", "xlsx": "SELFTESTXLSX"}


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), (30, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


def make_samples(d: Path) -> dict[str, Path]:
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph

    out = {k: d / f"sample.{k}" for k in TOKEN}
    ss = getSampleStyleSheet()
    SimpleDocTemplate(str(out["pdf"])).build([Paragraph("Heading", ss["Title"]), Paragraph(f"{TOKEN['pdf']} body text for the self test.", ss["BodyText"])])
    doc = Document()
    doc.add_heading("Self test", 1)
    doc.add_paragraph(f"{TOKEN['docx']} body text")
    t = doc.add_table(rows=2, cols=2)
    for i in range(2):
        for j in range(2):
            t.cell(i, j).text = f"c{i}{j}"
    doc.save(str(out["docx"]))
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = TOKEN["pptx"]
    s.placeholders[1].text = "bullet text"
    prs.save(str(out["pptx"]))
    wb = Workbook()
    wb.active.append(["Name", "Value"])
    wb.active.append([TOKEN["xlsx"], 42])
    wb.save(str(out["xlsx"]))
    return out


def run(verbose: bool = True) -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="proconvert-selftest-") as tmp:
        d = Path(tmp)
        samples = make_samples(d)
        for r in all_routes():
            t0 = time.monotonic()
            target = d / f"{r.source}_to.{r.target}"
            entry = {"route": r.key, "ok": False, "seconds": 0.0, "detail": ""}
            try:
                res = convert_file(samples[r.source], target, temp_root=d / "tmp")
                text = extract_text(target)
                token = TOKEN[r.source]
                entry["ok"] = token in text.replace(" ", "")
                entry["detail"] = "" if entry["ok"] else f"expected content {token} missing from output"
                entry["warnings"] = len(res.warnings)
            except Exception as exc:  # noqa: BLE001
                tech = getattr(exc, "technical", None)   # e.g. the real ImportError behind a DependencyMissingError
                entry["detail"] = f"{type(exc).__name__}: {exc}" + (f" [{tech}]" if tech else "")
            entry["seconds"] = round(time.monotonic() - t0, 2)
            results.append(entry)
            if verbose:
                print(f"{'PASS' if entry['ok'] else 'FAIL'}  {r.key:12s} {entry['seconds']:5.2f}s {entry['detail']}")
    report = {"app_version": __version__, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
              "passed": sum(e["ok"] for e in results), "total": len(results), "routes": results}
    return report


def main(report_path: str | None = None) -> int:
    report = run(verbose=sys.stdout is not None)
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps({k: v for k, v in report.items() if k != "routes"}))
    return 0 if report["passed"] == report["total"] else 1
