"""Platform-specific application directories and resource lookup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import config

_FOLDER = config.APP_NAME.replace(" ", "")


def _home() -> Path:
    return Path.home()


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or _home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = _home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config")
    return base / _FOLDER


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or _home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = _home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or _home() / ".local" / "share")
    return base / _FOLDER


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or _home() / "AppData" / "Local")
        return base / _FOLDER / "Cache"
    if sys.platform == "darwin":
        return _home() / "Library" / "Caches" / _FOLDER
    base = Path(os.environ.get("XDG_CACHE_HOME") or _home() / ".cache")
    return base / _FOLDER


def log_dir() -> Path:
    return data_dir() / "logs"


def crash_dir() -> Path:
    return data_dir() / "crash-reports"


def default_temp_root() -> Path:
    return cache_dir() / "tmp"


def default_output_dir() -> Path:
    docs = _home() / "Documents"
    return docs if docs.is_dir() else _home()


def resource_path(relative: str) -> Path:
    """Locate a bundled resource both from source and from a frozen (PyInstaller) build."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidate = Path(frozen_root) / "proconvert" / relative
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / relative
