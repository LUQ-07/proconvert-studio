# Developer guide

> **Scope change:** the product now targets **Windows only** (Microsoft Store). Any macOS/Linux section below is legacy and no longer built, tested or shipped.


**Run:** `pip install -r requirements/gui.txt && python -m proconvert`. **Tests:** `python -m unittest discover -s tests -t .` or `python tools/run_tests.py` (writes `docs/TEST_REPORT.md`). Tests need no Qt; `tests/test_ui_smoke.py` uses a fake Qt (`tests/qt_stub.py`).

## Rules of thumb
* Keep Qt out of `core/`, `converters/`, `workers/`, `services/`, `settings/`, `history/`. The UI is a thin layer.
* Everything a user can hit is a `ConversionError` subclass with a message and troubleshooting text. Raw exceptions are wrapped by `wrap_unexpected`; technical text goes to the log only.
* Every limit must be explicit **and reported** (`ctx.warn`). Never truncate silently.
* Writers must never emit formulas from text, and must handle control characters (`utils/text.py`).
* New UI text -> add the key to `locales/en.json` and `tr("key")`; `tests/test_ui_support.py` fails on missing/unused keys and on placeholder mismatches in other languages.
* New dependency -> license check (`LICENSES.md`), pin in `requirements/`, `tools/gen_notices.py`.

## Add a route / format
1. Reader `converters/<fmt>_reader.py` -> `DocumentIR`; writer `converters/<fmt>_writer.py`.
2. Register in `converters/registry.py` and describe in `core/capabilities.py` (tier + limitations).
3. Add a corpus builder in `tests/make_corpus.py` and extend `tests/test_routes.py`.

## Debugging
Logs: `~/.local/share/ProConvertStudio/logs` (Linux). Raise level in Settings > Advanced. `python -m proconvert convert a.pdf b.docx` reproduces issues without the UI. Corpus: `from tests.make_corpus import build_all`.

## Performance notes learned the hard way
python-docx `row.cells`/`para.style`/`run.style` are O(n) per call - address XML directly or cache (see `docx_reader.py`, `docx_writer.py`). pdfplumber `extract_text_lines()` retained ~4 MB/page; use `extract_words()`.
