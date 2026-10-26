"""Tests for the pork and chicken by-market extractor, on pages 3-5 of the December 29, 2022
report (tests/fixtures/pdfs/)."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.extract.by_market import extract, items_from_page
from ingestion.da_prices.extract.items import Unsupported
from ingestion.da_prices.extract.layout import Table

FIXTURE = Path(__file__).parent / "fixtures" / "pdfs" / "by_market_2022-12-29_p3-5.pdf"


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


def test_prevailing_price_pages_are_not_read_yet() -> None:
    # 2021-2022: today and last report side by side, which would read as low and high
    title = "Prevailing Retail Prices of Whole Chicken in NCR Markets\nNovember 28, 2022 (Today)"
    table = Table(
        (0, 0, 600, 100),
        [[(0, 0, 600, 50)], [(0, 50, 250, 60), (250, 50, 600, 60)]],
        [[f"{title}\nFRESH WHOLE CHICKEN"], ["MARKET", "Fully-dressed, whole chicken"]],
    )
    with pytest.raises(Unsupported, match="not a price range page"):
        items_from_page(5, [], [table])


def test_heading_of_another_page_off_the_page_edge_is_ignored() -> None:
    # page 2 also carries "FRESH WHOLE CHICKEN" to the right of the page
    assert {r[1] for r in _rows() if r[0] == 2} == {"FRESH & FROZEN PORK LIEMPO"}
