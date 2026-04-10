"""Ingest pipeline — orchestrates reading, extracting, and updating the vault wiki.

Primary flow (MarkItDown path — cheaper, faster):
  source doc → MarkItDown → markdown text → Claude text API → wiki updates

Fallback flow (vision path — for scanned/image docs):
  source doc → PyMuPDF render → PNG images → Claude vision API → wiki updates
"""

import re
from pathlib import Path

from pencilpusher.config import WIKI_PAGES
from pencilpusher.ingest.extractor import extract_from_images, extract_from_text
from pencilpusher.ingest.reader import (
    detect_file_type,
    read_image,
    read_pdf_as_images,
    read_with_markitdown,
)
from pencilpusher.vault.store import Vault
from pencilpusher.wiki.pages import merge_extraction_into_page


def ingest_document(
    vault: Vault,
    source_path: Path,
    category: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Ingest a source document into the vault.

    Steps (following Karpathy's ingest pattern):
    1. Convert document to markdown (MarkItDown) or images (fallback)
    2. Send to LLM with current wiki state for context
    3. Extract structured data
    4. Update relevant wiki pages (including company pages)
    5. Update index
    6. Log the operation
    """
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source document not found: {source_path}")

    file_type = detect_file_type(source_path)
    current_wiki = vault.read_all_wiki_pages()

    # Step 1-3: Try MarkItDown first (text API — cheaper, faster)
    markdown_text = read_with_markitdown(source_path)

    if markdown_text:
        result = extract_from_text(markdown_text, source_path.name, current_wiki, model=model)
    elif file_type == "pdf":
        # Fallback: render PDF pages as images for vision API
        images = read_pdf_as_images(source_path)
        result = extract_from_images(images, current_wiki, model=model)
    elif file_type == "image":
        img_bytes, media_type = read_image(source_path)
        result = extract_from_images([(img_bytes, media_type)], current_wiki, model=model)
    else:
        raise ValueError(f"Unsupported file type: {source_path.suffix}")

    if result.get("_parse_error"):
        return result

    # Auto-detect category
    if category is None:
        category = _guess_category(result)

    # Store raw source
    vault.store_raw(source_path, category)

    # Step 4: Update wiki pages
    updates = result.get("updates", {})
    pages_updated = []

    for page_name, update_data in updates.items():
        # Handle both standard pages and company pages
        if page_name in WIKI_PAGES or page_name.startswith("companies/"):
            current_content = vault.read_wiki_page(page_name)
            if not current_content and page_name.startswith("companies/"):
                # Create new company page
                company_name = page_name.replace("companies/", "").replace("_", " ").title()
                current_content = f"# {company_name}\n\nNo data ingested yet.\n"
            new_content = merge_extraction_into_page(
                page_name, current_content, update_data, source_path.name
            )
            vault.write_wiki_page(page_name, new_content)
            pages_updated.append(page_name)

    # Step 5: Update index
    _update_index(vault, pages_updated)

    # Mark as ingested in manifest
    vault.mark_ingested(source_path.name)

    result["pages_updated"] = pages_updated
    result["stored_as"] = category
    result["reader"] = "markitdown" if markdown_text else "vision"
    return result


def ingest_all(vault: Vault, model: str = "claude-sonnet-4-6") -> list[dict]:
    """Ingest all new files from sources/ directory.

    Skips files already in the manifest. Returns list of results.
    """
    sources = vault.list_sources()
    results = []

    for source_path in sources:
        if vault.is_ingested(source_path.name):
            continue

        try:
            result = ingest_document(vault, source_path, model=model)
            results.append({"file": source_path.name, "status": "ok", **result})
        except Exception as e:
            results.append({"file": source_path.name, "status": "error", "error": str(e)})

    return results


def _guess_category(result: dict) -> str:
    """Guess the storage category from the extraction result."""
    source_type = result.get("source_type", "other")
    mapping = {
        "passport": "identity",
        "id_card": "identity",
        "bank_letter": "banking",
        "utility_bill": "residence",
        "company_reg": "company",
        "company_printout": "company",
        "tax_cert": "tax",
    }
    return mapping.get(source_type, "other")


def _update_index(vault: Vault, updated_pages: list[str]) -> None:
    """Update the index.md to reflect which pages were updated."""
    import datetime

    if not updated_pages:
        return

    index_content = vault.read_wiki_page("index")
    today = datetime.date.today().isoformat()

    for page_name in updated_pages:
        old_pattern = f"| [{page_name}]({page_name}.md) |"
        if old_pattern in index_content:
            lines = index_content.split("\n")
            for i, line in enumerate(lines):
                if old_pattern in line:
                    parts = line.rsplit("|", 2)
                    if len(parts) >= 3:
                        lines[i] = f"{parts[0]}| {today} |"
            index_content = "\n".join(lines)

    vault._write_wiki_page("index", index_content)
