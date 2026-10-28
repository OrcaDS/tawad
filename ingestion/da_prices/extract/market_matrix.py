"""Per-market matrix pages (Feb 2018 → Apr 2020): commodities down, markets across.

pdfplumber reads each page as one table. The header takes two rows: ``Commodity |
Specification | <market> … `` on top, and under every market ``Prevailing | Low | High``
(plus ``Average`` from Nov 2019). The NCR-wide ``Prevailing | Low | High | Average`` columns
come last (not on every page), their headers spanning both rows, so the cell under them is
empty. Header text is often garbled (``revailin | gLow``, ``P\\nHigh``), so a column's field is
matched loosely (``low``, ``high``, ``aver``, ``vail``) and its market is the top-row cell it
falls under. Market names drop their list number (``1. Commonwealth`` → ``Commonwealth``).

Category rows (``RICE``, ``COMMERCIAL``, ``NFA RICE``) have one ALL-CAPS name and no price, and
carry into the rows below and over page breaks. Cells are kept exactly as read: ``#N/A``,
``#DIV/0!``, ``0.00`` (DA's blank in 2018–19) and digits spaced apart by the PDF (``5 0.00``).

A page that continues the rows of the one before has no header; it reuses the previous
header when its rows have the same number of cells. Late 2018 and 2019 sheets are also cut
into column strips across pages: a strip without commodity names raises ``Unsupported``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract.items import Item, Unsupported
from ingestion.da_prices.extract.ncr_summary import FOOTER

Row = Sequence[str | None]
Column = tuple[int, str | None, str]  # cell index, market (None: NCR-wide), price field

_FIELDS = (  # checked in this order: "P\nHigh" is high, "gLow" is low
    ("low", "price_low_raw"),
    ("high", "price_high_raw"),
    ("aver", "price_average_raw"),
    ("vail", "price_prevailing_raw"),
)
_LIST_NUMBER = re.compile(r"^\d+\.\s*")
BLANK = ""  # field of a column without header
# a category row: ALL-CAPS words, then (Feb 2018) the first spec word of the row below
_CATEGORY = re.compile(r"^([A-Z][A-Z&,\- ]*[A-Z])(?:\s+([a-z]\S*(?: \S+)*))?$")
_LEFTOVER = {"", "#DIV/0!", "#N/A", "0", "0.00"}  # formula leftovers in category rows


def _field(cell: str | None) -> str | None:
    text = (cell or "").lower()
    return next((field for word, field in _FIELDS if word in text), None)


def _is_header(row: Row) -> bool:
    return sum(_field(cell) == "price_prevailing_raw" for cell in row) >= 2


def _header(table: Sequence[Row]) -> tuple[int, list[Column], str] | None:
    """Index of the sub-header row, the price columns and the layout, or None."""
    sub = next((i for i, row in enumerate(table) if _is_header(row)), None)
    if sub is None:
        return None
    if sub == 0 or not (table[sub - 1][0] or "").lower().startswith("commodity"):
        raise Unsupported("matrix strip without commodity names")
    top, below = table[sub - 1], table[sub]
    columns: list[Column] = []
    market: str | None = None
    for i in range(2, len(below)):
        if below[i] is None:  # NCR-wide column: its header spans both rows
            if top[i] == "":
                columns.append((i, None, BLANK))  # Dec 12, 2019: an empty last column
                continue
            if (field := _field(top[i])) is None:
                raise Unsupported(f"unknown NCR column {top[i]!r}")
            columns.append((i, None, field))
            continue
        if top[i] is not None:
            market = _LIST_NUMBER.sub("", top[i].strip())
        if (field := _field(below[i])) is None or market is None:
            raise Unsupported(f"unknown market column {below[i]!r}")
        columns.append((i, market, field))
    # a lost market name (Nov 2, 2018) puts two markets' columns under one name
    fields = [(market, field) for _, market, field in columns if field != BLANK]
    if len(fields) != len(set(fields)):
        raise Unsupported("a market's price columns repeat (market names missing)")
    layout = " | ".join(normalize(c) for row in (top, below) for c in row if c)
    return sub, columns, layout


def items_from_table(
    table: Sequence[Row],
    header: tuple[list[Column], str] | None = None,
    category: str | None = None,
) -> tuple[list[Item], tuple[list[Column], str], str | None]:
    """Rows of one page's table, and the header and category in force at its end.

    ``header`` and ``category`` carry over from the page before."""
    found = _header(table)
    if found is not None:
        start, columns, layout = found
        body = table[start + 1 :]
    elif header is not None and table and len(table[0]) == max(i for i, _, _ in header[0]) + 1:
        (columns, layout), body = header, table
    else:
        raise Unsupported("no header and no header to continue")
    if not any((row[0] or "").strip() for row in body):
        raise Unsupported("matrix strip without commodity names")
    items: list[Item] = []
    spec_start = None  # spec words glued to the category row above
    for row in body:
        if not any((cell or "").strip() for cell in row):
            continue
        name = (row[0] or "").strip()
        if FOOTER.match(name):
            break
        heading = _CATEGORY.match(name)
        if heading and all((cell or "").strip() in _LEFTOVER for cell in row[1:]):
            category, spec_start = heading[1], heading[2]
            continue
        spec = "\n".join(filter(None, [spec_start, row[1]])) if spec_start else row[1]
        spec_start = None
        markets: dict[str | None, dict[str, str | None]] = {}
        for i, market, field in columns:
            if field != BLANK:
                markets.setdefault(market, {})[field] = row[i]
            elif (row[i] or "").strip():
                raise Unsupported(f"text in a column without header: {row[i]!r}")
        items += [
            Item(
                layout=layout,
                category_header_raw=category,
                commodity_raw=row[0],
                specification_raw=spec,
                market_raw=market,
                **prices,
            )
            for market, prices in markets.items()
        ]
    return items, (columns, layout), category


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    result: list[tuple[int, Item]] = []
    header = category = None
    for number, page in pages:
        for table in page.extract_tables():
            items, header, category = items_from_table(table, header, category)
            result += [(number, item) for item in items]
    return result
