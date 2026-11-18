"""Print license metadata of installed dependencies (cross-check for LICENSES.md; run in the release venv)."""
from importlib import metadata

PKGS = ["PySide6", "shiboken6", "pdfplumber", "pdfminer.six", "pypdf", "pypdfium2", "python-docx", "python-pptx", "openpyxl",
        "reportlab", "Pillow", "lxml", "cryptography", "defusedxml", "pytesseract", "XlsxWriter", "pyinstaller", "charset-normalizer", "et_xmlfile", "typing_extensions", "cffi", "pycparser"]


def lic(md) -> str:
    v = md.get("License-Expression") or ""
    if not v:
        raw = (md.get("License") or "").strip()
        v = raw if raw and len(raw) < 80 else ""
    if not v:
        v = "; ".join(c.split("::")[-1].strip() for c in md.get_all("Classifier", []) if c.startswith("License ::"))
    return v or "(not declared in metadata - check the project)"


for name in PKGS:
    try:
        md = metadata.metadata(name)
        print(f"{name:20s} {metadata.version(name):12s} {lic(md)}")
    except metadata.PackageNotFoundError:
        print(f"{name:20s} {'-':12s} not installed here")
