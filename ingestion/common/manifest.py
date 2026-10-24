"""The DA file manifest: one row per report PDF ever seen, with its download and extract status.

It lives in the lake at ``MANIFEST_PATH`` as a small Parquet file that is rewritten whole on
each save (a few thousand rows). Rows are never deleted: a report that disappears from DA's
page (for example, replaced by a revised file) keeps its row, so revisions can be ranked
across everything ever downloaded, not just what the page shows today.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime

import pyarrow as pa

from ingestion.common.storage import Storage
from ingestion.da_prices.discover import Report, rank_revisions

logger = logging.getLogger(__name__)

MANIFEST_PATH = "bronze/manifest/da_files.parquet"

# Status values
DISCOVERED = "discovered"  # known from the page, not downloaded yet
DOWNLOADED = "downloaded"  # PDF stored in bronze/files
FAILED = "failed"  # download or extract failed; see status_reason
EXTRACTED = "extracted"  # rows written to bronze/tables
STATUSES = (DISCOVERED, DOWNLOADED, FAILED, EXTRACTED)

# Fixed offset, not "UTC": a named zone needs a tz database, which Windows lacks
_TS = pa.timestamp("us", tz="+00:00")
SCHEMA = pa.schema(
    [
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("file_name", pa.string(), nullable=False),
        pa.field("section", pa.string(), nullable=False),
        pa.field("link_text", pa.string(), nullable=False),
        pa.field("series", pa.string(), nullable=False),
        pa.field("report_date", pa.date32(), nullable=False),
        pa.field("period_start", pa.date32()),
        pa.field("date_check", pa.string(), nullable=False),
        pa.field("revision_level", pa.int16(), nullable=False),
        pa.field("revision_rank", pa.int16(), nullable=False),
        pa.field("on_page", pa.bool_(), nullable=False),
        pa.field("first_seen_at", _TS, nullable=False),
        pa.field("lake_path", pa.string()),
        pa.field("sha256", pa.string()),
        pa.field("size_bytes", pa.int64()),
        pa.field("downloaded_at", _TS),
        pa.field("status", pa.string(), nullable=False),
        pa.field("status_reason", pa.string()),
    ]
)


@dataclass(frozen=True)
class Entry:
    """One manifest row."""

    source_url: str
    file_name: str
    section: str
    link_text: str
    series: str
    report_date: date
    period_start: date | None
    date_check: str
    revision_level: int
    revision_rank: int
    on_page: bool  # still linked from DA's page at the last discovery
    first_seen_at: datetime
    lake_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    downloaded_at: datetime | None = None
    status: str = DISCOVERED
    status_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"Unknown manifest status {self.status!r}")

    def as_report(self) -> Report:
        report_fields = {f.name for f in fields(Report)}
        return Report(**{k: v for k, v in asdict(self).items() if k in report_fields})


def bronze_file_path(report: Report | Entry) -> str:
    """Where a report's PDF lives in the lake (partitioned by report date, not upload date)."""
    d = report.report_date
    return f"bronze/files/da/{report.series}/year={d:%Y}/month={d:%m}/{report.file_name}"


def load(storage: Storage) -> list[Entry]:
    """Read the manifest, or an empty one on the first run."""
    if not storage.exists(MANIFEST_PATH):
        return []
    table = storage.read_parquet(MANIFEST_PATH)
    return [Entry(**row) for row in table.to_pylist()]


def save(storage: Storage, entries: list[Entry]) -> None:
    """Rewrite the manifest, sorted for stable diffs."""
    ordered = sorted(entries, key=lambda e: (e.series, e.report_date, e.revision_rank, e.file_name))
    table = pa.Table.from_pylist([asdict(e) for e in ordered], schema=SCHEMA)
    storage.write_parquet(MANIFEST_PATH, table, SCHEMA)
    logger.debug("Saved manifest with %d entries", len(entries))


def merge(entries: list[Entry], reports: list[Report], now: datetime) -> list[Entry]:
    """Fold a fresh discovery into the manifest.

    New reports are added as ``discovered``. Known ones keep their download state but take
    the page's current labels. Reports no longer on the page stay, with ``on_page=False``.
    Revision ranks are then recomputed across all rows, so a revised file that replaced an
    already-downloaded original ranks above it.
    """
    by_url = {e.source_url: e for e in entries}
    on_page = {r.source_url for r in reports}
    merged: dict[str, Entry] = {
        url: replace(e, on_page=url in on_page) for url, e in by_url.items()
    }
    added = 0
    for report in reports:
        labels = asdict(report)
        if report.source_url in merged:
            merged[report.source_url] = replace(merged[report.source_url], **labels)
        else:
            merged[report.source_url] = Entry(**labels, on_page=True, first_seen_at=now)
            added += 1
    ranked = rank_revisions([e.as_report() for e in merged.values()])
    result = [replace(merged[r.source_url], revision_rank=r.revision_rank) for r in ranked]
    logger.info(
        "Manifest: %d entries (%d new, %d no longer on the page)",
        len(result),
        added,
        sum(not e.on_page for e in result),
    )
    return result
