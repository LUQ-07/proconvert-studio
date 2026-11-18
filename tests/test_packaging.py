"""Packaging verification that is possible without PyInstaller/PySide6/Windows/macOS.

Real installers are NOT built here; see docs/KNOWN_ISSUES.md.
"""
import configparser
import os
import plistlib
import py_compile
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from proconvert import __version__
from proconvert.utils.semver import SemVer

from .base import TmpCase

ROOT = Path(__file__).resolve().parent.parent


class Metadata(unittest.TestCase):
    def test_version_is_semver_and_pyproject_reads_it_dynamically(self):
        SemVer(__version__)
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertIn("version", data["project"]["dynamic"])
        self.assertEqual("proconvert.__version__", data["tool"]["setuptools"]["dynamic"]["version"]["attr"])
        self.assertTrue(data["project"]["requires-python"].startswith(">=3.11"))

    def test_requirements_parse_and_pin_secure_pypdf(self):
        text = (ROOT / "requirements" / "base.txt").read_text()
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
        self.assertTrue(all(">=" in l for l in lines), "every runtime dependency needs a lower bound")
        self.assertIn("pypdf>=6.14.1", text)
        self.assertNotIn("pymupdf", text.lower(), "AGPL dependency must not return")
        self.assertNotIn("PyMuPDF", (ROOT / "requirements" / "build.txt").read_text())

    def test_no_agpl_or_gpl_python_imports_in_source(self):
        banned = ("fitz", "pymupdf", "PySide6.QtCharts", "PySide6.QtDataVisualization", "win32com")
        for p in (ROOT / "proconvert").rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            for b in banned:
                self.assertNotIn(f"import {b}", src, f"{p.name} imports {b}")

    def test_bundled_resources_exist(self):
        a = ROOT / "proconvert" / "assets"
        for f in ("icon.png", "icon.ico", "icon_256.png", "icon.svg", "THIRD_PARTY_NOTICES.txt",
                  "fonts/DejaVuSans.ttf", "fonts/DejaVuSans-Bold.ttf", "fonts/DejaVuSans-Oblique.ttf", "fonts/DejaVuSans-BoldOblique.ttf",
                  "fonts/LICENSE-DejaVu.txt"):
            self.assertTrue((a / f).is_file(), f)
        for l in ("en", "fr", "es", "ar"):
            self.assertTrue((ROOT / "proconvert" / "localization" / "locales" / f"{l}.json").is_file())

    def test_spec_and_python_tools_compile(self):
        for p in [ROOT / "packaging/pyinstaller/proconvert.spec", ROOT / "packaging/windows/make_version_info.py",
                  ROOT / "packaging/verify_build.py", ROOT / "launch.py", *(ROOT / "tools").glob("*.py")]:
            py_compile.compile(str(p), cfile=str(Path(tempfile.mkdtemp()) / "x.pyc"), doraise=True)

    def test_inno_script_has_required_sections(self):
        iss = (ROOT / "packaging/windows/installer.iss").read_text()
        for needle in ("[Setup]", "[Icons]", "[Tasks]", "desktopicon", "UninstallDisplayIcon", "PrivilegesRequired=lowest", "LicenseFile="):
            self.assertIn(needle, iss)


class FrozenSelfTest(unittest.TestCase):
    def test_verify_build_script_works_against_the_source_install(self):
        """verify_build.py is what the build scripts run on the FROZEN exe; here we point it at a shim for the source tree."""
        import tempfile
        if os.name == "nt":      # a .cmd file is directly executable on Windows; a .sh file is not
            shim = Path(tempfile.mkdtemp()) / "shim.cmd"
            shim.write_text(f'@echo off\r\nset "PYTHONPATH={ROOT}"\r\n"{os.sys.executable}" -m proconvert %*\r\n')
        else:
            shim = Path(tempfile.mkdtemp()) / "shim.sh"
            shim.write_text(f'#!/bin/sh\nPYTHONPATH={ROOT} exec {os.sys.executable} -m proconvert "$@"\n')
            shim.chmod(0o755)
        r = subprocess.run([os.sys.executable, str(ROOT / "packaging/verify_build.py"), str(shim)], capture_output=True, text=True)
        from proconvert.core.capabilities import all_routes
        n = len(all_routes())
        self.assertIn(f"{n}/{n} routes passed", r.stdout, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        # a non-frozen run is reported as frozen=False so verify_build exits non-zero when pointed at source - by design
        self.assertEqual(1, r.returncode)



class CiWorkflow(unittest.TestCase):
    """Static checks only: the workflow is validated on GitHub, not here."""

    def setUp(self):
        import yaml
        self.text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.wf = yaml.safe_load(self.text)

    def test_every_job_runs_on_windows_only(self):
        for name, job in self.wf["jobs"].items():
            self.assertEqual("windows-latest", job["runs-on"], name)
        self.assertNotIn("macos", self.text)
        self.assertNotIn("ubuntu", self.text)

    def test_supply_chain_and_frozen_verification_steps_exist(self):
        for needle in ("pip_audit", "pip-licenses", "packaging/verify_build.py", "6.14.1", "pyinstaller"):
            self.assertIn(needle, self.text)

    def test_only_windows_packaging_is_shipped(self):
        self.assertEqual({"pyinstaller", "windows"}, {p.name for p in (ROOT / "packaging").iterdir() if p.is_dir() and p.name != "__pycache__"})


if __name__ == "__main__":
    unittest.main()
