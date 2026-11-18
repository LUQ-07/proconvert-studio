"""Minimal Semantic Versioning 2.0 parsing and precedence comparison."""
from __future__ import annotations

import re
from functools import total_ordering

_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@total_ordering
class SemVer:
    __slots__ = ("major", "minor", "patch", "pre", "build", "raw")

    def __init__(self, text: str) -> None:
        m = _SEMVER.match(text.strip().lstrip("v"))
        if not m:
            raise ValueError(f"Not a valid semantic version: {text!r}")
        self.major, self.minor, self.patch = int(m["major"]), int(m["minor"]), int(m["patch"])
        self.pre = tuple(m["pre"].split(".")) if m["pre"] else ()
        self.build = m["build"] or ""
        self.raw = text.strip().lstrip("v")

    def _key(self):
        return (self.major, self.minor, self.patch)

    @staticmethod
    def _pre_key(ident: str):
        # numeric identifiers sort before alphanumeric ones; numerics compare numerically
        return (0, int(ident), "") if ident.isdigit() else (1, 0, ident)

    def _cmp(self, other: "SemVer") -> int:
        if self._key() != other._key():
            return -1 if self._key() < other._key() else 1
        if not self.pre and not other.pre:
            return 0
        if not self.pre:
            return 1  # a release outranks its own pre-release
        if not other.pre:
            return -1
        a = [self._pre_key(x) for x in self.pre]
        b = [self._pre_key(x) for x in other.pre]
        if a == b:
            return 0
        return -1 if a < b else 1  # list comparison implements "more fields wins when prefix equal"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SemVer) and self._cmp(other) == 0

    def __lt__(self, other: "SemVer") -> bool:
        return self._cmp(other) < 0

    def __hash__(self) -> int:
        return hash((self._key(), self.pre))

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"SemVer({self.raw!r})"
