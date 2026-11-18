"""Safe filename and file-system helpers. Never uses a shell."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME_BYTES = 200


def sanitize_filename(name: str, fallback: str = "converted") -> str:
    """Turn arbitrary text into a filename that is valid on Windows, macOS and Linux."""
    cleaned = _ILLEGAL.sub("_", name).strip().strip(".")
    if not cleaned:
        cleaned = fallback
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = "_" + cleaned
    encoded = cleaned.encode("utf-8")
    if len(encoded) > MAX_NAME_BYTES:
        cleaned = encoded[:MAX_NAME_BYTES].decode("utf-8", "ignore")
    return cleaned


def is_safe_filename(name: str) -> tuple[bool, str]:
    """Validate (not rewrite) a filename typed by the user."""
    if not name or name in (".", ".."):
        return False, "The file name is empty."
    if _ILLEGAL.search(name):
        return False, 'The file name contains characters that are not allowed (< > : " / \\ | ? *).'
    if name != name.strip() or name.endswith("."):
        return False, "The file name must not start or end with a space, or end with a dot."
    if name.split(".")[0].upper() in _RESERVED:
        return False, "That file name is reserved by the operating system."
    if len(name.encode("utf-8")) > 255:
        return False, "The file name is too long."
    return True, ""


def unique_path(path: Path) -> Path:
    """Return ``path`` or ``name (n).ext`` if it already exists."""
    if not path.exists():
        return path
    for n in range(1, 10_000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free file name near {path.name}")


def human_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def reveal_in_file_manager(path: Path) -> bool:
    """Open the containing folder (selecting the file where the OS supports it)."""
    try:
        path = Path(path)
        if sys.platform == "win32":
            if path.exists():
                subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603,S607
            else:
                os.startfile(str(path.parent))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)] if path.exists() else ["open", str(path.parent)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])  # noqa: S603,S607
        return True
    except OSError:
        return False


def open_with_default_app(path: Path) -> bool:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        return True
    except OSError:
        return False
