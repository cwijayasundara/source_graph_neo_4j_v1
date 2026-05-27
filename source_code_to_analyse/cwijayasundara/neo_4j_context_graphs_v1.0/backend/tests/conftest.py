"""Shared fixtures for ingestion pipeline tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_jsonl_content():
    """Two representative JSONL transaction lines."""
    return [
        '{"statement_id": "12345678-2025-01-01", "account_id": "12345678", "account_id_token": "12345678", "institution": "Halifax", "date": "2025-01-01", "description": "WATFORD BOROUGH COUNCIL (DD)", "description_raw_len": 28, "amount": -342.89, "balance": 5897.11, "year": 2025, "month": "2025-01"}',
        '{"statement_id": "12345678-2025-01-01", "account_id": "12345678", "account_id_token": "12345678", "institution": "Halifax", "date": "2025-01-02", "description": "TESCO STORES 3372 Watford WD17 2UB (DEB)", "description_raw_len": 31, "amount": -28.74, "balance": 5372.83, "year": 2025, "month": "2025-01"}',
    ]


@pytest.fixture
def sample_jsonl_file(tmp_path, sample_jsonl_content):
    """Write sample JSONL content to a temp file and return its path."""
    f = tmp_path / "test_statement.jsonl"
    f.write_text("\n".join(sample_jsonl_content))
    return f


@pytest.fixture
def sample_credit_md_content():
    """A minimal credit-card Markdown statement with frontmatter + table."""
    return """---
account_id: "1588"
account_type: "credit_card"
institution: "Halifax Clarity"
period_start: "2024-12-13"
period_end: "2025-01-12"
---

# Halifax Clarity Credit Card Statement

## Transactions

| Date | Description | Amount | Balance |
|------|-------------|--------|---------|
| 2024-12-14 | TESCO STORES 3372 | -64.27 | -64.27 |
| 2024-12-17 | GITHUB, INC. SAN FRANCISCO CA | -12.00 | -76.27 |
"""


@pytest.fixture
def sample_credit_md_file(tmp_path, sample_credit_md_content):
    """Write sample credit-card Markdown content to a temp file."""
    f = tmp_path / "Statement_1588_Jan-25.md"
    f.write_text(sample_credit_md_content)
    return f
