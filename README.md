# pencilpusher

[![CI](https://github.com/Loodt/pencilpusher/actions/workflows/ci.yml/badge.svg)](https://github.com/Loodt/pencilpusher/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/paperpusher.svg)](https://pypi.org/project/paperpusher/)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#limitations--known-issues)

**The AI bureaucrat that fills forms so you don't have to.**

> Install with `pip install paperpusher` — the `pencilpusher` name was taken on PyPI by an unrelated project, so the distribution ships as `paperpusher` while the CLI and import remain `pencilpusher`.

Drop your documents into a folder. pencilpusher reads them, builds a personal + company knowledge wiki, and when you drop a form into the inbox — it fills it. PDFs, Word docs, government forms, company registrations. No re-typing, no re-extracting.

Built on [Karpathy's LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) + [Microsoft MarkItDown](https://github.com/microsoft/markitdown) for document conversion.

## How it works

```
sources/                         wiki/                          inbox/ → outbox/
(drop your docs here)           (auto-built by LLM)            (drop forms → filled forms)

  passport.pdf     ──ingest──►  identity.md              ┐
  id_card.pdf      ──ingest──►  contacts.md              │
  pacra_printout   ──ingest──►  companies/acme.md        ├──►  Form10_filled.docx
  bank_letter.pdf  ──ingest──►  banking.md               │     KYC_filled.pdf
  company_reg.pdf  ──ingest──►  companies/mycorp.md      ┘
```

Three layers (Karpathy's architecture):
1. **sources/** — drop your documents here (IDs, passports, company docs, bank letters)
2. **wiki/** — LLM-maintained knowledge base (personal data + per-company pages)
3. **inbox/outbox/** — drop forms to fill, get filled forms back

## Quick start

```bash
pip install paperpusher    # PyPI distribution name (the `pencilpusher` name was taken)

# 1. Initialize your vault
pencilpusher init

# 2. Drop documents into ~/.pencilpusher/sources/
#    (IDs, passports, company registrations, bank letters, etc.)

# 3. Build your knowledge wiki
pencilpusher ingest-all

# 4. Check what it extracted
pencilpusher show identity
pencilpusher show companies/acme

# 5. Drop forms into ~/.pencilpusher/inbox/

# 6. Fill them all!
pencilpusher fill-all
```

Or fill individual files:

```bash
pencilpusher ingest passport.pdf
pencilpusher fill application.docx -o filled.docx
```

## Features

- **Folder-based workflow** — drop docs in, get filled forms out
- **PDF forms** — AcroForm fields (exact fill) and flat PDFs (text position detection)
- **Word docs** — SDT content controls (zipfile+lxml), table cells, placeholders
- **MarkItDown powered** — converts any document to Markdown (cheaper than vision API)
- **Company pages** — auto-creates per-company wiki pages from PACRA/CIPC printouts
- **Smart matching** — Claude matches "Applicant Full Name" → your name from the wiki
- **Style preservation** — fills values without touching fonts, sizes, colors, or layout
- **Manifest tracking** — skips already-ingested files automatically

## Real-world tested

Successfully produced a 10-document Zambian PACRA compliance package:
- 4 filled PACRA forms (Form 10, 20, 22, 24)
- 6 supporting documents (board resolution, notices, minutes, consent, cover letter)
- From scattered data: company printouts, ID card, passport, chat history

## Technical stack

| Component | Tool | Why |
|-----------|------|-----|
| Document → Markdown | MarkItDown (Microsoft, 96K stars) | Structured text from any format |
| DOCX SDT filling | zipfile + lxml (first principles) | Bypasses python-docx limitations |
| DOCX table filling | python-docx table cell access | Government form tables |
| PDF AcroForm filling | PyMuPDF widget API | Direct field value setting |
| PDF flat filling | PyMuPDF insert_text | Clean text at detected positions |
| Data extraction | Claude API (text) | Structured extraction from markdown |
| Field matching | Claude API (text) | Semantic matching to wiki data |
| CLI | Click + Rich | Clean command interface |

## Commands

| Command | Description |
|---------|-------------|
| `pencilpusher init` | Create vault with sources/inbox/outbox/wiki folders |
| `pencilpusher ingest <file>` | Ingest a single document (API) |
| `pencilpusher ingest-all` | Ingest all new files from sources/ (API) |
| `pencilpusher fill <form>` | Fill a single form (API) |
| `pencilpusher fill-all` | Fill all forms in inbox/ → outbox/ (API) |
| `pencilpusher show [page]` | Display vault index or specific wiki page |
| `pencilpusher lint` | Health-check the wiki |
| `pencilpusher files` | List stored source documents |
| `pencilpusher read <file>` | Convert any document to Markdown (no API) |
| `pencilpusher detect <form>` | Detect form fields as JSON (no API for AcroForm/DOCX) |
| `pencilpusher write-wiki <page> <content>` | Write directly to a vault wiki page (no API) |
| `pencilpusher fill <form> --field-map '{...}'` | Fill with explicit mapping (no API) |
| `pencilpusher fill <form> --field-map '{...}' --fields-json '[...]'` | Fill flat PDF with agent-provided field positions (no API) |

## Agent-driven mode (no API key needed)

pencilpusher can be used by AI coding agents (Claude Code, OpenAI Codex, etc.) without an Anthropic API key. The agent does the LLM reasoning; pencilpusher does the document manipulation.

```bash
# 1. Read a document — agent gets Markdown back
pencilpusher read passport.pdf

# 2. Agent reasons about the data, then writes to vault
pencilpusher write-wiki identity "# Identity\nName: Jane Moyo\nDOB: 1990-03-15"

# 3. Detect form fields — agent gets JSON back
pencilpusher detect application.pdf

# 4. Agent matches fields to vault data, then fills
pencilpusher fill application.pdf --field-map '{"Full Name": "Jane Moyo", "Date of Birth": "15 March 1990"}'

# For flat PDFs (no AcroForm), the agent also provides field positions:
pencilpusher fill flat.pdf \
  --field-map '{"Full Name": "Jane Moyo"}' \
  --fields-json '[{"name": "Full Name", "bbox": [15, 20, 50, 3], "page": 0}]'
```

The `read`, `detect`, `write-wiki`, and `fill --field-map` commands make zero API calls. For flat PDFs, pass `--fields-json` with field positions from the agent's own vision analysis. The existing `ingest` and `fill` commands still work standalone with an API key.

## Requirements

- Python 3.10+
- Anthropic API key (`ANTHROPIC_API_KEY`) — only needed for `ingest`, `fill` (without --field-map), and `lint`

## Limitations & known issues

pencilpusher is alpha (v0.1.0). It works well on the document classes it has been tested against; it will not handle every form in the wild yet.

**What works well today:**
- AcroForm PDFs with named fields
- Flat PDFs where field labels are present as selectable text
- DOCX with SDT content controls, table cells, or simple `{{placeholder}}` markers
- Latin-script (English) form labels and values

**What's flaky or unsupported:**
- **Scanned / image-only PDFs** — no OCR in the default install. The optional `[ocr]` extra installs `pytesseract` but the pipeline doesn't yet feed OCR output into field detection. Expect to do this manually for now.
- **Non-Latin scripts** in field labels — Claude can match them, but PyMuPDF text insertion uses the document's default font, which may not contain the needed glyphs. Workaround: AcroForm PDFs only.
- **Checkboxes and radio groups in flat PDFs** — only AcroForm checkboxes are reliably filled. Flat-PDF checkbox detection is not yet implemented.
- **Multi-page forms with repeating sections** (e.g. "list each director on a separate row") — the field matcher treats each row independently and may duplicate values.
- **Forms with overlapping or rotated text** — flat-PDF position detection assumes labels are upright and non-overlapping.
- **Encrypted / password-protected PDFs** — must be unlocked before passing to pencilpusher.
- **Excel (XLSX) and OpenDocument (ODT)** — not supported. PRs welcome.
- **Windows path edge cases** — generally works, but report anything you hit.

If you have a form that fails, please [open an issue](https://github.com/Loodt/pencilpusher/issues/new?template=bug_report.yml) with an anonymised sample. Real-world failures are the main thing driving v0.2.

## Development

```bash
git clone https://github.com/Loodt/pencilpusher.git
cd pencilpusher
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## License

MIT — see [LICENSE](LICENSE).
