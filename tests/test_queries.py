"""Every example and dashboard query runs against the gold tables. Needs a dbt build first
(CI runs this file again after `tawad transform`); skipped when there is no database."""

from pathlib import Path

import duckdb
import pytest

from config.settings import load_settings

QUERIES = sorted(Path("warehouse/queries").glob("*.sql")) + sorted(
    Path("warehouse/dashboard").glob("*.sql")
)


@pytest.mark.parametrize("path", QUERIES, ids=lambda p: p.name)
def test_query_runs_on_gold(path):
    db = load_settings().duckdb_path
    if not db.exists():
        pytest.skip(f"no {db}: run `tawad transform` first")
    con = duckdb.connect()
    # BigQuery names the dataset palengke_gold; here that is the attached DuckDB file
    con.execute(f"ATTACH '{db.as_posix()}' AS palengke_gold (READ_ONLY)")
    con.execute("USE palengke_gold")
    rows = con.execute(path.read_text().rstrip().rstrip(";")).fetchall()
    assert rows, f"{path.name} returned no rows"
