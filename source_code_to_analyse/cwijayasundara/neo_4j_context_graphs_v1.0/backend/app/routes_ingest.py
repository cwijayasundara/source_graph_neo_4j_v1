"""Ingest API routes — trigger ingestion pipeline, check status."""

import logging
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

# Module-level state for tracking ingestion status
_ingest_state = {
    "running": False,
    "last_run": None,
    "last_result": None,
    "error": None,
}
_lock = threading.Lock()


def _run_ingestion():
    """Execute the ingestion pipeline in a background thread."""
    global _ingest_state
    with _lock:
        if _ingest_state["running"]:
            return
        _ingest_state["running"] = True
        _ingest_state["error"] = None

    try:
        from neo4j import GraphDatabase

        from ingestion.categorizer import Categorizer
        from ingestion.loader import GraphLoader
        from ingestion.normalizer import (
            extract_payment_method,
            extract_person,
            generate_transaction_id,
            normalize_merchant,
        )
        from ingestion.parsers.jsonl_parser import parse_jsonl
        from ingestion.parsers.markdown_parser import parse_markdown

        statements_dir = os.environ.get("STATEMENTS_DIR", "./data/statements")
        statements_path = Path(statements_dir)
        if not statements_path.exists():
            raise FileNotFoundError(f"Statements directory not found: {statements_dir}")

        all_transactions = []
        accounts = {}

        for subdir in ["crdit_stmt", "savings_stmt"]:
            dir_path = statements_path / subdir
            if not dir_path.exists():
                continue
            normalized_dir = dir_path / "_normalized"
            if normalized_dir.exists():
                for jsonl_file in sorted(normalized_dir.glob("*.jsonl")):
                    records = parse_jsonl(jsonl_file)
                    all_transactions.extend(records)
                    if records:
                        acct = records[0]
                        accounts[acct["account_id"]] = {
                            "account_id": acct["account_id"],
                            "institution": acct["institution"],
                            "account_type": "credit_card" if "crdit" in subdir else "current",
                        }
            else:
                for md_file in sorted(dir_path.glob("*.md")):
                    meta, records = parse_markdown(md_file)
                    all_transactions.extend(records)
                    accounts[meta["account_id"]] = {
                        "account_id": meta["account_id"],
                        "institution": meta["institution"],
                        "account_type": meta.get("account_type", "current"),
                    }

        # Normalize
        seq_counter: dict[str, int] = {}
        persons = []
        for txn in all_transactions:
            txn["raw_description"] = txn["description"]
            txn["normalized_merchant"] = normalize_merchant(txn["description"])
            txn["payment_method"] = extract_payment_method(txn["description"])
            person = extract_person(txn["description"])
            if person:
                txn["person"] = person
                persons.append(person)
            key = f"{txn['account_id']}-{txn['date']}-{txn['amount']}"
            seq_counter[key] = seq_counter.get(key, -1) + 1
            txn["id"] = generate_transaction_id(
                txn["account_id"], txn["date"], txn["amount"], seq_counter[key]
            )

        # Categorize
        unique_merchants = list({txn["normalized_merchant"] for txn in all_transactions})
        cache_path = Path(
            os.environ.get("MERCHANT_CACHE_PATH", "./data/merchant_categories.json")
        )
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        categorizer = Categorizer(cache_path=cache_path, openai_api_key=openai_key)
        categories = categorizer.categorize_merchants(unique_merchants)

        for txn in all_transactions:
            cat_info = categories.get(txn["normalized_merchant"], {})
            txn["category"] = cat_info.get("subcategory", "Uncategorized")

        # Load to Neo4j
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "financegraph")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        loader = GraphLoader(driver)

        loader.load_time_periods(all_transactions)
        loader.load_accounts(list(accounts.values()))
        loader.load_persons(persons)
        loader.load_merchants(categories)
        loader.load_transactions(all_transactions)
        loader.load_person_links(all_transactions)
        driver.close()

        with _lock:
            _ingest_state["last_result"] = {
                "transactions": len(all_transactions),
                "accounts": len(accounts),
                "merchants": len(unique_merchants),
            }
            logger.info(
                "Ingestion complete: %d transactions, %d accounts",
                len(all_transactions),
                len(accounts),
            )
    except Exception as e:
        with _lock:
            _ingest_state["error"] = str(e)
            logger.exception("Ingestion failed")
    finally:
        with _lock:
            _ingest_state["running"] = False
            _ingest_state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@router.post("")
def trigger_ingest(background_tasks: BackgroundTasks):
    """Trigger ingestion pipeline as a background task."""
    with _lock:
        if _ingest_state["running"]:
            return {"status": "already_running", "message": "Ingestion is already in progress"}

    background_tasks.add_task(_run_ingestion)
    return {"status": "started", "message": "Ingestion pipeline started in background"}


@router.get("/status")
def ingest_status():
    """Check ingestion status — running, last result, any errors."""
    with _lock:
        return {
            "running": _ingest_state["running"],
            "last_run": _ingest_state["last_run"],
            "last_result": _ingest_state["last_result"],
            "error": _ingest_state["error"],
        }
