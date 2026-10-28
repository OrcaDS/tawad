"""NCR summary pages (2018 → Aug 2021): one NCR-wide row per commodity.

pdfplumber reads these as one clean table per page. The header takes two rows: ``COMMODITY |
SPECIFICATION[(S)] | [Unit |] <price group>`` above the price columns, which are ``Prevailing
| Low | High | Average`` (2018 → early 2020) or ``High | Low | Prevailing`` (June 2020 on).
Columns are mapped by header text, and some files put the report title in the table's first
row. Category rows (``IMPORTED COMMERCIAL RICE``) have one ALL-CAPS name and no price; they
are carried into the rows below, because imported vs local rice is told apart only there.

``NOT AVAILABLE`` (2021) is one cell merged across all price columns: its text fills each of
them. Everything else is kept exactly as read (``NONE``, ``N/A``, ``#N/A``, ``0.00``).

The right-hand strips of the 2018–19 per-market matrix (the last market and the NCR columns,
no commodity names) also carry a ``Prevailing Low High Average`` header; without a COMMODITY
column they raise ``Unsupported``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract.items import Item, Unsupported

Row = Sequence[str | None]

FOOTER = re.compile(r"^(markets covered|notes?\b|source)", re.IGNORECASE)

PRICES = {
    "prevailing": "price_prevailing_raw",
    "low": "price_low_raw",
    "high": "price_high_raw",
    "average": "price_average_raw",
}
NAMES = {
    "commodity": "commodity_raw",
    "specification": "specification_raw",
    "unit": "unit_raw",
}


def _fields(row: Row, words: dict[str, str]) -> dict[str, int]:
    """Field -> column of the cells in ``row`` that start with one of ``words``."""
    found: dict[str, int] = {}
    for i, cell in enumerate(row):
        for word, field in words.items():
            if (cell or "").strip().lower().startswith(word):
                found.setdefault(field, i)
    return found


def _header(table: Sequence[Row]) -> tuple[int, int, dict[str, int], dict[str, int]]:
    """Indexes of the name and price header rows, then the price and the name columns."""
    for i, row in enumerate(table):
        prices = _fields(row, PRICES)
        if "price_low_raw" not in prices or "price_high_raw" not in prices:
            continue
        for top in range(i, -1, -1):
            if "commodity_raw" in (names := _fields(table[top], NAMES)):
                return top, i, prices, names
        raise Unsupported("price columns without a COMMODITY column")
    raise Unsupported("no price header row")


def items_from_table(
    table: Sequence[Row], category: str | None = None
) -> tuple[list[Item], str | None]:
    """Rows of one page's table and the category in force at its end; ``category`` is the
    one carried over from the page before."""
    top, start, prices, names = _header(table)
    layout = " | ".join(normalize(cell) for row in table[top : start + 1] for cell in row if cell)
    price_columns = sorted(prices.items(), key=lambda kv: kv[1])
    items = []
    for row in table[start + 1 :]:
        if not any((cell or "").strip() for cell in row):
            continue
        values = {field: row[i] for field, i in names.items()}
        name = (values["commodity_raw"] or "").strip()
        if FOOTER.match(name):
            break
        spans: list[list[str]] = []  # price fields under each cell (None: merged to the left)
        for field, i in price_columns:
            if row[i] is None and spans:
                spans[-1].append(field)
            else:
                spans.append([field])
        for span in spans:
            text = row[prices[span[0]]]
            parts = (text or "").split()
            # one value per merged column (Jul 2021 "300.00 270.00 300.00"), else one for all
            split = len(span) > 1 and len(parts) == len(span)
            values |= dict(zip(span, parts if split else [text] * len(span), strict=True))
        others = [row[i] for i in range(len(row)) if i != names["commodity_raw"]]
        if name.isupper() and not any((cell or "").strip() for cell in others):
            category = name
            continue
        items.append(Item(layout=layout, category_header_raw=category, **values))
    return items, category


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    result: list[tuple[int, Item]] = []
    category = None
    for number, page in pages:
        for table in page.extract_tables():
            items, category = items_from_table(table, category)
            result += [(number, item) for item in items]
    return result
