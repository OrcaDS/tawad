"""Find every DA report PDF on the price-monitoring page and describe it.

The page is one long HTML document: section headings ("Daily Retail Price Range", "Daily
Price Index", ...) followed by tables of links whose text is the report date. For each link
this module works out the series, the report date and the revision, using only the link and
its filename. The PDF title confirms series and date later, after download.

Report dates come from the filename and the link text, never the upload folder (December
2018 reports sit in ``uploads/2019/02/``). When the two disagree, the filename wins and the
report is flagged.
"""

from __future__ import annotations

import calendar
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

PRICE_WATCH = "price_watch"  # era A daily report, 2018-02 to 2019-10
RETAIL_MONITORING = "retail_monitoring"  # transitional daily report, 2019-09 to 2020-01
PRICE_MONITORING = "price_monitoring"  # daily retail price range, 2019-10 onwards
DAILY_INDEX = "daily_index"  # daily prevailing prices, 2025-04 onwards
WEEKLY_AVG = "weekly_avg"  # weekly average prices, 2023-08 onwards
SERIES = (PRICE_WATCH, RETAIL_MONITORING, PRICE_MONITORING, DAILY_INDEX, WEEKLY_AVG)

SKIPPED_SECTIONS = ("Daily Cigarette Price Monitoring",)  # out of scope

# First three letters of each month, which also catches DA's typos ("Octermber", "Augsut")
_MONTHS = {name[:3].lower(): number for number, name in enumerate(calendar.month_name) if name}

# Filename date patterns, most specific first. Each yields (start, end); start is None
# for a single-day report.
_M = r"(?P<{}>[A-Za-z]+)"
_D = r"(?P<{}>\d{{1,2}})"
_Y = r"(?P<{}>\d{{4}})"
_FILENAME_RANGES = (
    # Weekly-Average-Prices-December-29-2025-January-3-2026
    re.compile(
        "-".join((_M.format("m1"), _D.format("d1"), _Y.format("y1")))
        + "-"
        + "-".join((_M.format("m2"), _D.format("d2"), _Y.format("y2")))
    ),
    # Weekly-Average-Prices-September-28-October-4-2026
    re.compile(
        "-".join(
            (_M.format("m1"), _D.format("d1"), _M.format("m2"), _D.format("d2"), _Y.format("y"))
        )
    ),
    # Weekly-Average-Prices-October-12-18-2026
    re.compile("-".join((_M.format("m1"), _D.format("d1"), _D.format("d2"), _Y.format("y")))),
)
_FILENAME_SINGLE = (
    re.compile("-".join((_M.format("m"), _D.format("d"), _Y.format("y")))),  # March-01-2021
    re.compile(r"_(?P<mm>\d{2})-(?P<d>\d{2})-(?P<y>\d{4})"),  # Price_Monitoring_02-24-2020
    re.compile(r"_(?P<d>\d{2})(?P<m>[A-Za-z]{3,4})(?P<yy>\d{2})(?!\d)"),  # ..._04SEPT19
    re.compile(r"^Daily(?P<m>[A-Za-z]+?)(?P<d>\d{2})(?P<y>\d{4})$"),  # DailyApril042018
)

# Link text patterns ("October 12-18, 2026"), matched against whitespace-normalized text
_LINK_PATTERNS = (
    re.compile(
        r"^(?P<m1>[A-Za-z]+) (?P<d1>\d{1,2}),? (?P<y1>\d{4}) ?- ?"
        r"(?P<m2>[A-Za-z]+) (?P<d2>\d{1,2}),? (?P<y2>\d{4})$"
    ),
    re.compile(
        r"^(?P<m1>[A-Za-z]+) (?P<d1>\d{1,2}) ?- ?(?P<m2>[A-Za-z]+) (?P<d2>\d{1,2}),? (?P<y>\d{4})$"
    ),
    re.compile(r"^(?P<m1>[A-Za-z]+) (?P<d1>\d{1,2}) ?- ?(?P<d2>\d{1,2}),? (?P<y>\d{4})$"),
    re.compile(r"^(?P<m>[A-Za-z]+) (?P<d>\d{1,2}),? (?P<y>\d{4})$"),
)

DateSpan = tuple[date | None, date]  # (period start or None for a single day, report date)


@dataclass(frozen=True)
class Link:
    """One PDF link as it appears on the page."""

    section: str
    url: str
    text: str


@dataclass(frozen=True)
class Report:
    """A report PDF to download, with everything known before opening it."""

    source_url: str
    file_name: str
    section: str
    link_text: str
    series: str
    report_date: date
    period_start: date | None  # first day covered, for weekly reports
    date_check: str  # agree | filename_only | link_only | mismatch
    revision_level: int  # 0 original, 1 revised/updated, n for "nth-Revision", 9 final
    revision_rank: int  # 0 = oldest version of this (series, report_date); highest wins


class _ListingParser(HTMLParser):
    """Collect (section heading, href, link text) for every PDF link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._section = ""
        self._heading: list[str] | None = None
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        # Section headings are plain <h3>s; the year accordions use <h3 class="ea-header">
        if tag == "h3" and "ea-header" not in (attributes.get("class") or ""):
            self._heading = []
        href = attributes.get("href") or ""
        if tag == "a" and urlsplit(href).path.lower().endswith(".pdf"):
            self._href = href
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self._heading is not None:
            heading = " ".join("".join(self._heading).split())
            if heading:
                self._section = heading
            self._heading = None
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append(Link(self._section, self._href, text))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)
        if self._href is not None:
            self._text.append(data)


def parse_listing(html: str) -> list[Link]:
    """Return every PDF link on the price-monitoring page, in page order."""
    parser = _ListingParser()
    parser.feed(html)
    parser.close()
    return parser.links


def file_name_of(url: str) -> str:
    """The PDF's original filename, taken from the URL path."""
    return unquote(urlsplit(url).path.rsplit("/", 1)[-1])


def _month(word: str) -> int | None:
    return _MONTHS.get(word[:3].lower()) if len(word) >= 3 else None


def _make_date(year: str | int, month: int | None, day: str | int) -> date | None:
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def _span_from(groups: dict[str, str]) -> DateSpan | None:
    """Build a DateSpan from named regex groups (m/d/y, m1/d1/m2/d2/y, mm, yy variants)."""
    if "d1" in groups:
        end_month = _month(groups["m2"]) if groups.get("m2") else _month(groups["m1"])
        start = _make_date(groups.get("y1") or groups["y"], _month(groups["m1"]), groups["d1"])
        end = _make_date(groups.get("y2") or groups["y"], end_month, groups["d2"])
        if start is None or end is None or not start < end:
            return None
        return start, end
    if "mm" in groups:
        month: int | None = int(groups["mm"])
    else:
        month = _month(groups["m"])
    year = groups["y"] if "y" in groups else f"20{groups['yy']}"
    day = _make_date(year, month, groups["d"])
    return None if day is None else (None, day)


def _first_span(
    patterns: tuple[re.Pattern[str], ...], text: str, *, search: bool
) -> DateSpan | None:
    for pattern in patterns:
        matches = pattern.finditer(text) if search else filter(None, [pattern.match(text)])
        for match in matches:
            span = _span_from({k: v for k, v in match.groupdict().items() if v is not None})
            if span is not None:
                return span
    return None


def date_from_filename(file_name: str) -> DateSpan | None:
    """Parse the report date (or week) from a DA filename, or None if it has none."""
    stem = file_name.rsplit(".", 1)[0]
    return _first_span(_FILENAME_RANGES, stem, search=True) or _first_span(
        _FILENAME_SINGLE, stem, search=True
    )


def date_from_link_text(text: str) -> DateSpan | None:
    """Parse the date label DA shows as link text ("October 12-18, 2026")."""
    return _first_span(_LINK_PATTERNS, " ".join(text.split()), search=False)


def series_of(section: str, file_name: str) -> str | None:
    """Map a link to its report series, or None for out-of-scope links."""
    name = file_name.lower()
    if section == "Daily Retail Price Range":
        if "price-watch" in name or re.match(r"daily[a-z]", name):
            return PRICE_WATCH
        if "retail" in name:
            return RETAIL_MONITORING
        return PRICE_MONITORING
    if section == "Daily Price Index":
        return DAILY_INDEX
    if section == "Weekly Average Retail Prices":
        return WEEKLY_AVG
    return None


def revision_level(file_name: str) -> int:
    """How far along the revision chain a filename says it is (higher replaces lower)."""
    name = file_name.lower()
    if "final" in name:
        return 9
    nth = re.search(r"(\d+)(?:st|nd|rd|th)-revision", name)
    if nth:
        return int(nth.group(1))
    if "revised" in name or "updated" in name:
        return 1
    return 0


def _upload_folder(url: str) -> str:
    """'YYYY/MM' upload folder, used only to order re-uploads, never as the report date."""
    match = re.search(r"/uploads/(\d{4}/\d{2})/", urlsplit(url).path)
    return match.group(1) if match else ""


def _reupload_number(file_name: str) -> int:
    """Trailing '-1' / '_2' that WordPress adds when a file is uploaded again."""
    match = re.search(r"[-_](\d)$", file_name.rsplit(".", 1)[0])
    return int(match.group(1)) if match else 0


def _report_from_link(link: Link) -> Report | None:
    file_name = file_name_of(link.url)
    series = series_of(link.section, file_name)
    if series is None:
        if link.section not in SKIPPED_SECTIONS:
            logger.warning("Skipping PDF outside known sections (%r): %s", link.section, link.url)
        return None
    from_name = date_from_filename(file_name)
    from_text = date_from_link_text(link.text)
    if from_name and from_text:
        span, check = from_name, "agree" if from_name == from_text else "mismatch"
    elif from_name:
        span, check = from_name, "filename_only"
    elif from_text:
        span, check = from_text, "link_only"
    else:
        logger.warning("No report date in filename or link text, skipping: %s", link.url)
        return None
    if check == "mismatch":
        logger.warning(
            "Filename and link text disagree for %s (%r): using the filename date",
            file_name,
            link.text,
        )
    return Report(
        source_url=link.url,
        file_name=file_name,
        section=link.section,
        link_text=link.text,
        series=series,
        report_date=span[1],
        period_start=span[0],
        date_check=check,
        revision_level=revision_level(file_name),
        revision_rank=0,
    )


def rank_revisions(reports: list[Report]) -> list[Report]:
    """Number the versions of each (series, report_date): 0 is oldest, highest is current.

    Order is the filename's revision level, then the re-upload suffix, then upload folder.
    """
    groups: dict[tuple[str, date], list[Report]] = defaultdict(list)
    for report in reports:
        groups[(report.series, report.report_date)].append(report)
    ranks: dict[str, int] = {}
    for versions in groups.values():
        ordered = sorted(
            versions,
            key=lambda r: (
                r.revision_level,
                _reupload_number(r.file_name),
                _upload_folder(r.source_url),
                r.file_name,
            ),
        )
        ranks.update({r.source_url: rank for rank, r in enumerate(ordered)})
    return [replace(r, revision_rank=ranks[r.source_url]) for r in reports]


def discover(html: str) -> list[Report]:
    """All in-scope reports on the page, with series, dates and revision ranks."""
    links = parse_listing(html)
    reports: list[Report] = []
    seen: set[str] = set()
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        report = _report_from_link(link)
        if report is not None:
            reports.append(report)
    reports = rank_revisions(reports)
    logger.info("Found %d PDF links, %d in-scope reports", len(links), len(reports))
    return reports
