"""Load the gold tables to BigQuery (sandbox), at most about once a month (project.md §6.7).

The sandbox's 10 GiB storage is a lifetime quota that deletions don't give back, and a full
gold load is ~0.1 GiB, so a table is reloaded only when it is missing, about to expire, or
changed and its last load is at least LOAD_EVERY old. Load state lives in BigQuery itself
(each table's description holds the export hash; a dataset label holds the bytes loaded so
far), so no state file is needed between runs.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

GOLD_DIR = Path("transform/models/gold")  # every model here is a gold table
LOAD_EVERY = timedelta(days=28)  # Kurt's choice (2026-10-28): monthly reloads
EXPIRES_AFTER = timedelta(days=59)  # sandbox tables expire after 60 days at most
RELOAD_BEFORE_EXPIRY = timedelta(days=10)
CLUSTER_BY = {"fct_prices": ["commodity_id"], "fct_srp_compliance": ["commodity_id"]}
HASH_PREFIX = "sha256:"
TOTAL_LABEL = "bytes_loaded_total"


@dataclass(frozen=True)
class Export:
    table: str
    path: Path
    sha256: str
    rows: int


def gold_tables(gold_dir: Path = GOLD_DIR) -> list[str]:
    return sorted(p.stem for p in gold_dir.glob("*.sql"))


def export_gold(duckdb_path: Path, out_dir: Path, tables: list[str]) -> list[Export]:
    """Write each gold table to Parquet in a stable row order, so equal data hashes equal."""
    out_dir.mkdir(parents=True, exist_ok=True)
    exports = []
    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        for table in tables:
            path = out_dir / f"{table}.parquet"
            con.execute(
                f"COPY (SELECT * FROM {table} ORDER BY ALL) TO '{path.as_posix()}' (FORMAT parquet)"
            )
            rows = con.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            exports.append(Export(table, path, sha, rows))
    return exports


def stored_hash(description: str | None) -> str | None:
    if description and description.startswith(HASH_PREFIX):
        return description.removeprefix(HASH_PREFIX).split()[0]
    return None


def load_reason(bq_table, sha256: str, now: datetime) -> str | None:
    """Why this table must be loaded now, or None to skip it (bq_table None = missing)."""
    if bq_table is None:
        return "missing"
    if bq_table.expires is not None and bq_table.expires - now < RELOAD_BEFORE_EXPIRY:
        return f"expires {bq_table.expires:%Y-%m-%d}"
    if stored_hash(bq_table.description) != sha256 and now - bq_table.modified >= LOAD_EVERY:
        return f"changed, last load {bq_table.modified:%Y-%m-%d}"
    return None


def export_to_bigquery(
    client, dataset_id: str, exports: list[Export], *, force: bool = False, now=None
) -> int:
    """Load the gold exports that are due and check each loaded table's row count against
    DuckDB. Returns 1 on a mismatch, else 0. (Skipped tables are behind on purpose.)"""
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    now = now or datetime.now(UTC)
    dataset = client.get_dataset(dataset_id)  # created by hand (needs Kurt's OK), not here
    loaded_bytes = mismatched = 0
    for exp in exports:
        table_id = f"{dataset_id}.{exp.table}"
        try:
            current = client.get_table(table_id)
        except NotFound:
            current = None
        reason = "forced" if force else load_reason(current, exp.sha256, now)
        if reason is None:
            logger.info("%s: up to date or not due, skipped", exp.table)
            continue
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            clustering_fields=CLUSTER_BY.get(exp.table),
            destination_table_description=f"{HASH_PREFIX}{exp.sha256}",
        )
        with exp.path.open("rb") as f:
            client.load_table_from_file(f, table_id, job_config=config).result()
        table = client.get_table(table_id)
        # set explicitly: a WRITE_TRUNCATE load may keep the old expiry
        table.expires = now + EXPIRES_AFTER
        client.update_table(table, ["expires"])
        loaded_bytes += table.num_bytes
        logger.info("%s: loaded (%s), %d bytes", exp.table, reason, table.num_bytes)
        if table.num_rows != exp.rows:
            logger.error("%s: DuckDB has %d rows, BigQuery %d", exp.table, exp.rows, table.num_rows)
            mismatched += 1

    total = int(dataset.labels.get(TOTAL_LABEL, 0)) + loaded_bytes
    if loaded_bytes:
        dataset.labels = {**dataset.labels, TOTAL_LABEL: str(total)}
        client.update_dataset(dataset, ["labels"])
    logger.info(
        "Loaded %d bytes this run; %.2f GiB of the 10 GiB lifetime quota used so far",
        loaded_bytes,
        total / 2**30,
    )
    return 1 if mismatched else 0
