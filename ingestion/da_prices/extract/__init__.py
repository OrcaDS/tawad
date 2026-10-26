"""Extract DA report PDFs into bronze rows: one Parquet file per report.

Every page is classified (``classify.py``) and handed to the extractor for its page type. Rows
keep cell text exactly as pdfplumber reads it; typing and cleaning happen in silver. A report
is extracted only when every price page in it has an extractor, so a partly supported report
waits rather than landing half-read. A report that can't be read is marked ``failed`` in the
manifest with the reason, never dropped.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

import pdfplumber
import pyarrow as pa
from pdfplumber.page import Page

from ingestion.common import manifest
from ingestion.common.manifest import DOWNLOADED, EXTRACTED, FAILED, Entry
from ingestion.common.storage import Storage
from ingestion.da_prices import classify
from ingestion.da_prices.extract import daily_index
from ingestion.da_prices.extract.items import Item

logger = logging.getLogger(__name__)

_TS = pa.timestamp("us", tz="+00:00")
SCHEMA = pa.schema(
    [
        pa.field("report_date", pa.date32(), nullable=False),
        pa.field("series", pa.string(), nullable=False),
        pa.field("layout", pa.string(), nullable=False),
        pa.field("page_type", pa.string(), nullable=False),
        pa.field("market_raw", pa.string()),
        pa.field("category_header_raw", pa.string()),
        pa.field("commodity_raw", pa.string()),
        pa.field("specification_raw", pa.string()),
        pa.field("unit_raw", pa.string()),
        pa.field("price_low_raw", pa.string()),
        pa.field("price_high_raw", pa.string()),
        pa.field("price_prevailing_raw", pa.string()),
        pa.field("price_average_raw", pa.string()),
        pa.field("markets_covered", pa.int16()),
        pa.field("source_file", pa.string(), nullable=False),
        pa.field("page", pa.int16(), nullable=False),
        pa.field("revision_rank", pa.int16(), nullable=False),
        pa.field("extractor_version", pa.string(), nullable=False),
        pa.field("ingested_at", _TS, nullable=False),
    ]
)


@dataclass(frozen=True)
class Extractor:
    version: str  # bump when the output for the same PDF changes
    # all pages of its type in a report, as (page number, page), to (page number, item) rows
    extract: Callable[[Sequence[tuple[int, Page]]], list[tuple[int, Item]]]


EXTRACTORS: dict[str, Extractor] = {
    classify.DAILY_INDEX: Extractor("1", daily_index.extract),
}


_COVERED = re.compile(r"covered\b.*\bmarkets?\b", re.IGNORECASE)  # "Covered wet markets and …"
_LIST_NUMBER = re.compile(r"(?<!\S)(\d{1,3})\. (?=\S)")  # "12. Malabon Central Market"


class ExtractError(Exception):
    """The report can't be extracted; the message becomes the manifest's status reason."""


def table_path(entry: Entry) -> str:
    d = entry.report_date
    return (
        f"bronze/tables/da_prices/year={d:%Y}/month={d:%m}/"
        f"part-{entry.series}-{d.isoformat()}-r{entry.revision_rank}.parquet"
    )


def supported(page_types: Sequence[str]) -> bool:
    """Every price page has an extractor (reports with no price page are supported: they fail)."""
    return all(t in EXTRACTORS for t in page_types if t in classify.PRICE_TYPES)


def markets_covered(lines: Sequence[str]) -> int | None:
    """How many markets the footnote's numbered "Covered market(s)" list names, if it has one."""
    start = next((i for i, line in enumerate(lines) if _COVERED.search(line)), None)
    if start is None:
        return None
    numbers = [int(n) for line in lines[start + 1 :] for n in _LIST_NUMBER.findall(line)]
    return max(numbers, default=None)


def extract_pdf(
    pages: Sequence[Page], classes: Sequence[classify.PageClass], entry: Entry, now: datetime
) -> list[dict]:
    """Bronze rows (as dicts in ``SCHEMA`` order) for one report, or ``ExtractError``."""
    types = [c.page_type for c in classes]
    if classify.UNKNOWN in types:
        raise ExtractError(f"unknown page {types.index(classify.UNKNOWN) + 1}")
    if not any(t in classify.PRICE_TYPES for t in types):
        for reason in (classify.IMAGE_ONLY, classify.UNREADABLE):
            if reason in types:
                raise ExtractError(reason)
        raise ExtractError("no price pages")
    markets = markets_covered(
        [line for p in pages[-2:] for line in (p.extract_text() or "").splitlines()]
    )
    rows: list[dict] = []
    for page_type, extractor in EXTRACTORS.items():
        numbered = [
            (c.page, page)
            for page, c in zip(pages, classes, strict=True)
            if c.page_type == page_type
        ]
        if not numbered:
            continue
        items = extractor.extract(numbered)
        empty = sorted({n for n, _ in numbered} - {n for n, _ in items})
        if empty:
            raise ExtractError(f"no rows on page {empty[0]} ({page_type})")
        rows += [
            {
                "report_date": entry.report_date,
                "series": entry.series,
                "page_type": page_type,
                **asdict(item),
                "markets_covered": markets,
                "source_file": entry.file_name,
                "page": number,
                "revision_rank": entry.revision_rank,
                "extractor_version": f"{page_type}/{extractor.version}",
                "ingested_at": now,
            }
            for number, item in items
        ]
    return sorted(rows, key=lambda row: row["page"])  # stable: keeps the order within a page


def extract_one(entry: Entry, storage: Storage, now: datetime) -> Entry | None:
    """Extract one downloaded report. None if its page types aren't all supported yet."""
    try:
        with pdfplumber.open(io.BytesIO(storage.read_bytes(entry.lake_path))) as pdf:
            classes = classify.classify_document([classify.page_text(p) for p in pdf.pages])
            if not supported([c.page_type for c in classes]):
                return None
            rows = extract_pdf(pdf.pages, classes, entry, now)
    except ExtractError as exc:
        logger.warning("Extract failed for %s: %s", entry.file_name, exc)
        return replace(entry, status=FAILED, status_reason=str(exc))
    except Exception as exc:  # a broken PDF must not stop the run
        logger.warning("Extract failed for %s: %r", entry.file_name, exc)
        return replace(entry, status=FAILED, status_reason=f"extract: {exc!r}")
    storage.write_parquet(table_path(entry), pa.Table.from_pylist(rows, schema=SCHEMA), SCHEMA)
    return replace(entry, status=EXTRACTED, status_reason=None)


def extract_pending(
    storage: Storage,
    entries: list[Entry],
    *,
    series: str | None = None,
    redo: bool = False,
    limit: int | None = None,
) -> list[Entry]:
    """Extract downloaded reports (also extracted and failed ones with ``redo``).

    The manifest is saved after each report. Returns the updated entries.
    """
    statuses = (DOWNLOADED, EXTRACTED, FAILED) if redo else (DOWNLOADED,)
    current = {e.source_url: e for e in entries}
    pending = [
        e
        for e in entries
        if e.status in statuses and e.lake_path and (series is None or e.series == series)
    ]
    if limit is not None:
        pending = pending[:limit]
    logger.info("%d reports to extract", len(pending))
    counts = {EXTRACTED: 0, FAILED: 0, "waiting": 0}
    for number, entry in enumerate(pending, start=1):
        updated = extract_one(entry, storage, datetime.now(UTC))
        if updated is None:
            counts["waiting"] += 1
            continue
        counts[updated.status] += 1
        current[entry.source_url] = updated
        manifest.save(storage, list(current.values()))
        if number % 50 == 0:
            logger.info("Extracted %d of %d", number, len(pending))
    logger.info(
        "Extract done: %d extracted, %d failed, %d waiting for an extractor",
        counts[EXTRACTED],
        counts[FAILED],
        counts["waiting"],
    )
    return list(current.values())
