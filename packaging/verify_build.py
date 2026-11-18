"""Packaging verification: run the FROZEN executable's built-in self test and check its report.

Usage: python packaging/verify_build.py <path-to-executable> [--timeout 300]
A passing run proves every bundled library, font and data file needed by all 12 routes is present.
It does NOT prove the GUI starts (use a real desktop session / `QT_QPA_PLATFORM=offscreen` smoke start for that).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        report = Path(d) / "selftest.json"
        subprocess.run([a.exe, "--self-test", "--report", str(report)], check=False, timeout=a.timeout)
        if not report.exists():
            print("FAIL: the executable did not produce a self-test report")
            return 2
        data = json.loads(report.read_text(encoding="utf-8"))
    for r in data["routes"]:
        print(("PASS " if r["ok"] else "FAIL ") + r["route"], r["detail"])
    ok = data["passed"] == data["total"] and data.get("frozen", True)
    print(f"{data['passed']}/{data['total']} routes passed (frozen={data.get('frozen')})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
