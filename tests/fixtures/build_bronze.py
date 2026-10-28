"""Build the tiny CI bronze lake from `bronze_da_prices.csv` (real DA rows, one report per
page type plus one row per kind of odd price value) and `bronze_psa_*.csv` (real PSA rows:
the mapped retail items and all-items/food CPI for a few months).

    uv run python tests/fixtures/build_bronze.py   # then LAKE_ROOT=tests/fixtures/parquet

The CSV is the reviewable source; the Parquet it writes is git-ignored.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pv
import pyarrow.parquet as pq

from ingestion.da_prices.extract import SCHEMA
from ingestion.psa import openstat

HERE = Path(__file__).parent
LAKE = HERE / "parquet"


def _read(csv_path: Path, schema: pa.Schema) -> pa.Table:
    return (
        pv.read_csv(
            csv_path,
            convert_options=pv.ConvertOptions(
                column_types=schema,
                strings_can_be_null=True,  # empty cell = NULL, quoted "" = empty string
                quoted_strings_can_be_null=False,
            ),
        )
        .select(schema.names)
        .cast(schema)
    )


def build_psa(lake: Path = LAKE) -> None:
    """Write each PSA fixture CSV as one bronze file of its dataset."""
    for dataset in ("psa_cpi", "psa_retail"):
        out = lake / f"bronze/tables/{dataset}/fixture.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(_read(HERE / f"bronze_{dataset}.csv", openstat.SCHEMA), out)


def build(csv_path: Path = HERE / "bronze_da_prices.csv", lake: Path = LAKE) -> int:
    """Write the CSV's rows as bronze Parquet, one file per report month. Returns rows written."""
    table = _read(csv_path, SCHEMA)
    months = pc.strftime(table["report_date"], "%Y-%m")
    for month in pc.unique(months).to_pylist():
        part = table.filter(pc.equal(months, month))
        year, mm = month.split("-")
        out = lake / f"bronze/tables/da_prices/year={year}/month={mm}/part-fixture.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(part, out, compression="snappy")
    return table.num_rows


if __name__ == "__main__":
    build()
    build_psa()
