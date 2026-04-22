# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`pencilpusher probe <form>`** — new command that dumps a flat PDF's layout as JSON: column dividers (unique x-coords of vertical cell edges), row horizontals (y-coords of horizontal cell edges), and digit spans (short digit-only text spans with their bboxes). Gives agents the structural information they need to compute answer-box positions for dense supplier / government forms without guessing.
- **`pencilpusher fill ... --textbox-mode`** — new flag on `fill` that switches the flat-PDF code path from `_create_and_fill_widgets` (fixed 10 pt widgets, no wrap, clip on overflow) to `_fill_with_textboxes` using `page.insert_textbox()` with automatic font-size shrink fallback. Narrow cells with multi-word answers now render cleanly. Per-field styling (font, size, colour, alignment) is configurable via a `textbox_options` dict on each `--fields-json` entry.
- New module `pencilpusher.fill.prober` with a public `probe_pdf_layout()` function.
- Tests covering `probe` and `fill --textbox-mode` in `tests/test_agent_mode.py`.
- **Claude Code plugin** at `.claude-plugin/marketplace.json` and an [Agent Skills](https://agentskills.io)-compliant skill at `skills/pencilpusher/` (`SKILL.md` + `reference.md` + `LICENSE.txt`). Installable via `/plugin marketplace add Loodt/pencilpusher` then `/plugin install pencilpusher@pencilpusher`. Versioned independently of the package — starts at skill `0.1.0`, `status: alpha`.

### Context
These additions are driven by a real-world miss on the GKD filter-press enquiry form (2026-04-20) where the widget path clipped every multi-word answer in the narrow Specification and Remarks columns, forcing a half-day of bespoke PyMuPDF work. The `probe` + `--textbox-mode` pair brings those patterns back into the library so the next dense questionnaire is a one-command fill.

### Known gaps (scope for v0.3)
An end-to-end dogfood on the GKD form covered 70 text cells in one CLI call; the remaining ~20% still requires PyMuPDF directly. See the [Roadmap section in the README](README.md#roadmap) for the concrete v0.3 scope:

- Drawing primitives via a new `--marks-json` flag — ovals around Yes/No words, ticks / X / em-dash next to option labels, and "?" markers for cells where Yes/No doesn't map.
- `detect` on a flat PDF to embed the `probe` layout in its output (single round-trip).
- OCR output → field detection pipeline, flat-PDF checkbox/radio groups, XLSX support.

## [0.1.1] — 2026-04-13

### Fixed
- **Critical:** `src/pencilpusher/vault/` was being matched by the `vault/` `.gitignore` rule (intended for user vault-data dirs), so the vault module was never committed to git and never shipped in the `paperpusher 0.1.0` wheel. `pencilpusher init` and any vault operation crashed with `ModuleNotFoundError: No module named 'pencilpusher.vault'`. The gitignore rule is now anchored to the repo root (`/vault/`), the vault module is in the source tree, and CI now exercises it.

### Yanked
- `0.1.0` is yanked on PyPI — broken; use `0.1.1` or later.

## [0.1.0] — 2026-04-10

### Added
- GitHub Actions CI running `ruff` + `pytest` across Python 3.10/3.11/3.12 on Linux, macOS, Windows
- Issue templates for bug reports and feature requests
- `CONTRIBUTING.md` with dev setup and PR guidance
- README badges (CI, PyPI, Python version, licence) and a Limitations section
- **Published to PyPI as `paperpusher`** — the `pencilpusher` distribution name was taken by an unrelated 2021 project, so `pip install paperpusher` installs the `pencilpusher` CLI and module

### Fixed
- `pyproject.toml` `[project.urls]` pointed to a non-existent GitHub org

Initial release.

### Added
- Folder-based workflow: `sources/` → `wiki/` → `inbox/` → `outbox/`
- `pencilpusher init`, `ingest`, `ingest-all`, `fill`, `fill-all`, `show`, `lint`, `files`
- AcroForm PDF filling via PyMuPDF widget API
- Flat PDF filling via PyMuPDF text insertion at detected label positions
- DOCX SDT content control filling via zipfile + lxml
- DOCX table cell filling via python-docx
- MarkItDown-based document → Markdown conversion
- Auto-creation of per-company wiki pages from PACRA/CIPC printouts
- Claude-powered semantic field matching (`Applicant Full Name` → wiki value)
- Manifest tracking to skip already-ingested files
- Agent-driven mode (no API key): `read`, `detect`, `write-wiki`, `fill --field-map`, `fill --fields-json`

[Unreleased]: https://github.com/Loodt/pencilpusher/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Loodt/pencilpusher/releases/tag/v0.1.0
