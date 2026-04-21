"""PDF filler — write matched values into PDF documents.

Three proven approaches (tested on real documents):

1. AcroForm fill — set existing form field values via PyMuPDF widgets.
2. Flat-PDF widget fill — CREATE form fields at detected coordinates, then
   fill them. Styles like-a-form-field. Hard-coded 10 pt font, no wrap.
3. Flat-PDF textbox fill — overlay text using `page.insert_textbox()` with
   auto-font-shrink on overflow. Use when cells are narrow and answers
   are multi-word / multi-line — widgets clip those. See the `mode`
   argument of `fill_pdf()`.

All modes preserve the original document styling — modes 1 + 2 add widget
annotations; mode 3 only overlays text.
"""

from pathlib import Path

from pencilpusher.fill.detector import DetectedField


def fill_pdf(
    pdf_path: Path,
    matches: list[dict],
    fields: list[DetectedField],
    output_path: Path,
    mode: str = "widget",
) -> Path:
    """Fill a PDF.

    Auto-detects whether the PDF already has AcroForm fields. If it does,
    fills them regardless of `mode`. If it's flat, `mode` controls the
    fallback strategy:

    - ``"widget"`` (default): create single-line text widgets at each bbox.
      Fast, style-preserving, but uses a fixed 10 pt font with no wrap —
      answers longer than the cell are clipped.
    - ``"textbox"``: overlay text via ``page.insert_textbox()`` with
      automatic font-size shrink on overflow. Slower, but handles narrow
      cells with multi-word answers. Per-field overrides (font size,
      colour, alignment) can be supplied in the matched field's
      ``options`` dict — see ``_fill_with_textboxes`` below.
    """
    import fitz

    doc = fitz.open(str(pdf_path))

    # Check if it already has form fields
    has_widgets = any(
        True for page in doc for _ in page.widgets()
    )

    if has_widgets:
        _fill_existing_widgets(doc, matches)
    elif mode == "textbox":
        _fill_with_textboxes(doc, matches, fields)
    else:
        _create_and_fill_widgets(doc, matches, fields)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()

    return output_path


def _fill_existing_widgets(doc, matches: list[dict]) -> None:
    """Fill existing AcroForm fields by matching field names to values."""
    # Build name -> value lookup
    fill_map = {}
    for match in matches:
        val = match.get("matched_value")
        if not val:
            continue
        if match.get("field_key"):
            fill_map[match["field_key"]] = val
        if match.get("field_name"):
            fill_map[match["field_name"]] = val

    for page in doc:
        for widget in page.widgets():
            name = widget.field_name
            value = fill_map.get(name)
            if value:
                widget.field_value = str(value)
                widget.update()


def _create_and_fill_widgets(
    doc,
    matches: list[dict],
    fields: list[DetectedField],
) -> None:
    """Create form fields on a flat PDF at detected coordinates, then fill them.

    This is the proven approach for flat PDFs: instead of fragile text overlay,
    we create proper AcroForm widgets that blend with the existing document.
    """
    import fitz

    # Build field lookup
    field_lookup = {f.name: f for f in fields}

    for match in matches:
        value = match.get("matched_value")
        field_name = match.get("field_name")
        if not value or not field_name:
            continue

        field = field_lookup.get(field_name)
        if not field or not field.bbox or field.page is None:
            continue

        page = doc[field.page]
        page_rect = page.rect

        # Convert percentage bbox to page coordinates
        bx, by, bw, bh = field.bbox
        x0 = page_rect.width * bx / 100
        y0 = page_rect.height * by / 100
        x1 = x0 + page_rect.width * bw / 100
        y1 = y0 + page_rect.height * bh / 100

        # Create a proper form field widget
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = field_name.replace(" ", "_").lower()
        widget.rect = fitz.Rect(x0, y0, x1, y1)
        widget.field_value = str(value)
        widget.text_fontsize = 10
        widget.text_color = (0, 0, 0)
        # Borderless to blend with existing form layout
        widget.border_color = None
        widget.fill_color = None

        page.add_widget(widget)


def _fill_with_textboxes(
    doc,
    matches: list[dict],
    fields: list[DetectedField],
) -> None:
    """Fill a flat PDF by overlaying text via ``insert_textbox``.

    Unlike ``_create_and_fill_widgets``, this path handles narrow cells
    with multi-word answers: ``insert_textbox`` wraps text, and when the
    text still overflows, we retry at smaller font sizes before falling
    back to a truncated write.

    Per-field options may be supplied on each DetectedField via
    ``context`` (kept for backward compatibility) or, preferably,
    through a ``textbox_options`` dict on the match record:

        {"font": "helv",
         "font_size": 9.5,
         "font_color": [0, 0, 0.75],   # RGB, 0-1
         "align": "left"}              # left | center | right

    Defaults: Helvetica 10 pt, black, left-aligned.
    """
    import fitz

    field_lookup = {f.name: f for f in fields}
    align_map = {
        "left": fitz.TEXT_ALIGN_LEFT,
        "center": fitz.TEXT_ALIGN_CENTER,
        "centre": fitz.TEXT_ALIGN_CENTER,
        "right": fitz.TEXT_ALIGN_RIGHT,
    }

    for match in matches:
        value = match.get("matched_value")
        field_name = match.get("field_name")
        if not value or not field_name:
            continue

        field = field_lookup.get(field_name)
        if not field or not field.bbox or field.page is None:
            continue

        opts = match.get("textbox_options") or {}
        font = opts.get("font", "helv")
        base_size = float(opts.get("font_size", 10))
        color_raw = opts.get("font_color", (0, 0, 0))
        color = tuple(color_raw) if isinstance(color_raw, list) else color_raw
        align = align_map.get(str(opts.get("align", "left")).lower(),
                              fitz.TEXT_ALIGN_LEFT)

        page = doc[field.page]
        page_rect = page.rect

        bx, by, bw, bh = field.bbox
        x0 = page_rect.width * bx / 100
        y0 = page_rect.height * by / 100
        x1 = x0 + page_rect.width * bw / 100
        y1 = y0 + page_rect.height * bh / 100
        rect = fitz.Rect(x0, y0, x1, y1)

        text = str(value)
        # Try progressively smaller font sizes until the text fits.
        # insert_textbox returns a non-negative number on success, negative
        # if the text overflows the box.
        for fs in (base_size,
                   base_size - 1.0,
                   base_size - 2.0,
                   base_size - 2.5,
                   base_size - 3.0):
            if fs < 5.0:
                break
            rc = page.insert_textbox(
                rect, text,
                fontname=font, fontsize=fs, color=color, align=align,
            )
            if rc >= 0:
                break
        else:
            # Last resort: truncate with an ellipsis at the minimum font.
            truncated = text
            # Rough heuristic: ~1.8 chars per point of cell width at 5 pt.
            max_chars = max(12, int(rect.width / 2.6))
            if len(truncated) > max_chars:
                truncated = truncated[:max_chars - 1].rstrip() + "\u2026"
            page.insert_textbox(
                rect, truncated,
                fontname=font, fontsize=5.0, color=color, align=align,
            )


# Keep legacy functions as aliases for backward compatibility
def fill_pdf_acroform(pdf_path: Path, matches: list[dict], output_path: Path) -> Path:
    """Fill existing AcroForm fields. Legacy wrapper."""
    import fitz
    doc = fitz.open(str(pdf_path))
    _fill_existing_widgets(doc, matches)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path


def fill_pdf_overlay(
    pdf_path: Path, matches: list[dict], fields: list[DetectedField], output_path: Path, **kwargs
) -> Path:
    """Create widgets on flat PDF. Legacy wrapper (renamed from overlay to widget creation)."""
    return fill_pdf(pdf_path, matches, fields, output_path)
