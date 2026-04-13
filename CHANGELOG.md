# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
