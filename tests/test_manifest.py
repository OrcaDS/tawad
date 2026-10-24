"""Tests for the DA file manifest."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ingestion.common import manifest
from ingestion.common.manifest import DOWNLOADED, Entry
from ingestion.common.storage import LocalStorage
from ingestion.da_prices.discover import PRICE_MONITORING, Report, revision_level

T0 = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)


def _report(file_name: str, day: int = 6) -> Report:
    return Report(
        source_url=f"https://www.da.gov.ph/wp-content/uploads/2025/11/{file_name}",
        file_name=file_name,
        section="Daily Retail Price Range",
        link_text=f"November {day}, 2025",
        series=PRICE_MONITORING,
        report_date=date(2025, 11, day),
        period_start=None,
        date_check="agree",
        revision_level=revision_level(file_name),
        revision_rank=0,
    )


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "lake")


def test_load_empty_when_missing(storage: LocalStorage) -> None:
    assert manifest.load(storage) == []


def test_save_and_load_round_trip(storage: LocalStorage) -> None:
    entries = manifest.merge([], [_report("Price-Monitoring-November-6-2025.pdf")], T0)
    entries = [
        replace(e, status=DOWNLOADED, sha256="ab", size_bytes=10, downloaded_at=T0, lake_path="x")
        for e in entries
    ]
    manifest.save(storage, entries)
    assert manifest.load(storage) == entries


def test_merge_keeps_download_state_and_ranks_a_later_revision_higher() -> None:
    original = _report("Price-Monitoring-November-6-2025.pdf")
    entries = manifest.merge([], [original], T0)
    entries = [replace(entries[0], status=DOWNLOADED, sha256="ab", lake_path="x")]

    # Next day DA has replaced the original link with a revised file
    revised = _report("Revised-Price-Monitoring-November-6-2025.pdf")
    merged = {e.file_name: e for e in manifest.merge(entries, [revised], T1)}

    old = merged["Price-Monitoring-November-6-2025.pdf"]
    new = merged["Revised-Price-Monitoring-November-6-2025.pdf"]
    assert (old.status, old.sha256, old.on_page, old.revision_rank) == (DOWNLOADED, "ab", False, 0)
    assert (new.status, new.on_page, new.revision_rank, new.first_seen_at) == (
        "discovered",
        True,
        1,
        T1,
    )


def test_merge_does_not_reset_first_seen() -> None:
    report = _report("Price-Monitoring-November-6-2025.pdf")
    entries = manifest.merge(manifest.merge([], [report], T0), [report], T1)
    assert [e.first_seen_at for e in entries] == [T0]


def test_bronze_file_path_uses_report_date() -> None:
    report = replace(_report("Price-Watch-December-3-2018.pdf"), report_date=date(2018, 12, 3))
    assert manifest.bronze_file_path(report) == (
        "bronze/files/da/price_monitoring/year=2018/month=12/Price-Watch-December-3-2018.pdf"
    )


def test_unknown_status_rejected() -> None:
    entry = manifest.merge([], [_report("Price-Monitoring-November-6-2025.pdf")], T0)[0]
    with pytest.raises(ValueError, match="status"):
        Entry(**{**entry.__dict__, "status": "done"})
