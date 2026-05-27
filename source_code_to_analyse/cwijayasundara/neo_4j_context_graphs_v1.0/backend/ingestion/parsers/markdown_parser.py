"""Parser for Markdown bank/credit-card statement files.

Expected format
---------------
A YAML frontmatter block followed by a pipe-delimited transaction table::

    ---
    account_id: "1588"
    account_type: "credit_card"
    institution: "Halifax Clarity"
    period_start: "2024-12-13"
    period_end: "2025-01-12"
    ---

    ## Transactions

    | Date | Description | Amount | Balance |
    |------|-------------|--------|---------|
    | 2024-12-14 | TESCO STORES 3372 | -64.27 | -64.27 |
"""

import re
from datetime import date
from pathlib import Path

import yaml


def parse_markdown(file_path: Path) -> tuple[dict, list[dict]]:
    """Parse a Markdown statement file.

    Parameters
    ----------
    file_path:
        Path to the ``.md`` file.

    Returns
    -------
    tuple[dict, list[dict]]
        A 2-tuple of (metadata dict, list of transaction dicts).

    Raises
    ------
    ValueError
        If the file does not contain valid YAML frontmatter.
    """
    file_path = Path(file_path)
    text = file_path.read_text()
    meta = _extract_frontmatter(text)
    transactions = _extract_transactions(text, meta)
    return meta, transactions


def _extract_frontmatter(text: str) -> dict:
    """Extract the YAML frontmatter from *text*."""
    match = re.match(r"^---\s*\n(.+?)\n---", text, re.DOTALL)
    if not match:
        raise ValueError("No YAML frontmatter found")
    return yaml.safe_load(match.group(1))


def _extract_transactions(text: str, meta: dict) -> list[dict]:
    """Extract transaction rows from the Markdown table."""
    table_pattern = re.compile(
        r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*(-?[\d,]+\.\d{2})\s*\|\s*(-?[\d,]+\.\d{2})\s*\|"
    )
    statement_id = f"{meta['account_id']}-{meta['period_start']}"
    transactions: list[dict] = []
    for m in table_pattern.finditer(text):
        txn_date = m.group(1)
        parsed_date = date.fromisoformat(txn_date)
        transactions.append(
            {
                "statement_id": statement_id,
                "account_id": str(meta["account_id"]),
                "institution": meta["institution"],
                "date": txn_date,
                "description": m.group(2).strip(),
                "amount": float(m.group(3).replace(",", "")),
                "balance": float(m.group(4).replace(",", "")),
                "year": parsed_date.year,
                "month": f"{parsed_date.year}-{parsed_date.month:02d}",
            }
        )
    return transactions
