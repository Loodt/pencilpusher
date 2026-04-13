# Contributing to pencilpusher

Thanks for the interest. pencilpusher is a young project — bug reports, real-world test forms, and PRs are all welcome.

## Quick dev setup

```bash
git clone https://github.com/Loodt/pencilpusher.git
cd pencilpusher
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Python 3.10+ required. CI runs against 3.10, 3.11, and 3.12 on Linux, macOS, and Windows.

## Reporting bugs

Use the [Bug Report](https://github.com/Loodt/pencilpusher/issues/new?template=bug_report.yml) template. Two things make bug reports much easier to act on:

1. **The exact command you ran** and the output / traceback
2. **The kind of document involved** — AcroForm PDF, flat PDF, DOCX with SDT controls, DOCX table, scanned, non-Latin script, etc.

If you can attach a small anonymised sample form that triggers the bug, that's gold. Real-world failure cases are the main thing driving v0.2.

## Suggesting features

Open a [Feature Request](https://github.com/Loodt/pencilpusher/issues/new?template=feature_request.yml). Describe the workflow you're trying to unblock — pain points are more useful than proposed APIs.

## Submitting a PR

1. Fork and create a branch from `master`
2. Make your change
3. Run `ruff check src tests` and `pytest` — both should pass
4. Open a PR with a description of *why* the change is needed (the diff already shows *what*)

Small PRs land faster. If you're planning something large (a new document format, a new wiki layout), open an issue first so we can talk through the approach.

## Code style

- `ruff` for linting and import ordering — config is in `pyproject.toml`
- Keep CLI commands small and composable — the agent-driven mode (`read`, `detect`, `write-wiki`, `fill --field-map`) is a load-bearing pattern
- New commands should work without an API key wherever possible

## What's in scope

- New document formats (XLSX, ODT, RTF) and form types
- Better flat-PDF field detection
- More wiki page types (tax, banking, regulatory)
- Cross-platform fixes (Windows path handling especially)

## What's out of scope (for now)

- Hosted / cloud version
- Web UI
- Document storage backends other than the local vault

## Licence

By contributing you agree your contributions are licensed under the [MIT licence](LICENSE).
