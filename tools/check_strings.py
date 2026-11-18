"""List every translation key referenced by the UI (literal keys + known dynamic families)."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DYNAMIC = {
    "nav.": ["dashboard", "convert", "batch", "history", "settings", "help", "about"],
    "category.": ["pdf", "docx", "pptx", "xlsx"],
    "stage.": ["validating", "reading", "writing", "verifying", "finalizing", "done"],
    "status.": ["success", "failed", "cancelled"],
    "batch.status.": ["pending", "running", "done", "failed", "cancelled", "skipped"],
}
CALLEES = {"tr", "tr_"}


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in (ROOT / "proconvert" / "ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name not in CALLEES:
                continue
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                keys.add(a.value)
            elif isinstance(a, ast.JoinedStr) and a.values and isinstance(a.values[0], ast.Constant):
                prefix = a.values[0].value
                for suffix in DYNAMIC.get(prefix, []):
                    keys.add(prefix + suffix)
    return keys


_KEY_SHAPE = re.compile(r"^[a-z]+(\.[a-z_]+)+$")


def candidate_keys() -> set[str]:
    """Every key-shaped string constant in the UI (covers keys passed through variables/tables)."""
    out: set[str] = set()
    for path in (ROOT / "proconvert" / "ui").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _KEY_SHAPE.match(node.value):
                out.add(node.value)
    return out | used_keys()


if __name__ == "__main__":
    en = json.loads((ROOT / "proconvert/localization/locales/en.json").read_text(encoding="utf-8")) if (ROOT / "proconvert/localization/locales/en.json").exists() else {}
    used = used_keys()
    missing = sorted(k for k in used if k not in en)
    print(f"{len(used)} keys used, {len(missing)} missing from en.json")
    for k in missing:
        print(" ", k)
    sys.exit(1 if missing else 0)
