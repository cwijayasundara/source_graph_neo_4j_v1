"""CLI entrypoint for the FinanceGraph statement ingestion pipeline.

Orchestrates: parse -> normalize -> categorize -> load into Neo4j.
"""

import os
from pathlib import Path

import click
from neo4j import GraphDatabase

from ingestion.parsers.jsonl_parser import parse_jsonl
from ingestion.parsers.markdown_parser import parse_markdown
from ingestion.normalizer import (
    normalize_merchant,
    extract_payment_method,
    extract_person,
    generate_transaction_id,
)
from ingestion.categorizer import Categorizer
from ingestion.loader import GraphLoader


@click.group()
def cli():
    """FinanceGraph statement ingestion pipeline."""
    pass


@cli.command()
@click.argument("statements_dir", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Parse and normalize without loading to Neo4j")
def ingest(statements_dir: str, dry_run: bool):
    """Ingest bank statements into the Neo4j context graph."""
    statements_path = Path(statements_dir)
    all_transactions = []
    accounts = {}
    statements_meta = []

    for subdir in ["crdit_stmt", "savings_stmt"]:
        dir_path = statements_path / subdir
        if not dir_path.exists():
            click.echo(f"Skipping {subdir}: directory not found")
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
                    statements_meta.append({
                        "statement_id": acct["statement_id"],
                        "account_id": acct["account_id"],
                        "period_start": acct.get("date", ""),
                        "period_end": "",
                    })
        else:
            for md_file in sorted(dir_path.glob("*.md")):
                meta, records = parse_markdown(md_file)
                all_transactions.extend(records)
                accounts[meta["account_id"]] = {
                    "account_id": meta["account_id"],
                    "institution": meta["institution"],
                    "account_type": meta.get("account_type", "current"),
                }
                statements_meta.append({
                    "statement_id": f"{meta['account_id']}-{meta['period_start']}",
                    "account_id": meta["account_id"],
                    "period_start": meta.get("period_start", ""),
                    "period_end": meta.get("period_end", ""),
                })

    click.echo(f"Parsed {len(all_transactions)} transactions from {len(accounts)} accounts")

    # --- Normalize ---
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

    # --- Categorize ---
    unique_merchants = list({txn["normalized_merchant"] for txn in all_transactions})
    click.echo(f"Found {len(unique_merchants)} unique merchants")

    cache_path = Path(os.environ.get("MERCHANT_CACHE_PATH", "./data/merchant_categories.json"))
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    categorizer = Categorizer(cache_path=cache_path, openai_api_key=openai_key)
    categories = categorizer.categorize_merchants(unique_merchants)
    click.echo(f"Categorized {len(categories)} merchants")

    for txn in all_transactions:
        cat_info = categories.get(txn["normalized_merchant"], {})
        txn["category"] = cat_info.get("subcategory", "Uncategorized")

    if dry_run:
        click.echo("Dry run — skipping Neo4j load")
        for txn in all_transactions[:5]:
            click.echo(
                f"  {txn['date']} | {txn['normalized_merchant']:20s} | "
                f"{txn['category']:15s} | £{abs(txn['amount']):.2f}"
            )
        return

    # --- Load to Neo4j ---
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "financegraph")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    loader = GraphLoader(driver)

    click.echo("Loading to Neo4j...")
    loader.load_time_periods(all_transactions)
    loader.load_accounts(list(accounts.values()))
    loader.load_persons(persons)
    loader.load_merchants(categories)
    loader.load_statements(statements_meta)
    loader.load_transactions(all_transactions)
    loader.load_person_links(all_transactions)
    loader.load_account_owners("Tony Stark", list(accounts.keys()))
    driver.close()
    click.echo(f"Done. Loaded {len(all_transactions)} transactions into Neo4j.")


@cli.command()
@click.option("--merchant", required=True)
@click.option("--category", required=True)
@click.option("--subcategory", required=True)
def reclassify(merchant: str, category: str, subcategory: str):
    """Override a merchant's category in the cache."""
    cache_path = Path(os.environ.get("MERCHANT_CACHE_PATH", "./data/merchant_categories.json"))
    categorizer = Categorizer(cache_path=cache_path, openai_api_key="")
    categorizer.override(merchant, category, subcategory)
    click.echo(f"Updated {merchant} → {category}/{subcategory}")


if __name__ == "__main__":
    cli()
