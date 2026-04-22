---
name: pencilpusher
description: |
  Use this skill whenever the user wants to fill a form automatically — KYC
  documents, supplier registrations, compliance questionnaires, permit
  applications, bank onboarding, tax returns with fixed fields, insurance
  forms, medical-aid forms, or any `.pdf` / `.docx` where the data is
  repetitive (name, address, company details, bank details, directors). Also
  use for dense flat-PDF supplier questionnaires where cells are narrow and
  answers need wrapping. Triggers include "fill this form", "complete the
  KYC", "populate the questionnaire", "fill my details", mentions of
  AcroForm, SDT content controls, `{{placeholder}}` markers, or the words
  "form", "questionnaire", "enquiry", "registration", "application",
  "onboarding". The deliverable is a filled-in form ready for signature
  review. Do NOT use for creating new documents from scratch, reading form
  responses out of an inbox, scanned image-only PDFs with no text layer
  (OCR first), or `.xlsx` forms (not supported — use openpyxl directly).
version: 0.1.0
status: alpha
dependencies:
  - paperpusher
  - PyMuPDF
  - lxml
last_updated: 2026-04-22
---

# pencilpusher — SKILL guide

**Purpose.** Fill structured forms from a persistent knowledge vault — AcroForm PDFs, DOCX with SDT content controls, DOCX tables, `{{placeholder}}` markers, and (with `--textbox-mode`) dense flat-PDF supplier questionnaires. Agent-driven commands bypass the Anthropic API entirely: the calling agent does the LLM reasoning, pencilpusher does the deterministic document manipulation.

**Status: alpha.** The underlying package is `paperpusher 0.1.1` (alpha) — the CLI contract is proven on the document classes it has been tested against (AcroForm PDFs, DOCX SDT / table / placeholder, flat PDFs with selectable text) but will not handle every form in the wild. Real-world failures drive the roadmap; file an issue with an anonymised sample if something breaks.

**Naming note.** The PyPI distribution is `paperpusher` (`pip install paperpusher`) because the `pencilpusher` name was taken on PyPI by an unrelated 2021 project. The CLI command and the importable Python module remain `pencilpusher` — only the `pip install` line differs.

Install: `pip install paperpusher` · CLI: `pencilpusher` · Source: <https://github.com/Loodt/pencilpusher>

---

## When to use

- **AcroForm PDFs** with named fields (`ApplicantFullName`, `DateOfBirth`). Filled via PyMuPDF's widget API — clean and style-preserving.
- **DOCX with SDT content controls** — unpacks the docx, edits `word/document.xml` via lxml, preserves every `<w:rPr>` formatting run.
- **DOCX with `{{placeholder}}` markers** or government-form-style table cells.
- **Compliance / registration / KYC workflows** — `ingest` your source documents once, `fill-all` the same forms many times (the vault value proposition).
- **Agent-driven explicit fill** via `--field-map` when you (the calling agent) already know the mapping — zero Anthropic API calls.
- **Dense flat-PDF supplier questionnaires** — `pencilpusher probe` + `fill --textbox-mode` (recipe in [reference.md](reference.md)).

## When NOT to use

- **Scanned / image-only PDFs** → run an OCR pass first (e.g. Tesseract). The optional `[ocr]` extra installs `pytesseract`, but the pipeline doesn't yet feed OCR output into field detection.
- **Encrypted / password-protected PDFs** → unlock first.
- **`.xlsx` forms** → not supported. Use openpyxl directly for now. (PRs welcome.)
- **Creating new documents from a template** → this skill fills existing forms; generate new documents with a separate tool.
- **Circling Yes/No on a flat PDF, tick/X marks next to options, or placing remarks at a custom offset** → pencilpusher only fills text cells today. Combine with PyMuPDF directly (`page.draw_oval`, `page.insert_text`) for marks. See [reference.md](reference.md) → "Gaps pencilpusher doesn't own".
- **Non-Latin-script labels and values** → pencilpusher matches them, but the document's default font may lack the needed glyphs when written back.

---

## Quick start

```bash
# Agent-driven AcroForm fill (no API key needed — the calling agent does the matching)
pencilpusher fill application.pdf \
  --field-map '{"Full Name": "Jane Moyo", "Date of Birth": "15 March 1990"}' \
  -o application_filled.pdf --yes

# Standalone vault workflow (one-time setup + recurring fills, uses Anthropic API)
pencilpusher init
cp ~/docs/{passport,company_cert,bank_letter}.pdf ~/.pencilpusher/sources/
pencilpusher ingest-all
cp ~/forms/kyc.pdf ~/.pencilpusher/inbox/
pencilpusher fill-all

# Dense flat PDF (two-step: probe structure, then fill with textbox mode)
pencilpusher probe enquiry.pdf > layout.json
pencilpusher fill enquiry.pdf \
  --field-map '{...}' --fields-json '[...]' \
  --textbox-mode --yes -o enquiry_filled.pdf
```

---

## Commands

### Agent-driven (no Anthropic API key required)

| Command | Description |
|---------|-------------|
| `read <file>` | Document → Markdown on stdout (via MarkItDown). |
| `detect <form>` | Form fields → JSON on stdout. AcroForm / DOCX only; flat PDFs return `{"fields": [], "warning": "flat_pdf_requires_vision"}`. |
| `probe <form>` | Flat-PDF layout introspection → JSON (column dividers, row horizontals, digit spans). |
| `fill <form> --field-map '{...}'` | AcroForm / DOCX fill with explicit mapping. |
| `fill <form> --field-map '{...}' --fields-json '[...]'` | Flat-PDF fill using widget mode (fixed 10pt, no wrap). |
| `fill <form> --field-map '{...}' --fields-json '[...]' --textbox-mode` | Flat-PDF fill with auto-wrap + font-shrink via `page.insert_textbox`. |
| `write-wiki <page> <content>` | Write directly to a vault wiki page. |

### Vault workflow (uses Anthropic API)

| Command | Description |
|---------|-------------|
| `init` | Create the vault at `~/.pencilpusher/`. |
| `ingest <file>` / `ingest-all` | Extract data from source documents into the wiki. |
| `fill <form>` / `fill-all` | Fill one / all forms in the inbox from vault data. |
| `show [page]` / `lint` / `files` | Inspect vault state. |

Set `ANTHROPIC_API_KEY` in the environment for the standalone vault commands. Agent-driven commands work with no key set.

For full argument semantics, the `--fields-json` bbox format, vault layout, and the dense-flat-PDF recipe, see [reference.md](reference.md).

---

## Critical: `--fields-json` bboxes are PERCENTAGES

The single most common misfire on flat PDFs. Each `--fields-json` entry is:

```json
{"name": "Full Name", "bbox": [x, y, w, h], "page": 0}
```

**`bbox` values are percentages of page dimensions (0-100), not PDF points.** The filler internally multiplies by `page_rect.width / 100` and `page_rect.height / 100`. Feeding raw PDF-point coordinates (e.g. from PyMuPDF `span['bbox']`) sends every widget off-page — the PDF renders blank while `pencilpusher` still prints *"Filled N fields"*. Silent misfire, with no error raised.

Convert from PDF points (A4 portrait):
```python
PAGE_W_PT, PAGE_H_PT = 595.4, 841.8
def to_pct(x, y, w, h):
    return [x / PAGE_W_PT * 100, y / PAGE_H_PT * 100,
            w / PAGE_W_PT * 100, h / PAGE_H_PT * 100]
```

---

## Gotchas

1. **Bbox percentages, not points.** See above. This will bite you at least once.
2. **Hard-coded 10pt font on flat-PDF widgets, no wrap.** Narrow cells clip multi-word answers silently. Use `--textbox-mode`, which adds auto-shrink + wrap via `page.insert_textbox`.
3. **Widget borders disabled** (`border_color = None`) so flat-PDF fills overlay the original cell cleanly; visible in most viewers, may disappear in print.
4. **Em-dashes render as `?`** on some viewers' widget-font substitutions. Use ASCII `-` in answer strings for supplier-facing output.
5. **`detect` on a flat PDF** returns `{"fields": [], "warning": "flat_pdf_requires_vision"}`. The agent must supply field positions manually (via `probe` + its own layout reasoning).
6. **Repeat-search ambiguity** in flat-PDF position detection. `page.search_for("Filtration")` may match the page title *and* the row label. Anchor off a unique nearby token (row digit in the No. column, for example).
7. **The vault lives at `~/.pencilpusher/`** (user-wide), not in the current project directory. One vault, many projects.
8. **Subprocess invocation needs `--yes`** on the `fill*` commands to skip the confirmation prompt.
9. **`ANTHROPIC_API_KEY` not required for the agent-driven path.** It is only read by `ingest`, `fill` (without `--field-map`), and `lint`.

---

## QA checklist

- [ ] Open the filled PDF / DOCX and visually confirm every field is correct and legible.
- [ ] Narrow cells aren't clipping — if they are, re-run with `--textbox-mode` or reduce `font_size` per field via `textbox_options`.
- [ ] For flat PDFs: bboxes were percentage-scale (not PDF points).
- [ ] For AcroForm PDFs: every named field in `detect` output was actually filled (no silent omission).
- [ ] No `?` character where an em-dash, en-dash, or other unicode was intended.
- [ ] Signature fields identified and left blank for the human to sign post-print.
- [ ] Tick / X / circle marks on Yes/No options are in the right place (use PyMuPDF directly — pencilpusher does not own these).
- [ ] No duplicate fills from repeat-search ambiguity.
- [ ] Em-dashes replaced with ASCII hyphens for supplier-facing output.

---

## Harness integration

Repository-agnostic. Pair with any agent harness that can run shell commands — Claude Code, OpenAI Codex, Aider, Cursor, a custom SDK agent, or a plain `subprocess.run(["pencilpusher", ...])` from Python.

The agent-driven path is the load-bearing pattern: `read` → reason → `write-wiki`, and `detect` (+ `probe` for flat PDFs) → reason → `fill --field-map --fields-json`. Everything deterministic happens inside pencilpusher; everything inferential happens inside the agent's existing LLM context.

---

## See also

- [reference.md](reference.md) — full argument semantics, `--fields-json` bbox format, vault layout, dense flat-PDF recipe, gaps pencilpusher doesn't own.
- Repository root: [`README.md`](../../README.md), [`docs/HOW_IT_WORKS.md`](../../docs/HOW_IT_WORKS.md), [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
- PyPI: <https://pypi.org/project/paperpusher/> · Issues: <https://github.com/Loodt/pencilpusher/issues>
