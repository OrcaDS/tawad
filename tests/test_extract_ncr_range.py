"""Tests for the NCR range extractor. Synthetic positions follow the December 11, 2025 report;
posters are read from cuts of real reports in tests/fixtures/pdfs/."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.ncr_range import RowMerge, extract, items_from_page
from tests.test_extract_layout import chars

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"

PAGE_BOTTOM = 612
CAPITAL = 4.4  # width of a header letter


def header(top: float, x0: float, glued: bool = False) -> list:
    """``COMMODITIES LOW HIGH PREVAILING AVERAGE`` at the 2025 spacing, from ``x0``."""

    def word(text: str, dx: float) -> list:
        return chars(text, x0 + dx, top, width=CAPITAL)

    parts = word("COMMODITIES", 0) + word("LOW", 85)
    if glued:  # November 17, 2025
        parts += word("HIGHPREVALING", 125)
    else:
        parts += word("HIGH", 125) + word("PREVAILING", 150)
    return parts + word("AVERAGE", 206)


def row(
    top: float, x: float, name: str, low: str | None, high: str | None, prev: str, avg: str
) -> list:
    """One row: name from ``x``; prices under the header that starts at ``x + 32``."""
    out = chars(name, x, top + 0.5)  # names sit a little lower than their prices
    if low:
        out += chars(f"{low}-", x + 117, top)  # "160.00-": the separator glued on
    if high:
        out += chars(high, x + 157, top)
    if low and not high:
        out = out[: -len(low) - 1] + chars(low, x + 138, top)  # one value centred across both
    return out + chars(prev, x + 207, top) + chars(avg, x + 251, top)


def items(page):
    return [
        (i.category_header_raw, i.commodity_raw, i.price_low_raw, i.price_high_raw)
        + (i.price_prevailing_raw, i.price_average_raw)
        for i in items_from_page(4, page, PAGE_BOTTOM)
    ]


def test_two_tables_side_by_side_with_headings_and_category_labels() -> None:
    page = (
        header(120, 138)
        + header(120, 478)
        + chars("IMPORTED COMMERCIAL RICE", 106, 135)  # a sub-heading
        + row(150, 106, "Basmati", "190.00", "250.00", "190.00", "211.00")
        + chars("RICE", 70, 160)  # a label spanning rows in the far-left column
        + row(170, 106, "Glutinous", "54.00", "70.00", "60.00", "62.25")
        + row(150, 446, "Bell Pepper (Green)", "200.00", "350.00", "300.00", "277.36")
        + chars("Markets Covered: Agora Market (San Juan), Alabang Central Market", 52, 400)
    )
    assert items(page) == [
        ("IMPORTED COMMERCIAL RICE", "Basmati", "190.00", "250.00", "190.00", "211.00"),
        ("IMPORTED COMMERCIAL RICE", "Glutinous", "54.00", "70.00", "60.00", "62.25"),
        (None, "Bell Pepper (Green)", "200.00", "350.00", "300.00", "277.36"),
    ]
    assert items_from_page(4, page, PAGE_BOTTOM)[0].layout == (
        "COMMODITIES | LOW | HIGH | PREVAILING | AVERAGE"
    )


def test_one_value_across_low_and_high_is_both() -> None:
    page = header(120, 138) + row(150, 106, "Jasponica/Japonica", "60.00", None, "60.00", "61.32")
    assert items(page) == [(None, "Jasponica/Japonica", "60.00", "60.00", "60.00", "61.32")]


def test_wrapped_names_glued_header_and_not_available() -> None:
    page = (
        header(120, 138, glued=True)
        + chars("Imported Round Scad", 106, 143)  # two name lines around one row of prices
        + chars("300.00-", 223, 150)
        + chars("320.00", 263, 150)
        + chars("300.00", 313, 150)
        + chars("306.96", 357, 150)
        + chars("(Galunggong)", 106, 157)
        + chars("Corn Grits (White, Food Grade)", 106, 175)
        + chars("NOT", 270, 175)
        + chars("AVAILABLE", 280, 175)
    )
    assert items(page) == [
        (None, "Imported Round Scad\n(Galunggong)", "300.00", "320.00", "300.00", "306.96"),
        (None, "Corn Grits (White, Food Grade)", None, "NOT AVAILABLE", None, None),  # one cell
    ]


def test_two_rows_run_together_are_refused_not_guessed() -> None:
    page = header(120, 138) + chars("200.00", 263, 150) + chars("250.00", 263, 153)
    with pytest.raises(RowMerge):
        items_from_page(4, page, PAGE_BOTTOM)


def test_a_page_with_neither_headers_nor_price_groups_waits() -> None:
    with pytest.raises(Unsupported):
        items_from_page(1, chars("COMMODITIES", 690, 183) + chars("Special", 42, 178), 612)


def _poster(fixture: str) -> list[tuple]:
    with pdfplumber.open(FIXTURES / fixture) as pdf:
        return [
            (it.category_header_raw, it.commodity_raw, it.price_low_raw, it.price_high_raw)
            for _, it in extract([(1, pdf.pages[0])])
        ]


def test_2023_poster() -> None:
    rows = _poster("ncr_poster_2023-05-25_p1.pdf")
    assert len(rows) == 51
    assert rows[0] == ("IMPORTED COMMERCIAL RICE", "Special", "50.00", "58.00")
    # imported vs local rice exists only in the panel's sub-heading
    assert ("LOCAL COMMERCIAL RICE", "Special", "48.00", "60.00") in rows
    assert ("IMPORTED COMMERCIAL RICE", "Regular Milled", "NOT AVAILABLE", "NOT AVAILABLE") in rows
    # names wrap above and below their price; the footnote mark stays raw
    assert ("FISH\n(per kg)", "Indian mackerel\nAlumahan b", "240.00", "360.00") in rows
    assert ("OTHER\nCOMMODITIES", "Palm Oil - 350ml", "25.00", "40.00") in rows  # not a range
    assert not any("8926" in str(row) or "Retail" in str(row) for row in rows)  # contact, title


def test_2024_poster() -> None:
    rows = _poster("ncr_poster_2024-07-26_p1.pdf")
    assert len(rows) == 76
    assert ("Feed Grade", "Corn Cracked", "42.00", "60.00") in rows  # a mixed-case sub-heading
    # two NOT AVAILABLE rows stacked tightly; a dash set higher than its prices
    assert (None, "Corn Grits\n(White)", "NOT AVAILABLE", "NOT AVAILABLE") in rows
    assert ("LOCAL COMMERCIAL RICE", "Premium", "50.00", "58.00") in rows
    # one centred value is low = high; footnote marks stay raw
    assert ("SPICES\n(per kg)", "Local Garlic\nBawang f", "400.00", "400.00") in rows
    assert (
        "LIVESTOCK AND\nPOULTRY\nPRODUCTS",
        "Whole Chicken\n(per kg)",
        "200.00",
        "250.00*",
    ) in rows
    # the eggs share CORN's price column but not its panel: no category, not a wrong one
    assert (None, "Egg (White, Medium)\nper piece", "6.80", "8.50") in rows
