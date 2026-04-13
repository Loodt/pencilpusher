"""Wiki page management — merge extractions, format pages, maintain structure."""

import json

import anthropic

MERGE_SYSTEM_PROMPT = """You are pencilpusher's wiki page editor. You maintain personal data wiki pages.

You receive:
1. The current content of a wiki page (markdown)
2. New data extracted from a source document
3. The source document filename

Your job:
- Merge the new data into the existing page content
- Keep the page well-organized with clear sections and fields
- Update existing values if the new data supersedes them (add "(updated from {source})" note)
- Add new values in the appropriate section
- Never remove existing data unless explicitly superseded
- Use a clean, consistent format:
  - **Field Name:** Value
  - Group related fields under ## subheadings
  - Include source attribution: (Source: filename)

Return ONLY the complete updated page content in markdown. No explanation, no code fences.
"""


def merge_extraction_into_page(
    page_name: str,
    current_content: str,
    update_data: dict,
    source_filename: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Merge extracted data into a wiki page using LLM for intelligent merging.

    Args:
        page_name: Wiki page name (e.g., "identity")
        current_content: Current page markdown content
        update_data: Dict with "fields" and/or "raw_text" from extraction
        source_filename: Name of the source document

    Returns:
        Updated page content as markdown string
    """
    fields = update_data.get("fields", {})
    raw_text = update_data.get("raw_text", "")

    # For simple cases (empty page + structured fields), skip the LLM
    if "No data ingested yet" in current_content and fields:
        return _simple_merge(page_name, fields, source_filename)

    # For complex merges, use the LLM
    client = anthropic.Anthropic()

    prompt = f"""Wiki page: {page_name}.md

Current content:
```
{current_content}
```

New data from "{source_filename}":
Fields: {json.dumps(fields, indent=2)}
{f'Additional text: {raw_text}' if raw_text else ''}

Merge the new data into the page. Return the complete updated page."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=MERGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


def _simple_merge(page_name: str, fields: dict, source_filename: str) -> str:
    """Simple merge for first-time data into an empty page."""
    title = page_name.replace("_", " ").title()
    lines = [f"# {title}\n"]

    for key, value in fields.items():
        label = key.replace("_", " ").title()
        lines.append(f"**{label}:** {value}")

    lines.append(f"\n---\n*Source: {source_filename}*")
    return "\n".join(lines)
