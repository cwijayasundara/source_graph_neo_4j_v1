"""Tests for the Markdown statement parser."""

import pytest
from ingestion.parsers.markdown_parser import parse_markdown


class TestParseMarkdown:
    """Tests for parse_markdown()."""

    def test_metadata_extraction(self, sample_credit_md_file):
        """Frontmatter should be parsed into a metadata dict."""
        meta, _ = parse_markdown(sample_credit_md_file)
        assert meta["account_id"] == "1588"
        assert meta["account_type"] == "credit_card"
        assert meta["institution"] == "Halifax Clarity"
        assert meta["period_start"] == "2024-12-13"
        assert meta["period_end"] == "2025-01-12"

    def test_transaction_count(self, sample_credit_md_file):
        """Should extract the correct number of transaction rows."""
        _, txns = parse_markdown(sample_credit_md_file)
        assert len(txns) == 2

    def test_transaction_fields(self, sample_credit_md_file):
        """Each transaction should have all required keys."""
        required = {
            "statement_id",
            "account_id",
            "institution",
            "date",
            "description",
            "amount",
            "balance",
            "year",
            "month",
        }
        _, txns = parse_markdown(sample_credit_md_file)
        for txn in txns:
            assert required.issubset(txn.keys())

    def test_first_transaction_values(self, sample_credit_md_file):
        """Spot-check the first transaction."""
        _, txns = parse_markdown(sample_credit_md_file)
        first = txns[0]
        assert first["date"] == "2024-12-14"
        assert first["description"] == "TESCO STORES 3372"
        assert first["amount"] == pytest.approx(-64.27)
        assert first["balance"] == pytest.approx(-64.27)

    def test_derived_statement_id(self, sample_credit_md_file):
        """statement_id should be '{account_id}-{period_start}'."""
        _, txns = parse_markdown(sample_credit_md_file)
        assert txns[0]["statement_id"] == "1588-2024-12-13"

    def test_derived_year_month(self, sample_credit_md_file):
        """year and month should be derived from the transaction date."""
        _, txns = parse_markdown(sample_credit_md_file)
        assert txns[0]["year"] == 2024
        assert txns[0]["month"] == "2024-12"
        assert txns[1]["year"] == 2024
        assert txns[1]["month"] == "2024-12"

    def test_account_id_is_string(self, sample_credit_md_file):
        """account_id in transactions should be a string."""
        _, txns = parse_markdown(sample_credit_md_file)
        for txn in txns:
            assert isinstance(txn["account_id"], str)

    def test_no_frontmatter_raises(self, tmp_path):
        """A file without frontmatter should raise ValueError."""
        f = tmp_path / "bad.md"
        f.write_text("# No frontmatter here\n| Date | Desc | Amount | Balance |\n")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_markdown(f)

    def test_empty_table(self, tmp_path):
        """A file with frontmatter but no table rows should return empty list."""
        content = """---
account_id: "999"
account_type: "current"
institution: "Test Bank"
period_start: "2025-01-01"
period_end: "2025-01-31"
---

# Test Statement

No transactions this period.
"""
        f = tmp_path / "empty_table.md"
        f.write_text(content)
        meta, txns = parse_markdown(f)
        assert meta["account_id"] == "999"
        assert txns == []

    def test_current_account_statement(self, tmp_path):
        """Should parse a current-account statement with (DEB) suffixes."""
        content = """---
account_id: "12345678"
account_type: "current"
institution: "Halifax"
period_start: "2025-03-01"
period_end: "2025-03-31"
---

# Halifax Current Account

## Your Transactions

| Date | Description | Amount | Balance |
|------|-------------|--------|---------|
| 2025-03-01 | TESCO STORES 3372 WATFORD (DEB) | -27.48 | 11661.72 |
| 2025-03-01 | INTEREST (GROSS) () | 11.69 | 11673.41 |
"""
        f = tmp_path / "current.md"
        f.write_text(content)
        meta, txns = parse_markdown(f)
        assert meta["account_type"] == "current"
        assert len(txns) == 2
        assert txns[0]["institution"] == "Halifax"
        assert txns[1]["amount"] == pytest.approx(11.69)
