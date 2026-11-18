"""Shared helpers: one corpus per test run, convenience conversion wrapper."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from proconvert.core.options import ConversionOptions, Limits
from proconvert.core.pipeline import convert_file

from .make_corpus import build_all

_CORPUS: dict[str, Path] | None = None
_CORPUS_DIR: Path | None = None


def corpus() -> dict[str, Path]:
    global _CORPUS, _CORPUS_DIR
    if _CORPUS is None:
        _CORPUS_DIR = Path(tempfile.mkdtemp(prefix="pc-corpus-"))
        _CORPUS = build_all(_CORPUS_DIR)
    return _CORPUS


def squash(text: str) -> str:
    return "".join(text.split())


class TmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = self.tmp / "work"

    def conv(self, src: Path, dst_name: str, options: ConversionOptions | None = None, **kw):
        return convert_file(src, self.tmp / dst_name, options, temp_root=self.work, **kw)

    def assertNoLeftovers(self) -> None:
        names = [p.name for p in self.tmp.iterdir() if p.name != "work"]
        self.assertFalse([n for n in names if n.endswith(".part")], names)
        if self.work.exists():
            self.assertEqual([], [p.name for p in self.work.glob("job-*")])
