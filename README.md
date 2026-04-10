# pencilpusher

**The AI bureaucrat that fills forms so you don't have to.**

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
pip install pencilpusher

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
| `pencilpusher ingest <file>` | Ingest a single document |
| `pencilpusher ingest-all` | Ingest all new files from sources/ |
| `pencilpusher fill <form>` | Fill a single form |
| `pencilpusher fill-all` | Fill all forms in inbox/ → outbox/ |
| `pencilpusher show [page]` | Display vault index or specific wiki page |
| `pencilpusher lint` | Health-check the wiki |
| `pencilpusher files` | List stored source documents |

## Requirements

- Python 3.10+
- Anthropic API key (`ANTHROPIC_API_KEY` environment variable)

## Development

```bash
git clone https://github.com/Loodt/pencilpusher.git
cd pencilpusher
pip install -e ".[dev]"
pytest
```

## License

MIT
