"""PDF filler — write matched values into PDF documents.

Two proven approaches (tested on real documents):

1. AcroForm fill — set existing form field values via PyMuPDF widgets
2. Flat PDF fill — CREATE form fields at detected coordinates, then fill them

Both preserve all original document styling since we only add/modify widget annotations.
"""

from pathlib import Path

from pencilpusher.fill.detector import DetectedField


def fill_pdf(
    pdf_path: Path,
    matches: list[dict],
    fields: list[DetectedField],
    output_path: Path,
) -> Path:
    """Fill a PDF — auto-detects whether it has AcroForm fields or needs widget creation."""
    import fitz

    doc = fitz.open(str(pdf_path))

    # Check if it already has form fields
    has_widgets = any(
        True for page in doc for _ in page.widgets()
    )

    if has_widgets:
        _fill_existing_widgets(doc, matches)
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
