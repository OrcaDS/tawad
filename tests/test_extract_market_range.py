"""Tests for the per-market extractor. Positions follow real 2024-2026 pages."""

import pytest

from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.layout import Table
from ingestion.da_prices.extract.market_range import items_from_page
from tests.test_extract_layout import chars

# MARKET, then one column per commodity (cell boxes from May 13, 2024)
HEADER = ["MARKET", "Pechay Baguio", "Red Onion (Local)", "Sugar (Washed)"]
BOXES = [
    (45.9, 88, 121.2, 101),
    (499.9, 88, 534.2, 101),
    (534.2, 88, 572.6, 101),
    (572.6, 88, 608.5, 101),
]


def table(header=HEADER, boxes=BOXES) -> Table:
    return Table(
        (45.9, 80, 608.5, 377), [[None] * len(header), boxes], [["COMMODITY (PHP/KG)"], header]
    )


def rows(page_chars, tables=None):
    return [
        (i.market_raw, i.commodity_raw, i.price_low_raw, i.price_high_raw, i.price_prevailing_raw)
        for i in items_from_page(2, page_chars, tables or [table()])
    ]


def test_cells_are_cut_at_the_column_edges_not_where_pdfplumber_glues_words() -> None:
    line = (
        chars("Pritil Market/Manila", 46.9, 120)
        + chars("70.00 -100.00", 502.5, 120)
        + chars("100.00 - 120.00", 535.1, 120)  # touches the cell before it
        + chars("70.00 -80.00", 575.5, 120)
    )
    assert rows(line) == [
        ("Pritil Market/Manila", "Pechay Baguio", "70.00", "100.00", None),
        ("Pritil Market/Manila", "Red Onion (Local)", "100.00", "120.00", None),
        ("Pritil Market/Manila", "Sugar (Washed)", "70.00", "80.00", None),
    ]
    (item,) = items_from_page(
        2, chars("Bicutan Market", 46.9, 120) + chars("52.00", 502, 120), [table()]
    )
    assert item.layout == "COMMODITY (PHP/KG) | MARKET"


def test_single_values_ranges_without_a_dash_and_text_stay_raw() -> None:
    line = (
        chars("Agora Public Market/San Juan", 46.9, 120)
        + chars("120.00", 503, 120)  # 2026: one prevailing price
        + chars("360.00 360.00", 536, 120)  # DA left out the dash
        + chars("NOT AVAILABKE", 575, 120)  # DA's typo, kept
    )
    assert rows(line) == [
        ("Agora Public Market/San Juan", "Pechay Baguio", None, None, "120.00"),
        ("Agora Public Market/San Juan", "Red Onion (Local)", "360.00", "360.00", None),
        ("Agora Public Market/San Juan", "Sugar (Washed)", None, None, "NOT AVAILABKE"),
    ]


def test_wrapped_cells_join_the_nearest_market_line() -> None:
    page = (
        chars("NOT", 503, 113)  # wrapped above the market's line
        + chars("Paco Market", 46.9, 120)
        + chars("AVAILABLE", 503, 127)
        + chars("Pasay City Market", 46.9, 140)
        + chars("85.00", 575, 140)
    )
    assert rows(page) == [
        ("Paco Market", "Pechay Baguio", None, None, "NOT AVAILABLE"),
        ("Pasay City Market", "Sugar (Washed)", None, None, "85.00"),
    ]


def test_header_after_an_empty_column_and_footer_inside_the_table() -> None:
    header, boxes = [None, *HEADER], [(30, 88, 45.9, 101), *BOXES]
    page = chars("Bicutan Market", 46.9, 120) + chars("52.00", 503, 120)
    page += chars("Source: DA Agribusiness and Marketing Assistance Service", 46.9, 300)
    assert rows(page, [table(header, boxes)]) == [
        ("Bicutan Market", "Pechay Baguio", None, None, "52.00")
    ]


def test_2022_header_naming_several_commodities_in_one_cell_waits() -> None:
    merged = (
        "Pechay Red Onion Sugar\n*Egg (Medium) Ampalaya Tomato Cabbage\nBaguio (Local) (Washed)"
    )
    with pytest.raises(Unsupported):
        items_from_page(2, [], [table([*HEADER[:3], merged])])


def test_tables_without_a_market_header_give_nothing() -> None:
    title_box = Table((0, 0, 9, 9), [[None]], [[""]])
    page = chars("Bicutan Market", 46.9, 120) + chars("52.00", 503, 120)
    assert len(items_from_page(2, page, [title_box, table()])) == 1
    with pytest.raises(Unsupported):  # late 2021: a poster, no MARKET header anywhere
        items_from_page(2, page, [title_box])
