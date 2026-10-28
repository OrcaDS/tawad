"""Build the tiny CI bronze lake from `bronze_da_prices.csv` (real DA rows, one report per
page type plus one row per kind of odd price value).

    uv run python tests/fixtures/build_bronze.py   # then LAKE_ROOT=tests/fixtures/parquet

The CSV is the reviewable source; the Parquet it writes is git-ignored.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.compute as pc
import pyarrow.csv as pv
import pyarrow.parquet as pq

from ingestion.da_prices.extract import SCHEMA

HERE = Path(__file__).parent
LAKE = HERE / "parquet"


def build(csv_path: Path = HERE / "bronze_da_prices.csv", lake: Path = LAKE) -> int:
    """Write the CSV's rows as bronze Parquet, one file per report month. Returns rows written."""
    table = pv.read_csv(
        csv_path,
        convert_options=pv.ConvertOptions(
            column_types=SCHEMA,
            strings_can_be_null=True,  # empty cell = NULL, quoted "" = empty string
            quoted_strings_can_be_null=False,
        ),
    ).select(SCHEMA.names)
    table = table.cast(SCHEMA)
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
