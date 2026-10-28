"""Tests for the 2018-2021 NCR summary extractor. Table rows are real pdfplumber output."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.ncr_summary import extract, items_from_table

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"
PRICES = ("price_prevailing_raw", "price_low_raw", "price_high_raw", "price_average_raw")


def rows(items):
    return [
        (i.category_header_raw, i.commodity_raw, i.specification_raw, i.unit_raw)
        + tuple(getattr(i, f) for f in PRICES)
        for i in items
    ]


def test_2019_layout_with_title_row_and_footnote() -> None:
    table = [
        ["DAILY PRICE MONITORING\nPRELIMINARY REPORT as of\nDate : October 14, 2019", *[None] * 5],
        ["COMMODITY", "SPECIFICATION(S)", "Retail price per kilogram (PhP/kg)", None, None, None],
        [None, None, "Prevailing", "Low", "High", "Average"],
        ["NFA RICE", "", "", "", "", ""],
        ["NFA (Well milled)", "kg", "27.00", "27.00", "27.00", "27.00"],
        ["", "", "None", "None", "None", "None"],  # nameless row: kept raw
        ["IMPORTED COMMERCIAL RICE", "", "", "", "", ""],
        ["Regular milled (White tag)", "kg", "N/A", "32.00", "40.00", "36.00"],
        [
            "Markets Covered: Las Piñas, San Andres, Commonwealth, Quinta, Guadalupe, Mega Q\n"
            "Note: #N/A (Not applicable) - Absence of prevailing price although stocks are",
            None,
            "-mart, Muñoz, Pasig & Pasay\nd and prices are monitored in the market",
            None,
            None,
            None,
        ],
    ]
    items, category = items_from_table(table)
    assert rows(items) == [
        ("NFA RICE", "NFA (Well milled)", "kg", None, "27.00", "27.00", "27.00", "27.00"),
        ("NFA RICE", "", "", None, "None", "None", "None", "None"),
        ("IMPORTED COMMERCIAL RICE", "Regular milled (White tag)", "kg", None)
        + ("N/A", "32.00", "40.00", "36.00"),
    ]
    assert category == "IMPORTED COMMERCIAL RICE"
    assert items[0].layout == (
        "COMMODITY | SPECIFICATION(S) | Retail price per kilogram (PhP/kg) | "
        "Prevailing | Low | High | Average"
    )


def test_2021_merged_cells_fill_or_split() -> None:
    table = [
        ["COMMODITY", "SPECIFICATION", "Unit", "Summary", None, None],
        [None, None, None, "High", "Low", "Prevailing"],
        ["NFA (Well milled)", "well milled", "kg", "NOT AVAILABLE", None, None],
        ["Garlic (Native)", "", "kg", "300.00 270.00 300.00", None, None],
        ["Alumahan", "med(4-6pcs/kg)", "kg", "", "340.00", "340.00"],
    ]
    items, category = items_from_table(table, category="FISH")
    assert rows(items) == [
        ("FISH", "NFA (Well milled)", "well milled", "kg")
        + ("NOT AVAILABLE", "NOT AVAILABLE", "NOT AVAILABLE", None),
        ("FISH", "Garlic (Native)", "", "kg", "300.00", "270.00", "300.00", None),
        ("FISH", "Alumahan", "med(4-6pcs/kg)", "kg", "340.00", "340.00", "", None),
    ]


def test_matrix_strip_without_commodity_column_is_unsupported() -> None:
    table = [[None, "Prevailing", "Low", "High", "Average"], ["27.00", "27.00", "27.00", "27.00"]]
    with pytest.raises(Unsupported):
        items_from_table(table)


def test_reads_a_real_2021_page() -> None:
    with pdfplumber.open(FIXTURES / "ncr_summary_2021-07-27_p1.pdf") as pdf:
        items = [item for _, item in extract([(1, pdf.pages[0])])]
    assert len(items) == 50
    garlic = next(i for i in items if i.commodity_raw == "Garlic (Native)")
    assert (garlic.price_high_raw, garlic.price_low_raw, garlic.price_prevailing_raw) == (
        "300.00",
        "270.00",
        "300.00",
    )
    assert items[0].price_low_raw == "NOT AVAILABLE"
    assert {i.category_header_raw for i in items} >= {"IMPORTED COMMERCIAL RICE", "SPICES"}
