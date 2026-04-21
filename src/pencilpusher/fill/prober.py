"""Flat-PDF layout prober — dump cell-divider x-coords and candidate row anchors.

Many real-world supplier and government forms are flat PDFs with no AcroForm
fields and no consistent `search_for(label)` anchors. Filling them requires
computing where the cells are. This module does that up-front so an agent
building a `--fields-json` payload has the structural information it needs
instead of guessing.

Returns for each page:

- `column_dividers` — unique x-coords of vertical cell dividers (from thin,
  tall rectangles found in `page.get_drawings()`). These are the
  authoritative column boundaries to clamp answer-box x-starts against.
- `row_horizontals` — y-coords of horizontal dividers (the row separators).
- `digit_spans` — every short digit-only text span with its bbox. Useful
  for anchoring row numbers in a "No." column; the agent filters by
  x-range to build a `{row_number: y_top}` map.

Use together:

```python
from pencilpusher.fill.prober import probe_pdf_layout
layout = probe_pdf_layout("enquiry.pdf")
# Filter digit_spans to the No.-column (x in [120, 150], say), build row map,
# clamp answer x-starts to the first column divider > label bbox.x1.
```
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path


def probe_pdf_layout(
    pdf_path: str | Path,
    *,
    min_divider_count: int = 3,
    divider_line_thickness: float = 1.0,
) -> dict:
    """Probe a flat PDF's cell structure and return a JSON-serialisable layout.

    Args:
        pdf_path: path to the flat PDF to inspect.
        min_divider_count: a vertical divider is reported only if it appears in
            at least this many rectangles (filters out one-off graphics).
        divider_line_thickness: a rectangle is treated as a thin divider line
            if its short edge is <= this many PDF points.

    Returns:
        A dict with one entry per page: dimensions, column_dividers,
        row_horizontals, and digit_spans.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    try:
        pages = [_probe_page(page, min_divider_count, divider_line_thickness)
                 for page in doc]
    finally:
        doc.close()

    return {"pages": pages}


def _probe_page(page, min_divider_count: int, thin: float) -> dict:
    rect = page.rect
    vertical_x: Counter = Counter()
    horizontal_y: Counter = Counter()

    for drawing in page.get_drawings():
        r = drawing.get("rect")
        if r is None:
            continue
        w = r.width
        h = r.height
        # Thin-and-tall → vertical divider; thin-and-wide → horizontal divider.
        if w <= thin and h > thin:
            vertical_x[round(r.x0, 1)] += 1
        elif h <= thin and w > thin:
            horizontal_y[round(r.y0, 1)] += 1
        elif h <= thin and w <= thin:
            # Tiny anchor-tick — ignore.
            continue
        else:
            # Full cell rectangle — its four edges are divider hints.
            vertical_x[round(r.x0, 1)] += 1
            vertical_x[round(r.x1, 1)] += 1
            horizontal_y[round(r.y0, 1)] += 1
            horizontal_y[round(r.y1, 1)] += 1

    column_dividers = sorted(
        x for x, n in vertical_x.items() if n >= min_divider_count
    )
    row_horizontals = sorted(
        y for y, n in horizontal_y.items() if n >= min_divider_count
    )

    digit_spans: list[dict] = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = (span.get("text") or "").strip()
                if not t:
                    continue
                if not (t.isascii() and t.isdigit() and 1 <= len(t) <= 3):
                    continue
                bb = span["bbox"]
                digit_spans.append({
                    "text": t,
                    "bbox": [round(v, 2) for v in bb],
                })

    return {
        "page": page.number,
        "width": round(rect.width, 2),
        "height": round(rect.height, 2),
        "column_dividers": column_dividers,
        "row_horizontals": row_horizontals,
        "digit_spans": digit_spans,
    }
