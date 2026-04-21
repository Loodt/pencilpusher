"""Fill pipeline — orchestrates field detection, matching, and document filling.

This is the main user-facing operation: "here's a form, fill it with my data."
"""

from pathlib import Path

from rich.console import Console
from rich.table import Table

from pencilpusher.fill.detector import detect_docx_fields, detect_pdf_fields
from pencilpusher.fill.docx_filler import fill_docx
from pencilpusher.fill.matcher import match_fields_to_vault
from pencilpusher.fill.pdf_filler import fill_pdf
from pencilpusher.ingest.reader import detect_file_type
from pencilpusher.vault.store import Vault

console = Console()


def fill_document(
    vault: Vault,
    target_path: Path,
    output_path: Path | None = None,
    model: str = "claude-sonnet-4-6",
    auto_confirm: bool = False,
    textbox_mode: bool = False,
) -> Path:
    """Fill a document with data from the vault.

    Steps:
    1. Detect fields in the target document
    2. Match fields to vault data
    3. Show preview and ask for confirmation
    4. Fill the document
    5. Save to output path

    Args:
        vault: The vault instance with personal data
        target_path: Path to the form/document to fill
        output_path: Where to save the filled document (default: alongside original)
        model: Anthropic model for field detection and matching
        auto_confirm: Skip confirmation prompt

    Returns:
        Path to the filled document
    """
    target_path = Path(target_path)
    if not target_path.exists():
        raise FileNotFoundError(f"Target document not found: {target_path}")

    file_type = detect_file_type(target_path)

    # Default output path
    if output_path is None:
        stem = target_path.stem
        output_path = target_path.parent / f"{stem}_filled{target_path.suffix}"
    output_path = Path(output_path)

    # Step 1: Detect fields
    console.print(f"\n[bold]Detecting fields in {target_path.name}...[/bold]")

    if file_type == "pdf":
        fields = detect_pdf_fields(target_path, model=model)
    elif file_type == "docx":
        fields = detect_docx_fields(target_path)
    else:
        raise ValueError(f"Unsupported file type for filling: {target_path.suffix}")

    if not fields:
        console.print("[yellow]No fillable fields detected.[/yellow]")
        return target_path

    console.print(f"Found [bold]{len(fields)}[/bold] fields.")

    # Step 2: Match fields to vault data
    console.print("\n[bold]Matching fields to your vault data...[/bold]")
    wiki_pages = vault.read_all_wiki_pages()
    match_result = match_fields_to_vault(fields, wiki_pages, model=model)

    matches = match_result.get("matches", [])
    warnings = match_result.get("warnings", [])
    unmatchable = match_result.get("unmatchable_fields", [])

    # Step 3: Preview
    _show_preview(matches, unmatchable, warnings)

    if not auto_confirm:
        confirm = console.input("\n[bold]Fill document with these values? [Y/n]:[/bold] ")
        if confirm.lower() in ("n", "no"):
            console.print("[yellow]Cancelled.[/yellow]")
            return target_path

    # Step 4: Fill
    console.print(f"\n[bold]Filling {target_path.name}...[/bold]")

    successful_matches = [m for m in matches if m.get("matched_value")]

    if file_type == "pdf":
        result_path = fill_pdf(
            target_path, successful_matches, fields, output_path,
            mode="textbox" if textbox_mode else "widget",
        )
    elif file_type == "docx":
        result_path = fill_docx(target_path, successful_matches, fields, output_path)
    else:
        raise ValueError(f"Unsupported file type for filling: {target_path.suffix}")

    # Step 5: Report
    filled_count = len(successful_matches)
    total_count = len(fields)
    console.print(f"\n[bold green]Done![/bold green] Filled {filled_count}/{total_count} fields.")
    console.print(f"Saved to: [bold]{result_path}[/bold]")

    if unmatchable:
        console.print(f"\n[yellow]{len(unmatchable)} fields could not be matched:[/yellow]")
        for name in unmatchable:
            console.print(f"  - {name}")

    vault._log("fill", f"Filled {target_path.name} → {output_path.name} ({filled_count}/{total_count} fields)")

    return result_path


def fill_document_with_map(
    target_path: Path,
    field_map: dict[str, str],
    output_path: Path | None = None,
    fields_override: list[dict] | None = None,
    textbox_mode: bool = False,
) -> Path:
    """Fill a document using an explicit field-to-value mapping (no API calls).

    For AcroForm PDFs and DOCX, field detection is deterministic.
    For flat PDFs, pass fields_override with bbox data from agent vision analysis.

    Args:
        target_path: Path to the form/document to fill
        field_map: Dict mapping field names to values (e.g. {"Full Name": "Jane Moyo"})
        output_path: Where to save (default: alongside original with _filled suffix)
        fields_override: List of field dicts with name, bbox, page, etc.
            Used for flat PDFs where the agent provides field positions.
        textbox_mode: For flat PDFs, use ``insert_textbox`` overlay with
            font-size shrink fallback instead of creating fixed-10pt
            single-line widgets. Prefer this for dense supplier /
            government forms where answers are multi-word and cells
            are narrow. Per-field font / colour / alignment overrides
            can be supplied via a ``textbox_options`` key on each
            fields_override entry, which will be passed through to the
            matches list.

    Returns:
        Path to the filled document
    """
    from pencilpusher.fill.detector import DetectedField, detect_acroform_fields

    target_path = Path(target_path)
    if not target_path.exists():
        raise FileNotFoundError(f"Target document not found: {target_path}")

    file_type = detect_file_type(target_path)

    if output_path is None:
        output_path = target_path.parent / f"{target_path.stem}_filled{target_path.suffix}"
    output_path = Path(output_path)

    # Use fields_override if provided (agent-driven flat PDF filling)
    if fields_override is not None:
        fields = [
            DetectedField(
                name=f.get("name", ""),
                field_type=f.get("field_type", "visual"),
                page=f.get("page"),
                field_key=f.get("field_key", f.get("name", "")),
                bbox=f.get("bbox", []),
                value=f.get("value", ""),
                required=f.get("required", False),
                context=f.get("context", ""),
            )
            for f in fields_override
        ]
    elif file_type == "pdf":
        fields = detect_acroform_fields(target_path)
        if not fields:
            console.print("[yellow]Warning: Flat PDF — no AcroForm fields found. "
                          "Use --fields-json to provide field positions for flat PDFs.[/yellow]")
    elif file_type == "docx":
        fields = detect_docx_fields(target_path)
    else:
        raise ValueError(f"Unsupported file type: {target_path.suffix}")

    # Convert field_map to matches format expected by fillers
    # (pull textbox_options from fields_override so per-field formatting
    # flows through to the textbox filler).
    override_opts = {}
    if fields_override:
        for f in fields_override:
            name = f.get("name")
            if name and f.get("textbox_options"):
                override_opts[name] = f["textbox_options"]

    matches = []
    for field_name, value in field_map.items():
        # Try to find a matching detected field for the key
        field_key = field_name
        for f in fields:
            if f.name.lower() == field_name.lower() or f.field_key.lower() == field_name.lower():
                field_key = f.field_key
                break
        match = {
            "field_name": field_name,
            "field_key": field_key,
            "matched_value": value,
        }
        if field_name in override_opts:
            match["textbox_options"] = override_opts[field_name]
        matches.append(match)

    # Fill
    if file_type == "pdf":
        result_path = fill_pdf(
            target_path, matches, fields, output_path,
            mode="textbox" if textbox_mode else "widget",
        )
    elif file_type == "docx":
        result_path = fill_docx(target_path, matches, fields, output_path)

    filled_count = len([m for m in matches if m.get("matched_value")])
    console.print(f"[bold green]Filled {filled_count} fields.[/bold green] Saved to: {result_path}")

    return result_path


def _show_preview(matches: list[dict], unmatchable: list[str], warnings: list[str]) -> None:
    """Show a preview table of matched fields."""
    table = Table(title="Field Matches", show_lines=True)
    table.add_column("Field", style="bold")
    table.add_column("Value", style="green")
    table.add_column("Source", style="dim")
    table.add_column("Confidence")

    for match in matches:
        value = match.get("matched_value") or "[red]No match[/red]"
        source = match.get("source_page", "—")
        confidence = match.get("confidence", 0)
        conf_str = f"{'[green]' if confidence > 0.8 else '[yellow]'}{confidence:.0%}[/]"

        if not match.get("matched_value"):
            value = "[red]— not found —[/red]"
            conf_str = "[red]0%[/red]"

        table.add_row(match.get("field_name", "?"), str(value), source, conf_str)

    console.print(table)

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  [yellow]![/yellow] {w}")
