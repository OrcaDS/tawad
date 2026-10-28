"""Tests for polite, idempotent DA downloads (no network: fetches are faked)."""

import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ingestion.common import manifest
from ingestion.common.manifest import DOWNLOADED, FAILED, Entry
from ingestion.common.storage import LocalStorage
from ingestion.da_prices.discover import PRICE_MONITORING, Report
from ingestion.da_prices.download import PoliteFetcher, download_pending, https_url

T0 = datetime(2026, 10, 24, tzinfo=UTC)


def _entries(*days: int) -> list[Entry]:
    reports = [
        Report(
            source_url=f"http://www.da.gov.ph/wp-content/uploads/2025/11/PM-November-{d}-2025.pdf",
            file_name=f"PM-November-{d}-2025.pdf",
            section="Daily Retail Price Range",
            link_text=f"November {d}, 2025",
            series=PRICE_MONITORING,
            report_date=date(2025, 11, d),
            period_start=None,
            date_check="agree",
            revision_level=0,
            revision_rank=0,
        )
        for d in days
    ]
    return manifest.merge([], reports, T0)


class FakeFetch:
    def __init__(self, responses: dict[str, bytes | Exception] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        response = self.responses.get(url, b"%PDF-1.7 " + url.encode())
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "lake")


def test_downloads_newest_first_and_records_hashes(storage: LocalStorage) -> None:
    fetch = FakeFetch()
    result = {e.report_date.day: e for e in download_pending(storage, _entries(1, 2), fetch)}
    assert [url.rsplit("-", 2)[-2] for url in fetch.calls] == ["2", "1"]
    entry = result[2]
    assert entry.status == DOWNLOADED and len(entry.sha256 or "") == 64
    assert storage.read_bytes(entry.lake_path or "").startswith(b"%PDF-")
    assert entry.lake_path == (
        "bronze/files/da/price_monitoring/year=2025/month=11/PM-November-2-2025.pdf"
    )
    assert manifest.load(storage) == sorted(result.values(), key=lambda e: e.report_date)


def test_rerun_skips_downloaded_files(storage: LocalStorage) -> None:
    entries = download_pending(storage, _entries(1, 2), FakeFetch())
    fetch = FakeFetch()
    download_pending(storage, entries, fetch)
    assert fetch.calls == []


def test_missing_file_is_downloaded_again(storage: LocalStorage, tmp_path: Path) -> None:
    entries = download_pending(storage, _entries(1), FakeFetch())
    (tmp_path / "lake" / (entries[0].lake_path or "")).unlink()
    fetch = FakeFetch()
    download_pending(storage, entries, fetch)
    assert len(fetch.calls) == 1


def test_failures_are_recorded_and_do_not_stop_the_run(storage: LocalStorage) -> None:
    entries = _entries(1, 2, 3)
    url = {e.report_date.day: e.source_url for e in entries}
    fetch = FakeFetch({url[3]: urllib.error.URLError("timed out"), url[2]: b"<html>404</html>"})
    result = {e.report_date.day: e for e in download_pending(storage, entries, fetch)}
    assert (result[3].status, result[3].status_reason) == (
        FAILED,
        "download: <urlopen error timed out>",
    )
    assert (result[2].status, result[2].status_reason) == (FAILED, "download: not a PDF")
    assert result[1].status == DOWNLOADED
    retry = FakeFetch()
    download_pending(storage, list(result.values()), retry)
    assert sorted(retry.calls) == sorted([url[2], url[3]])  # failed downloads are retried


def test_since_and_limit(storage: LocalStorage) -> None:
    fetch = FakeFetch()
    download_pending(storage, _entries(1, 2, 3, 4), fetch, since=date(2025, 11, 2), limit=2)
    assert len(fetch.calls) == 2 and all("-1-2025" not in c for c in fetch.calls)


def test_identical_bytes_are_noted(storage: LocalStorage) -> None:
    entries = _entries(1, 2)
    fetch = FakeFetch({e.source_url: b"%PDF-same" for e in entries})
    result = {e.report_date.day: e for e in download_pending(storage, entries, fetch)}
    assert result[2].status_reason is None
    assert result[1].status_reason == "same bytes as PM-November-2-2025.pdf"


def test_polite_fetcher_spaces_requests_and_sets_user_agent() -> None:
    now = [100.0]
    sleeps: list[float] = []
    requests: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request, timeout: float) -> bytes:
        requests.append(request)
        now[0] += 1.0  # each request takes 1 s
        return b"ok"

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    fetch = PoliteFetcher("TestAgent/1", 5, opener=opener, clock=lambda: now[0], sleep=sleep)
    fetch("http://www.da.gov.ph/a.pdf")
    fetch("https://www.da.gov.ph/b.pdf")
    assert sleeps == [5.0]  # no wait before the first request, full delay before the second
    assert requests[0].full_url == "https://www.da.gov.ph/a.pdf"
    assert requests[0].get_header("User-agent") == "TestAgent/1"


def test_polite_fetcher_posts_json() -> None:
    requests: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request, timeout: float) -> bytes:
        requests.append(request)
        return b"ok"

    PoliteFetcher("T", 5, opener=opener)("https://x/t.px", b'{"a": 1}')
    assert requests[0].get_method() == "POST" and requests[0].data == b'{"a": 1}'
    assert requests[0].get_header("Content-type") == "application/json"


def test_polite_fetcher_waits_after_a_failure_too() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def failing(request: urllib.request.Request, timeout: float) -> bytes:
        raise urllib.error.URLError("down")

    fetch = PoliteFetcher(
        "T", 5, opener=failing, clock=lambda: now[0], sleep=lambda s: sleeps.append(s)
    )
    for _ in range(2):
        with pytest.raises(urllib.error.URLError):
            fetch("https://x/a.pdf")
    assert sleeps == [5.0]


def test_https_url() -> None:
    assert https_url("http://www.da.gov.ph/a.pdf") == "https://www.da.gov.ph/a.pdf"
    assert https_url("https://da.gov.ph/a.pdf") == "https://da.gov.ph/a.pdf"
