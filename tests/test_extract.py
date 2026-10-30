"""Tests for the extract runner, on cuts of real DPI and weekly reports in tests/fixtures/pdfs/."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ingestion.common import manifest
from ingestion.common.manifest import DOWNLOADED, EXTRACTED, FAILED, Entry
from ingestion.common.storage import LocalStorage
from ingestion.da_prices.discover import DAILY_INDEX, PRICE_MONITORING, WEEKLY_AVG
from ingestion.da_prices.extract import EXTRACTORS, SCHEMA, Extractor, extract_pending, table_path
from ingestion.da_prices.extract.items import Unsupported

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"
T0 = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "lake")


def _entry(storage: LocalStorage, fixture: str, day: date, series: str = DAILY_INDEX) -> Entry:
    entry = Entry(
        source_url=f"https://www.da.gov.ph/wp-content/uploads/{fixture}",
        file_name=fixture,
        section="Daily Price Index",
        link_text=f"{day:%B %d, %Y}",
        series=series,
        report_date=day,
        period_start=None,
        date_check="agree",
        revision_level=0,
        revision_rank=0,
        on_page=True,
        first_seen_at=T0,
        status=DOWNLOADED,
    )
    entry = replace(entry, lake_path=manifest.bronze_file_path(entry))
    storage.write_bytes(entry.lake_path, (FIXTURES / fixture).read_bytes())
    return entry


def test_extracts_rows_with_lineage_and_updates_the_manifest(storage: LocalStorage) -> None:
    entry = _entry(storage, "dpi_2026-10-24_p7-8.pdf", date(2026, 10, 24))
    (result,) = extract_pending(storage, [entry])
    assert result.status == EXTRACTED
    assert manifest.load(storage)[0].status == EXTRACTED

    table = storage.read_parquet(table_path(entry))
    assert table.schema.equals(SCHEMA)
    assert table_path(entry) == (
        "bronze/tables/da_prices/year=2026/month=10/part-daily_index-2026-10-24-r0.parquet"
    )
    rows = table.to_pylist()
    assert {r["page"] for r in rows} == {1, 2}
    assert {r["markets_covered"] for r in rows} == {33}
    assert {r["extractor_version"] for r in rows} == {"daily_index/1"}
    sugar = next(r for r in rows if r["commodity_raw"] == "Sugar (Refined)")
    # page 2 continues the category that page 1 started
    assert (sugar["page"], sugar["category_header_raw"]) == (2, "OTHER BASIC COMMODITIES")
    assert sugar["price_prevailing_raw"] == "81.01"
    assert sugar["market_raw"] is None
    assert any(r["price_prevailing_raw"] == "n/a" for r in rows)  # raw, not NULL


def test_numbered_2025_layout(storage: LocalStorage) -> None:
    entry = _entry(storage, "dpi_2025-05-11_p6-7.pdf", date(2025, 5, 11))
    extract_pending(storage, [entry])
    rows = storage.read_parquet(table_path(entry)).to_pylist()
    assert {r["markets_covered"] for r in rows} == {5}  # Sundays cover fewer markets
    calamansi = next(r for r in rows if r["commodity_raw"] == "Calamansi")
    assert (calamansi["category_header_raw"], calamansi["price_prevailing_raw"]) == (
        "FRUITS",
        "114.00",
    )


def test_price_monitoring_market_and_ncr_pages(storage: LocalStorage) -> None:
    entry = _entry(storage, "pm_2026-10-01_p3-4.pdf", date(2026, 10, 1), PRICE_MONITORING)
    (result,) = extract_pending(storage, [entry])
    assert result.status == EXTRACTED
    rows = storage.read_parquet(table_path(entry)).to_pylist()
    assert {(r["page"], r["page_type"]) for r in rows} == {(1, "market_range"), (2, "ncr_range")}
    chili = next(
        r
        for r in rows
        if r["market_raw"] == "Bicutan Market" and r["commodity_raw"] == "Chili (Green)"
    )
    assert chili["price_prevailing_raw"] == "180.00"
    basmati = next(r for r in rows if r["commodity_raw"] == "Basmati")
    assert basmati["market_raw"] is None
    assert basmati["category_header_raw"] == "IMPORTED COMMERCIAL RICE"
    assert [basmati[f"price_{f}_raw"] for f in ("low", "high", "prevailing", "average")] == [
        "150.00",
        "250.00",
        "150.00",
        "188.75",
    ]


def _poster(pages):
    raise Unsupported("2023 poster")


def test_unread_layout_lands_the_rest_as_partial(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(EXTRACTORS, "ncr_range", Extractor("1", _poster))
    entry = _entry(storage, "pm_2026-10-01_p3-4.pdf", date(2026, 10, 1), PRICE_MONITORING)
    (result,) = extract_pending(storage, [entry])
    assert (result.status, result.status_reason) == (EXTRACTED, "partial: ncr_range")
    rows = storage.read_parquet(table_path(entry)).to_pylist()
    assert {r["page_type"] for r in rows} == {"market_range"}

    monkeypatch.undo()  # the extractor learns the layout: --redo fills the report in
    (redone,) = extract_pending(storage, [result], redo=True)
    assert (redone.status, redone.status_reason) == (EXTRACTED, None)
    rows = storage.read_parquet(table_path(entry)).to_pylist()
    assert {r["page_type"] for r in rows} == {"market_range", "ncr_range"}


def test_page_type_without_extractor_lands_the_rest_as_partial(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(EXTRACTORS, "ncr_range")
    entry = _entry(storage, "pm_2026-10-01_p3-4.pdf", date(2026, 10, 1), PRICE_MONITORING)
    (result,) = extract_pending(storage, [entry])
    assert (result.status, result.status_reason) == (EXTRACTED, "partial: ncr_range")


def test_no_readable_price_page_leaves_the_report_waiting(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(EXTRACTORS, "ncr_range", Extractor("1", _poster))
    monkeypatch.setitem(EXTRACTORS, "market_range", Extractor("1", _poster))
    entry = _entry(storage, "pm_2026-10-01_p3-4.pdf", date(2026, 10, 1), PRICE_MONITORING)
    (result,) = extract_pending(storage, [entry])
    assert result.status == DOWNLOADED
    assert not storage.exists(table_path(entry))


def test_weekly_report_across_three_pages(storage: LocalStorage) -> None:
    entry = _entry(storage, "weekly_2026-10-11_p1-3.pdf", date(2026, 10, 11), WEEKLY_AVG)
    (result,) = extract_pending(storage, [entry])
    assert result.status == EXTRACTED
    rows = storage.read_parquet(table_path(entry)).to_pylist()
    assert len(rows) == 100
    assert {r["page"] for r in rows} == {1, 2, 3}
    assert {r["markets_covered"] for r in rows} == {36}
    assert {r["extractor_version"] for r in rows} == {"weekly_avg/1"}
    oil = rows[-1]  # page 3's table has no header and one cell fewer
    assert (oil["page"], oil["category_header_raw"], oil["commodity_raw"]) == (
        3,
        "OTHER BASIC COMMODITIES",
        "Cooking Oil (Coconut)",
    )
    assert (oil["specification_raw"], oil["unit_raw"], oil["price_average_raw"]) == (
        "1 Liter/bottle",
        "L",
        "153.91",
    )
    assert any(r["price_average_raw"] == "-" for r in rows)  # raw, not NULL


def test_a_broken_pdf_fails_without_stopping_the_run(storage: LocalStorage) -> None:
    good = _entry(storage, "dpi_2026-10-24_p7-8.pdf", date(2026, 10, 24))
    broken = _entry(storage, "dpi_2025-05-11_p6-7.pdf", date(2025, 5, 11), PRICE_MONITORING)
    storage.write_bytes(broken.lake_path, b"%PDF-1.4 truncated")
    result = {e.series: e for e in extract_pending(storage, [broken, good])}
    assert result[PRICE_MONITORING].status == FAILED
    assert result[PRICE_MONITORING].status_reason.startswith("extract: ")
    assert result[DAILY_INDEX].status == EXTRACTED


def test_a_copy_of_another_report_is_never_extracted(storage: LocalStorage) -> None:
    # May 8, 2019: DA linked the May 10 report's file
    entry = _entry(storage, "dpi_2026-10-24_p7-8.pdf", date(2026, 10, 23))
    twin = replace(entry, status_reason="same bytes as Daily-Price-Index-October-24-2026.pdf")
    for redo in (False, True):
        (result,) = extract_pending(storage, [twin], redo=redo)
        assert (result.status, result.status_reason) == (FAILED, twin.status_reason)
        assert not storage.exists(table_path(twin))
        twin = result


def test_redo_and_series_filter(storage: LocalStorage) -> None:
    entry = _entry(storage, "dpi_2026-10-24_p7-8.pdf", date(2026, 10, 24))
    (done,) = extract_pending(storage, [entry])
    assert extract_pending(storage, [done]) == [done]  # nothing pending
    assert extract_pending(storage, [entry], series=PRICE_MONITORING) == [entry]
    (redone,) = extract_pending(storage, [done], redo=True)
    assert redone.status == EXTRACTED


def test_report_whose_pdf_is_not_in_the_lake_is_left_alone(storage: LocalStorage) -> None:
    entry = _entry(storage, "dpi_2026-10-24_p7-8.pdf", date(2026, 10, 24))
    missing = replace(entry, source_url=entry.source_url + "x", lake_path="bronze/files/gone.pdf")
    result = {e.source_url: e for e in extract_pending(storage, [entry, missing])}
    assert result[missing.source_url] == missing
    assert result[entry.source_url].status == EXTRACTED
