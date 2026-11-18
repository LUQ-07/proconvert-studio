"""Diagnostics export: a zip the user can inspect and choose to send to support. Never automatic."""
from __future__ import annotations

import json
import os
import platform
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime
from importlib import metadata
from pathlib import Path

from .. import __version__
from ..core.capabilities import all_routes
from ..converters import ocr
from ..settings.store import AppSettings
from ..utils.paths import log_dir
from .logging_setup import RedactingFilter

_LIBS = ("PySide6", "pdfplumber", "pdfminer.six", "pypdf", "pypdfium2", "python-docx", "python-pptx",
         "openpyxl", "reportlab", "Pillow", "lxml", "cryptography", "defusedxml", "pytesseract")


def total_ram_bytes() -> int | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMSTAT()
            m.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
            return int(m.ullTotalPhys)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, ValueError, OSError):
        return None


def system_info() -> dict:
    libs = {}
    for name in _LIBS:
        try:
            libs[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            libs[name] = "not installed"
    ram = total_ram_bytes()
    return {
        "app_version": __version__, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
        "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
        "ram_gb": round(ram / 1024 ** 3, 1) if ram else None, "ocr_engine_available": ocr.is_available(),
        "libraries": libs,
    }


def export_diagnostics(dest: str | Path, settings: AppSettings, logs: Path | None = None) -> Path:
    dest = Path(dest)
    redactor = RedactingFilter()
    safe_settings = asdict(settings)
    for k in ("output_dir", "temp_dir"):
        safe_settings[k] = "<set>" if safe_settings.get(k) else ""
    safe_settings["last_formats"] = "<omitted>"
    readme = ("ProConvert Studio diagnostics\n"
              f"Created: {datetime.now():%Y-%m-%d %H:%M}\n\n"
              "Contents: application/system information, settings (folder paths removed), the capability\n"
              "list and recent log files (home folder and e-mail addresses redacted).\n"
              "It does NOT contain any document content. Review the files before sending them to support.\n")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("system.json", json.dumps(system_info(), indent=2))
        zf.writestr("settings.json", json.dumps(safe_settings, indent=2))
        zf.writestr("routes.json", json.dumps([{"route": r.key, "status": r.status} for r in all_routes()], indent=2))
        for f in sorted((logs or log_dir()).glob("proconvert.log*")):
            try:
                zf.writestr(f"logs/{f.name}", redactor.redact(f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    return dest
