"""JSON-based translations, stored apart from application logic. English is the fallback."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..utils.paths import resource_path

RTL = {"ar", "he", "fa", "ur"}


def locales_dir() -> Path:
    return resource_path("localization/locales")


@lru_cache(maxsize=16)
def load_catalog(lang: str) -> dict[str, Any]:
    path = locales_dir() / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_rtl(lang: str) -> bool:
    return lang in RTL


def available_languages() -> list[dict[str, Any]]:
    """[{code, name, complete, reviewed, coverage}] - the UI labels unreviewed/incomplete ones honestly."""
    en = {k for k in load_catalog("en") if not k.startswith("_")}
    out = []
    for p in sorted(locales_dir().glob("*.json")):
        cat = load_catalog(p.stem)
        keys = {k for k in cat if not k.startswith("_")}
        meta = cat.get("_meta", {})
        out.append({"code": p.stem, "name": meta.get("name", p.stem), "reviewed": bool(meta.get("reviewed", False)),
                    "coverage": len(keys & en) / max(len(en), 1), "complete": en <= keys})
    out.sort(key=lambda d: (d["code"] != "en", d["code"]))
    return out


class Translator:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang
        self._cat = load_catalog(lang)
        self._en = load_catalog("en")

    def __call__(self, key: str, **fmt: Any) -> str:
        text = self._cat.get(key) or self._en.get(key) or key
        if fmt:
            try:
                return str(text).format(**fmt)
            except (KeyError, IndexError, ValueError):
                return str(text)
        return str(text)
