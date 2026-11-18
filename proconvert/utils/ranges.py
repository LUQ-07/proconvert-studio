"""Page-range parsing ("1-3,7,10-")."""
from __future__ import annotations

import re

from ..core.errors import InvalidOptionsError

_PART = re.compile(r"^(\d+)?\s*(-)?\s*(\d+)?$")


def parse_page_ranges(spec: str, total: int) -> list[int]:
    """Return sorted, de-duplicated zero-based page indexes. Empty spec means all pages."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(total))
    if len(spec) > 200:
        raise InvalidOptionsError("The page range is too long.")
    chosen: set[int] = set()
    for raw in spec.split(","):
        part = raw.strip()
        m = _PART.match(part)
        if not part or not m or (m[1] is None and m[3] is None):
            raise InvalidOptionsError(f"'{raw.strip()}' is not a valid page range.")
        start_s, dash, end_s = m[1], m[2], m[3]
        if not dash:
            start = end = int(start_s)
        else:
            start = int(start_s) if start_s else 1
            end = int(end_s) if end_s else total
        if start < 1 or end < start:
            raise InvalidOptionsError(f"'{part}' is not a valid page range.")
        if start > total:
            raise InvalidOptionsError(f"Page {start} does not exist; the document has {total} page(s).")
        chosen.update(range(start - 1, min(end, total)))
    return sorted(chosen)
