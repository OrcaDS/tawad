"""Tests for the NCR range extractor. Positions follow the December 11, 2025 report."""

import pytest

from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.ncr_range import RowMerge, items_from_page
from tests.test_extract_layout import chars

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


def test_posters_without_column_headers_wait() -> None:
    with pytest.raises(Unsupported):
        items_from_page(
            1, chars("COMMODITIES", 690, 183) + chars("Special 50.00-58.00", 42, 178), 612
        )
