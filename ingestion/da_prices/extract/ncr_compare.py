"""NCR prevailing prices, today against the last report (Sep 2021 → Dec 2022): posters.

"Prevailing Retail Prices of Selected Agri-fishery Commodities at NCR Markets": panels of
``name  today  yesterday`` (or last Friday, last week, previous monitoring), as on the
2023-2024 NCR posters but with two prevailing prices where those have low and high. So
``ncr_range``'s poster reader does the reading, after three changes to the page:

- Pages come 792 to 1257 pt wide; positions are scaled to 792 so one set of distances fits.
- The legend box (``Legend: TODAY'S PREVAILING PRICE …`` and the two dates under it) and the
  column labels over each panel (``Today Yesterday``, ``Today Last Friday``) are dropped, or
  they would read as headings.
- ``NOT`` over ``AVAILABLE`` (two lines in one cell) becomes one word at the cell's middle
  height, beside the other column's price.

Only today's price is kept, in ``price_prevailing_raw``: the other is the earlier report's
own price. A lone price is today's.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pdfplumber.page import Page

from ingestion.da_prices.extract import layout, ncr_range
from ingestion.da_prices.extract.items import Item, Unsupported
from ingestion.da_prices.extract.layout import Char

LAYOUT = "compare"  # poster rows have no header cells
WIDTH = 792.0  # positions are scaled to this page width
GROUP_GAP = 35.0  # today and yesterday sit up to ~30 pt apart; panels further
LEGEND_HEIGHT = 15.0  # the legend line and the dates under it
STACK_GAP = 14.0  # AVAILABLE sits ~10 pt below its NOT
# "Today", "Last Friday", "This Monday", "Previous Monitoring", glued "TodayPrevious"
_LABEL = re.compile(
    r"^(?:Today|Yesterday|Last|This|Previous|Monitoring|Week|"
    r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day)+$",
    re.IGNORECASE,
)


def _stack_not_available(words: Sequence[Char]) -> list[Char]:
    used: set[int] = set()
    result = []
    for word in words:
        if word.text == "NOT":
            below = next(
                (
                    w
                    for w in words
                    if w.text.startswith("AVA")
                    and 3 <= w.top - word.top < STACK_GAP
                    and w.x0 < word.x1
                    and word.x0 < w.x1
                ),
                None,
            )
            if below is not None:
                used.add(id(below))
                word = Char(
                    f"NOT {below.text}",
                    word.x0,
                    max(word.x1, below.x1),
                    (word.top + below.top) / 2,
                    below.bottom,
                )
        result.append(word)
    return [w for w in result if id(w) not in used]


def items_from_page(number: int, chars: Sequence[Char], width: float, height: float) -> list[Item]:
    k = WIDTH / width
    words = layout.words([Char(c.text, c.x0 * k, c.x1 * k, c.top * k, c.bottom * k) for c in chars])
    legend = next((w for w in words if w.text == "Legend:"), None)
    if legend is None:
        raise Unsupported(f"no legend on page {number}")
    words = [
        w
        for w in words
        if not _LABEL.match(w.text)
        and not (w.x0 >= legend.x0 - 5 and legend.top - 3 <= w.top <= legend.top + LEGEND_HEIGHT)
    ]
    words = _stack_not_available(words)
    footer = ncr_range._footer_top(words, height * k)
    return [
        Item(
            layout=LAYOUT,
            commodity_raw=item.commodity_raw,
            category_header_raw=item.category_header_raw,
            # shortcut: a lone price counts as today's (true of all 16 in 2021-2022: a panel
            # with no yesterday column, and DA's overprinted cells); check positions if not
            price_prevailing_raw=item.price_low_raw,
        )
        for item in ncr_range._poster(number, words, footer, GROUP_GAP)
    ]


def extract(pages: Sequence[tuple[int, Page]]) -> list[tuple[int, Item]]:
    return [
        (number, item)
        for number, page in pages
        for item in items_from_page(number, layout.page_chars(page), page.width, page.height)
    ]
