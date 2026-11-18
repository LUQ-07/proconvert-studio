# Release checklist

Tick every box with evidence (a link to a CI run, a screenshot, a test report) before publishing a release.

## Code and dependencies
- [ ] Fresh virtual environment from `requirements/build.txt`; `python -m pip freeze` saved; **pypdf >= 6.14.1** installed.
- [ ] `python tools/run_tests.py` ends with `FAIL: 0, ERROR: 0`; `docs/TEST_REPORT.md` regenerated.
- [ ] CI (`.github/workflows/ci.yml`) is green on the commit being released (tests, supply-chain, frozen build, size report).
- [ ] `pip-audit` clean, or each finding triaged in writing; `pip-licenses` matches `LICENSES.md`; `python tools/gen_notices.py` run.
- [ ] Version bumped in `proconvert/__init__.py` and `CHANGELOG.md` updated (SemVer).
## Real-system verification
- [ ] The GUI launched and used by hand on Windows 10 and Windows 11: keyboard-only pass, dark/light/system themes,
      French / Spanish / Arabic (right-to-left) screens, high-DPI display.
- [ ] Every conversion route tried by hand with real documents; results looked at, not only counted.
- [ ] Screen-reader smoke test (NVDA).
## Packaging
- [ ] `pyinstaller` build runs and `packaging/verify_build.py` passes on the frozen executable.
- [ ] Installer (Inno Setup) installs and uninstalls cleanly on a clean Windows VM; user data is left in place on uninstall.
- [ ] SHA-256 sums of every file in the release are published in the release notes.
## Publishing
- [ ] Git tag `vX.Y.Z`; GitHub Release with the notes from `CHANGELOG.md`, the installer / zip and their SHA-256 sums.
- [ ] `docs/KNOWN_ISSUES.md` is up to date and says what has NOT been verified.
