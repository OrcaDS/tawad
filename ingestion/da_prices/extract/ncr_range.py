"""NCR price range pages (Jan 2025 → now): low, high, [prevailing,] average per commodity.

Each page holds two tables side by side, each under a header ``COMMODITIES LOW HIGH
[PREVAILING] AVERAGE`` (``PREVALING`` in some; prevailing appears in Feb 2025), and a table can
start again lower down with a new header. pdfplumber's table cells are unusable here (the two
tables run into each other), so the page is read from words built from its characters
(``layout.py``):

- Every header starts a block that runs down to the next header of the same table, or to the
  footnote (``Markets Covered``). Price columns are matched to the nearest header word.
- A row is a cluster of price words at about the same height. Names are centred in their
  cells and often wrap, so each name line joins the nearest row.
- An ALL-CAPS name line with no prices is a sub-heading (``IMPORTED COMMERCIAL RICE``) and
  becomes the category of the rows below it. The labels spanning several rows in the far-left
  column (``RICE (per kg)``) can't be tied to rows reliably and are not kept; silver takes
  categories from ``commodity_map.csv``.
- The range separator (``160.00-`` or a lone ``-`` between LOW and HIGH) is dropped. One
  value centred across LOW and HIGH is a merged cell (low = high) and fills both.
- A row that gets two values for one column is two rows run together: ``RowMerge`` is
  raised (the report fails with that reason) rather than guessing which price is whose.

The Dec 2022 - Dec 2024 posters (panels of ``name  low-high`` with no column headers) are not
read yet: those pages raise ``Unsupported``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace

from pdfplumber.page import Page

from ingestion.da_prices.extract import layout
from ingestion.da_prices.extract.items import Item, Unsupported
from ingestion.da_prices.extract.layout import Char

FIELDS = {
    "LOW": "price_low_raw",
    "HIGH": "price_high_raw",
    "PREVAILING": "price_prevailing_raw",
    "PREVALING": "price_prevailing_raw",
    "AVERAGE": "price_average_raw",
}


class RowMerge(ValueError):
    """Two rows' prices fell into one row: never guess which price belongs to which item."""


BOTH = "low_and_high"
ROW_GAP = 5.0  # price words of one row differ in height by less than this
_FOOTER = re.compile(r"^(markets covered|source:|note)", re.IGNORECASE)
_KEYWORDS = re.compile("|".join(FIELDS))


def _split_glued(word: Char) -> list[Char]:
    """``HIGHPREVALING`` (Nov 2025) as two header words, placed in proportion to their length."""
    parts = _KEYWORDS.findall(word.text)
    if len(parts) < 2 or "".join(parts) != word.text:
        return [word]
    width = (word.x1 - word.x0) / len(word.text)
    result, x = [], word.x0
    for part in parts:
        result.append(replace(word, text=part, x0=x, x1=x + width * len(part)))
        x += width * len(part)
    return result


@dataclass(frozen=True)
class Header:
    top: float
    x0: float  # of the COMMODITIES word
    columns: dict[str, Char]  # field -> its header word

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.columns.values())


def _headers(words: Sequence[Char]) -> list[Header]:
    headers = []
    for word in words:
        if word.text != "COMMODITIES":
            continue
        # header words on this line (PREVALING sits a point above in some files), up to the
        # next COMMODITIES to the right
        right = min(
            (
                w.x0
                for w in words
                if w.text == "COMMODITIES" and abs(w.top - word.top) < 3 and w.x0 > word.x0
            ),
            default=float("inf"),
        )
        found = [
            part
            for w in words
            if abs(w.top - word.top) < 3 and word.x1 < w.x0 < right
            for part in _split_glued(w)
            if part.text in FIELDS
        ]
        columns = {FIELDS[w.text]: w for w in sorted(found, key=lambda w: w.x0)}
        if "price_low_raw" in columns and "price_high_raw" in columns:
            headers.append(Header(word.top, word.x0, columns))
    return headers


def _footer_top(words: Sequence[Char], page_bottom: float) -> float:
    starts = [
        line[0].top
        for line in layout.lines(list(words))
        if _FOOTER.match(" ".join(w.text for w in line))
    ]
    return min(starts, default=page_bottom)


def _bands(words: Sequence[Char]) -> list[list[Char]]:
    """Words grouped by height: a band continues while the next word is within ``ROW_GAP``."""
    bands: list[list[Char]] = []
    for word in sorted(words, key=lambda w: w.top):
        if bands and word.top - bands[-1][-1].top < ROW_GAP:
            bands[-1].append(word)
        else:
            bands.append([word])
    return bands


def _join_not_available(words: Sequence[Char]) -> list[Char]:
    """``NOT`` and ``AVAILABLE`` are two words that can land in two columns: make them one."""
    result: list[Char] = []
    for band in _bands(words):
        line: list[Char] = []
        for word in sorted(band, key=lambda w: w.x0):
            if word.text == "AVAILABLE" and line and line[-1].text == "NOT":
                line[-1] = replace(line[-1], text="NOT AVAILABLE", x1=word.x1)
            else:
                line.append(word)
        result += line
    return result


def _is_heading(band: Sequence[Char]) -> bool:
    text = " ".join(w.text for w in band)
    return text.isupper() and not re.search(r"\d", text)


def _name_left(words: Sequence[Char], low: Char) -> float:
    """Names are left-aligned: the commonest start left of the LOW column is the name column.
    Anything further left is a category label spanning several rows."""
    starts = Counter(round(w.x0) for w in words if w.x1 < low.x0 - 5)
    return starts.most_common(1)[0][0] - 2 if starts else 0.0


def items_from_page(number: int, chars: Sequence[Char], page_bottom: float) -> list[Item]:
    words = layout.words(chars)
    headers = _headers(words)
    if not headers:
        raise Unsupported(f"no LOW/HIGH header on page {number}")
    words = _join_not_available(words)
    # tables side by side: a new table starts where a header starts right of the last one's end
    tables: list[list[Header]] = []
    for header in sorted(headers, key=lambda h: h.x0):
        if tables and header.x0 < max(h.x1 for h in tables[-1]):
            tables[-1].append(header)
        else:
            tables.append([header])
    footer = _footer_top(words, page_bottom)
    items: list[Item] = []
    for i, table in enumerate(tables):
        left = max(h.x1 for h in tables[i - 1]) + 10 if i else 0.0
        right = max(h.x1 for h in table) + 10 if i < len(tables) - 1 else float("inf")
        blocks = sorted(table, key=lambda h: h.top)
        body = [w for w in words if blocks[0].top + 3 < w.top < footer and left <= w.x < right]
        name_left = _name_left(body, blocks[0].columns["price_low_raw"])
        for j, header in enumerate(blocks):
            bottom = blocks[j + 1].top - 1 if j + 1 < len(blocks) else footer
            inside = [w for w in body if header.top + 3 < w.top < bottom and w.x0 >= name_left]
            items += _block(header, inside)
    return items


def _block(header: Header, words: Sequence[Char]) -> list[Item]:
    layout_name = " | ".join(["COMMODITIES", *(w.text for w in header.columns.values())])
    low, high = header.columns["price_low_raw"], header.columns["price_high_raw"]
    names: list[Char] = []
    prices: dict[int, str] = {}  # id of the price word -> its field
    for word in words:
        if word.x1 < low.x0 - 5:
            names.append(word)
        elif word.text != "-":  # the range separator
            prices[id(word)] = min(header.columns, key=lambda f: abs(header.columns[f].x - word.x))
    rows = _bands([w for w in words if id(w) in prices])
    for row in rows:
        ends = [w for w in row if prices[id(w)] in ("price_low_raw", "price_high_raw")]
        if len(ends) == 1 and low.x < ends[0].x < high.x:
            prices[id(ends[0])] = BOTH  # one value centred across LOW and HIGH: low = high
    centres = [sum(w.top for w in row) / len(row) for row in rows]
    row_names: list[list[list[Char]]] = [[] for _ in rows]  # per row, its name bands
    headings: list[tuple[float, str]] = []
    for band in _bands(names):
        top = sum(w.top for w in band) / len(band)
        nearest = min(range(len(rows)), key=lambda k: abs(centres[k] - top), default=None)
        if _is_heading(band) and (nearest is None or abs(centres[nearest] - top) > ROW_GAP):
            headings.append((top, " ".join(w.text for w in sorted(band, key=lambda w: w.x0))))
        elif nearest is not None:
            row_names[nearest].append(band)
    items = []
    for row, centre, bands in zip(rows, centres, row_names, strict=True):
        fields = {}
        for word in row:
            field, text = prices[id(word)], word.text
            if field == "price_low_raw" and text.endswith("-") and text != "-":
                text = text[:-1]  # "160.00-": the separator is glued to the low price
            for name in ("price_low_raw", "price_high_raw") if field == BOTH else (field,):
                if name in fields:
                    raise RowMerge(f"two {name} values in one row: {fields[name]!r}, {text!r}")
                fields[name] = text
        name = "\n".join(" ".join(w.text for w in sorted(b, key=lambda w: w.x0)) for b in bands)
        above = [text for top, text in headings if top < centre]
        items.append(
            Item(
                layout=layout_name,
                commodity_raw=name or None,
                category_header_raw=above[-1] if above else None,
                **fields,
            )
        )
    return items


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return [
        (number, item)
        for number, page in pages
        for item in items_from_page(number, layout.page_chars(page), page.height)
    ]
