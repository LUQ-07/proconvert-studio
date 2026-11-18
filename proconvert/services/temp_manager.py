"""Application temp folder: stale-job cleanup and a manual "clear temporary files" action."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..utils.files import dir_size
from ..utils.paths import default_temp_root


class TempManager:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else default_temp_root()

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def usage_bytes(self) -> int:
        return dir_size(self.root)

    def cleanup_stale(self, max_age_hours: float = 6.0) -> int:
        """Remove job folders older than ``max_age_hours`` (left by crashes/force-quits)."""
        removed = 0
        if not self.root.exists():
            return 0
        cutoff = time.time() - max_age_hours * 3600
        for p in self.root.glob("job-*"):
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
        return removed

    def clear_all(self) -> int:
        """Remove every job folder. Returns bytes freed."""
        before = self.usage_bytes()
        if self.root.exists():
            for p in self.root.glob("job-*"):
                shutil.rmtree(p, ignore_errors=True)
        return max(0, before - self.usage_bytes())
