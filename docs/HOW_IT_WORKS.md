# pencilpusher — How It Works

**Version:** 0.1.0
**Date:** 2026-04-10
**Status:** Alpha — core form-filling proven, agent-driven mode shipped

---

## 1. What pencilpusher is

pencilpusher is an open-source AI form-filling tool. You drop personal and company documents into a folder, it builds a structured knowledge wiki, and when you drop a form into the inbox it fills it — PDFs, Word docs, government forms, company registrations.

It works in two modes:

1. **Standalone** — pencilpusher makes its own Claude API calls for data extraction and field matching
2. **Agent-driven** — an external LLM agent (Claude Code, OpenAI Codex, etc.) does the reasoning; pencilpusher only does deterministic document manipulation. Zero API calls.

Built on [Karpathy's LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) for the data vault and [Microsoft MarkItDown](https://github.com/microsoft/markitdown) (96K stars) for document-to-Markdown conversion.

---

## 2. Architecture

### 2.1 The three-layer vault (Karpathy pattern)

```
~/.pencilpusher/
├── sources/          Raw documents (IDs, passports, company certs)
├── wiki/             LLM-maintained knowledge base
│   ├── index.md
│   ├── identity.md
│   ├── banking.md
│   ├── contacts.md
│   ├── addresses.md
│   ├── tax.md
│   ├── companies/
│   │   ├── acme.md
│   │   └── mycorp.md
│   └── ... (12 categories)
├── inbox/            Drop forms here to fill
├── outbox/           Filled forms appear here
└── raw/              Stored copies of ingested documents (by category)
```

The vault persists at `~/.pencilpusher/` across sessions. Ingest a document once, fill forms forever.

### 2.2 Source code structure

```
src/pencilpusher/
├── cli.py                  Click-based CLI (12 commands)
├── config.py               Wiki page categories, vault location, config loading
├── ingest/
│   ├── reader.py           MarkItDown conversion (no API)
│   ├── extractor.py        Claude API data extraction
│   └── pipeline.py         Ingest orchestration
├── fill/
│   ├── detector.py         Field detection (AcroForm, DOCX SDTs, visual)
│   ├── matcher.py          Claude API field-to-vault matching
│   ├── pdf_filler.py       PyMuPDF filling (widgets + flat text)
│   ├── docx_filler.py      zipfile+lxml SDT + python-docx table/placeholder
│   └── pipeline.py         Fill orchestration + agent-driven fill_document_with_map
├── vault/
│   ├── store.py            Vault operations (init, read, write, manifest)
│   └── crypto.py           Optional Fernet encryption (PBKDF2, 600K iterations)
└── wiki/
    ├── pages.py            Wiki page merging (Claude API)
    └── lint.py             Vault health check (Claude API)
```

### 2.3 What uses the API vs what is deterministic

| Module | API calls | What it does |
|--------|-----------|-------------|
| `reader.py` | 0 | MarkItDown document → Markdown |
| `extractor.py` | 1-2 per doc | Claude extracts structured data from text/images |
| `pages.py` | 0-1 per page | Claude merges new data into existing wiki pages |
| `detector.py` | 0 (AcroForm/DOCX), 1/page (flat PDF) | Field detection — programmatic for structured forms, vision for flat PDFs |
| `matcher.py` | 1 per form | Claude matches detected fields to vault data |
| `pdf_filler.py` | 0 | PyMuPDF writes values into PDF widgets/text |
| `docx_filler.py` | 0 | zipfile+lxml writes values into DOCX XML |
| `store.py` | 0 | All vault operations (filesystem) |
| `lint.py` | 1 | Claude checks for contradictions and gaps |

**Key design decision:** LLM decides WHAT to fill, deterministic code does the XML/PDF manipulation. This is the Harvey AI pattern — proven in production legal tech.

---

## 3. How filling works (the technical details)

### 3.1 DOCX filling — three passes

pencilpusher fills Word documents in three passes, each targeting a different field type:

**Pass 1: SDT content controls (zipfile + lxml)**

This is the most reliable approach. Opens the DOCX as a ZIP, parses `word/document.xml` as XML, finds `<w:sdt>` elements by their `<w:tag>` or `<w:alias>`, and replaces the text in `<w:sdtContent>` while preserving all `<w:rPr>` formatting.

Why zipfile+lxml instead of python-docx? Because python-docx can read SDTs via XPath but **cannot persist SDT edits on save** (issue #965, confirmed by hands-on testing). The zipfile approach modifies the raw XML and repackages the ZIP.

Tested: 6/6 SDT fields filled successfully, output verified non-corrupt.

**Pass 2: Table cells (python-docx)**

Government forms (like Zambian PACRA forms) use complex merged-cell tables with no SDTs, no content controls, no placeholders. Just empty cells next to label cells.

python-docx table cell access works for these — iterate rows, find label cells, write into adjacent empty cells. This is fragile (depends on table structure) but handles the real-world forms we tested.

Tested: Successfully filled Form 10 (83 rows x 9 columns, extensive cell merging), Form 24, and Form 4.

**Pass 3: Placeholder replacement (python-docx runs)**

For documents with `[___]`, `{name}`, `<<name>>`, or `________` patterns. Regex detects placeholders, python-docx replaces the text runs while preserving formatting.

### 3.2 PDF filling — two approaches

**AcroForm PDFs (structured forms with form fields)**

Uses PyMuPDF's widget API: iterate `page.widgets()`, match by field name, set `widget.field_value`, call `widget.update()`. About 8 lines of code. Works on any PDF with AcroForm fields.

Tested: 3/3 fields filled on test AcroForm PDF.

**Flat PDFs (no form fields — just text and lines)**

Uses PyMuPDF `page.insert_text()` at positions detected by label analysis. The text position detection pipeline:

1. `page.get_text('dict')` extracts all text with bounding boxes
2. Field labels are identified (text near blank areas)
3. Text is inserted at `bbox[1] + fontsize` y-position (placing it on the same line as the label)
4. Font size and colour matched to surrounding text

For field detection on flat PDFs, Claude vision identifies where fields should be (renders page as PNG, asks Claude to locate fillable areas). This is the one place where agent-driven mode falls short — flat PDF detection still needs an API call.

Tested: 9 fields on a real PACRA form, user confirmed "looks perfect".

### 3.3 Field matching

The matcher takes detected fields + all wiki pages and asks Claude to semantically match form fields to vault data. For example:

- Form says "Applicant Full Name" → matches to `identity.md` → "Lodewyk Bronn"
- Form says "Registration Number" → matches to `companies/acme.md` → "120240067890"
- Form says "NRC" → matches to `identity.md` → "445566/77/1"

Returns JSON with matches, confidence scores, source pages, and unmatchable fields.

In agent-driven mode, this step is replaced by `--field-map` — the calling agent does the matching and passes an explicit JSON mapping.

---

## 4. How ingestion works

### 4.1 Document reading

Primary reader is Microsoft MarkItDown — converts PDF, DOCX, images, PPTX, XLSX, and more to structured Markdown. This is cheaper and faster than vision API because it produces text that goes through the text API.

Fallback: PyMuPDF renders PDF pages as PNG images for Claude vision (used when MarkItDown produces insufficient text — scanned documents, image-heavy PDFs).

### 4.2 Data extraction

Claude reads the Markdown (or images) and extracts structured data into categories:

- Source summary and type classification
- Field-value pairs mapped to wiki pages (identity, banking, contacts, etc.)
- Company data auto-creates per-company wiki pages (`companies/{slug}.md`)

### 4.3 Wiki merging

Extracted data is merged into existing wiki pages. If a page is empty, a simple merge writes the content directly. If a page has existing data, Claude merges intelligently — avoiding duplicates, noting "updated from source", preserving formatting.

In agent-driven mode, the agent reads the document with `pencilpusher read`, reasons about the data, and writes directly with `pencilpusher write-wiki`.

---

## 5. Agent-driven mode

Added in v0.1.0 (2026-04-10). Four commands that make zero API calls:

| Command | What it does | Equivalent standalone command |
|---------|-------------|------------------------------|
| `read <file>` | MarkItDown → Markdown on stdout | Part of `ingest` |
| `detect <form>` | Field list as JSON on stdout | Part of `fill` |
| `write-wiki <page> <content>` | Write directly to vault wiki | Part of `ingest` |
| `fill <form> --field-map '{...}'` | Fill with explicit mapping | `fill` (without API matching) |
| `fill <form> --field-map --fields-json` | Fill flat PDF with agent-provided positions | `fill` (without API detection or matching) |

### 5.1 Agent workflow

```
Agent                                          pencilpusher
  │                                                │
  ├── "read passport.pdf" ──────────────────────► │ MarkItDown → Markdown
  │◄──────────── Markdown text ──────────────────┤
  │                                                │
  │  [Agent reasons: "This is a passport.          │
  │   Name: Jane Moyo, DOB: 1990-03-15,           │
  │   Passport: M12345678"]                        │
  │                                                │
  ├── "write-wiki identity '# Identity\n...'" ──► │ Write to vault
  │                                                │
  ├── "detect application.pdf" ──────────────────► │ AcroForm field extraction
  │◄──────────── JSON field list ────────────────┤
  │                                                │
  ├── "show identity" ───────────────────────────► │ Read vault page
  │◄──────────── Wiki page content ──────────────┤
  │                                                │
  │  [Agent reasons: "Full Name" → "Jane Moyo",   │
  │   "Date of Birth" → "15 March 1990"]           │
  │                                                │
  ├── "fill app.pdf --field-map '{...}'" ────────► │ PyMuPDF fills PDF
  │◄──────────── Filled document path ───────────┤
  │                                                │
  │  [For flat PDFs, agent also provides positions]│
  │                                                │
  ├── "fill flat.pdf --field-map '{...}'           │
  │    --fields-json '[{name,bbox,page}]'" ──────► │ Creates widgets at positions
  │◄──────────── Filled document path ───────────┤
```

### 5.2 Why this matters

- **No API cost** — the LLM reasoning happens in the agent's existing context
- **Works with any LLM** — Claude Code, OpenAI Codex, Gemini, local models
- **No API key needed** — `ANTHROPIC_API_KEY` only required for standalone mode
- **Better control** — the agent can inspect, modify, and verify at each step

### 5.3 Flat PDF handling

Flat PDFs (no AcroForm fields) need field positions to know WHERE to place text. In agent-driven mode:

1. `detect` returns an empty list with a warning for flat PDFs
2. The agent uses its own vision to identify field positions (name, bbox as percentages, page number)
3. The agent passes both `--field-map` (values) and `--fields-json` (positions) to `fill`

```bash
pencilpusher fill flat.pdf \
  --field-map '{"Full Name": "Jane Moyo"}' \
  --fields-json '[{"name": "Full Name", "bbox": [15, 20, 50, 3], "page": 0}]'
```

The `--fields-json` array accepts objects with: `name` (string), `bbox` ([x, y, width, height] as page percentages 0-100), `page` (0-indexed), and optional `field_type`, `field_key`, `context`, `required`.

### 5.4 Limitations

- **Wiki page merging** in standalone mode is smarter (Claude handles deduplication). Agent-driven `write-wiki` does a full overwrite — the agent is responsible for merging.

---

## 6. What we tested (real-world)

### 6.1 Case study: Zambian PACRA company forms

**The task:** A South African investor needed to make corporate changes to two Zambian companies — remove a director, appoint a new one, update beneficial ownership. A colleague sent 3 government forms via WhatsApp.

**What pencilpusher produced:** A 10-document compliance package:

| Document | Type | How produced |
|----------|------|-------------|
| Form 10 (Showplus) | PACRA DOCX — 83-row table | Table cell filling (python-docx) |
| Form 10 (Ulapa) | PACRA DOCX — 83-row table | Table cell filling (python-docx) |
| Form 24 | PACRA DOCX — notice of removal | Table cell filling (python-docx) |
| Form 20 | PACRA PDF — beneficial ownership | PDF filling (PyMuPDF) |
| Board resolution | Generated DOCX | Drafted from template + vault data |
| Shareholder resolution | Generated DOCX | Drafted from template + vault data |
| Notice to director | Generated DOCX | Drafted from vault data |
| Consent to act | Generated DOCX | Drafted from vault data |
| Meeting minutes | Generated DOCX | Drafted from vault data |
| Cover letter to PACRA | Generated DOCX | Drafted from vault data |

**Data sources ingested:** ID card (PDF scan), passport (PDF scan), PACRA company printouts (PDF), chat history (Afrikaans text), project files.

**User verdict:** "No issues."

### 6.2 Technical tests performed

All hands-on, verified with real documents:

| Test | Input | Result |
|------|-------|--------|
| DOCX SDT filling | 6 content controls | 6/6 filled, output non-corrupt |
| DOCX table filling | PACRA Form 10 (83 rows, merged cells) | Successful, user confirmed |
| PDF AcroForm filling | Test form with 3 fields | 3/3 filled via widget API |
| PDF flat filling | PACRA Form 20 (9 fields, no AcroForm) | 9/9 placed correctly, "looks perfect" |
| MarkItDown reading | PACRA PDF printout | 2,698 chars extracted |
| Vision reading | SA ID card, passport | Successfully extracted personal data |
| Chat ingestion | Afrikaans WhatsApp export | Correctly parsed multi-language context |
| Agent-driven fill | AcroForm PDF + --field-map | Filled without API call |
| Agent-driven detect | AcroForm PDF, DOCX, flat PDF | Correct JSON output, flat PDF warned |
| Agent-driven write-wiki | Identity page write | Content verified in vault |
| Agent-driven read | DOCX document | Markdown on stdout |

### 6.3 Automated test suite

25 tests, all passing:

**Agent mode tests (15):**
- `test_read_docx` — MarkItDown converts DOCX to Markdown
- `test_read_nonexistent_file` — fails gracefully
- `test_detect_acroform_pdf` — extracts AcroForm fields as JSON
- `test_detect_flat_pdf_warns` — returns warning for flat PDFs
- `test_detect_docx_placeholders` — detects `[___]` patterns
- `test_write_wiki_page` — writes and verifies content
- `test_write_wiki_stdin` — reads content from stdin
- `test_write_wiki_company_page` — creates company sub-pages
- `test_write_wiki_invalid_page` — rejects unknown pages
- `test_write_wiki_no_content` — fails without content
- `test_fill_acroform_with_field_map` — fills PDF with explicit mapping
- `test_fill_docx_with_field_map` — fills DOCX with explicit mapping
- `test_fill_flat_pdf_with_fields_json` — fills flat PDF with agent-provided positions
- `test_fill_invalid_json` — rejects bad JSON in --field-map
- `test_fill_invalid_fields_json` — rejects bad JSON in --fields-json

**Vault and detector tests (10):**
- `test_encrypt_decrypt_roundtrip` — Fernet encryption works
- `test_wrong_password_raises` — wrong password rejected
- `test_salt_persists` — re-opening with same password works
- `test_init_creates_structure` — vault init creates all directories
- `test_wiki_page_roundtrip` — write then read wiki page
- `test_read_all_wiki_pages` — reads all category pages
- `test_store_raw_file` — stores and lists raw files
- `test_vault_with_password` — encrypted vault works
- `test_detect_docx_placeholder_brackets` — detects `[___]` placeholders
- `test_detect_docx_placeholder_underlines` — detects `_____` placeholders

---

## 7. Technical decisions and why

| Decision | Choice | Why | Alternatives considered |
|----------|--------|-----|------------------------|
| DOCX SDT filling | zipfile + lxml | python-docx can't persist SDT edits (issue #965). Direct XML manipulation is reliable. | python-docx (broken), docx-form (untested), Aspose (commercial) |
| DOCX table filling | python-docx | Table cell access works. Government forms use tables, not SDTs. | zipfile+lxml (overkill for tables) |
| PDF AcroForm | PyMuPDF widget API | Direct field value setting, handles all field types. ~8 lines. | pypdf (no field creation), PyPDFForm (less tested) |
| PDF flat filling | PyMuPDF insert_text | Clean text placement at detected positions. No blue widget highlights. | PyMuPDF add_widget (shows blue highlights), CommonForms (ML detection, untested) |
| Document reading | MarkItDown | 96K stars, structured Markdown from any format. Text API is cheaper than vision. | PyMuPDF text extraction (less structured), vision API (expensive) |
| Data extraction | Claude API (text) | Semantic understanding of unstructured documents. | Regex (too brittle), local models (slower) |
| Field matching | Claude API (text) | Semantic matching ("Applicant Full Name" → identity.md:name). | Fuzzy string matching (too rigid), embeddings (overkill) |
| CLI framework | Click + Rich | Click for commands, Rich for pretty output. Standard Python CLI stack. | argparse (verbose), Typer (extra dependency) |
| Vault pattern | Karpathy LLM-wiki | Three-layer (sources/wiki/outbox) is proven. 15+ implementations in first week of the gist. | Database (overhead), flat files (no structure) |
| Encryption | Optional Fernet (PBKDF2) | Local-first vault doesn't need encryption by default. Available for sensitive deployments. | Always-on encryption (friction), no encryption (less secure) |
| Agent-driven mode | Separate deterministic commands | Let the calling agent's LLM do the reasoning. Zero extra API cost. | MCP server (more complex), function calling (ties to one provider) |
| Flat PDF agent fill | `--fields-json` with bbox positions | Agent provides field positions from its own vision. Closes the last API gap. | Require standalone mode for flat PDFs (forces API key) |

---

## 8. Competitive landscape

Based on deep research (DR-I002, 2026-04-10):

**Nobody is building an open-source AI company secretary.** The market is fragmented:

| Layer | Who does it | Open source? | Covers Africa? |
|-------|-------------|-------------|----------------|
| Understand regulations | Norm AI ($87M raised) | No | No |
| Entity management + deadlines | Diligent ($20-75K/yr), Athennian ($25K/yr) | No | No |
| Document drafting | Harvey AI, Clio Draft | No | No |
| Form filling | **pencilpusher** | Yes (MIT) | Yes |
| Government e-filing | Companies House API (UK only) | UK gov | UK only |
| SA company filing | InfoDocs, Konsise, ClearComply | No | SA only |
| Zambian company filing | **Nothing** | Nothing | Nothing |

The closest open-source platform is **Docassemble** (guided interviews → PDF/DOCX) — but no corporate governance packages exist for it. pencilpusher is the only tool that bridges a personal data vault to form filling.

---

## 9. Known pain points (from real-world testing)

10 pain points documented during the Zambian PACRA case study:

| # | Pain point | Status in v0.1.0 |
|---|-----------|-----------------|
| 1 | Nobody tells you what you actually need | Not solved — pencilpusher fills blanks, doesn't know the procedure |
| 2 | Forms are the tip of the iceberg (resolutions, notices, minutes needed) | Partially solved — produced supporting documents manually |
| 3 | Data scattered across 5+ sources | Solved — vault consolidates personal + company data |
| 4 | Government forms use hostile table structures | Solved — python-docx table cell filling handles merged cells |
| 5 | Don't know which form goes with which action | Not solved — user must provide forms |
| 6 | Legal context determines everything | Not solved — no jurisdiction-specific knowledge |
| 7 | Deadlines create anxiety | Not solved — no deadline tracking |
| 8 | Multiple languages and jurisdictions | Partially solved — handled Afrikaans chat + English forms |
| 9 | Nobody drafts supporting documents | Partially solved — drafted in case study, not automated |
| 10 | Don't know when you're done | Not solved — no completion tracking |

---

## 10. What's next (product direction)

pencilpusher started as a form filler. Real-world testing showed it should become an **open-source AI company secretary**:

1. **Form filling** (v0.1 — built, tested, working)
2. **Agent-driven mode** (v0.1 — built, tested, working)
3. **Compliance package generation** (proven manually in case study — needs automation)
4. **Legal procedure knowledge** (per jurisdiction — researched, not built)
5. **Deadline tracking** (identified as pain point — not built)
6. **Government portal filing** (Skyvern for browser automation — identified, not integrated)

The full vision is a 6-layer stack from data vault → procedure knowledge → document drafting → form filling → deadline tracking → government filing. v0.1 covers layer 1 (data vault) and layer 4 (form filling). Everything else is designed but not yet built.

---

## 11. Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| anthropic | >=0.40.0 | Claude API client (standalone mode only) | MIT |
| pypdf | >=4.0 | PDF AcroForm field reading | BSD-3 |
| python-docx | >=1.0 | DOCX table/paragraph access | MIT |
| lxml | >=4.9 | XML parsing for DOCX SDT manipulation | BSD |
| PyMuPDF | >=1.24 | PDF filling (widgets + text insertion) | AGPL-3 |
| markitdown | >=0.1.0 | Document → Markdown conversion | MIT |
| PyYAML | >=6.0 | Configuration file parsing | MIT |
| rich | >=13.0 | Terminal formatting | MIT |
| click | >=8.0 | CLI framework | BSD-3 |

Optional: `cryptography` (for vault encryption), `pytesseract` + `Pillow` (for OCR).

---

## 12. Commit history

```
beed4c9 Add agent-driven mode — read, detect, write-wiki, fill --field-map
1d94479 Update expected test fixture for application form
ba0c2d8 Scrub personal info and fix links in README
6f1b94a Fix PDF text alignment — place on same line as labels
9c50776 Initial release: pencilpusher v0.1.0
```
