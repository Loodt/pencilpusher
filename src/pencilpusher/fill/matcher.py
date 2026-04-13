"""Field matcher — maps detected fields to vault data using semantic matching.

The core intelligence: given a field like "Applicant Full Name" and a vault
that has identity.md with "Full Name: Lodewyk Bronn", figure out the match.
"""

import json

import anthropic

from pencilpusher.fill.detector import DetectedField

MATCHING_SYSTEM_PROMPT = """You are pencilpusher's field matcher. Your job is to match document form fields
to personal data stored in a wiki-style vault.

You receive:
1. A list of detected fields (with names, context, and types)
2. The user's personal data wiki (organized by category)

For each field, find the BEST matching value from the vault. Rules:
- Match semantically, not just by exact name ("Applicant Name" = "Full Name")
- Use context clues (e.g., a field in a "Banking Details" section likely wants bank info)
- If a field clearly asks for something not in the vault, mark it as "no_match"
- If ambiguous (multiple possible matches), pick the most likely and flag it
- For date fields, use the format suggested by the field context (DD/MM/YYYY etc.)
- For address fields, combine relevant parts (street, city, postal code) as needed
- NEVER fabricate data. If it's not in the vault, it's "no_match"

Return JSON:
{
    "matches": [
        {
            "field_name": "Full Name",
            "field_key": "the_technical_key",
            "matched_value": "Lodewyk Bronn",
            "source_page": "identity",
            "confidence": 0.95,
            "notes": null
        },
        {
            "field_name": "Spouse Name",
            "field_key": "spouse_name",
            "matched_value": null,
            "source_page": null,
            "confidence": 0.0,
            "notes": "no_match — not found in vault"
        }
    ],
    "unmatchable_fields": ["Spouse Name"],
    "warnings": ["Field 'Date' is ambiguous — used date of birth, but could be today's date"]
}
"""


def match_fields_to_vault(
    fields: list[DetectedField],
    wiki_pages: dict[str, str],
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Match detected fields to vault data.

    Args:
        fields: List of detected fields from the target document
        wiki_pages: Dict of {page_name: content} from the vault wiki
        model: Anthropic model to use

    Returns:
        Match result dict with matches, unmatchable fields, and warnings
    """
    client = anthropic.Anthropic()

    fields_data = [
        {
            "name": f.name,
            "field_key": f.field_key,
            "field_type": f.field_type,
            "context": f.context,
            "current_value": f.value,
            "page": f.page,
        }
        for f in fields
    ]

    wiki_text = "\n\n".join(
        f"### {name}.md\n{content}"
        for name, content in wiki_pages.items()
        if content and "No data ingested yet" not in content
    )

    if not wiki_text:
        return {
            "matches": [],
            "unmatchable_fields": [f.name for f in fields],
            "warnings": ["Vault is empty — ingest personal documents first"],
        }

    prompt = f"""Fields to match:
{json.dumps(fields_data, indent=2)}

Personal data vault:
{wiki_text}

Match each field to the best value from the vault."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=MATCHING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_match_response(response.content[0].text)


def _parse_match_response(response_text: str) -> dict:
    """Parse the LLM's matching response."""
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
            "matches": [],
            "unmatchable_fields": [],
            "warnings": [f"Failed to parse match response: {response_text[:200]}"],
            "_parse_error": True,
        }
