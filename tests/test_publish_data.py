import zipfile

import duckdb

from warehouse import export_to_bigquery as bq
from warehouse import publish_data


def _exports(tmp_path):
    db = tmp_path / "t.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE a AS SELECT * FROM range(3) t(i)")
        con.execute("CREATE TABLE b AS SELECT 'x' AS s")
    return bq.export_gold(db, tmp_path / "gold", ["a", "b"])


def test_changed_only_when_a_table_differs_from_the_latest_release(tmp_path):
    exports = _exports(tmp_path)
    same = {f"{e.table}.parquet": e.sha256 for e in exports}
    assert not publish_data.changed(exports, same)
    assert publish_data.changed(exports, {**same, "a.parquet": "other"})
    assert publish_data.changed(exports, {"a.parquet": same["a.parquet"]})  # b is new
    assert publish_data.changed(exports, {})  # no release yet


def test_csv_zip_holds_every_table_with_a_header(tmp_path):
    out = publish_data.csv_zip(_exports(tmp_path), tmp_path / publish_data.CSV_ZIP)
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["a.csv", "b.csv"]
        assert zf.read("a.csv").decode().splitlines() == ["i", "0", "1", "2"]
    assert not list(tmp_path.glob("*.csv"))  # temporary CSVs are removed
