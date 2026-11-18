# Update roadmap (proposed - not commitments)
* **3.0.0-rc / 3.0.0:** first real runs on Win/macOS/Linux, fix UI findings, frozen builds + self-test in CI, signed installers, `pip-audit` clean, native-speaker review of translations, legal review, real support/update hosts.
* **3.1:** RTL/Arabic shaping in PDF output (add `arabic-reshaper` + `python-bidi` after license/testing review), CJK font option (Noto, OFL), Windows Job-Object memory limits, drag-and-drop in the batch table, window-state persistence.
* **3.2:** better PDF tables (text-strategy detection with confidence), numbered lists, footnotes/headers in DOCX->PDF, XLSX charts as images, per-route quality presets.
* Monthly releases for fixes and dependency bumps; changelog per release; security fixes out of band.

## Status note
The items for 3.0.0-rc (real runs, CI, installers) are still open; see the top of `docs/KNOWN_ISSUES.md`. DOCX numbered lists/footnotes/headers (planned for 3.2) were pulled forward and are in [Unreleased].
