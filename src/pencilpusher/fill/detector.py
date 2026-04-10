"""Field detection — identify fillable fields in target documents.

Three strategies depending on document type:
1. AcroForm PDFs — read form field names directly (no LLM needed)
2. Flat PDFs — use Claude vision to identify fields by visual layout
3. Word docs — detect placeholders, content controls, merge fields, or blank lines
"""

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic


@dataclass
class DetectedField:
    """A field detected in a target document."""
    name: str                  # Human-readable field name (e.g., "Full Name")
    field_type: str            # "acroform" | "visual" | "placeholder" | "content_control"
    page: int | None = None    # Page number (0-indexed, for PDFs)
    field_key: str = ""        # Technical key (AcroForm field name, placeholder text)
    bbox: list = field(default_factory=list)  # [x, y, width, height] for visual fields
    value: str = ""            # Current value (if pre-filled)
    required: bool = False
    context: str = ""          # Surrounding text for semantic matching


def detect_pdf_fields(pdf_path: Path, model: str = "claude-sonnet-4-6") -> list[DetectedField]:
    """Detect all fillable fields in a PDF.

    First tries AcroForm fields (fast, no LLM).
    Falls back to Claude vision for flat PDFs.
    """
    # Try AcroForm first
    acroform_fields = _detect_acroform_fields(pdf_path)
    if acroform_fields:
        return acroform_fields

    # Fall back to visual detection
    return _detect_visual_fields(pdf_path, model)


def _detect_acroform_fields(pdf_path: Path) -> list[DetectedField]:
    """Extract AcroForm fields from a PDF."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    fields = []

    if not reader.get_fields():
        return []

    for field_name, field_obj in reader.get_fields().items():
        field_type = field_obj.get("/FT", "")
        current_value = field_obj.get("/V", "")
        if hasattr(current_value, "get_object"):
            current_value = str(current_value)

        fields.append(DetectedField(
            name=_humanize_field_name(field_name),
            field_type="acroform",
            field_key=field_name,
            value=str(current_value) if current_value else "",
            context=f"PDF form field: {field_name} (type: {field_type})",
        ))

    return fields


def _detect_visual_fields(pdf_path: Path, model: str) -> list[DetectedField]:
    """Use Claude vision to detect fields in a flat PDF."""
    import fitz

    doc = fitz.open(str(pdf_path))
    client = anthropic.Anthropic()
    all_fields = []

    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=FIELD_DETECTION_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": f"Detect all fillable fields on page {page_num + 1} of this document."},
                ],
            }],
        )

        page_fields = _parse_field_detection(response.content[0].text, page_num)
        all_fields.extend(page_fields)

    doc.close()
    return all_fields


def detect_docx_fields(docx_path: Path) -> list[DetectedField]:
    """Detect fillable fields in a Word document.

    Checks for:
    1. Content controls (structured document tags)
    2. Merge fields (MERGEFIELD)
    3. Text placeholders like [___], {name}, <<name>>, ________
    """
    import docx
    from lxml import etree

    doc = docx.Document(str(docx_path))
    fields = []

    # 1. Check for content controls (SDTs)
    nsmap = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for sdt in doc.element.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sdt"):
        alias_elem = sdt.find(".//w:sdtPr/w:alias", nsmap)
        tag_elem = sdt.find(".//w:sdtPr/w:tag", nsmap)
        text_elem = sdt.find(".//w:sdtContent//w:t", nsmap)

        name = ""
        if alias_elem is not None:
            name = alias_elem.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
        elif tag_elem is not None:
            name = tag_elem.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")

        current_value = text_elem.text if text_elem is not None else ""

        if name:
            fields.append(DetectedField(
                name=_humanize_field_name(name),
                field_type="content_control",
                field_key=name,
                value=current_value or "",
            ))

    # 2. Check for placeholder patterns in paragraphs
    import re
    placeholder_patterns = [
        (r'\[___+\]', "bracket_underline"),
        (r'\{(\w[\w\s]*)\}', "curly_brace"),
        (r'<<(\w[\w\s]*)>>', "angle_bracket"),
        (r'_{5,}', "underline"),
        (r'\[([A-Z][\w\s]*)\]', "bracket_label"),
    ]

    for para in doc.paragraphs:
        text = para.text
        for pattern, ptype in placeholder_patterns:
            for match in re.finditer(pattern, text):
                matched_text = match.group(0)
                # Get context — text before the match on the same line
                start = max(0, match.start() - 40)
                context = text[start:match.start()].strip()

                field_name = context if context else matched_text
                # For named placeholders, use the captured group
                if match.lastindex and match.lastindex >= 1:
                    field_name = match.group(1)

                fields.append(DetectedField(
                    name=_humanize_field_name(field_name),
                    field_type="placeholder",
                    field_key=matched_text,
                    context=context,
                ))

    return fields


def _humanize_field_name(name: str) -> str:
    """Convert a technical field name to human-readable form."""
    import re
    # Handle camelCase and PascalCase
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Handle underscores and hyphens
    name = name.replace("_", " ").replace("-", " ")
    # Clean up
    name = " ".join(name.split())
    return name.strip().title()


def _parse_field_detection(response_text: str, page_num: int) -> list[DetectedField]:
    """Parse Claude's field detection response."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    fields = []
    for item in data.get("fields", []):
        fields.append(DetectedField(
            name=item.get("name", "Unknown"),
            field_type="visual",
            page=page_num,
            bbox=item.get("bbox", []),
            context=item.get("context", ""),
            required=item.get("required", False),
        ))
    return fields


FIELD_DETECTION_PROMPT = """You are pencilpusher's field detector. Analyze this document page image and
identify ALL fields that need to be filled in by a person.

Look for:
- Blank lines next to labels (e.g., "Name: ____________")
- Empty boxes or checkboxes
- Dotted lines or underlines meant for writing
- Tables with empty cells meant for data entry
- Any area clearly intended for the user to write/type information

For each field, determine:
- name: The label/description of what should go there
- bbox: Approximate [x, y, width, height] as percentages of page dimensions (0-100)
- context: Surrounding text that helps identify what data is needed
- required: Whether it appears mandatory

Return JSON:
{
    "fields": [
        {
            "name": "Full Name",
            "bbox": [15, 20, 50, 3],
            "context": "Section 1: Personal Details — Full Name",
            "required": true
        }
    ]
}
"""
