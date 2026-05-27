"""Parser for pre-normalized JSONL bank statement files.

Each line is a JSON object with fields:
    statement_id, account_id, account_id_token, institution, date,
    description, description_raw_len, amount, balance, year, month
"""

import json
from pathlib import Path


def parse_jsonl(file_path: Path) -> list[dict]:
    """Read a ``.jsonl`` file and return a list of transaction dicts.

    Parameters
    ----------
    file_path:
        Path to the JSONL file.

    Returns
    -------
    list[dict]
        One dict per transaction line.

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {file_path}")

    records: list[dict] = []
    text = file_path.read_text().strip()
    if not text:
        return records

    for line in text.splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records
