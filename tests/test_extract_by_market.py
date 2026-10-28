"""Tests for the pork and chicken by-market extractor, on pages 3-5 of the December 29, 2022
report (tests/fixtures/pdfs/)."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.extract.by_market import extract, items_from_page
from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.layout import Table

FIXTURE = Path(__file__).parent / "fixtures" / "pdfs" / "by_market_2022-12-29_p3-5.pdf"
PREVAILING = FIXTURE.with_name("by_market_2022-11-28_p4-5.pdf")


def _rows() -> list[tuple]:
    with pdfplumber.open(FIXTURE) as pdf:
        return [
            (n, i.commodity_raw, i.specification_raw, i.market_raw)
            + (i.price_low_raw, i.price_high_raw, i.price_prevailing_raw)
            for n, i in extract(list(enumerate(pdf.pages, start=1)))
        ]


def test_heading_is_the_commodity_and_columns_the_specifications() -> None:
    rows = _rows()
    assert len(rows) == 13 * 2 + 13 * 2 + 13  # 13 markets; pork has Fresh and Frozen
    kasim = "FRESH & FROZEN PORK KASIM/PIGUE"
    market = "New Las Piñas City Public Market"  # the row number "1" is dropped
    assert rows[0] == (1, kasim, "Fresh", market, "310.00", "310.00", None)
    assert rows[1] == (1, kasim, "Frozen", market, None, None, "N/A")
    chicken = "FRESH WHOLE CHICKEN"
    assert rows[-1][:4] == (3, chicken, "Fully-dressed, whole chicken", "Malabon Central Market")


def test_prevailing_pages_keep_only_todays_price() -> None:
    # Nov 28, 2022 pages 4-5: "Today" and "Last Friday" sub-columns under Fresh and Frozen
    with pdfplumber.open(PREVAILING) as pdf:
        rows = extract(list(enumerate(pdf.pages, start=1)))
    assert len(rows) == 32 * 2 + 32
    assert {i.layout for _, i in rows} == {"compare"}
    assert {i.price_low_raw for _, i in rows} == {i.price_high_raw for _, i in rows} == {None}
    fresh = {
        i.market_raw: i.price_prevailing_raw for n, i in rows if i.specification_raw == "Fresh"
    }
    assert fresh["Trabajo Market"] == "400.00"  # last Friday: 335.00
    assert fresh["San Andres Market"] == "n/m"  # last Friday: 370.00
    assert fresh["Pamilihang Lungsod ng Muntinlupa"] == "(-)"  # closed, kept raw
    assert rows[-1][1].commodity_raw == "FRESH WHOLE CHICKEN"


def test_other_titles_are_not_read() -> None:
    table = Table(
        (0, 0, 600, 100),
        [[(0, 0, 600, 50)], [(0, 50, 250, 60), (250, 50, 600, 60)]],
        [["Pork Availability in NCR Markets\nFRESH PORK"], ["MARKET", "Fresh"]],
    )
    with pytest.raises(Unsupported, match="not a price range or prevailing page"):
        items_from_page(5, [], [table])


def test_heading_of_another_page_off_the_page_edge_is_ignored() -> None:
    # page 2 also carries "FRESH WHOLE CHICKEN" to the right of the page
    assert {r[1] for r in _rows() if r[0] == 2} == {"FRESH & FROZEN PORK LIEMPO"}
