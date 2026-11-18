"""Assemble proconvert/assets/THIRD_PARTY_NOTICES.txt from the license files of installed packages.

Run inside the RELEASE virtualenv (with PySide6 and the exact pinned versions installed) so every
component's own license text is included. Packages not installed are listed as TODO and fail
the release checklist until generated.
"""
from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "proconvert" / "assets" / "THIRD_PARTY_NOTICES.txt"
PKGS = ["PySide6", "shiboken6", "pdfplumber", "pdfminer.six", "pypdf", "pypdfium2", "python-docx", "python-pptx", "openpyxl",
        "et_xmlfile", "reportlab", "Pillow", "numpy", "lxml", "cryptography", "cffi", "pycparser", "defusedxml", "pytesseract",
        "charset-normalizer", "typing_extensions", "packaging"]
LIC = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.I)

STATIC = """\
ProConvert Studio - Third-party notices
=======================================
ProConvert Studio itself is free software released under the MIT License (see the LICENSE file). It includes or can use the open-source components below.
Each component remains under its own license; the texts that follow are reproduced as required.

NON-PYTHON COMPONENTS
---------------------
* Qt 6 / PySide6 (Qt for Python): LGPL-3.0-only (also available under GPL/commercial). ProConvert uses only the LGPL
  modules QtCore, QtGui and QtWidgets, ships Qt as separate shared libraries in the application folder (not statically
  linked), and you may replace them with a compatible Qt build. Source and license: https://www.qt.io/ and
  https://doc.qt.io/qtforpython/ . The GPL-only Qt add-on modules (e.g. Qt Charts, Qt Data Visualization) are excluded.
* PDFium (via pypdfium2): BSD-3-Clause and Apache-2.0 (plus third-party notices shipped inside the pypdfium2 package).
* Tesseract OCR (optional, if you install or bundle it): Apache-2.0. https://github.com/tesseract-ocr/tesseract
* PyInstaller (build tool): GPL-2.0-or-later with the bootloader exception that permits distributing the resulting applications under any license.
* DejaVu Sans fonts (bundled): see the DejaVu license text at the end of this file.

PYTHON COMPONENTS
-----------------
"""


def main() -> int:
    parts = [STATIC]
    missing = []
    for name in PKGS:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            parts.append(f"\n===== {name} =====\nTODO: not installed in this environment - regenerate in the release venv.\n")
            continue
        md = dist.metadata
        parts.append(f"\n===== {name} {dist.version} =====\nLicense: {md.get('License-Expression') or md.get('License') or '; '.join(c for c in md.get_all('Classifier', []) if c.startswith('License ::'))}\nHome: {md.get('Home-page') or ''}\n")
        for f in dist.files or []:
            if LIC.search(str(f)):
                try:
                    parts.append(f"\n--- {f} ---\n{Path(dist.locate_file(f)).read_text(encoding='utf-8', errors='replace')}\n")
                except OSError:
                    pass
    dj = ROOT / "proconvert" / "assets" / "fonts" / "LICENSE-DejaVu.txt"
    parts.append("\n===== DejaVu fonts =====\n" + dj.read_text(encoding="utf-8", errors="replace"))
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB); not installed here: {', '.join(missing) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
