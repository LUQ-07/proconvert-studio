# Security model and its limits

## Threats considered
Confidential documents; malformed or hostile files (corrupt, truncated, disguised, ZIP bombs, XML entity bombs, huge images); path/name tricks; formula injection in outputs; leakage via logs or history; unsafe updates.

## Controls implemented (and tested)
| Control | Where | Test |
|---|---|---|
| Local-only processing; no telemetry; no advertising; the app makes no network requests (updates are delivered by the Microsoft Store) | whole app | `test_release_1_0` (ad-free, no network imports) |
| Extension **and content** must agree (PDF header / OOXML manifest); legacy `.doc/.ppt/.xls`, encrypted OLE files rejected with guidance | `core/security.py` | `test_security` |
| ZIP limits: entry count, total uncompressed size, per-entry ratio | `check_zip_safety` | `test_security`, `test_errors` |
| XML DOCTYPE/ENTITY banned in all package parts (parser-independent defence against entity expansion) | `reject_xml_dtds` | `test_errors` |
| Size, page, row/cell, image-pixel and image-memory limits; every truncation reported | `core/options.py` | `test_readers`, `test_errors` |
| Macros are never executed or copied; a warning is shown | readers use data parsers only | `test_errors` |
| Output name/path validation, symlink refusal, never write over the source, overwrite only with consent | `validate_target` | `test_security` |
| Atomic output; no partial files after failure/cancel/disk-full | `core/pipeline.py` | `test_errors` |
| Formula/CSV injection neutralised (xlsx cells are strings; CSV export prefixes `'`) | writers, history | `test_routes`, `test_services` |
| Parsers run in a separate process with timeout (and optional Linux memory cap) | `workers/process_job.py` | `test_workers` |
| Logs and diagnostics redact home paths and e-mails; history stores metadata only | services | `test_services` |

## What this does NOT protect against
* **A malicious document that exploits a bug in a parser** (pdfminer, pypdf, lxml, Pillow, ...). Process isolation and limits reduce but do not remove this risk. Keep dependencies current.
* **Decompression/CPU/RAM exhaustion that stays inside the limits.** The timeout (default 15 min) is the backstop; the memory cap works on Linux only and is off by default. Windows has no equivalent in this version (a Job Object limit is on the roadmap).
* **Dependency CVEs.** pypdf < 6.14.1 has published DoS advisories (CVE-2026-33699, -40260, -57204, -59937, -59936 as found by search on 2026-10-23); `requirements/base.txt` therefore requires `>=6.14.1`. The suite was executed with 5.9.0 (offline sandbox) - **re-run it on the pinned versions and run `pip-audit` before release.**
* **Local attackers / malware** on the user's machine, **tampering with settings**.
* **Output safety**: converted files may still carry hyperlinks or text that is dangerous when opened elsewhere; the app does not sanitise content semantically.
* **Unsigned binaries** will trigger SmartScreen/Gatekeeper warnings; code signing is a release step.
