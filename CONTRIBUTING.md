# Contributing

Thank you for helping! Bug reports, test documents that convert badly, translations and code are all welcome.

## Report a bug
Open an issue with the **Bug report** template. The most useful thing you can add is a small example file (remove private
content first) and the diagnostics export from *Settings > Advanced* (it never contains your documents).

## Set up the development environment (Windows, Git Bash)
```bash
git clone https://github.com/LUQ-07/prodoc-suite.git
cd prodoc-suite
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements/dev.txt -r requirements/gui.txt
python tools/run_tests.py
python launch.py
```
`tools/run_tests.py` runs the whole test-suite and rewrites `docs/TEST_REPORT.md`.

## Rules for changes
1. **Every change comes with tests.** Never weaken an existing test to make it pass; if a test is wrong, explain why in the pull request.
2. Keep the architecture: the engine (`proconvert/core`, `converters`, `pdftools`, `services`) does not import Qt; the screens live in `proconvert/ui`.
3. Every user-facing failure is a `ConversionError` with a clear message.
4. New text goes in **all four** locale files (`proconvert/localization/locales`: en, fr, es, ar). A test checks that none is missing.
5. New dependencies must be permissively licensed (MIT/BSD/Apache/LGPL used dynamically). **No GPL/AGPL libraries** (for example no PyMuPDF). Add them to `LICENSES.md` and `tools/gen_notices.py`.
6. Do not claim a conversion is "Supported" unless tests and a real-document check back it (see `docs/FIDELITY_REPORT.md`).
7. Do not commit secrets, personal documents or generated files (`dist/`, `build/`).

## Pull requests
Keep them small and focused, describe what changed and how you tested it, and make sure `python tools/run_tests.py` ends with `FAIL: 0, ERROR: 0`.

By contributing you agree that your contribution is released under the project's [MIT license](LICENSE).
