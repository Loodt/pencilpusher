"""LLM-based data extraction from source documents.

Takes a document (PDF pages as images, DOCX as text) and extracts
structured personal data, then updates the relevant wiki pages.
"""

import base64
import json

import anthropic

from pencilpusher.config import WIKI_PAGES

EXTRACTION_SYSTEM_PROMPT = """You are pencilpusher's data extraction engine. Your job is to extract
personal AND company data from source documents and organize it into wiki page updates.

You will receive a document (as text or images) and the current state of relevant wiki pages.
Extract ALL factual data points and return structured updates.

Rules:
- Extract ONLY what is explicitly stated in the document. Never infer or fabricate.
- Preserve exact values: numbers, dates, reference numbers, account numbers, NRC numbers.
- If a value updates an existing entry, note it as an update (not a duplicate).
- Categorize each data point to the correct wiki page.
- Use the exact field names from the document where possible.

Wiki page categories:
- identity: name, ID number, passport, DOB, nationality, gender
- banking: bank accounts, branch codes
- company: general company info (use for the user's OWN company details)
- addresses: physical, postal addresses
- contacts: phone, email
- tax: tax numbers
- vehicles, medical, education, employment, legal, insurance: as expected

For COMPANY DOCUMENTS (company registrations, PACRA printouts, CIPC filings):
- Create a company-specific page using "companies/{slug}" as the key
- The slug should be lowercase, hyphens for spaces (e.g., "companies/showplus-investments")
- Include: registration number, company name, incorporation date, directors, shareholders,
  secretary, registered address, share capital, beneficial owners, annual returns status

Return JSON in this format:
{
    "source_summary": "One-line description of what this document is",
    "source_type": "passport|id_card|bank_letter|utility_bill|company_reg|company_printout|tax_cert|other",
    "updates": {
        "identity": {
            "fields": {"full_name": "John Doe", "id_number": "8501015800088"},
            "raw_text": "Markdown section to merge into identity.md"
        },
        "companies/showplus-investments": {
            "fields": {"reg_number": "120230055780", "name": "SHOWPLUS INVESTMENTS LIMITED"},
            "raw_text": "Markdown section with all company details"
        }
    },
    "unmatched": ["Any data that doesn't fit existing categories"]
}
"""


def extract_from_images(
    images: list[tuple[bytes, str]],
    current_wiki: dict[str, str],
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Extract personal data from document page images.

    Args:
        images: List of (image_bytes, media_type) tuples
        current_wiki: Current wiki page contents {page_name: content}
        model: Anthropic model to use

    Returns:
        Extraction result dict with updates per wiki page
    """
    client = anthropic.Anthropic()

    # Build the message with images + current wiki state
    content = []

    for img_bytes, media_type in images:
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })

    content.append({
        "type": "text",
        "text": "Extract all personal/business data from the document above.",
    })

    # Include current wiki state for context
    wiki_summary = _build_wiki_context(current_wiki)
    if wiki_summary:
        content.append({
            "type": "text",
            "text": f"Current wiki state (to avoid duplicates and detect updates):\n\n{wiki_summary}",
        })

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    return _parse_extraction_response(response.content[0].text)


def extract_from_text(
    text: str,
    source_description: str,
    current_wiki: dict[str, str],
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Extract personal data from document text (e.g., parsed DOCX)."""
    client = anthropic.Anthropic()

    wiki_summary = _build_wiki_context(current_wiki)
    prompt = f"Source document ({source_description}):\n\n{text}"
    if wiki_summary:
        prompt += f"\n\n---\nCurrent wiki state:\n\n{wiki_summary}"

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\nExtract all personal/business data from this document.",
        }],
    )

    return _parse_extraction_response(response.content[0].text)


def _build_wiki_context(wiki: dict[str, str]) -> str:
    """Build a concise wiki context string for the LLM."""
    parts = []
    for page_name in WIKI_PAGES:
        content = wiki.get(page_name, "")
        if content and "No data ingested yet" not in content:
            parts.append(f"### {page_name}.md\n{content}")
    return "\n\n".join(parts) if parts else ""


def _parse_extraction_response(response_text: str) -> dict:
    """Parse the LLM's JSON extraction response."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "source_summary": "Extraction failed — could not parse response",
            "source_type": "other",
            "updates": {},
            "unmatched": [response_text],
            "_parse_error": True,
        }
