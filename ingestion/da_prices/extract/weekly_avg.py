"""Weekly Average Retail Price pages (2023-08 → now): one NCR-wide weekly average per item.

Only the first page has the header ``COMMODITY | SPECIFICATION | UNIT | WEEKLY AVERAGE PRICE``,
preceded by an empty cell. Later tables (the rest of a page, the next pages) have no header and
either keep that empty first cell or drop it, so they are read with the last header's columns,
aligned from the right. Category rows (``IMPORTED COMMERCIAL RICE``, ``BEEF PRODUCTS``, …) have
one ALL-CAPS cell and are carried into the rows below. Cells are kept exactly as read: ``-``
means not sold and ``n/a`` not available.
"""

from __future__ import annotations

from collections.abc import Sequence

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract.items import Item

Row = Sequence[str | None]

PRICE = "price_average_raw"
_FIELDS = (
    ("commodity", "commodity_raw"),
    ("specification", "specification_raw"),
    ("unit", "unit_raw"),
    ("price", PRICE),
)


def _field(cell: str | None) -> str | None:
    text = (cell or "").lower()
    return next((field for word, field in _FIELDS if word in text), None)


def _is_header(row: Row) -> bool:
    fields = {_field(cell) for cell in row}
    return "commodity_raw" in fields and PRICE in fields


def items_from_pages(
    pages: Sequence[tuple[int, Sequence[Sequence[Row]]]],
) -> list[tuple[int, Item]]:
    """``(page, item)`` rows from each page's ``extract_tables()``, in order.

    Tables before the first header (blank title boxes) are ignored.
    """
    result: list[tuple[int, Item]] = []
    header: Row | None = None
    layout = ""
    category: str | None = None
    for number, tables in pages:
        for table in tables:
            for row in table:
                if _is_header(row):
                    header = row
                    layout = " | ".join(normalize(cell) for cell in row if cell)
                    continue
                if header is None:
                    continue
                offset = len(header) - len(row)  # continuation tables may drop the first cell
                fields = {
                    field: row[i - offset]
                    for i, cell in enumerate(header)
                    if (field := _field(cell)) and 0 <= i - offset < len(row)
                }
                # the unlabeled first cell is ignored (DA left a stray "x" in it twice)
                texts = [text for text in fields.values() if text and text.strip()]
                if not texts:
                    continue
                if texts == [fields.get("commodity_raw")] and texts[0].isupper():
                    category = texts[0]
                    continue
                result.append((number, Item(layout=layout, category_header_raw=category, **fields)))
    return result


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return items_from_pages([(number, page.extract_tables()) for number, page in pages])
