"""Tests for DA page classification. Lines are real title and header text from DA's PDFs."""

from pathlib import Path

import pdfplumber
import pytest

from ingestion.da_prices.classify import (
    BLANK,
    BY_HEADER,
    BY_INHERITED,
    BY_NO_TEXT,
    BY_NONE,
    BY_TITLE,
    CHICKEN_BY_MARKET,
    DAILY_INDEX,
    IMAGE_ONLY,
    INFOGRAPHIC,
    MARKET_MATRIX,
    MARKET_RANGE,
    NCR_COMPARE,
    NCR_RANGE,
    NCR_SUMMARY,
    NOTES,
    OVERFLOW,
    PORK_BY_MARKET,
    STALL_COUNT,
    UNKNOWN,
    UNREADABLE,
    WEEKLY_AVG,
    PageClass,
    PageText,
    classify_document,
    classify_page,
    page_text,
)


def page(*lines: str, images: int = 0) -> PageText:
    return PageText(tuple(lines), n_chars=sum(len(line) for line in lines), n_images=images)


MATRIX_2018 = page(
    "DAILY PRICE MONITORING REPORT",
    "Agribusiness Industry Support Division",
    "Market : Selected Wet Markets in Metro Manila",
    "Date : October 24, 2018",
    "Prevailing Price of Selected Agricultural Commodities",
    "Commonwealth Farmers Marikina Mega Q-mart Muñoz Pasay Pasig Polo Quinta",
    "Commodity Specification Prevailing Low High Average",
    "Prevailing Low High Prevailing Low High Prevailing Low High Prevailing",
)
NCR_SUMMARY_2019 = page(
    "DAILY PRICE MONITORING REPORT",
    "Surveillance, Monitoring and Enforcement Group",
    "PRELIMINARY REPORT as of 6:47 AM",
    "Date : Wednesday, October 16, 2019",
    "Retail Prices of Selected Agri-fishery Commodities in Selected Markets in Metro Manila",
    "Retail price per kilogram (Php/kg)",
    "COMMODITY SPECIFICATION(S)",
    "Prevailing Low High Average",
)
NCR_SUMMARY_2020 = page(
    "Department of Agriculture",
    "Bantay Presyo Prices Monitoring",
    "PRELIMINARY REPORT as of Monday, June 01, 2020",
    "Retail Prices of Selected Agri-fishery Commodities in Selected Markets in Metro Manila",
    "Summary",
    "COMMODITY SPECIFICATION Unit",
    "High Low Prevailing",
)
MATRIX_2020 = page(
    "DAILY PRICE MONITORING",
    "Date : February 1, 2020 (Saturday)",
    "Retail Prices of Selected Agri-fishery Commodities in Selected Markets in Metro Manila",
    "Prevailing Low High Average Prevailing Low High Average Prevailing Low High Average",
)
POSTER_2021 = page(
    "Retail Prices of Selected Agri-fishery Commodities in Selected Markets in Metro Manila as of",
    "Markets Covered: Commonwealth, Mega Q-Mart, Las Piñas, San Andres, Marikina",
    "RICE LIVESTOCK AND POULTRY UPLAND LOWLAND",
    images=78,
)
DPI_2025 = page(
    "Prevailing Retail Prices of Selected Agri-Fishery Commodities in Selected Wet",
    "Markets in the National Capital Region, May 10, 2025 (P/unit)",
    "PREVAILING RETAIL",
    "COMMODITY SPECIFICATION PRICE PER UNIT",
)
DPI_2026 = page(
    "Department of Agriculture",
    "DAILY PRICE INDEX",
    "National Capital Region (NCR)",
    "(Saturday, October 24, 2026)",
)
DPI_CONTINUATION = page(
    "PREVAILING RETAIL", "COMMODITY SPECIFICATION PRICE PER UNIT", "(P/UNIT)", "White Beans 151.76"
)
WEEKLY = page(
    "Department of Agriculture",
    "Bantay Presyo Monitoring",
    "For the period of January 12-17, 2026",
    "Weekly Average Retail Price of Selected Agri-Fishery Commodities in NCR Markets",
    "COMMODITY SPECIFICATION UNIT WEEKLY AVERAGE PRICE",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (MATRIX_2018, (MARKET_MATRIX, BY_HEADER)),
        (NCR_SUMMARY_2019, (NCR_SUMMARY, BY_HEADER)),
        (NCR_SUMMARY_2020, (NCR_SUMMARY, BY_HEADER)),
        (MATRIX_2020, (MARKET_MATRIX, BY_HEADER)),
        (POSTER_2021, (INFOGRAPHIC, BY_TITLE)),
        (DPI_2025, (DAILY_INDEX, BY_TITLE)),
        (DPI_2026, (DAILY_INDEX, BY_TITLE)),
        (DPI_CONTINUATION, (DAILY_INDEX, BY_HEADER)),
        (WEEKLY, (WEEKLY_AVG, BY_TITLE)),
        (
            page("Retail Price Range of Selected Agri-fishery Commodities per Market"),
            (MARKET_RANGE, BY_TITLE),
        ),
        (
            page("Prevailing Retail Price Range of Selected Agri-fishery Commodities per Market"),
            (MARKET_RANGE, BY_TITLE),
        ),
        (
            page(
                "BANTAY PRESYO",
                "Prevailing Retail Prices of Selected",
                "Commodities (PHP/KG) per Market",
            ),
            (MARKET_RANGE, BY_TITLE),
        ),
        (
            page("Retail Price of Selected Agri-fishery Commodities at NCR Markets"),
            (NCR_RANGE, BY_TITLE),
        ),
        (
            page("Retail Price Range of Fresh and Frozen Pork Products in NCR Markets"),
            (PORK_BY_MARKET, BY_TITLE),
        ),
        (page("Retail Price Range of Whole Chicken in NCR Markets"), (CHICKEN_BY_MARKET, BY_TITLE)),
        (
            page("TODAY'S PREVAILING PRICE YESTERDAY'S PREVAILING PRICE"),
            (NCR_COMPARE, BY_TITLE),
        ),
        (page("COMMODITIES LOW HIGH AVERAGE", "KADIWA RICE-FOR-ALL"), (NCR_RANGE, BY_HEADER)),
        (
            page("*Percentage excludes stalls that are closed", "Retail Price Range per Market"),
            (STALL_COUNT, BY_TITLE),
        ),
        (page("NUMBER OF STALLS SELLING PORK PRODUCTS"), (STALL_COUNT, BY_TITLE)),
        (
            page(
                "BANTAY PRESYO", "Prevailing Retail Prices (PHP/KG) in", "Metro Manila", images=16
            ),
            (INFOGRAPHIC, BY_TITLE),
        ),
        (page("Source: DA Agribusiness and Marketing Assistance Service"), (NOTES, BY_HEADER)),
        (page("13. Trabajo Market M. Dela Fuente Cor. Loyola St."), (NOTES, BY_HEADER)),
        (PageText((), n_chars=0, n_images=1), (IMAGE_ONLY, BY_NO_TEXT)),
        (PageText((), n_chars=0, n_images=0), (BLANK, BY_NO_TEXT)),
        (PageText(("  ",), n_chars=2, n_images=0), (BLANK, BY_NO_TEXT)),
        (
            page("(cid:39)(cid:36)(cid:44)(cid:47)(cid:60)(cid:3)(cid:51)", "(cid:53)(cid:40)"),
            (UNREADABLE, BY_NO_TEXT),
        ),
        (page("Something DA has never printed before"), (UNKNOWN, BY_NONE)),
    ],
)
def test_classify_page(text: PageText, expected: tuple[str, str]) -> None:
    assert classify_page(text) == expected


def test_shared_title_without_known_header_is_unknown() -> None:
    assert classify_page(page("DAILY PRICE MONITORING", "Unfamiliar header")) == (
        UNKNOWN,
        BY_HEADER,
    )


def test_whitespace_in_lines_is_collapsed() -> None:
    assert classify_page(page("Retail  Price of Whole   Chicken in  NCR Markets"))[0] == (
        CHICKEN_BY_MARKET
    )


def test_title_below_title_zone_is_ignored() -> None:
    filler = [f"Agora Public Market {n} 50.00 - 60.00" for n in range(8)]
    text = page(*filler, "Retail Price Range of Whole Chicken in NCR Markets")
    assert classify_page(text, previous=MARKET_RANGE) == (MARKET_RANGE, BY_INHERITED)


def test_continuation_pages_inherit_the_previous_price_type() -> None:
    rows = page("Agora Public Market/San Juan 50.00 - 60.00", "Bicutan Market 48.00 - 55.00")
    title = page("Retail Price Range of Selected Agri-fishery Commodities per Market")
    assert classify_document([title, rows, rows]) == [
        PageClass(1, MARKET_RANGE, BY_TITLE),
        PageClass(2, MARKET_RANGE, BY_INHERITED),
        PageClass(3, MARKET_RANGE, BY_INHERITED),
    ]


def test_skip_pages_are_not_inherited() -> None:
    rows = page("Agora Public Market/San Juan 50.00 - 60.00")
    poster = page("BANTAY PRESYO", "Prevailing Retail Prices (PHP/KG) in", images=30)
    assert [c.page_type for c in classify_document([poster, rows])] == [INFOGRAPHIC, UNKNOWN]


def test_first_page_without_title_is_unknown() -> None:
    rows = page("Agora Public Market/San Juan 50.00 - 60.00")
    assert classify_document([rows]) == [PageClass(1, UNKNOWN, BY_NONE)]


def test_text_off_the_page_is_ignored() -> None:
    # Nov 28, 2022: the chicken page also carries the pork page's title past its left edge
    fixture = Path(__file__).parent / "fixtures" / "pdfs" / "by_market_2022-11-28_p4-5.pdf"
    with pdfplumber.open(fixture) as pdf:
        types = [c.page_type for c in classify_document([page_text(p) for p in pdf.pages])]
    assert types == [PORK_BY_MARKET, CHICKEN_BY_MARKET]


def test_page_mostly_off_the_page_is_overflow() -> None:
    # Oct 5, 2021 page 2: the poster's right strip, its names on page 1 or in pictures
    strip = PageText(("OTHER", "COMMODITIES", "Today Yesterday", "50.00 50.00"), 551, 0, 450)
    assert classify_page(strip, previous=NCR_COMPARE) == (OVERFLOW, BY_NO_TEXT)
