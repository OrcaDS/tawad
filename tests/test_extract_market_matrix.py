"""Tests for the 2018-2020 per-market matrix extractor. Table rows are real pdfplumber output."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.market_matrix import extract, items_from_table

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"


def rows(items):
    return [
        (
            i.category_header_raw,
            i.commodity_raw,
            i.market_raw,
            i.price_prevailing_raw,
            i.price_low_raw,
            i.price_high_raw,
            i.price_average_raw,
        )
        for i in items
    ]


# Nov 2019: numbered markets, four columns each, NCR-wide columns last (cut to 2 markets)
NOV_2019 = [
    ["COMMODITY", "SPECIFICATION", "1. Commonwealth", None, None, None]
    + ["2. Guadalupe", None, None, None, "Prevailing", "Low", "High", "Average"],
    [None, None] + ["Prevailing", "Low", "High", "Average"] * 2 + [None] * 4,
    ["NFA RICE", "", "", None, None, None, "", None, None, None, "", None, None, None],
    ["NFA (Well milled)", "kg", "27.00", "27.00", "27.00", "27.00"]
    + ["#N/A", "0.00", "0.00", "#DIV/0!", "27.00", "27.00", "27.00", "27.00"],
]


def test_2019_numbered_markets_and_ncr_columns() -> None:
    items, header, category = items_from_table(NOV_2019)
    assert rows(items) == [
        ("NFA RICE", "NFA (Well milled)", "Commonwealth", "27.00", "27.00", "27.00", "27.00"),
        ("NFA RICE", "NFA (Well milled)", "Guadalupe", "#N/A", "0.00", "0.00", "#DIV/0!"),
        ("NFA RICE", "NFA (Well milled)", None, "27.00", "27.00", "27.00", "27.00"),
    ]
    assert items[0].specification_raw == "kg"
    assert category == "NFA RICE"

    # the next page continues the rows without a header
    page2 = [["Sugar (Brown)", "kg", "5 0.00", "48.00", "50.00", "49.00"] + ["45.00"] * 8]
    more, _, _ = items_from_table(page2, header, category)
    assert rows(more)[0] == (
        "NFA RICE",
        "Sugar (Brown)",
        "Commonwealth",
        "5 0.00",  # digits spaced apart by the PDF: kept as read
        "48.00",
        "50.00",
        "49.00",
    )


def test_2018_garbled_header_words() -> None:
    table = [
        ["Commodity", "Specification\nP", "Marikina Zone", None, None, "Quinta", None, None]
        + ["revailin", "gLow", "High", "Average"],
        [None, None, "Prevaili", "ngLow", "High", "Prevailin", "gLow", "P\nHigh"] + [None] * 4,
        ["RICE"] + [""] * 11,
        ["NFA(premium)", "", "32", "32", "32", "N/A", "0", "0", "32", "32", "32", "32.00"],
    ]
    items, _, _ = items_from_table(table)
    assert rows(items) == [
        ("RICE", "NFA(premium)", "Marikina Zone", "32", "32", "32", None),
        ("RICE", "NFA(premium)", "Quinta", "N/A", "0", "0", None),
        ("RICE", "NFA(premium)", None, "32", "32", "32", "32.00"),
    ]


def test_category_rows_with_leftovers_glued_spec_and_footnote() -> None:
    table = [
        *NOV_2019[:2],
        ["FISH", "", "", None, None, None, "#DIV/0!", None, None, None, "", None, None, None],
        ["Bangus", "med(3-4pcs/kg)", *["190.00"] * 12],
        ["MEAT & POULTRY lean", None, *[""] * 12],  # Feb 2018: Beef Rump's first spec word
        ["Beef Rump", "meat/tapadera", *["320"] * 12],
        ["Markets Covered: Commonwealth, Guadalupe\nNote: #N/A (Not applicable)", None]
        + ["are monitored in the market", *[None] * 11],
    ]
    items, _, category = items_from_table(table)
    assert [(i.category_header_raw, i.commodity_raw, i.specification_raw) for i in items] == [
        ("FISH", "Bangus", "med(3-4pcs/kg)"),
    ] * 3 + [("MEAT & POULTRY", "Beef Rump", "lean\nmeat/tapadera")] * 3
    assert category == "MEAT & POULTRY"


def test_blank_last_column_is_skipped_only_when_empty() -> None:
    table = [row + [extra] for row, extra in zip(NOV_2019, ["", None, None, ""], strict=True)]
    assert len(items_from_table(table)[0]) == 3
    table[-1][-1] = "12.00"
    with pytest.raises(Unsupported):
        items_from_table(table)


def test_glued_market_names_are_unsupported() -> None:
    # Jan 2019: "Mega Q-mart Pasig" is two markets' names in one cell over six columns
    table = [
        ["Commodity", "Specification", "Mega Q-mart Pasig", None, None, None, None, None],
        [None, None] + ["Prevailing", "Low", "High"] * 2,
        ["Fancy", "", "50.00", "49.00", "57.00", "54.00", "50.00", "58.00"],
    ]
    with pytest.raises(Unsupported):
        items_from_table(table)


def test_column_strip_without_names_is_unsupported() -> None:
    table = [
        ["Guadalupe", None, None, "Quinta", None, None],
        [None, "Low", "High", "Prevailing", "Low", "High"],
        ["27", "27.00", "27.00", "#N/A", "0.00", "0.00"],
    ]
    with pytest.raises(Unsupported):
        items_from_table(table)


def test_reads_a_real_2019_page() -> None:
    with pdfplumber.open(FIXTURES / "market_matrix_2019-06-10_p1.pdf") as pdf:
        items = [item for _, item in extract([(1, pdf.pages[0])])]
    markets = {i.market_raw for i in items}
    assert markets == {
        "Commonwealth",
        "Marikina",
        "Pasig",
        "Guadalupe",
        "Las Piñas",
        "Maypajo",
        "Taguig",
        "Alabang",
        None,
    }
    fancy = {i.market_raw: i for i in items if i.commodity_raw == "Fancy"}
    assert (fancy["Guadalupe"].price_prevailing_raw, fancy["Guadalupe"].price_high_raw) == (
        "5 0.00",
        "52.00",
    )
    assert fancy[None].price_average_raw == "50.76"
    assert len(items) == 9 * sum(i.market_raw is None for i in items)
