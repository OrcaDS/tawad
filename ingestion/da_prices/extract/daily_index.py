"""Daily Price Index pages (2025-04 → now): one NCR-wide prevailing price per item.

Columns are ``COMMODITY | SPECIFICATION | [UNIT |] PREVAILING RETAIL PRICE …``, mapped by header
text. In 2025 pdfplumber splits each column into several cells, and text can sit in any of
them, so a column is every cell from its header to the next header. Mid-2025 files also number
rows (``1``, ``2`` …) and letter categories (``A``, ``B`` …) in cells of their own; those
labels are dropped. Category rows (``IMPORTED COMMERCIAL RICE``, ``PORK MEAT PRODUCTS``, …)
have one ALL-CAPS cell and no price, sometimes wrapped over two rows; they are carried into
the rows below, because imported vs local rice is told apart only there. Cells are otherwise
kept exactly as read (``n/a`` included).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract.items import Item

Row = Sequence[str | None]

_LABEL = re.compile(r"^(\d+|[A-Z])$")  # row number or category letter
PRICE = "price_prevailing_raw"


def _field(header_cell: str) -> str | None:
    text = header_cell.lower()
    if "price" in text:  # before "unit": the price header says "PRICE PER UNIT"
        return PRICE
    for word, field in (
        ("commodity", "commodity_raw"),
        ("specification", "specification_raw"),
        ("unit", "unit_raw"),
    ):
        if word in text:
            return field
    return None


def _columns(header: Row) -> dict[str, range]:
    """Each field's span of cells: from its header cell to the next header cell."""
    starts = [(i, f) for i, cell in enumerate(header) if cell and (f := _field(cell))]
    if not starts:
        return {}
    if starts[0][1] == "specification_raw" and not (header[0] or "").strip():
        starts.insert(0, (0, "commodity_raw"))  # July 2025 left the COMMODITY header blank
    ends = [i for i, _ in starts[1:]] + [len(header)]
    columns: dict[str, range] = {}
    for (start, field), end in zip(starts, ends, strict=True):
        columns.setdefault(field, range(start, end))
    return columns


def _is_header(row: Row) -> bool:
    columns = _columns(row)
    return "commodity_raw" in columns and PRICE in columns


def _texts(cells: Sequence[str | None]) -> list[str]:
    return [cell for cell in cells if cell and cell.strip() and not _LABEL.match(cell.strip())]


def _cell(row: Row, span: range) -> str | None:
    """The span's text; its first cell as-is (None or "") when the span is empty."""
    texts = _texts([row[i] for i in span if i < len(row)])
    return "\n".join(texts) if texts else (row[span.start] if span.start < len(row) else None)


def _join(item: Item, fields: dict[str, str | None]) -> Item:
    """Append a wrapped row's text to the item it continues."""
    joined = {
        field: "\n".join(filter(None, [getattr(item, field), text]))
        for field, text in fields.items()
        if _texts([text])
    }
    return replace(item, **joined)


def items_from_pages(
    pages: Sequence[tuple[int, Sequence[Sequence[Row]]]],
) -> list[tuple[int, Item]]:
    """``(page, item)`` rows from each page's ``extract_tables()``, in order.

    Tables without a header row (header fragments) are ignored. The category and wrapped text
    carry over page breaks.
    """
    result: list[tuple[int, Item]] = []
    category: str | None = None
    for number, tables in pages:
        for table in tables:
            start = next((i for i, row in enumerate(table) if _is_header(row)), None)
            if start is None:
                continue
            header = table[start]
            columns = _columns(header)
            layout = " | ".join(normalize(cell) for cell in header if cell)
            after_category = in_body = False
            for row in table[start + 1 :]:
                texts = _texts(row)
                if not texts:
                    continue
                fields = {field: _cell(row, span) for field, span in columns.items()}
                priced = bool(_texts([fields[PRICE]]))
                if (
                    not in_body
                    and texts == _texts([fields[PRICE]])
                    and not re.search(r"\d", texts[0])
                ):
                    layout += " " + normalize(texts[0])  # header wrapped onto a second row
                    continue
                in_body = True
                if len(texts) == 1 and not priced and texts[0].isupper():
                    category = f"{category}\n{texts[0]}" if after_category else texts[0]
                    after_category = True
                    continue
                after_category = False
                if not priced and result:  # DPI writes missing prices as n/a: this row wraps
                    result[-1] = (result[-1][0], _join(result[-1][1], fields))
                    continue
                result.append((number, Item(layout=layout, category_header_raw=category, **fields)))
    return result


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return items_from_pages([(number, page.extract_tables()) for number, page in pages])
