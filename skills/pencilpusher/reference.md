# pencilpusher — REFERENCE

Full mechanics. [SKILL.md](SKILL.md) is the entry point (triggers, quick start, QA); this file is the manual.

---

## Install

```bash
pip install paperpusher

# Or from source, for development:
git clone https://github.com/Loodt/pencilpusher
cd pencilpusher
pip install -e ".[dev]"
```

`ANTHROPIC_API_KEY` is needed only for `ingest`, `fill` (without `--field-map`), and `lint`. The agent-driven commands (`read`, `detect`, `probe`, `write-wiki`, `fill --field-map`) make zero API calls.

The PyPI distribution name is `paperpusher` because the `pencilpusher` name on PyPI is held by an unrelated 2021 project. The CLI command and the importable module are both `pencilpusher`.

---

## Vault layout

```
~/.pencilpusher/
  sources/           # drop source documents here (passport, company cert, bank letter, ...)
  inbox/             # drop forms to fill
  outbox/            # filled forms land here
  raw/               # stored copies of ingested documents (by category)
  wiki/              # structured knowledge extracted from sources
    index.md
    identity.md      # personal identity data
    banking.md
    contacts.md
    addresses.md
    tax.md
    ...
    companies/
      acme.md
      mycorp.md
```

- `pencilpusher init` creates the tree.
- `pencilpusher ingest <file>` extracts data from a single source into the correct wiki page(s).
- `pencilpusher ingest-all` processes everything in `sources/` that hasn't already been ingested (manifest-tracked).
- `pencilpusher fill-all` processes every form in `inbox/` → `outbox/`.
- `pencilpusher show identity`, `show companies/acme`, `lint` — vault introspection.
- `pencilpusher files` — list stored source documents by category.

The vault is **user-wide**, not per-project. One set of personal / company data is reused across every form you fill.

---

## Agent-driven commands (no API)

| Command | Description |
|---------|-------------|
| `read <file>` | Document → Markdown on stdout via MarkItDown. |
| `detect <form>` | Form fields → JSON on stdout. |
| `probe <form>` | Flat-PDF layout introspection → JSON. |
| `write-wiki <page> <content>` | Write directly to a vault wiki page. `--stdin` reads from stdin instead. |
| `fill <form> --field-map '{"FieldName": "value"}'` | Explicit fill. |
| `fill <form> --field-map '{...}' --fields-json '[...]'` | Flat-PDF fill with agent-supplied positions. |
| `fill <form> --field-map '{...}' --fields-json '[...]' --textbox-mode` | Flat-PDF with auto-wrap + font shrink. |

### `detect` output

For AcroForm PDFs and DOCX:

```json
{"fields": [{"name": "...", "bbox": [...], "page": 0, "field_type": "...", ...}]}
```

For flat PDFs:

```json
{"fields": [], "warning": "flat_pdf_requires_vision", "message": "..."}
```

The agent is expected to read that warning and either (a) run `probe` to get structural anchors and compute bboxes itself, or (b) do its own vision pass on the rendered page, then pass both `--field-map` and `--fields-json` to `fill`.

### `probe` output

One entry per page, each containing:

- `column_dividers` — unique x-coords (PDF points) of vertical cell edges shared by at least N rectangles. N defaults to 3; override with `--min-divider-count`.
- `row_horizontals` — unique y-coords (PDF points) of horizontal cell edges.
- `digit_spans` — every short digit-only text span with its bbox, for anchoring row numbers in a "No." column.
- `width`, `height` — page dimensions in PDF points.

Typical use: from `column_dividers`, pick the x that bounds the answer-column left edge. From `digit_spans` filtered by x-range, build `{row_num: y_top}`. Convert to percentages and emit `--fields-json`.

---

## `--fields-json` bbox format

Each entry:

```json
{"name": "<field name>", "bbox": [x, y, w, h], "page": 0}
```

**`bbox` values are percentages of page dimensions (0-100), NOT PDF points.**

Internally:
```python
widget_rect = fitz.Rect(
    bbox[0] * page_rect.width / 100,
    bbox[1] * page_rect.height / 100,
    (bbox[0] + bbox[2]) * page_rect.width / 100,
    (bbox[1] + bbox[3]) * page_rect.height / 100,
)
```

Feeding raw PDF-point coordinates (for example, `span['bbox']` from `page.get_text('dict')`) sends every widget off-page. The PDF renders blank while `pencilpusher` still prints *"Filled N fields"*. A silent misfire, with no error raised — this is the flat-PDF gotcha that bites everyone at least once.

Conversion helper for A4 portrait (`595.4 × 841.8` pt):
```python
PAGE_W_PT, PAGE_H_PT = 595.4, 841.8
def to_pct_bbox(x_pt, y_pt, w_pt, h_pt):
    return [x_pt / PAGE_W_PT * 100, y_pt / PAGE_H_PT * 100,
            w_pt / PAGE_W_PT * 100, h_pt / PAGE_H_PT * 100]
```

For other page sizes, swap in the values from `page.rect.width` / `page.rect.height`.

### `textbox_options` per field (with `--textbox-mode`)

Inside each `--fields-json` entry, alongside `name` / `bbox` / `page`:

```json
{
  "name": "Remarks",
  "bbox": [60, 45.2, 25, 2.8],
  "page": 0,
  "textbox_options": {
    "font": "helv",
    "font_size": 7,
    "font_color": [0, 0, 0.6],
    "align": 0
  }
}
```

Lets you set smaller fonts in dense Remarks columns and a distinguishing ink colour so the recipient can see what was written versus the form's own pre-printed text. `align` is `0`=left, `1`=centre, `2`=right. `font_color` is `[r, g, b]` in `0-1`.

`--textbox-mode` uses `page.insert_textbox()` with automatic font-size shrink: if the supplied `font_size` doesn't fit, it tries progressively smaller sizes until the text fits; it truncates with an ellipsis only as a last resort. This is the right mode for narrow supplier-questionnaire cells with multi-word answers.

---

## Dense flat-PDF supplier questionnaire recipe

The default flat-PDF widget path creates single-line AcroForm text widgets with a fixed 10pt font and no wrap — clips anything longer than ~4 words in a narrow cell. For dense supplier / government questionnaires, use the two-step pattern:

```bash
# 1. Probe the form's structure.
pencilpusher probe enquiry.pdf > layout.json
```

`layout.json` dumps one entry per page with `column_dividers`, `row_horizontals`, `digit_spans`, and `width` / `height`.

```bash
# 2. Agent reads layout.json:
#    - From column_dividers, pick the x-start of the answer column.
#    - From digit_spans filtered to the No.-column x-range, build
#      {row_num: y_top} so every row has a stable y anchor.
#    - Compute per-field bboxes in PERCENTAGES of page dimensions.
#    - Pick per-field font_size / colour via textbox_options.

# 3. Fill with the textbox path — auto-wrap + font shrink on overflow.
pencilpusher fill enquiry.pdf \
  --field-map '{"row01_answer": "...", "row02_answer": "...", ...}' \
  --fields-json '[
    {"name": "row01_answer", "bbox": [45, 12.3, 30, 2.5], "page": 0,
     "textbox_options": {"font_size": 8, "font_color": [0, 0, 0.6]}},
    ...
  ]' \
  --textbox-mode --yes \
  -o enquiry_filled.pdf
```

---

## Gaps pencilpusher doesn't own (use PyMuPDF directly)

For these operations, combine PyMuPDF directly with `--textbox-mode` for the text cells:

- **Circling a chosen Yes/No** inside the form's own printed text — use `page.draw_oval(fitz.Rect(...))` at the target word's position.
- **Tick / X marks next to an option** at a specific x-offset from a text label — `page.search_for(label)` + `page.insert_text` arithmetic.
- **Placing a remark BELOW the form's own prompt text** in the same cell — custom y-offset arithmetic needed.
- **Scanned / image-only PDFs** — no OCR in the default install. Pre-process with Tesseract or equivalent first.

These are on the roadmap as a `--marks-json` flag on `fill` — see the [Roadmap](../../README.md#roadmap) section of the repo README.

---

## Vault workflow (uses Anthropic API)

| Command | Description |
|---------|-------------|
| `init` | Create vault at `~/.pencilpusher/`. |
| `ingest <file> [--category <cat>] [-m <model>]` | Extract data from one source doc into the wiki. |
| `ingest-all [-m <model>]` | Ingest everything unprocessed in `sources/`. |
| `fill <form> [-o <out>] [--yes] [-m <model>]` | Fill one form from vault data. |
| `fill-all [--yes] [-m <model>]` | Fill all forms in `inbox/` → `outbox/`. |
| `show [page]` | Show vault index or a wiki page (e.g. `show identity`, `show companies/acme`). |
| `lint` | Health-check wiki for empty / missing pages and contradictions. |
| `files` | List stored source documents by category. |

Models default to `claude-sonnet-4-6` (configurable via `~/.pencilpusher/config.yaml` or `-m`).

---

## Architecture (short version)

| Module | API calls | What it does |
|--------|-----------|-------------|
| `ingest/reader.py` | 0 | MarkItDown → Markdown. |
| `ingest/extractor.py` | 1-2 per doc | Structured data extraction. |
| `wiki/pages.py` | 0-1 per page | Merge new data into existing wiki pages. |
| `fill/detector.py` | 0 (AcroForm / DOCX), 1/page (flat PDF in standalone mode) | Field detection. |
| `fill/matcher.py` | 1 per form | Semantic field-to-vault matching. |
| `fill/prober.py` | 0 | Flat-PDF layout introspection (`probe`). |
| `fill/pdf_filler.py` | 0 | PyMuPDF writes values into PDF widgets / text. |
| `fill/docx_filler.py` | 0 | zipfile + lxml writes SDT content; python-docx writes table cells and placeholders. |
| `vault/store.py` | 0 | All vault filesystem operations. |
| `wiki/lint.py` | 1 | Health check. |

Key invariant: **LLM decides WHAT to fill, deterministic code does the XML / PDF manipulation.** Agent-driven mode removes the first half too — the calling agent handles all reasoning, pencilpusher only does deterministic writes.

For the full architecture, see [docs/HOW_IT_WORKS.md](../../docs/HOW_IT_WORKS.md).

---

## Limitations

See the "Limitations & known issues" section of the [repo README](../../README.md#limitations--known-issues) for the authoritative list. Short version:

- Scanned / image-only PDFs — OCR first.
- Non-Latin scripts in values — font-substitution issues when writing back.
- Flat-PDF checkboxes and radio groups — only AcroForm checkboxes fill reliably.
- Multi-page forms with repeating sections (one row per director, for example) — the matcher may duplicate values across rows.
- Encrypted PDFs — unlock first.
- `.xlsx` / `.odt` — not supported.

---

## See also

- [SKILL.md](SKILL.md) — triggers, quick start, gotchas, QA checklist.
- Repo: <https://github.com/Loodt/pencilpusher>
- PyPI: <https://pypi.org/project/paperpusher/>
- Architecture doc: [docs/HOW_IT_WORKS.md](../../docs/HOW_IT_WORKS.md)
- Contributing: [CONTRIBUTING.md](../../CONTRIBUTING.md)
