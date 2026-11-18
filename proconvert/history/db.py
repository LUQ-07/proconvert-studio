"""SQLite conversion history. Stores metadata only - never document contents."""
from __future__ import annotations

import csv
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..utils.paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_name TEXT NOT NULL,
    input_path TEXT NOT NULL,
    input_format TEXT NOT NULL,
    output_format TEXT NOT NULL,
    output_path TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_summary TEXT NOT NULL DEFAULT '',
    warnings_count INTEGER NOT NULL DEFAULT 0,
    route_status TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_conv_started ON conversions(started_at);
"""
SORTABLE = {"started_at", "input_name", "input_format", "output_format", "duration_ms", "status"}
CSV_COLUMNS = ["id", "input_name", "input_format", "output_format", "started_at", "duration_ms",
               "status", "output_path", "error_summary", "warnings_count"]


@dataclass
class HistoryRecord:
    input_name: str
    input_path: str
    input_format: str
    output_format: str
    status: str                      # "success" | "failed" | "cancelled"
    output_path: str = ""
    duration_ms: int = 0
    error_summary: str = ""
    warnings_count: int = 0
    route_status: str = ""
    started_at: str = ""
    id: Optional[int] = None


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in exported text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


class HistoryDB:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else data_dir() / "history.sqlite3"
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            c.execute("PRAGMA user_version = 1")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, rec: HistoryRecord) -> int:
        started = rec.started_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, closing(self._conn()) as c, c:
            cur = c.execute(
                "INSERT INTO conversions (input_name,input_path,input_format,output_format,output_path,started_at,"
                "duration_ms,status,error_summary,warnings_count,route_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rec.input_name, rec.input_path, rec.input_format, rec.output_format, rec.output_path, started,
                 int(rec.duration_ms), rec.status, rec.error_summary[:500], rec.warnings_count, rec.route_status),
            )
            return int(cur.lastrowid)

    def get(self, rec_id: int) -> Optional[HistoryRecord]:
        with self._lock, closing(self._conn()) as c:
            row = c.execute("SELECT * FROM conversions WHERE id=?", (rec_id,)).fetchone()
        return HistoryRecord(**dict(row)) if row else None

    def query(self, search: str = "", status: str = "", input_format: str = "", output_format: str = "",
              sort: str = "started_at", descending: bool = True, limit: int = 500, offset: int = 0) -> list[HistoryRecord]:
        sort = sort if sort in SORTABLE else "started_at"
        where, args = [], []
        if search:
            where.append("(input_name LIKE ? ESCAPE '\\' OR output_path LIKE ? ESCAPE '\\' OR error_summary LIKE ? ESCAPE '\\')")
            args += [_like(search)] * 3
        for col, val in (("status", status), ("input_format", input_format), ("output_format", output_format)):
            if val:
                where.append(f"{col} = ?")
                args.append(val)
        sql = "SELECT * FROM conversions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {sort} {'DESC' if descending else 'ASC'}, id DESC LIMIT ? OFFSET ?"
        args += [max(1, min(limit, 5000)), max(0, offset)]
        with self._lock, closing(self._conn()) as c:
            rows = c.execute(sql, args).fetchall()
        return [HistoryRecord(**dict(r)) for r in rows]

    def count(self) -> int:
        with self._lock, closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM conversions").fetchone()[0])

    def delete(self, rec_id: int) -> None:
        with self._lock, closing(self._conn()) as c, c:
            c.execute("DELETE FROM conversions WHERE id=?", (rec_id,))

    def clear(self) -> None:
        with self._lock, closing(self._conn()) as c, c:
            c.execute("DELETE FROM conversions")
        with closing(self._conn()) as c:
            c.execute("VACUUM")

    def stats(self) -> dict[str, Any]:
        with self._lock, closing(self._conn()) as c:
            total = c.execute("SELECT COUNT(*) FROM conversions").fetchone()[0]
            ok = c.execute("SELECT COUNT(*) FROM conversions WHERE status='success'").fetchone()[0]
            ms = c.execute("SELECT COALESCE(SUM(duration_ms),0) FROM conversions WHERE status='success'").fetchone()[0]
            top = c.execute("SELECT input_format||' -> '||output_format AS r, COUNT(*) n FROM conversions "
                            "GROUP BY r ORDER BY n DESC LIMIT 1").fetchone()
        return {"total": total, "success": ok, "failed": total - ok,
                "success_rate": (ok / total) if total else 0.0, "total_seconds": ms / 1000.0,
                "top_route": top["r"] if top else ""}

    def export_csv(self, dest: str | Path, records: Optional[list[HistoryRecord]] = None) -> int:
        records = records if records is not None else self.query(limit=5000)
        with open(dest, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_COLUMNS)
            for r in records:
                w.writerow([_csv_safe(getattr(r, col)) for col in CSV_COLUMNS])
        return len(records)
