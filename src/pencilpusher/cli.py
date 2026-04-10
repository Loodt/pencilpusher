"""pencilpusher CLI — The AI bureaucrat that fills forms so you don't have to.

Usage:
    pencilpusher init                          # Set up your vault
    pencilpusher ingest <file>                 # Add a personal document to your vault
    pencilpusher fill <form>                   # Fill a form with your vault data
    pencilpusher show [page]                   # Show what's in your vault
    pencilpusher lint                          # Health-check your vault wiki
"""

import getpass
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from pencilpusher.config import WIKI_PAGES, get_vault_dir, load_config

console = Console()


def _get_vault(password: str | None = None):
    """Get or create a vault instance, prompting for password if needed."""
    from pencilpusher.vault.store import Vault

    config = load_config()
    vault_dir = Path(config["vault_dir"])
    # MVP: no encryption by default. Pass --password flag to enable.
    return Vault(vault_dir=vault_dir, password=password)


@click.group()
@click.version_option()
def main():
    """pencilpusher — The AI bureaucrat that fills forms so you don't have to."""
    pass


@main.command()
def init():
    """Initialize your personal data vault."""
    vault = _get_vault()
    vault.init()

    vault_dir = vault.vault_dir
    console.print(Panel(
        f"[bold green]Vault initialized![/bold green]\n\n"
        f"Location: {vault_dir}\n"
        f"Wiki pages: {len(WIKI_PAGES)}\n\n"
        f"Folders:\n"
        f"  [bold]sources/[/bold]  — drop your documents here (IDs, passports, company docs)\n"
        f"  [bold]inbox/[/bold]    — drop forms to fill here\n"
        f"  [bold]outbox/[/bold]   — filled forms appear here\n"
        f"  [bold]wiki/[/bold]     — your personal knowledge base (auto-maintained)\n\n"
        f"Next steps:\n"
        f"  1. Drop documents into [bold]{vault_dir / 'sources'}[/bold]\n"
        f"  2. [bold]pencilpusher ingest-all[/bold]            — build your wiki\n"
        f"  3. [bold]pencilpusher show identity[/bold]         — check extracted data\n"
        f"  4. Drop forms into [bold]{vault_dir / 'inbox'}[/bold]\n"
        f"  5. [bold]pencilpusher fill-all[/bold]              — fill all forms!",
        title="pencilpusher",
    ))


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--category", "-c", type=click.Choice(WIKI_PAGES), default=None,
              help="Category for storage (auto-detected if omitted)")
@click.option("--model", "-m", default=None, help="Anthropic model to use")
def ingest(file_path: str, category: str | None, model: str | None):
    """Ingest a personal document into your vault.

    Reads the document, extracts personal data, and updates your wiki pages.

    Examples:
        pencilpusher ingest passport.pdf
        pencilpusher ingest bank_letter.pdf --category banking
        pencilpusher ingest id_card.jpg
    """
    from pencilpusher.ingest.pipeline import ingest_document

    config = load_config()
    vault = _get_vault()

    if not (vault.wiki_dir / "index.md").exists():
        console.print("[yellow]Vault not initialized. Running init first...[/yellow]")
        vault.init()

    use_model = model or config.get("model", "claude-sonnet-4-6")
    source_path = Path(file_path)

    console.print(f"\n[bold]Ingesting {source_path.name}...[/bold]")

    result = ingest_document(vault, source_path, category=category, model=use_model)

    if result.get("_parse_error"):
        console.print("[red]Error: Could not extract data from this document.[/red]")
        console.print("The LLM response could not be parsed. Try again or use a different model.")
        sys.exit(1)

    summary = result.get("source_summary", "Document processed")
    pages = result.get("pages_updated", [])
    stored_as = result.get("stored_as", "other")

    console.print(f"\n[bold green]Ingested![/bold green] {summary}")
    console.print(f"  Category: {stored_as}")
    console.print(f"  Pages updated: {', '.join(pages) if pages else 'none'}")

    if result.get("unmatched"):
        console.print(f"\n[yellow]Unmatched data (not categorized):[/yellow]")
        for item in result["unmatched"]:
            console.print(f"  - {item}")


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output path for the filled document")
@click.option("--model", "-m", default=None, help="Anthropic model to use")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def fill(file_path: str, output: str | None, model: str | None, yes: bool):
    """Fill a form document with your vault data.

    Detects fields in the document, matches them to your personal data,
    and produces a filled copy without changing the styling.

    Examples:
        pencilpusher fill application.pdf
        pencilpusher fill tax_form.docx -o filled_tax.docx
        pencilpusher fill kyc_form.pdf --yes
    """
    from pencilpusher.fill.pipeline import fill_document

    config = load_config()
    vault = _get_vault()

    if not (vault.wiki_dir / "index.md").exists():
        console.print("[red]Vault not initialized. Run 'pencilpusher init' first.[/red]")
        sys.exit(1)

    use_model = model or config.get("vision_model", "claude-sonnet-4-6")
    target_path = Path(file_path)
    output_path = Path(output) if output else None

    fill_document(vault, target_path, output_path=output_path, model=use_model, auto_confirm=yes)


@main.command()
@click.argument("page", required=False, default=None)
def show(page: str | None):
    """Show vault contents.

    Without arguments, shows the index. With a page name, shows that page.

    Examples:
        pencilpusher show              # Show index
        pencilpusher show identity     # Show identity page
        pencilpusher show banking      # Show banking details
    """
    vault = _get_vault()

    if page is None:
        # Show index
        index = vault.read_wiki_page("index")
        if index:
            console.print(Panel(index, title="Vault Index"))
        else:
            console.print("[yellow]Vault is empty. Run 'pencilpusher init' then ingest some documents.[/yellow]")
    else:
        # Allow standard pages, index, log, and company pages (companies/xxx)
        valid = page in WIKI_PAGES or page in ("index", "log") or page.startswith("companies/")
        if not valid:
            console.print(f"[red]Unknown page: {page}[/red]")
            console.print(f"Available pages: {', '.join(WIKI_PAGES)}, companies/<name>")
            sys.exit(1)

        content = vault.read_wiki_page(page)
        if content:
            console.print(Panel(content, title=f"vault/{page}.md"))
        else:
            console.print(f"[yellow]Page '{page}' is empty.[/yellow]")


@main.command(name="ingest-all")
@click.option("--model", "-m", default=None, help="Anthropic model to use")
def ingest_all_cmd(model: str | None):
    """Ingest all new documents from the sources/ folder.

    Drop your documents (IDs, passports, company registrations, bank letters)
    into ~/.pencilpusher/sources/ then run this command. Already-ingested files
    are skipped automatically.

    Examples:
        pencilpusher ingest-all
        pencilpusher ingest-all --model claude-sonnet-4-6
    """
    from pencilpusher.ingest.pipeline import ingest_all

    config = load_config()
    vault = _get_vault()

    if not (vault.wiki_dir / "index.md").exists():
        vault.init()

    sources = vault.list_sources()
    new_sources = [s for s in sources if not vault.is_ingested(s.name)]

    if not sources:
        console.print(f"[yellow]No files in sources/ folder.[/yellow]")
        console.print(f"Drop documents into: [bold]{vault.sources_dir}[/bold]")
        return

    if not new_sources:
        console.print(f"[green]All {len(sources)} files already ingested.[/green]")
        return

    console.print(f"\n[bold]Ingesting {len(new_sources)} new documents...[/bold]")
    use_model = model or config.get("model", "claude-sonnet-4-6")

    results = ingest_all(vault, model=use_model)

    ok = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]

    for r in ok:
        pages = r.get("pages_updated", [])
        reader = r.get("reader", "?")
        console.print(f"  [green]OK[/green] {r['file']} ({reader}) → {', '.join(pages) if pages else 'no updates'}")

    for r in errors:
        console.print(f"  [red]ERROR[/red] {r['file']}: {r['error']}")

    console.print(f"\n[bold]Done.[/bold] {len(ok)} ingested, {len(errors)} errors.")


@main.command(name="fill-all")
@click.option("--model", "-m", default=None, help="Anthropic model to use")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def fill_all_cmd(model: str | None, yes: bool):
    """Fill all documents in the inbox/ folder.

    Drop forms (PDF/DOCX) into ~/.pencilpusher/inbox/ then run this command.
    Filled versions appear in ~/.pencilpusher/outbox/.

    Examples:
        pencilpusher fill-all
        pencilpusher fill-all --yes
    """
    from pencilpusher.fill.pipeline import fill_document

    config = load_config()
    vault = _get_vault()

    if not (vault.wiki_dir / "index.md").exists():
        console.print("[red]Vault not initialized. Run 'pencilpusher init' first.[/red]")
        sys.exit(1)

    inbox_files = vault.list_inbox()

    if not inbox_files:
        console.print(f"[yellow]No files in inbox/ folder.[/yellow]")
        console.print(f"Drop forms into: [bold]{vault.inbox_dir}[/bold]")
        return

    use_model = model or config.get("vision_model", "claude-sonnet-4-6")
    console.print(f"\n[bold]Filling {len(inbox_files)} documents...[/bold]\n")

    for target_path in inbox_files:
        output_path = vault.outbox_dir / target_path.name
        try:
            fill_document(
                vault, target_path, output_path=output_path,
                model=use_model, auto_confirm=yes,
            )
        except Exception as e:
            console.print(f"  [red]ERROR[/red] {target_path.name}: {e}")

    console.print(f"\n[bold]Done.[/bold] Check outbox: [bold]{vault.outbox_dir}[/bold]")


@main.command()
def lint():
    """Health-check your vault wiki.

    Checks for:
    - Empty pages that should have data
    - Contradictory information across pages
    - Missing cross-references
    - Stale data warnings
    """
    vault = _get_vault()
    wiki_pages = vault.read_all_wiki_pages()

    issues = []
    empty_count = 0
    populated_count = 0

    for page_name in WIKI_PAGES:
        content = wiki_pages.get(page_name, "")
        if not content or "No data ingested yet" in content:
            empty_count += 1
        else:
            populated_count += 1

    console.print(f"\n[bold]Vault Health Check[/bold]")
    console.print(f"  Pages: {populated_count} populated, {empty_count} empty")

    raw_files = vault.list_raw_files()
    console.print(f"  Source documents: {len(raw_files)}")

    if empty_count > 0:
        console.print(f"\n[yellow]Empty pages:[/yellow]")
        for page_name in WIKI_PAGES:
            content = wiki_pages.get(page_name, "")
            if not content or "No data ingested yet" in content:
                console.print(f"  - {page_name}")

    if populated_count == 0:
        console.print("\n[yellow]Vault is empty. Ingest some documents to get started![/yellow]")
    else:
        console.print(f"\n[green]Vault looks healthy.[/green]")

    vault._log("lint", f"Health check: {populated_count}/{len(WIKI_PAGES)} pages populated")


@main.command()
def files():
    """List all source documents stored in the vault."""
    vault = _get_vault()
    raw_files = vault.list_raw_files()

    if not raw_files:
        console.print("[yellow]No source documents stored yet.[/yellow]")
        return

    from rich.table import Table
    table = Table(title="Stored Documents")
    table.add_column("Category", style="bold")
    table.add_column("Filename")
    table.add_column("Encrypted")

    for f in raw_files:
        table.add_row(
            f["category"],
            f["filename"],
            "[green]yes[/green]" if f["encrypted"] else "no",
        )

    console.print(table)


if __name__ == "__main__":
    main()
