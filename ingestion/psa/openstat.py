"""Pull PSA OpenSTAT tables (CPI and retail prices) into bronze rows.

OpenSTAT is a PXWeb v1 API: GET a table for its metadata, POST a query for its data. Each
pull returns a table's whole history, so each table is one bronze file, overwritten on every
pull. Only the Philippines and NCR rows are pulled. Rows keep PSA's text exactly (periods
like ``2018 Jan``, values like ``97.2`` or ``.`` for missing); silver types them.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

import pyarrow as pa

from ingestion.common.storage import Storage

logger = logging.getLogger(__name__)

CPI_TABLE = "2M/PI/CPI/2018NEW/0012M4ACP22.px"  # CPI by commodity group, 2018 = 100
RETAIL_TABLES = tuple(f"2M/2018NEW/0042M4ARN{i:02d}.px" for i in range(1, 12))  # cereals…fish
TABLES = (("psa_cpi", CPI_TABLE), *(("psa_retail", t) for t in RETAIL_TABLES))
ENCODING = "cp1252"  # OpenSTAT's CSV is Windows-1252 ("purée"), not UTF-8
# Geolocation texts look like "PHILIPPINES" or "..NCR - National Capital Region"; \b keeps
# out "Areas Outside National Capital Region (AONCR)".
_PLACE = re.compile(r"^\.*philippines$|\bNCR\b", re.IGNORECASE)

Fetch = Callable[..., bytes]  # (url, json_body=None) -> bytes; see PoliteFetcher

_TS = pa.timestamp("us", tz="+00:00")
SCHEMA = pa.schema(
    [
        pa.field("table_id", pa.string(), nullable=False),
        pa.field("geolocation_raw", pa.string(), nullable=False),
        pa.field("item_raw", pa.string(), nullable=False),
        pa.field("period_raw", pa.string(), nullable=False),
        pa.field("value_raw", pa.string()),
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("pulled_at", _TS, nullable=False),
    ]
)


def table_id(path: str) -> str:
    """``2M/2018NEW/0042M4ARN01.px`` -> ``0042M4ARN01``."""
    return path.rsplit("/", 1)[-1].removesuffix(".px")


def bronze_path(dataset: str, path: str) -> str:
    return f"bronze/tables/{dataset}/{table_id(path)}.parquet"


def place_codes(metadata: dict) -> list[str]:
    """Geolocation value codes for the Philippines and NCR, read from the table metadata
    (codes differ between tables: NCR is ``1`` in CPI, ``130000000`` in retail)."""
    geo = next(v for v in metadata["variables"] if v["code"] == "Geolocation")
    codes = [
        code
        for code, text in zip(geo["values"], geo["valueTexts"], strict=True)
        if _PLACE.search(text)
    ]
    if len(codes) != 2:
        raise ValueError(f"expected Philippines and NCR geolocations, found {len(codes)}")
    return codes


def rows_from_csv(text: str, path: str, url: str, pulled_at: datetime) -> list[dict]:
    """Wide CSV (geolocation, item, one column per period) -> one row per cell."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    rows = []
    for geo, item, *values in reader:
        for period, value in zip(header[2:], values, strict=True):
            rows.append(
                {
                    "table_id": table_id(path),
                    "geolocation_raw": geo,
                    "item_raw": item,
                    "period_raw": period,
                    "value_raw": value,
                    "source_url": url,
                    "pulled_at": pulled_at,
                }
            )
    return rows


def pull_table(
    storage: Storage, fetch: Fetch, base: str, dataset: str, path: str, pulled_at: datetime
) -> int:
    """Pull one table into its bronze file. Returns rows written."""
    url = f"{base}/{path}"
    query = {
        "query": [
            {
                "code": "Geolocation",
                "selection": {"filter": "item", "values": place_codes(json.loads(fetch(url)))},
            }
        ],
        "response": {"format": "csv"},  # json-stat2 returns broken values (recon §3)
    }
    text = fetch(url, json.dumps(query).encode()).decode(ENCODING)
    rows = rows_from_csv(text, path, url, pulled_at)
    if not rows:
        raise ValueError("no rows in the response")
    storage.write_parquet(
        bronze_path(dataset, path), pa.Table.from_pylist(rows, schema=SCHEMA), SCHEMA
    )
    return len(rows)


def ingest(storage: Storage, fetch: Fetch, base: str) -> int:
    """Pull every table. A table that fails keeps its previous bronze file.

    Returns the number of tables that failed.
    """
    pulled_at = datetime.now(UTC)
    failed = 0
    for dataset, path in TABLES:
        try:
            n = pull_table(storage, fetch, base, dataset, path, pulled_at)
        except Exception as exc:  # one broken table must not stop the others
            failed += 1
            logger.error("PSA %s failed: %s", table_id(path), exc)
        else:
            logger.info("PSA %s: %d rows", table_id(path), n)
    return failed
