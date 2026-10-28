"""Pork and chicken price pages by market (Sep 2021 → Apr 2024): one commodity per page.

The page heading names the commodity (``FRESH & FROZEN PORK KASIM/PIGUE``, ``FRESH WHOLE
CHICKEN``); below it a ``MARKET`` header row names the specifications as columns (``Fresh`` |
``Frozen``, or ``Fully-dressed, whole chicken``). The body reads like a per-market range page,
so ``market_range`` does the reading; here the header cells become specifications and the
heading the commodity. The numbered list's row number is dropped from the market name, so
names match the other per-market pages. Some pages carry another page's heading off the
page's right edge; the table box leaves it out.

The 2021-2022 ``Prevailing Retail Prices`` pages split each specification into today's price
and the last report's (``Today`` | ``Yesterday``, ``Last Friday``, ...), in a sub-header row
under ``MARKET`` with a row of dates below it. Only today's price is kept, as the prevailing
price (the other is the earlier report's own value): the characters of the sub-header rows
and of every sub-column but ``Today`` are dropped before ``market_range`` reads the page.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract import layout, market_range
from ingestion.da_prices.extract.items import Item, Unsupported
from ingestion.da_prices.extract.layout import Char, Table

_ROW_NUMBER = re.compile(r"^\d+ ")
_RANGE_TITLE = re.compile(r"^retail price range\b", re.IGNORECASE)
_PREVAILING_TITLE = re.compile(r"^prevailing retail prices\b", re.IGNORECASE)
_YEAR = re.compile(r"\b20\d\d\b")


def _today_only(number: int, chars: Sequence[Char], table: Table) -> list[Char]:
    """The page's characters without the sub-header rows and the last report's sub-columns."""
    start = next((i for i, row in enumerate(table.text) if market_range.is_header(row)), None)
    below = [*table.text[start + 1 :], [], []] if start is not None else [[], []]
    subs, dates = below[:2]
    # dates are "(Sept. 7, 2021)" until Aug 2022, then "September 01, 2022"
    if market_range.first(subs) != "Today" or not _YEAR.search(market_range.first(dates)):
        raise Unsupported(f"no Today sub-header and dates under MARKET on page {number}")
    body_top = max(box[3] for box in table.cells[start + 2] if box)
    earlier = [
        (box[0], box[2])
        for cell, box in zip(subs, table.cells[start + 1], strict=True)
        if cell and box and normalize(cell) != "Today"
    ]
    return [c for c in chars if c.top >= body_top and not any(x0 <= c.x < x1 for x0, x1 in earlier)]


def items_from_page(number: int, chars: Sequence[Char], tables: Sequence[Table]) -> list[Item]:
    """One item per market and specification. ``Prevailing Retail Prices`` pages keep today's
    price only; pages with any other title raise ``Unsupported``."""
    # the first cell holds title, date and heading, one per line
    lines = (tables[0].text[0][0] or "").splitlines() if tables and tables[0].text else []
    compare = bool(lines) and bool(_PREVAILING_TITLE.match(lines[0]))
    if not compare and not (lines and _RANGE_TITLE.match(lines[0])):
        raise Unsupported(f"not a price range or prevailing page ({lines[:1]}) on page {number}")
    if compare:
        chars = _today_only(number, chars, tables[0])
    items = market_range.items_from_page(number, chars, tables)
    return [
        replace(
            item,
            layout="compare" if compare else item.layout,
            commodity_raw=normalize(lines[-1]),
            specification_raw=item.commodity_raw,
            market_raw=_ROW_NUMBER.sub("", item.market_raw or ""),
        )
        for item in items
    ]


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return [
        (number, item)
        for number, page in pages
        for item in items_from_page(number, layout.page_chars(page), layout.page_tables(page))
    ]
