"""The header of the 2021-2022 per-market grids, rebuilt from word positions.

These pages look like the later per-market pages (``market_range.py``), but most column lines
are missing, so pdfplumber puts several commodity names in one header cell, and each name
wraps over up to three lines (``Well-milled`` / ``Rice (Local)``, ``Whole`` / ``Chicken``).
The names are centred over their prices. Words of one column overlap or sit at most 2 pt
apart (``Red Onion``); neighbouring columns are 15 pt or more apart. So the header words are
merged into columns by horizontal position, and a new header row with one cell per column
replaces the table's own; ``market_range`` then reads the body as usual.
"""

from __future__ import annotations

from collections.abc import Sequence

from ingestion.da_prices.extract import layout
from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.layout import Char, Table

COLUMN_GAP = 6.0  # header words closer than this belong to one column
# a wrapped "NOT" / "AVAILABLE" cell of the first market can sit level with the header
CELL_WORDS = ("NOT", "AVAILABLE")


def header_table(number: int, chars: Sequence[Char], table: Table) -> Table:
    """``table`` with a ``COMMODITY (PHP/KG)`` row and a ``MARKET`` header row of one cell per
    column, built from the header words between those two labels' line and the first market."""
    x0, top, x1, bottom = table.bbox
    lines = layout.lines(layout.words([c for c in chars if x0 <= c.x < x1 and top <= c.top]))
    texts = [[w.text for w in line] for line in lines]
    above = next((i for i, t in enumerate(texts) if t[:1] == ["COMMODITY"]), None)
    market = next((w for line in lines for w in line if w.text.rstrip("*") == "MARKET"), None)
    if above is None or market is None:
        raise Unsupported(f"no COMMODITY and MARKET labels over the grid on page {number}")
    words: list[tuple[int, Char]] = []  # (line number, word) of the header
    for k, line in enumerate(lines[above + 1 :]):
        if any(w.x0 < market.x0 for w in line):  # a market name: the body starts
            break
        words += [(k, w) for w in line if w is not market and w.text not in CELL_WORDS]
    columns: list[list[tuple[int, Char]]] = []
    for k, word in sorted(words, key=lambda kw: kw[1].x0):
        if columns and word.x0 <= max(w.x1 for _, w in columns[-1]) + COLUMN_GAP:
            columns[-1].append((k, word))
        else:
            columns.append([(k, word)])
    if not columns:
        raise Unsupported(f"no commodity names over the grid on page {number}")
    header_bottom = max(w.bottom for _, w in words)
    names = [
        " ".join(w.text for _, w in sorted(col, key=lambda kw: (kw[0], kw[1].x0)))
        for col in columns
    ]
    spans = [(min(w.x0 for _, w in col), max(w.x1 for _, w in col)) for col in columns]
    # prices can be wider than their name, so a column starts halfway into the gap before it
    # (the first one as far left of its name as the gap after it is wide)
    gaps = [(a[1] + b[0]) / 2 for a, b in zip(spans, spans[1:], strict=False)]
    lefts = [spans[0][0] - (gaps[0] - spans[0][1] if gaps else 0), *gaps]
    boxes = [
        (left, top, right, header_bottom) for left, (_, right) in zip(lefts, spans, strict=True)
    ]
    market_box = (x0, top, lefts[0], header_bottom)
    return Table(
        table.bbox, [[None], [market_box, *boxes]], [["COMMODITY (PHP/KG)"], ["MARKET", *names]]
    )
