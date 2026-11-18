# Architecture

```
proconvert/
  core/          domain model + pipeline (no Qt)      ir, errors, options, context, security, images, verify,
                                                       capabilities, pipeline, extract
  converters/    readers (src -> IR) and writers (IR -> dst)
  workers/       process_job.py (isolated worker process), batch.py (queue)
  services/      logging, diagnostics, temp files
  settings/      validated JSON store           history/  SQLite history
  localization/  translator + locales/*.json     utils/    paths, files, text, ranges, semver
  ui/            PySide6 application (pages/, widgets/, theme, palette, icons)
  assets/        icons, DejaVu fonts, third-party notices
tests/  tools/  packaging/  docs/  requirements/
```
(`app/` in the original brief is named `proconvert/` so it is an importable package; the sub-folders match the suggested layout.)

## One pipeline, twelve routes
```
source file -> validate (ext, signature, zip safety, DTD ban) -> READER -> DocumentIR
            -> content check -> WRITER -> staged file -> verify (re-open with independent parser)
            -> copy to ".name.part" next to target -> atomic os.replace -> cleanup
```
4 readers + 4 writers cover all 12 routes (instead of 12 bespoke converters), so each fix helps every route.

**DocumentIR**: `Section(kind=page|slide|sheet|flow)` -> blocks `Paragraph(runs, heading, bullet, level)`, `Table(rows)`, `Picture(bytes, size)`.

## Process model
The UI never converts in-process. `ConversionJob` starts a `spawn`ed child; progress/results/errors travel over a queue as plain data.
Cancel = terminate the child, then the parent deletes its temp folder and partial file. Timeout and crash (non-zero exit) become friendly errors.
`BatchQueue` runs N such jobs in worker threads. The Qt layer only wraps these in `QThread`/signals, so almost all behaviour is unit-tested without Qt.

## Honest progress
Reading reports page/slide/sheet counts; PDF writing reports flowables laid out; verify/finalize are indeterminate (the bar switches to the busy animation).
A test asserts the sequence is monotonic and that only unmeasurable stages are indeterminate.

## Extension points
Add a format = one reader and/or writer + one entry in `converters/registry.py` and `core/capabilities.py`. A second UI (CLI already exists) can reuse `core` unchanged.
