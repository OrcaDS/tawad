"""Tests for the NCR today-vs-yesterday posters, on page 1 of the October 5, 2021 report
(tests/fixtures/pdfs/, images removed)."""

from pathlib import Path

import pdfplumber

from ingestion.da_prices.extract.ncr_compare import extract

FIXTURE = Path(__file__).parent / "fixtures" / "pdfs" / "ncr_compare_2021-10-05_p1.pdf"


def _rows() -> list[tuple]:
    with pdfplumber.open(FIXTURE) as pdf:
        return [
            (i.category_header_raw, i.commodity_raw, i.price_prevailing_raw)
            for _, i in extract([(1, pdf.pages[0])])
        ]


def test_today_price_is_kept_and_labels_dropped() -> None:
    rows = _rows()
    # 51 items, less the 11 OTHER COMMODITIES that DA printed without prices that day
    assert len(rows) == 40
    # today 46.50, yesterday 48.00
    assert rows[1] == ("IMPORTED COMMERCIAL RICE", "Premium", "46.50")
    assert ("FRUITS\n(per kg)", "Mango\n(Carabao)", "180.00") in rows
    assert not any("Today" in str(row) or "Legend" in str(row) for row in rows)


def test_not_over_available_is_one_price() -> None:
    assert ("IMPORTED COMMERCIAL RICE", "Regular Milled", "NOT AVAILABLE") in _rows()


def test_names_of_a_panel_without_prices_join_no_row() -> None:
    # the unpriced OTHER COMMODITIES panel sits right of FRUITS (Sugar Refined, Palm Oil …)
    assert not any("Sugar" in (name or "") or "Oil" in (name or "") for _, name, _ in _rows())
