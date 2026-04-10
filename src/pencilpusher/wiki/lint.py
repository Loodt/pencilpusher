"""Wiki lint — health checks for the personal data vault.

Follows Karpathy's lint pattern: periodically check for contradictions,
stale data, missing connections, and gaps.
"""

import json

import anthropic

from pencilpusher.config import WIKI_PAGES


LINT_SYSTEM_PROMPT = """You are pencilpusher's wiki linter. Analyze the personal data wiki pages
and identify issues.

Check for:
1. CONTRADICTIONS — same field with different values across pages
   (e.g., different addresses in identity.md vs banking.md)
2. STALE DATA — values that might be outdated (dates more than 2 years old)
3. INCOMPLETE — pages that reference other data not yet in the vault
4. FORMATTING — inconsistent field naming or structure
5. GAPS — important missing information for common form-filling scenarios

Return JSON:
{
    "issues": [
        {
            "severity": "error|warning|info",
            "category": "contradiction|stale|incomplete|formatting|gap",
            "page": "identity",
            "description": "Description of the issue",
            "suggestion": "How to fix it"
        }
    ],
    "summary": "One-line overall assessment"
}
"""


def lint_wiki(
    wiki_pages: dict[str, str],
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Run lint checks on the vault wiki."""
    client = anthropic.Anthropic()

    wiki_text = "\n\n".join(
        f"### {name}.md\n{content}"
        for name, content in wiki_pages.items()
        if content and "No data ingested yet" not in content
    )

    if not wiki_text:
        return {
            "issues": [{"severity": "info", "category": "gap", "page": "all",
                        "description": "Vault is empty", "suggestion": "Ingest some documents"}],
            "summary": "Vault is empty — nothing to lint",
        }

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=LINT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Lint these wiki pages:\n\n{wiki_text}"}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"issues": [], "summary": "Lint completed (could not parse detailed results)"}
