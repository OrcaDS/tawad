from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
from google.api_core.exceptions import NotFound

from warehouse import export_to_bigquery as bq

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def _table(sha="abc", loaded_days_ago=1, expires_in_days=58, rows=2):
    return SimpleNamespace(
        description=f"sha256:{sha}",
        modified=NOW - timedelta(days=loaded_days_ago),
        expires=NOW + timedelta(days=expires_in_days),
        num_rows=rows,
        num_bytes=100,
    )


def test_gold_tables_are_the_gold_models():
    tables = bq.gold_tables()
    assert "fct_prices" in tables and "mart_da_vs_psa" in tables
    assert not any(t.startswith("stg_") for t in tables)


def test_export_hash_is_stable_and_follows_the_data(tmp_path):
    db = tmp_path / "t.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE g AS SELECT * FROM range(1000) t(i) ORDER BY random()")
    first = bq.export_gold(db, tmp_path / "a", ["g"])[0]
    with duckdb.connect(str(db)) as con:  # same rows, different physical order
        con.execute("CREATE OR REPLACE TABLE g AS SELECT * FROM g ORDER BY random()")
    assert bq.export_gold(db, tmp_path / "b", ["g"])[0].sha256 == first.sha256
    assert first.rows == 1000
    with duckdb.connect(str(db)) as con:
        con.execute("INSERT INTO g VALUES (1000)")
    assert bq.export_gold(db, tmp_path / "c", ["g"])[0].sha256 != first.sha256


def test_export_works_while_dbt_holds_the_database(tmp_path):
    db = tmp_path / "t.duckdb"
    with duckdb.connect(str(db)) as held:  # as dbt's connection stays open within run-all
        held.execute("CREATE TABLE g AS SELECT 1 AS i")
        assert bq.export_gold(db, tmp_path / "out", ["g"])[0].rows == 1


def test_load_reason():
    assert bq.load_reason(None, "abc", NOW) == "missing"
    assert bq.load_reason(_table(), "abc", NOW) is None
    assert bq.load_reason(_table(loaded_days_ago=27), "new", NOW) is None  # not a month yet
    assert bq.load_reason(_table(loaded_days_ago=28), "new", NOW).startswith("changed")
    assert bq.load_reason(_table(loaded_days_ago=60), "abc", NOW) is None
    assert bq.load_reason(_table(expires_in_days=9), "abc", NOW).startswith("expires")
    no_expiry = _table(loaded_days_ago=400)
    no_expiry.expires = None  # outside the sandbox
    assert bq.load_reason(no_expiry, "abc", NOW) is None


class FakeClient:
    def __init__(self, tables, rows_after_load=None):
        self.tables = tables
        self.rows_after_load = rows_after_load
        self.dataset = SimpleNamespace(labels={"bytes_loaded_total": "1000"})
        self.loaded = []
        self.meta_rows = None

    def get_dataset(self, dataset_id):
        return self.dataset

    def get_table(self, table_id):
        if table_id not in self.tables:
            raise NotFound(table_id)
        return self.tables[table_id]

    def load_table_from_file(self, f, table_id, job_config):
        self.loaded.append(table_id)
        sha = bq.stored_hash(job_config.destination_table_description)
        self.tables[table_id] = _table(sha, 0, 60, self.rows_after_load)
        return SimpleNamespace(result=lambda: None)

    def load_table_from_json(self, rows, table_id, job_config):
        self.meta_rows = rows
        self.tables[table_id] = _table("", 0, 60, len(rows))
        return SimpleNamespace(result=lambda: None)

    def update_table(self, table, fields):
        pass

    def update_dataset(self, dataset, fields):
        self.dataset = dataset


def _exports(tmp_path):
    for name in ("a", "b"):
        (tmp_path / f"{name}.parquet").write_bytes(b"x")
    return [bq.Export(n, tmp_path / f"{n}.parquet", "new", 2) for n in ("a", "b")]


def test_loads_only_what_is_due_and_counts_bytes(tmp_path):
    client = FakeClient({"ds.a": _table(sha="new")}, rows_after_load=2)
    assert bq.export_to_bigquery(client, "ds", _exports(tmp_path), now=NOW) == 0
    assert client.loaded == ["ds.b"]
    assert client.tables["ds.b"].description == "sha256:new"
    assert client.dataset.labels["bytes_loaded_total"] == "1200"  # b + meta_last_refresh
    a, b = client.meta_rows
    assert (a["table_name"], b["table_name"]) == ("a", "b")
    assert a["loaded_at"] == (NOW - timedelta(days=1)).isoformat()  # a was not reloaded


def test_last_refresh_is_written_only_after_a_load_or_when_missing(tmp_path):
    client = FakeClient({"ds.a": _table(sha="new"), "ds.b": _table(sha="new")})
    bq.export_to_bigquery(client, "ds", _exports(tmp_path), now=NOW)
    assert client.meta_rows is not None  # missing, so written though nothing loaded
    client.meta_rows = None
    bq.export_to_bigquery(client, "ds", _exports(tmp_path), now=NOW)
    assert client.meta_rows is None


def test_force_reloads_everything(tmp_path):
    client = FakeClient({"ds.a": _table(sha="new")}, rows_after_load=2)
    bq.export_to_bigquery(client, "ds", _exports(tmp_path), force=True, now=NOW)
    assert client.loaded == ["ds.a", "ds.b"]


def test_row_count_mismatch_fails(tmp_path):
    client = FakeClient({}, rows_after_load=1)
    assert bq.export_to_bigquery(client, "ds", _exports(tmp_path), now=NOW) == 1
