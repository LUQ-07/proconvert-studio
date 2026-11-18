"""Score how much of a source document's TEXT survives a conversion (no layout judgement).

  python tools/score_fidelity.py SOURCE.pdf OUTPUT.docx|OUTPUT.pptx|OUTPUT.xlsx

Prints word recall (source words found in the output), word precision (output words that exist in the source),
the F1 of both, the ordered similarity of the word sequence (difflib, 0..1) and structure counts of the output.
Running headers/footers and page numbers are ignored on both sides. Only text is compared: it cannot tell whether
the result LOOKS right, so always inspect the result as well.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

PUA = re.compile(r"[\ue000-\uf8ff]|\(cid:\d+\)")
TOKEN = re.compile(r"[\w\u00c0-\u024f]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(PUA.sub(" ", text)) if not t.isdigit()]


def source_text(path: Path) -> str:
    import pdfplumber
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            h = page.height
            for ln in page.extract_text_lines():
                if ln["top"] < h * 0.10 or ln["bottom"] > h * 0.90:       # running header/footer zone
                    continue
                out.append(ln["text"])
    return "\n".join(out)


def output_text(path: Path) -> tuple[str, dict]:
    ext = path.suffix.lower()
    if ext == ".docx":
        from docx import Document
        d = Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.extend(c.text for c in row.cells)
        styles = Counter(p.style.name for p in d.paragraphs if p.text.strip())
        return "\n".join(parts), {"paragraphs": sum(styles.values()), "headings": sum(v for k, v in styles.items() if k.startswith("Heading") or k == "Title"),
                                  "list items": sum(v for k, v in styles.items() if k.startswith("List")), "tables": len(d.tables), "pictures": len(d.inline_shapes)}
    if ext == ".pptx":
        from pptx import Presentation
        pr = Presentation(str(path))
        per_slide, shapes, pics = [], 0, 0
        for slide in pr.slides:
            texts = []
            for sh in slide.shapes:
                shapes += 1
                if sh.has_text_frame:
                    texts.append(sh.text_frame.text)
                if getattr(sh, "has_table", False) and sh.has_table:
                    texts.extend(c.text for r in sh.table.rows for c in r.cells)
                if sh.shape_type == 13:
                    pics += 1
            per_slide.append(texts)
        # text boxes repeated on half the slides are running footers, and "(continued)" titles repeat a heading
        freq = Counter(t for texts in per_slide for t in set(texts))
        repeated = {t for t, n in freq.items() if n >= max(3, len(per_slide) // 2)}
        parts = [t for texts in per_slide for t in texts if t not in repeated and not t.endswith("(continued)")]
        return "\n".join(parts), {"slides": len(pr.slides), "shapes": shapes, "pictures": pics, "running footers ignored": len(repeated)}
    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(str(path), read_only=True)
        parts = [str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None]
        return "\n".join(parts), {"sheets": len(wb.worksheets)}
    raise SystemExit(f"unsupported output type {ext}")


def score(src: Path, out: Path, header_words: set[str] | None = None) -> dict:
    a, b = tokens(source_text(src)), None
    text, info = output_text(out)
    b = tokens(text)
    if header_words:
        b = [t for t in b if t not in header_words]
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    recall = common / max(len(a), 1)
    precision = common / max(len(b), 1)
    f1 = 2 * recall * precision / max(recall + precision, 1e-9)
    # ordered similarity, measured on 400-word windows so it stays fast on long documents
    sm = []
    step = 400
    for i in range(0, len(a), step):
        chunk = a[i:i + step]
        sm.append(SequenceMatcher(None, chunk, b[max(0, i - 200): i + step + 600], autojunk=False).find_longest_match().size / max(len(chunk), 1))
    ordered = sum(sm) / max(len(sm), 1)
    return {"source_words": len(a), "output_words": len(b), "recall": round(recall, 4), "precision": round(precision, 4),
            "f1": round(f1, 4), "longest_run_ratio": round(ordered, 4), **info}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    for k, v in score(Path(sys.argv[1]), Path(sys.argv[2])).items():
        print(f"{k:>18}: {v}")
