"""Command-line interface (also what automated tests and power users can call)."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .core.capabilities import all_routes
from .core.errors import ConversionError
from .core.options import ConversionOptions
from .core.pipeline import convert_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="proconvert", description="ProConvert Studio command line")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="convert one file")
    c.add_argument("source")
    c.add_argument("target")
    c.add_argument("--overwrite", action="store_true")
    c.add_argument("--pages", default="", help="PDF page range, e.g. 1-3,7")
    c.add_argument("--password", default=None, help="PDF password")
    c.add_argument("--ocr", action="store_true")
    c.add_argument("--quality", choices=("standard", "high", "original"), default="high")
    sub.add_parser("routes", help="list the 12 conversion routes and their status")
    st = sub.add_parser("selftest", help="run the built-in end-to-end self test")
    st.add_argument("--report", default="", help="write the JSON report to this file")
    a = ap.parse_args(argv)
    if a.cmd == "routes":
        for r in all_routes():
            print(f"{r.key:14s} {r.status}")
        return 0
    if a.cmd == "selftest":
        from .selftest import main as run_selftest
        return run_selftest(a.report or None)
    opts = ConversionOptions(quality=a.quality, pdf_pages=a.pages, pdf_password=a.password, ocr_enabled=a.ocr)
    try:
        res = convert_file(a.source, a.target, opts, overwrite=a.overwrite)
    except ConversionError as exc:
        print(f"Error: {exc.user_message}\n{exc.troubleshooting}", file=sys.stderr)
        return 2
    print(f"OK  {res.output_path}  ({res.status}, {res.duration_s:.2f}s)")
    for w in res.warnings:
        print(f"  note: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
