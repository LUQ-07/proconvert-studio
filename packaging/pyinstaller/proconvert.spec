# -*- mode: python ; coding: utf-8 -*-
# Windows-only product (Microsoft Store). Build with:  pyinstaller --noconfirm --clean packaging/pyinstaller/proconvert.spec
# NOT YET BUILT OR TESTED: the authoring sandbox had no PySide6/PyInstaller. See docs/BUILD_GUIDE.md.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from proconvert import __version__, config  # noqa: E402

NAME = config.APP_NAME.replace(" ", "")          # ProConvertStudio
ICON_DIR = ROOT / "proconvert" / "assets"

datas = [
    (str(ICON_DIR), "proconvert/assets"),
    (str(ROOT / "proconvert" / "localization" / "locales"), "proconvert/localization/locales"),
]
for pkg in ("pdfminer", "pdfplumber", "pypdf", "docx", "pptx", "reportlab", "openpyxl"):
    datas += collect_data_files(pkg)
binaries = []
for pkg in ("pypdfium2_raw", "pypdfium2"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# Keep the bundle small AND keep GPL-only Qt add-on modules out of a proprietary product.
excludes = [
    "tkinter", "unittest", "pydoc", "test", "IPython", "matplotlib", "numpy.tests",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",   # GPL/commercial-only in Qt 6: must not ship
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
]
# "pdfminer.six" is a DISTRIBUTION name, not an importable module; the importable packages are listed below.
# The three PDF routes (pdf->docx/pptx/xlsx) failed in the first frozen CI build with DependencyMissingError,
# so collect every submodule of the PDF stack explicitly instead of relying on static analysis.
hidden = ["pytesseract"]
for pkg in ("pdfplumber", "pdfminer", "pypdf", "pypdfium2", "charset_normalizer"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        hidden.append(pkg)

a = Analysis([str(ROOT / "launch.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)

icon = ICON_DIR / "icon.ico" if sys.platform == "win32" else None
version_file = ROOT / "build" / "version_info.txt"
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, debug=False, strip=False, upx=False,
    icon=str(icon) if icon else None,
    version=str(version_file) if sys.platform == "win32" and version_file.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)   # one-folder: LGPL-friendly (Qt libs stay replaceable)
