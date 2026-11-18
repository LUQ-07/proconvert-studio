"""Validated, atomically persisted application settings (plain JSON, Qt-free)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from ..core.options import ConversionOptions
from ..utils.paths import config_dir

log = logging.getLogger("proconvert.settings")
SCHEMA_VERSION = 1

CHOICES: dict[str, tuple[str, ...]] = {
    "appearance": ("system", "dark", "light"),
    "language": ("en", "fr", "es", "ar"),
    "quality": ("standard", "high", "original"),
    "log_level": ("DEBUG", "INFO", "WARNING", "ERROR"),
    "page_size": ("A4", "Letter"),
}
INT_RANGES: dict[str, tuple[int, int]] = {"max_concurrent_jobs": (1, 4)}


@dataclass
class AppSettings:
    schema_version: int = SCHEMA_VERSION
    # General
    output_dir: str = ""
    overwrite_confirm: bool = True
    open_folder_after: bool = False
    remember_last_format: bool = True
    last_formats: dict = field(default_factory=dict)
    notifications: bool = True
    sidebar_collapsed: bool = False          # remembered between sessions
    language: str = "en"
    appearance: str = "system"
    # Conversion
    quality: str = "high"
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    show_experimental_warning: bool = True
    max_concurrent_jobs: int = 2
    detect_columns: bool = True
    strip_headers_footers: bool = True
    page_size: str = "A4"
    # Privacy
    crash_reports_local: bool = False       # off by default; reports never leave the machine
    # Advanced
    log_level: str = "INFO"
    temp_dir: str = ""

    def to_options(self) -> ConversionOptions:
        return ConversionOptions(
            quality=self.quality, ocr_enabled=self.ocr_enabled, ocr_language=self.ocr_language,
            detect_columns=self.detect_columns, strip_headers_footers=self.strip_headers_footers,
            page_size=self.page_size,
        )


_DEFAULT = AppSettings()


def _valid(name: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if not isinstance(value, int) or isinstance(value, bool):
            return default
        lo, hi = INT_RANGES.get(name, (-(2**31), 2**31))
        return value if lo <= value <= hi else default
    if isinstance(default, str):
        if not isinstance(value, str) or len(value) > 1024:
            return default
        if name in CHOICES and value not in CHOICES[name]:
            return default
        return value
    if isinstance(default, dict):
        if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            return dict(list(value.items())[:50])
        return {}
    return default


def sanitize(data: Any) -> AppSettings:
    """Build settings from untrusted JSON: unknown keys dropped, bad values replaced by defaults."""
    data = data if isinstance(data, dict) else {}
    kw = {}
    for f in fields(AppSettings):
        default = getattr(_DEFAULT, f.name)
        kw[f.name] = _valid(f.name, data.get(f.name, default), default)
    kw["schema_version"] = SCHEMA_VERSION
    return AppSettings(**kw)


class SettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else config_dir() / "settings.json"
        self._lock = threading.RLock()
        self._listeners: list[Callable[[AppSettings], None]] = []
        self.settings = self.load()

    def subscribe(self, fn: Callable[[AppSettings], None]) -> None:
        self._listeners.append(fn)

    def load(self) -> AppSettings:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return AppSettings()
            except (OSError, ValueError):
                self._quarantine()
                return AppSettings()
            return sanitize(raw)

    def _quarantine(self) -> None:
        try:
            self.path.replace(self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}"))
            log.warning("settings file was unreadable and was set aside")
        except OSError:
            pass

    def save(self, settings: AppSettings | None = None) -> None:
        with self._lock:
            if settings is not None:
                self.settings = sanitize(asdict(settings))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(asdict(self.settings), fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        for fn in list(self._listeners):
            fn(self.settings)

    def update(self, **changes: Any) -> AppSettings:
        with self._lock:
            merged = asdict(self.settings)
            merged.update(changes)
            self.settings = sanitize(merged)
        self.save()
        return self.settings

    def reset(self) -> AppSettings:
        return self.update(**asdict(AppSettings()))
