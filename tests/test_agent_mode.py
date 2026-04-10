"""Tests for agent-driven mode commands (read, detect, write-wiki, fill --field-map).

These commands are designed for use by external LLM agents (Claude Code, Codex)
that do the reasoning themselves — no Anthropic API calls needed.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pencilpusher.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    """Point pencilpusher at a temp vault and initialize it."""
    monkeypatch.setenv("PENCILPUSHER_VAULT", str(tmp_path / "vault"))
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code == 0
    return tmp_path / "vault"


class TestRead:
    def test_read_docx(self, runner, tmp_path):
        """Read a DOCX file and get markdown back."""
        from docx import Document

        doc = Document()
        doc.add_paragraph("Test Document Title")
        doc.add_paragraph("This is the body text.")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))

        result = runner.invoke(main, ["read", str(docx_path)])
        assert result.exit_code == 0
        assert "Test Document Title" in result.output

    def test_read_nonexistent_file(self, runner):
        """Reading a nonexistent file should fail."""
        result = runner.invoke(main, ["read", "/nonexistent/file.pdf"])
        assert result.exit_code != 0


class TestDetect:
    def test_detect_acroform_pdf(self, runner):
        """Detect fields in an AcroForm PDF."""
        acroform_path = Path(__file__).parent / "test_form_acroform.pdf"
        if not acroform_path.exists():
            pytest.skip("test_form_acroform.pdf not available")

        result = runner.invoke(main, ["detect", str(acroform_path)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "fields" in data
        assert len(data["fields"]) > 0
        assert data["fields"][0]["field_type"] == "acroform"

    def test_detect_flat_pdf_warns(self, runner):
        """Flat PDFs should return empty fields with a warning."""
        flat_path = Path(__file__).parent / "test_form_flat.pdf"
        if not flat_path.exists():
            pytest.skip("test_form_flat.pdf not available")

        result = runner.invoke(main, ["detect", str(flat_path)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["fields"] == []
        assert data["warning"] == "flat_pdf_requires_vision"

    def test_detect_docx_placeholders(self, runner, tmp_path):
        """Detect placeholder fields in a DOCX."""
        from docx import Document

        doc = Document()
        doc.add_paragraph("Full Name: [_______________]")
        doc.add_paragraph("ID Number: [_______________]")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))

        result = runner.invoke(main, ["detect", str(docx_path)])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "fields" in data
        assert len(data["fields"]) >= 2


class TestWriteWiki:
    def test_write_wiki_page(self, runner, vault_dir):
        """Write content to a wiki page and read it back."""
        result = runner.invoke(main, [
            "write-wiki", "identity",
            "# Identity\\nName: Jane Moyo\\nDOB: 1990-03-15",
        ])
        assert result.exit_code == 0
        assert "Updated wiki/identity.md" in result.output

        # Verify content was written
        content = (vault_dir / "wiki" / "identity.md").read_text(encoding="utf-8")
        assert "Jane Moyo" in content
        assert "1990-03-15" in content

    def test_write_wiki_stdin(self, runner, vault_dir):
        """Write wiki page from stdin."""
        result = runner.invoke(main, [
            "write-wiki", "banking", "--stdin",
        ], input="# Banking\nAccount: 123456\n")
        assert result.exit_code == 0
        assert "Updated wiki/banking.md" in result.output

        content = (vault_dir / "wiki" / "banking.md").read_text(encoding="utf-8")
        assert "123456" in content

    def test_write_wiki_company_page(self, runner, vault_dir):
        """Write to a company sub-page."""
        result = runner.invoke(main, [
            "write-wiki", "companies/acme",
            "# Acme Corp\\nReg: 123",
        ])
        assert result.exit_code == 0

        content = (vault_dir / "wiki" / "companies" / "acme.md").read_text(encoding="utf-8")
        assert "Acme Corp" in content

    def test_write_wiki_invalid_page(self, runner, vault_dir):
        """Writing to an unknown page name should fail."""
        result = runner.invoke(main, ["write-wiki", "nonsense_page", "content"])
        assert result.exit_code != 0

    def test_write_wiki_no_content(self, runner, vault_dir):
        """Writing with no content and no --stdin should fail."""
        result = runner.invoke(main, ["write-wiki", "identity"])
        assert result.exit_code != 0


class TestFillWithFieldMap:
    def test_fill_acroform_with_field_map(self, runner, tmp_path):
        """Fill an AcroForm PDF using explicit field mapping."""
        acroform_path = Path(__file__).parent / "test_form_acroform.pdf"
        if not acroform_path.exists():
            pytest.skip("test_form_acroform.pdf not available")

        # First detect to get field names
        detect_result = runner.invoke(main, ["detect", str(acroform_path)])
        data = json.loads(detect_result.output)
        if not data["fields"]:
            pytest.skip("No fields detected in test PDF")

        # Use the first field's name
        field_name = data["fields"][0]["field_key"]
        field_map = json.dumps({field_name: "Test Value"})

        output_path = tmp_path / "filled.pdf"
        result = runner.invoke(main, [
            "fill", str(acroform_path),
            "--field-map", field_map,
            "-o", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.exists()

    def test_fill_docx_with_field_map(self, runner, tmp_path):
        """Fill a DOCX with placeholder fields using explicit mapping."""
        from docx import Document

        doc = Document()
        doc.add_paragraph("Full Name: [_______________]")
        doc.add_paragraph("ID Number: [_______________]")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))

        field_map = json.dumps({
            "[_______________]": "Jane Moyo",
        })

        output_path = tmp_path / "filled.docx"
        result = runner.invoke(main, [
            "fill", str(docx_path),
            "--field-map", field_map,
            "-o", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.exists()

    def test_fill_flat_pdf_with_fields_json(self, runner, tmp_path):
        """Fill a flat PDF using --field-map + --fields-json for positioning."""
        flat_path = Path(__file__).parent / "test_form_flat.pdf"
        if not flat_path.exists():
            pytest.skip("test_form_flat.pdf not available")

        # Agent provides both the values and the field positions
        field_map = json.dumps({"Full Name": "Jane Moyo"})
        fields_json = json.dumps([{
            "name": "Full Name",
            "field_type": "visual",
            "page": 0,
            "bbox": [15, 20, 50, 3],
        }])

        output_path = tmp_path / "filled_flat.pdf"
        result = runner.invoke(main, [
            "fill", str(flat_path),
            "--field-map", field_map,
            "--fields-json", fields_json,
            "-o", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.exists()
        # Verify the output is larger than the input (widget added)
        assert output_path.stat().st_size > flat_path.stat().st_size

    def test_fill_invalid_json(self, runner, tmp_path):
        """Invalid JSON in --field-map should fail gracefully."""
        from docx import Document

        doc = Document()
        doc.add_paragraph("Name: [___]")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))

        result = runner.invoke(main, [
            "fill", str(docx_path),
            "--field-map", "not-json",
        ])
        assert result.exit_code != 0

    def test_fill_invalid_fields_json(self, runner, tmp_path):
        """Invalid JSON in --fields-json should fail gracefully."""
        flat_path = Path(__file__).parent / "test_form_flat.pdf"
        if not flat_path.exists():
            pytest.skip("test_form_flat.pdf not available")

        result = runner.invoke(main, [
            "fill", str(flat_path),
            "--field-map", '{"Name": "Test"}',
            "--fields-json", "not-json",
        ])
        assert result.exit_code != 0
