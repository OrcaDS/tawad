"""Identify the page type of every page in a DA report PDF.

DA's reports changed layout many times (project.md §6.3, docs/parsing_notes.md). Each page is
classified from its text, in this order:

1. No text at all: ``image_only`` (a picture of a table or poster) or ``blank``.
2. Pages to skip: stall counts and footnote-only pages.
3. The title line. Some titles cover more than one layout (2019-2020 reports reuse one title for
   the NCR summary, the per-market matrix and the poster), so for those the header row decides.
4. The header row alone, for untitled pages.
5. Otherwise the page continues the previous page's table and inherits its type.

The result also says which rule decided, so extractors can be stricter with inherited pages.
A page nothing recognizes is ``unknown``; the extract step marks its file as failed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdfplumber.page import Page

# Page types with prices (one extractor each)
MARKET_MATRIX = "market_matrix"  # commodities x named markets x (prevailing, low, high[, avg])
NCR_SUMMARY = "ncr_summary"  # one row per commodity, NCR prevailing/low/high[/average]
NCR_COMPARE = "ncr_compare"  # NCR prevailing today vs yesterday / last week (2021-2022)
NCR_RANGE = "ncr_range"  # "... at NCR Markets": NCR ranges, often two tables side by side
MARKET_RANGE = "market_range"  # "... per Market": markets x key commodities
PORK_BY_MARKET = "pork_by_market"  # fresh and frozen pork by market
CHICKEN_BY_MARKET = "chicken_by_market"  # whole chicken by market
DAILY_INDEX = "daily_index"  # Daily Price Index: NCR prevailing per item
WEEKLY_AVG = "weekly_avg"  # weekly average per item
PRICE_TYPES = (
    MARKET_MATRIX,
    NCR_SUMMARY,
    NCR_COMPARE,
    NCR_RANGE,
    MARKET_RANGE,
    PORK_BY_MARKET,
    CHICKEN_BY_MARKET,
    DAILY_INDEX,
    WEEKLY_AVG,
)

# Page types without extractable prices
STALL_COUNT = "stall_count"  # number or share of stalls selling an item
INFOGRAPHIC = "infographic"  # poster; its prices are part of an image
NOTES = "notes"  # footnotes or market list only
IMAGE_ONLY = "image_only"  # no text layer, only images (would need OCR)
UNREADABLE = "unreadable"  # text without a character map: "(cid:39)(cid:36)..." (would need OCR)
BLANK = "blank"
SKIP_TYPES = (STALL_COUNT, INFOGRAPHIC, NOTES, IMAGE_ONLY, UNREADABLE, BLANK)

UNKNOWN = "unknown"

# How the type was decided
BY_NO_TEXT = "no_text"
BY_TITLE = "title"
BY_HEADER = "header"
BY_INHERITED = "inherited"
BY_NONE = "none"

TITLE_LINES = 8  # titles sit in the first few text lines
HEADER_LINES = 12
POSTER_MIN_IMAGES = 20  # posters carry dozens of food pictures; tables carry a logo or two


@dataclass(frozen=True)
class PageText:
    """The text of one page as needed for classification."""

    lines: tuple[str, ...]  # text lines from the top of the page down
    n_chars: int
    n_images: int


@dataclass(frozen=True)
class PageClass:
    """The classification of one page (1-based page number)."""

    page: int
    page_type: str
    decided_by: str


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


_STALLS = _rx(r"percentage excludes stalls", r"number of stalls", r"pork availability")
# Shared by the 2018-2020 report families: the header row decides between these two layouts
_SHARED_TITLE = _rx(
    r"markets in metro manila",
    r"daily price monitoring",
    r"price monitoring report",
    r"prevailing price of selected agricultural",
    r"retail price of selected agricultural",
)
_TITLES = (
    (WEEKLY_AVG, _rx(r"weekly average")),
    (DAILY_INDEX, _rx(r"daily price index", r"\(dpi\)", r"in the national capital region")),
    (PORK_BY_MARKET, _rx(r"pork products in ncr")),
    (CHICKEN_BY_MARKET, _rx(r"whole chicken in ncr")),
    (MARKET_RANGE, _rx(r"\bper market\b")),
    (NCR_COMPARE, _rx(r"today'?s prevailing price")),
    (NCR_RANGE, _rx(r"commodities (at|in) ncr markets")),
)
_POSTER_START = _rx(r"^bantay presyo", r"^markets covered", r"^legend\b")
_POSTER_ANYWHERE = _rx(r"markets covered", r"b ?anta ?y ?p?resyo")
_NOTES = _rx(
    r"^source\b",
    r"^notes?\b",
    r"^note/s",
    r"^disclaimer",
    r"^\*",
    r"^\(?[a-z]\)",
    r"^\(\*+\)",
    r"^(none|n/a) - ",
    r"^\d+\. .*\bmarket\b",  # numbered list of covered markets (DPI annex)
)
_NO_UNICODE = re.compile(r"\(cid:\d+\)")  # glyphs without a character map

# Header rows, in priority order over all header lines. The matrix header repeats
# "Prevailing Low High" once per market, sometimes garbled ("PrevailingLow High", or market
# names mixed into the letters), so two "prevailing" on one line is enough. The 2025+ NCR range
# header also has two (side-by-side tables), so it is checked first.
_NCR_RANGE_HEADER = (NCR_RANGE, _rx(r"^commodities low high"))
_MATRIX_HEADER = (MARKET_MATRIX, _rx(r"prevailing.*prevailing"))
_NCR_SUMMARY_HEADER = (
    NCR_SUMMARY,
    _rx(r"^prevailing low high( average)?$", r"^high low prevailing$"),
)
_HEADERS = (
    (WEEKLY_AVG, _rx(r"^commodity specification unit weekly average")),
    _NCR_RANGE_HEADER,
    _MATRIX_HEADER,
    _NCR_SUMMARY_HEADER,
    # DPI headers wrap differently in almost every file
    (DAILY_INDEX, _rx(r"^(commodity )?specification( unit)?( (prevailing|retail|price)|$)")),
)
_SHARED_TITLE_HEADERS = (_MATRIX_HEADER, _NCR_SUMMARY_HEADER)


def normalize(line: str) -> str:
    """Collapse whitespace so patterns can use single spaces."""
    return re.sub(r"\s+", " ", line).strip()


def _first_match(lines: Iterable[str], pattern: re.Pattern[str]) -> bool:
    return any(pattern.search(line) for line in lines)


def _from_header(
    lines: Sequence[str], headers: Sequence[tuple[str, re.Pattern[str]]] = _HEADERS
) -> str | None:
    """Page type from the header row alone, or None."""
    for page_type, pattern in headers:
        if _first_match(lines, pattern):
            return page_type
    return None


def _is_unreadable(lines: Sequence[str]) -> bool:
    text = "".join(lines)
    return len("".join(_NO_UNICODE.findall(text))) > len(text) / 2


def classify_page(page: PageText, previous: str | None = None) -> tuple[str, str]:
    """Return ``(page_type, decided_by)`` for one page.

    ``previous`` is the type of the page before it in the same file, used for continuation pages.
    """
    lines = [normalize(line) for line in page.lines if line.strip()]
    if page.n_chars == 0 or not lines:  # some pages hold only whitespace characters
        return (IMAGE_ONLY if page.n_images else BLANK), BY_NO_TEXT
    if _is_unreadable(lines):
        return UNREADABLE, BY_NO_TEXT
    title_zone = lines[:TITLE_LINES]
    header_zone = lines[:HEADER_LINES]
    many_images = page.n_images >= POSTER_MIN_IMAGES

    if _first_match(title_zone, _STALLS):
        return STALL_COUNT, BY_TITLE
    if _NOTES.search(lines[0]):
        return NOTES, BY_HEADER
    for page_type, pattern in _TITLES:
        if _first_match(title_zone, pattern):
            return page_type, BY_TITLE
    if many_images and _first_match(title_zone, _POSTER_ANYWHERE):
        return INFOGRAPHIC, BY_TITLE
    if _first_match(title_zone, _SHARED_TITLE):
        return (_from_header(header_zone, _SHARED_TITLE_HEADERS) or UNKNOWN), BY_HEADER
    if _first_match(title_zone[:2], _POSTER_START):
        return INFOGRAPHIC, BY_TITLE

    header_type = _from_header(header_zone)
    if header_type is not None:
        return header_type, BY_HEADER
    if previous in PRICE_TYPES:
        return previous, BY_INHERITED
    return UNKNOWN, BY_NONE


def classify_document(pages: Sequence[PageText]) -> list[PageClass]:
    """Classify every page of one PDF, carrying the type forward to continuation pages."""
    result: list[PageClass] = []
    previous: str | None = None
    for number, page in enumerate(pages, start=1):
        page_type, decided_by = classify_page(page, previous)
        result.append(PageClass(number, page_type, decided_by))
        previous = page_type
    return result


def page_text(page: Page) -> PageText:
    """Build a ``PageText`` from a pdfplumber page (text sorted top to bottom)."""
    text = page.extract_text() or ""
    lines = tuple(line for line in text.splitlines() if line.strip())[:HEADER_LINES]
    return PageText(lines, len(page.chars), len(page.images))
