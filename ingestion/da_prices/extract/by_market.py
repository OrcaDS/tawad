"""Pork and chicken price pages by market (Dec 2022 → Apr 2024): one commodity per page.

The page heading names the commodity (``FRESH & FROZEN PORK KASIM/PIGUE``, ``FRESH WHOLE
CHICKEN``); below it a ``MARKET`` header row names the specifications as columns (``Fresh`` |
``Frozen``, or ``Fully-dressed, whole chicken``). The body reads like a per-market range page,
so ``market_range`` does the reading; here the header cells become specifications and the
heading the commodity. The numbered list's row number is dropped from the market name, so
names match the other per-market pages. Some pages carry another page's heading off the
page's right edge; the table box leaves it out.
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


def items_from_page(number: int, chars: Sequence[Char], tables: Sequence[Table]) -> list[Item]:
    """One item per market and specification. Pages that aren't ``Retail Price Range`` ones
    (the 2021-2022 ``Prevailing Retail Prices``: today and last report side by side, which
    would read as low and high) raise ``Unsupported``."""
    items = market_range.items_from_page(number, chars, tables)
    # the first cell holds title, date and heading, one per line
    lines = (tables[0].text[0][0] or "").splitlines()
    if not lines or not _RANGE_TITLE.match(lines[0]):
        raise Unsupported(f"not a price range page ({lines[:1]}) on page {number}")
    return [
        replace(
            item,
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
