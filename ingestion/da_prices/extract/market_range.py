"""Per-market price pages (Sep 2021 → now): markets down the side, commodities across the top.

The header row starts with ``MARKET`` and names one commodity per column; the row above it
says ``COMMODITY (PHP/KG)``. pdfplumber's table cells can't be trusted below the header:
rows often lose their borders and land in one cell, sometimes two markets in one. So only the
header comes from the table: each commodity's column runs from its header cell to the next.
The rows come from the characters under the header, grouped into lines by height and put in
a column by their horizontal centre (``layout.py`` says why characters, not words). A line
with no market name holds the wrapped half of some cells (``NOT`` / ``AVAILABLE``) and joins
the nearest market's line; a ``Source:`` or ``Note:`` line ends the table.

Until 2025 the cells are ranges (``40.00 -44.00``, or one value when low and high agree);
later ones hold a single prevailing price. A ``low - high`` cell is split into the low and
high fields; anything else (a single price, ``NOT AVAILABLE``) goes to the prevailing field.
Both halves stay raw text.

The 2021-2022 grids hold single prices, and pdfplumber finds so few column lines that one
header cell names several commodities; ``market_grid.py`` rebuilds that header from word
positions. A ``NO MONITORING ACTIVITY CONDUCTED`` note across a row stands for every column.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pdfplumber.page import Page

from ingestion.da_prices.classify import normalize
from ingestion.da_prices.extract import layout, market_grid
from ingestion.da_prices.extract.items import Item, Unsupported
from ingestion.da_prices.extract.layout import Char, Table

# "40.00 -44.00", "##### - 120.00", and "360.00 360.00" where DA left out the dash; not "(-)"
# (a market closed for disinfection, 2021-2022)
_RANGE = re.compile(r"^(?!\(-\)$)(\S+?)\s*-\s*(\S+)$|^([\d.,]+) ([\d.,]+)$")
_FOOTER = re.compile(r"^(source|notes?)\b", re.IGNORECASE)
_WHOLE_ROW = re.compile(r"^no monitoring\b", re.IGNORECASE)  # 2021-2022 grids
# The longest real header is "PREMIUM RICE (Imported, 5% broken)"; the 2021-2022 grids put
# 8 to 12 words (several commodities) in one cell
MAX_NAME_WORDS = 6


def first(row: Sequence[str | None]) -> str:
    """The row's first non-empty cell (some tables start with an empty column)."""
    return next((normalize(cell) for cell in row if cell and cell.strip()), "")


def is_header(row: Sequence[str | None]) -> bool:
    """The ``MARKET`` header row (``MARKET*`` on a few 2022 pages)."""
    return first(row).rstrip("*") == "MARKET"


def _price(text: str) -> dict[str, str]:
    if match := _RANGE.match(text):
        low, high = (match[1], match[2]) if match[1] else (match[3], match[4])
        return {"price_low_raw": low, "price_high_raw": high}
    return {"price_prevailing_raw": text}


def items_from_page(number: int, chars: Sequence[Char], tables: Sequence[Table]) -> list[Item]:
    """One item per market and commodity on one page. Tables without a MARKET header give
    nothing; a page with none at all (the late-2021 posters) raises ``Unsupported``."""
    if not any(is_header(row) for table in tables for row in table.text):
        raise Unsupported(f"no MARKET header on page {number}")
    items: list[Item] = []
    for table in tables:
        start = next((i for i, row in enumerate(table.text) if is_header(row)), None)
        if start is None:
            continue
        if any(len((name or "").split()) > MAX_NAME_WORDS for name in table.text[start]):
            table, start = market_grid.header_table(number, chars, table), 1
        header, boxes = table.text[start], table.cells[start]
        starts = [
            (box[0], name)
            for name, box in zip(header, boxes, strict=True)
            if name and name.strip() and box and normalize(name).rstrip("*") != "MARKET"
        ]
        if any(len(name.split()) > MAX_NAME_WORDS for _, name in starts):
            raise Unsupported(f"several commodities in one header cell on page {number}")
        edges = [x0 for x0, _ in starts[1:]] + [table.bbox[2]]
        columns = [(name, x0, x1) for (x0, name), x1 in zip(starts, edges, strict=True)]
        above = [normalize(c) for c in table.text[start - 1] if c] if start else []
        layout_text = " | ".join([*above, "MARKET"])
        top = max(box[3] for box in boxes if box)
        x0, _, x1, bottom = table.bbox
        body = [c for c in chars if top <= c.top < bottom and x0 <= c.x < x1]
        # (top, market, cell text per column) per line; a line without a market name holds the
        # wrapped second line of some cells ("NOT" / "AVAILABLE") and joins the nearest market
        lines = []
        for line in layout.lines(body):
            market = layout.text([c for c in line if c.x < columns[0][1]])
            if _FOOTER.match(market):
                break
            cells = [
                layout.text([c for c in line if left <= c.x < right]) for _, left, right in columns
            ]
            whole = layout.text([c for c in line if c.x >= columns[0][1]])
            if _WHOLE_ROW.match(whole):  # one note across the row stands for every column
                cells = [whole] * len(columns)
            lines.append((line[0].top, market, cells))
        rows = [(t, m, list(cells)) for t, m, cells in lines if m]
        for t, market, cells in lines:
            if market or not rows:
                continue
            row_top, _, target = min(rows, key=lambda row: abs(row[0] - t))
            for k, cell in enumerate(cells):
                if cell:
                    parts = [cell, target[k]] if t < row_top else [target[k], cell]
                    target[k] = " ".join(p for p in parts if p)
        for _, market, cells in rows:
            items += [
                Item(layout=layout_text, market_raw=market, commodity_raw=name, **_price(cell))
                for (name, _, _), cell in zip(columns, cells, strict=True)
                if cell
            ]
    return items


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return [
        (number, item)
        for number, page in pages
        for item in items_from_page(number, layout.page_chars(page), layout.page_tables(page))
    ]
