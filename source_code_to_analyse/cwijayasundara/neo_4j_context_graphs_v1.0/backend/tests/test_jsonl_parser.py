"""Tests for the JSONL statement parser."""

import pytest
from ingestion.parsers.jsonl_parser import parse_jsonl


class TestParseJsonl:
    """Tests for parse_jsonl()."""

    def test_parse_valid_jsonl(self, sample_jsonl_file):
        """A valid JSONL file should return one dict per line."""
        records = parse_jsonl(sample_jsonl_file)
        assert len(records) == 2

    def test_empty_file(self, tmp_path):
        """An empty file should return an empty list."""
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert parse_jsonl(f) == []

    def test_file_not_found(self, tmp_path):
        """A missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_jsonl(tmp_path / "does_not_exist.jsonl")

    def test_required_fields(self, sample_jsonl_file):
        """Each record must contain all expected keys."""
        required = {
            "statement_id",
            "account_id",
            "account_id_token",
            "institution",
            "date",
            "description",
            "description_raw_len",
            "amount",
            "balance",
            "year",
            "month",
        }
        records = parse_jsonl(sample_jsonl_file)
        for rec in records:
            assert required.issubset(rec.keys())

    def test_amount_types(self, sample_jsonl_file):
        """Amounts and balances should be numeric."""
        records = parse_jsonl(sample_jsonl_file)
        for rec in records:
            assert isinstance(rec["amount"], (int, float))
            assert isinstance(rec["balance"], (int, float))

    def test_first_record_values(self, sample_jsonl_file):
        """Spot-check the first record's values."""
        records = parse_jsonl(sample_jsonl_file)
        first = records[0]
        assert first["statement_id"] == "12345678-2025-01-01"
        assert first["account_id"] == "12345678"
        assert first["institution"] == "Halifax"
        assert first["date"] == "2025-01-01"
        assert first["description"] == "WATFORD BOROUGH COUNCIL (DD)"
        assert first["amount"] == pytest.approx(-342.89)
        assert first["balance"] == pytest.approx(5897.11)
        assert first["year"] == 2025
        assert first["month"] == "2025-01"

    def test_whitespace_lines_ignored(self, tmp_path):
        """Blank lines between records should be skipped."""
        content = (
            '{"statement_id": "a", "amount": 1}\n'
            "\n"
            '{"statement_id": "b", "amount": 2}\n'
            "   \n"
        )
        f = tmp_path / "whitespace.jsonl"
        f.write_text(content)
        records = parse_jsonl(f)
        assert len(records) == 2
