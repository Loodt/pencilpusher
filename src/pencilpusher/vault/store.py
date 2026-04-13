"""Vault store — manages the wiki directory, raw sources, and operations log.

Follows Karpathy's LLM-wiki pattern:
  - sources/ : DROP your documents here (IDs, passports, company docs)
  - wiki/    : LLM-maintained markdown knowledge base
  - inbox/   : DROP forms to fill here
  - outbox/  : Filled forms appear here
  - raw/     : archived copies of ingested sources
"""

import datetime
import json
import shutil
from pathlib import Path

from pencilpusher.config import WIKI_PAGES, get_vault_dir


class Vault:
    """Personal data vault with wiki-style knowledge pages.

    Folder-based workflow (Karpathy LLM-wiki pattern):
      1. Drop source docs into sources/
      2. `pencilpusher ingest-all` builds the wiki
      3. Drop forms into inbox/
      4. `pencilpusher fill-all` produces filled forms in outbox/
    """

    def __init__(self, vault_dir: Path | None = None, password: str | None = None):
        self.vault_dir = vault_dir or get_vault_dir()
        self.raw_dir = self.vault_dir / "raw"
        self.wiki_dir = self.vault_dir / "wiki"
        self.output_dir = self.vault_dir / "output"
        self.sources_dir = self.vault_dir / "sources"
        self.inbox_dir = self.vault_dir / "inbox"
        self.outbox_dir = self.vault_dir / "outbox"
        self.manifest_path = self.vault_dir / ".manifest.json"
        self.fernet = None

        if password:
            try:
                from pencilpusher.vault.crypto import init_vault_encryption
                self.fernet = init_vault_encryption(self.vault_dir, password)
            except ImportError:
                raise ImportError(
                    "Encryption requires the 'cryptography' package. "
                    "Install with: pip install cryptography"
                )

    def init(self) -> None:
        """Initialize vault directory structure and seed wiki pages."""
        for d in [
            self.raw_dir, self.wiki_dir, self.output_dir,
            self.sources_dir, self.inbox_dir, self.outbox_dir,
            self.wiki_dir / "companies",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Seed wiki pages if they don't exist
        for page_name in WIKI_PAGES:
            page_path = self.wiki_dir / f"{page_name}.md"
            if not page_path.exists():
                content = f"# {page_name.replace('_', ' ').title()}\n\nNo data ingested yet.\n"
                self._write_wiki_page(page_name, content)

        # Seed index.md
        index_path = self.wiki_dir / "index.md"
        if not index_path.exists():
            lines = ["# Vault Index\n", "Personal data knowledge base.\n"]
            lines.append("| Page | Description | Last Updated |")
            lines.append("|------|-------------|--------------|")
            for page_name in WIKI_PAGES:
                desc = _page_descriptions().get(page_name, "")
                lines.append(f"| [{page_name}]({page_name}.md) | {desc} | — |")
            lines.append("")
            self._write_wiki_page("index", "\n".join(lines))

        # Seed log.md
        log_path = self.wiki_dir / "log.md"
        if not log_path.exists():
            self._write_wiki_page("log", "# Operation Log\n\nChronological record of vault operations.\n")

        # Seed manifest
        if not self.manifest_path.exists():
            self._save_manifest({})

        self._log("init", "Vault initialized")

    def store_raw(self, source_path: Path, category: str) -> Path:
        """Store a raw source document in the vault."""
        dest_dir = self.raw_dir / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source_path.name

        if self.fernet:
            from pencilpusher.vault.crypto import encrypt_file
            dest = dest_dir / (source_path.name + ".enc")
            encrypt_file(self.fernet, source_path, dest)
        else:
            shutil.copy2(source_path, dest)

        self._log("store", f"Stored {source_path.name} → raw/{category}/")
        return dest

    def read_raw(self, raw_path: Path) -> bytes:
        """Read a raw source document."""
        if self.fernet and raw_path.suffix == ".enc":
            from pencilpusher.vault.crypto import decrypt_file
            return decrypt_file(self.fernet, raw_path)
        return raw_path.read_bytes()

    def read_wiki_page(self, page_name: str) -> str:
        """Read a wiki page. Returns content as string. Supports nested paths like 'companies/showplus'."""
        page_path = self.wiki_dir / f"{page_name}.md"
        if not page_path.exists():
            return ""
        return page_path.read_text(encoding="utf-8")

    def write_wiki_page(self, page_name: str, content: str) -> None:
        """Write/update a wiki page and log the operation."""
        self._write_wiki_page(page_name, content)
        self._log("update", f"Updated wiki/{page_name}.md")

    def _write_wiki_page(self, page_name: str, content: str) -> None:
        """Write a wiki page as plaintext markdown."""
        page_path = self.wiki_dir / f"{page_name}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(content, encoding="utf-8")

    def read_all_wiki_pages(self) -> dict[str, str]:
        """Read all wiki pages into a dict, including company pages."""
        pages = {}
        for page_name in WIKI_PAGES:
            content = self.read_wiki_page(page_name)
            if content:
                pages[page_name] = content

        # Also read company pages
        companies_dir = self.wiki_dir / "companies"
        if companies_dir.exists():
            for f in sorted(companies_dir.glob("*.md")):
                key = f"companies/{f.stem}"
                content = f.read_text(encoding="utf-8")
                if content and "No data ingested yet" not in content:
                    pages[key] = content

        return pages

    def list_raw_files(self) -> list[dict]:
        """List all raw source files in the vault."""
        files = []
        if not self.raw_dir.exists():
            return files
        for category_dir in sorted(self.raw_dir.iterdir()):
            if category_dir.is_dir():
                for f in sorted(category_dir.iterdir()):
                    files.append({
                        "category": category_dir.name,
                        "filename": f.name.removesuffix(".enc"),
                        "path": f,
                        "encrypted": f.suffix == ".enc",
                    })
        return files

    # --- Manifest for tracking ingested sources ---

    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )

    def mark_ingested(self, filename: str) -> None:
        """Mark a source file as ingested in the manifest."""
        manifest = self._load_manifest()
        manifest[filename] = {
            "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._save_manifest(manifest)

    def is_ingested(self, filename: str) -> bool:
        """Check if a source file has already been ingested."""
        manifest = self._load_manifest()
        return filename in manifest

    def list_sources(self) -> list[Path]:
        """List all files in sources/ directory."""
        if not self.sources_dir.exists():
            return []
        return sorted(
            f for f in self.sources_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        )

    def list_inbox(self) -> list[Path]:
        """List all files in inbox/ directory."""
        if not self.inbox_dir.exists():
            return []
        return sorted(
            f for f in self.inbox_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        )

    def _log(self, operation: str, message: str) -> None:
        """Append to the operation log."""
        log_path = self.wiki_dir / "log.md"
        if not log_path.exists():
            return
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{timestamp}] {operation} | {message}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)


def _page_descriptions() -> dict[str, str]:
    return {
        "identity": "Name, ID number, passport, date of birth, nationality",
        "banking": "Bank accounts, branch codes, SWIFT/BIC codes",
        "company": "Company registration, VAT, directors, B-BBEE",
        "addresses": "Physical, postal, and registered addresses",
        "contacts": "Phone numbers, email, emergency contacts",
        "tax": "Tax numbers, tax practitioner, returns info",
        "vehicles": "Vehicle registration, license discs",
        "medical": "Medical aid, doctor, allergies, blood type",
        "education": "Qualifications, institutions, dates",
        "employment": "Current and past employment",
        "legal": "Powers of attorney, trusts, wills",
        "insurance": "Insurance policies, brokers, claim numbers",
    }
