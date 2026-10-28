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

The Dec 2022 → Jan 15, 2025 pages are posters instead: panels of ``name  low - high`` with no
column headers (``_poster``):

- A price group is the prices on one line close together (``low``, ``-``, ``high``; or one
  value, or ``NOT AVAILABLE``, for low = high). Group starts line up into the page's price
  columns, and every word belongs to the column whose prices end right of it.
- Within a column, each name line joins the nearest price group within ``REACH`` (names wrap
  above and below their price). Lines that join none are panel titles and sub-headings
  (``IMPORTED COMMERCIAL RICE``, ``Feed Grade``); lines less than ``CHAIN`` apart are one
  heading. A heading is the category of the rows below it until the next heading or a gap
  wider than ``PANEL_GAP``: a panel can share a price column with one whose heading sits in
  another column (2024: the eggs below CORN), and its rows get no category rather than a
  wrong one.
- The report title and date above the panels, and the footnote, are not read.
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
        return _poster(number, words, _footer_top(words, page_bottom))
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


POSTER = "poster"  # the layout of poster rows: they have no header cells
REACH = 10.0  # a name line sits at most this far above or below its price group
GROUP_GAP = 25.0  # the prices of one group are closer than this; columns are further apart
COLUMN_GAP = 30.0  # the starts of one column's price groups differ by less than this
CHAIN = 15.0  # heading lines closer than this are one heading ("FRUITS" / "(per kg)": 13.2)
PANEL_GAP = 29.0  # rows of one panel are at most ~27 pt apart; a wider gap starts a new panel
SEPARATOR_REACH = 10.0  # a range separator sits at most this far outside its group's prices
# footnote marks around prices stay in the raw text: "250.00*", "**35.00", "100*", "90.00g"
_POSTER_PRICE = re.compile(r"^\**(\d{1,3}(,\d{3})*\.\d{1,2}|\d{1,3}(?=\*))\**[a-j]?$")
_CONTACT = re.compile(r"@|^loc\.$|^\(02\)$|^\d{3,4}-\d{4}$|^Floor,$|^Elliptical$|Diliman")
_WEEKDAY = re.compile(r"(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b")


def _is_price(word: Char) -> bool:
    return word.text.startswith("NOT AVA") or bool(_POSTER_PRICE.match(word.text))  # AVALABLE


def _same_height(a: Char, b: Char) -> bool:
    return abs(a.top - b.top) < layout.LINE_GAP


def _join_not_available_pairs(words: Sequence[Char]) -> list[Char]:
    """``NOT`` + ``AVAILABLE`` side by side as one word. Posters stack rows too tightly for
    ``_join_not_available``'s bands: two rows' NOTs would pair with one AVAILABLE."""
    used: set[int] = set()
    result = []
    for word in words:
        if word.text == "NOT":
            after = next(
                (
                    w
                    for w in words
                    if w.text.startswith("AVA") and _same_height(w, word) and 0 < w.x0 - word.x1 < 5
                ),
                None,
            )
            if after is not None:
                used.add(id(after))
                word = replace(word, text=f"NOT {after.text}", x1=after.x1)
        result.append(word)
    return [w for w in result if id(w) not in used]


def _groups(words: Sequence[Char], gap: float) -> list[list[Char]]:
    """Price groups: prices side by side at about the same height. Not by line: a high price
    can sit a little lower than its low and fall into another line."""
    groups: list[list[Char]] = []
    for word in sorted((w for w in words if _is_price(w)), key=lambda w: w.x0):
        group = next(
            (g for g in groups if _same_height(g[-1], word) and 0 <= word.x0 - g[-1].x1 < gap),
            None,
        )
        if group is None:
            groups.append([word])
        else:
            group.append(word)
    return groups


def _separates(dash: Char, group: Sequence[Char]) -> bool:
    """A ``-`` between, or just before or after, a group's prices is the range separator."""
    return (
        abs(dash.top - group[0].top) < ROW_GAP
        and group[0].x0 - SEPARATOR_REACH <= dash.x0
        and dash.x1 <= group[-1].x1 + SEPARATOR_REACH
    )


def _contact(words: Sequence[Char]) -> set[int]:
    """DA's contact block (phone, email, address) at the top right: not part of any panel."""
    found = [w for w in words if _CONTACT.search(w.text)]
    if not found:
        return set()
    left = min(w.x0 for w in found) - 15  # the "-" bullets in front of each line
    top, bottom = min(w.top for w in found) - 3, max(w.top for w in found) + 3
    return {id(w) for w in words if w.x0 >= left and top <= w.top <= bottom}


def _text(line: Sequence[Char]) -> str:
    return " ".join(w.text for w in sorted(line, key=lambda w: w.x0))


def _poster(
    number: int, words: Sequence[Char], footer: float, group_gap: float = GROUP_GAP
) -> list[Item]:
    date = min((w.top for w in words if _WEEKDAY.match(w.text)), default=0.0)
    body = _join_not_available_pairs([w for w in words if date + 3 < w.top < footer])
    contact = _contact(body)
    body = [w for w in body if id(w) not in contact]
    groups = _groups(body, group_gap)
    if not groups:
        raise Unsupported(f"no LOW/HIGH header or price groups on page {number}")
    # columns: price group starts that line up, each ending at its rightmost price
    columns: list[list[list[Char]]] = []
    for group in sorted(groups, key=lambda g: g[0].x0):
        if columns and group[0].x0 - columns[-1][-1][0].x0 < COLUMN_GAP:
            columns[-1].append(group)
        else:
            columns.append([group])
    rights = [max(w.x1 for g in column for w in g) for column in columns]
    in_group = {id(w) for g in groups for w in g}
    in_group |= {id(w) for w in body if w.text == "-" for g in groups if _separates(w, g)}
    items: list[Item] = []
    for k, column in enumerate(columns):
        left = rights[k - 1] if k else float("-inf")
        right = rights[k]  # names sit left of their prices
        rows = sorted(column, key=lambda g: g[0].top)
        tops = [min(w.top for w in g) for g in rows]
        names: list[list[str]] = [[] for _ in rows]
        headings: list[tuple[float, float, list[str]]] = []  # top, bottom, lines
        other = [w for w in body if left < w.x <= right and id(w) not in in_group]
        for line in layout.lines(other):
            line = [w for w in line if w.text != "-" or len(line) > 1]  # a stray separator
            if not line:
                continue
            top = min(w.top for w in line)
            near = min(range(len(rows)), key=lambda i: abs(tops[i] - top))
            gap = abs(tops[near] - top)
            if gap <= REACH and not (_is_heading(line) and gap > ROW_GAP):
                names[near].append(_text(line))
            elif headings and top - headings[-1][1] < CHAIN:
                headings[-1][2].append(_text(line))
                headings[-1] = (headings[-1][0], top, headings[-1][2])
            else:
                headings.append((top, top, [_text(line)]))
        category, previous = None, float("-inf")
        for group, top, name in zip(rows, tops, names, strict=True):
            if len(group) > 2:
                raise RowMerge(f"{len(group)} prices in one group on page {number}")
            between = [lines for start, _, lines in headings if previous < start < top]
            if between:
                category = "\n".join(between[-1])
            elif top - previous > PANEL_GAP:
                category = None  # a new panel whose heading is in another column
            previous = top
            items.append(
                Item(
                    layout=POSTER,
                    commodity_raw="\n".join(name) or None,
                    category_header_raw=category,
                    price_low_raw=group[0].text,
                    price_high_raw=group[-1].text,
                )
            )
    return items


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return [
        (number, item)
        for number, page in pages
        for item in items_from_page(number, layout.page_chars(page), page.height)
    ]
