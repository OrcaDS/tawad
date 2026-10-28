from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.common.storage import LocalStorage
from ingestion.psa import openstat

BASE = "https://psa.test/DB"
CPI_META = {
    "variables": [
        {
            "code": "Geolocation",
            "values": ["0", "1", "2"],
            "valueTexts": [
                "PHILIPPINES",
                "..National Capital Region (NCR)",
                "..Areas Outside National Capital Region (AONCR)",
            ],
        }
    ]
}
RETAIL_META = {
    "variables": [
        {
            "code": "Geolocation",
            "values": ["000000000", "130000000", "140000000"],
            "valueTexts": [
                "Philippines",
                "..NCR - National Capital Region",
                "..CAR - Cordillera Administrative Region",
            ],
        }
    ]
}
# Real shape: wide, cp1252, "." and ".." for missing
CPI_CSV = (
    '"Geolocation","Commodity Description","2018 Jan","2018 Ave"\r\n'
    '"PHILIPPINES","01.2.3 - Tea, mat\xe9 (ND)","97.2000000000000",".."\r\n'
).encode("cp1252")
RETAIL_CSV = (
    b'"Geolocation","Commodity","2026 September","2026 October"\r\n'
    b'"..NCR - National Capital Region","FRESH PORK, KASIM, 1 KG","336.42","."\r\n'
)


class FakeFetch:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.queries: dict[str, dict] = {}

    def __call__(self, url: str, json_body: bytes | None = None) -> bytes:
        if self.fail and self.fail in url:
            raise OSError("down")
        is_cpi = openstat.CPI_TABLE in url
        if json_body is None:
            return json.dumps(CPI_META if is_cpi else RETAIL_META).encode()
        self.queries[url] = json.loads(json_body)
        return CPI_CSV if is_cpi else RETAIL_CSV


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path)


def test_place_codes_skip_areas_outside_ncr() -> None:
    assert openstat.place_codes(CPI_META) == ["0", "1"]
    assert openstat.place_codes(RETAIL_META) == ["000000000", "130000000"]


def test_place_codes_fail_when_ncr_is_missing() -> None:
    meta = {"variables": [{"code": "Geolocation", "values": ["0"], "valueTexts": ["PHILIPPINES"]}]}
    with pytest.raises(ValueError, match="found 1"):
        openstat.place_codes(meta)


def test_rows_keep_text_exactly() -> None:
    at = datetime(2026, 10, 28, tzinfo=UTC)
    rows = openstat.rows_from_csv(CPI_CSV.decode("cp1252"), openstat.CPI_TABLE, "u", at)
    assert [(r["item_raw"], r["period_raw"], r["value_raw"]) for r in rows] == [
        ("01.2.3 - Tea, maté (ND)", "2018 Jan", "97.2000000000000"),
        ("01.2.3 - Tea, maté (ND)", "2018 Ave", ".."),
    ]
    assert rows[0]["table_id"] == "0012M4ACP22"


def test_ingest_writes_one_file_per_table(storage: LocalStorage) -> None:
    fetch = FakeFetch()
    assert openstat.ingest(storage, fetch, BASE) == 0
    files = storage.list("bronze/tables")
    assert len(files) == 12
    assert "bronze/tables/psa_retail/0042M4ARN11.parquet" in files
    cpi_query = fetch.queries[f"{BASE}/{openstat.CPI_TABLE}"]
    assert cpi_query["query"][0]["selection"]["values"] == ["0", "1"]
    assert cpi_query["response"] == {"format": "csv"}
    table = storage.read_parquet("bronze/tables/psa_retail/0042M4ARN01.parquet")
    assert table.column("value_raw").to_pylist() == ["336.42", "."]


def test_failed_table_keeps_its_old_file_and_others_continue(storage: LocalStorage) -> None:
    openstat.ingest(storage, FakeFetch(), BASE)
    before = storage.read_bytes("bronze/tables/psa_retail/0042M4ARN05.parquet")
    assert openstat.ingest(storage, FakeFetch(fail="ARN05"), BASE) == 1
    assert storage.read_bytes("bronze/tables/psa_retail/0042M4ARN05.parquet") == before
    assert len(storage.list("bronze/tables")) == 12
