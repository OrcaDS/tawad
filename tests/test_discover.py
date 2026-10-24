"""Tests for DA report discovery: listing parsing, dates, series and revisions."""

from datetime import date
from pathlib import Path

import pytest

from ingestion.da_prices.discover import (
    DAILY_INDEX,
    PRICE_MONITORING,
    PRICE_WATCH,
    RETAIL_MONITORING,
    WEEKLY_AVG,
    Report,
    date_from_filename,
    date_from_link_text,
    discover,
    file_name_of,
    parse_listing,
    rank_revisions,
    revision_level,
    series_of,
)

LISTING = (Path(__file__).parent / "fixtures" / "da_listing.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("Price-Monitoring-October-9-2026.pdf", (None, date(2026, 10, 9))),
        ("Price-Monitoring-March-01-2021.pdf", (None, date(2021, 3, 1))),
        ("Price-Watch-February-1-2018.pdf", (None, date(2018, 2, 1))),
        ("Revised-Daily-Price-Index-October-7-2026.pdf", (None, date(2026, 10, 7))),
        ("Daily-Price-Index-October-8-2026-1.pdf", (None, date(2026, 10, 8))),
        ("October-24-2026-DPI-AFC.pdf", (None, date(2026, 10, 24))),
        ("Price-Monitoring-May-22-2023-Revised.pdf", (None, date(2023, 5, 22))),
        ("Price-Monitrong-September-24-2020.pdf", (None, date(2020, 9, 24))),
        ("Retail-Price-Monitoring-Jan-2-2020.pdf", (None, date(2020, 1, 2))),
        ("Price-Monitoring-Octermber-5-2022.pdf", (None, date(2022, 10, 5))),
        ("Price_Monitoring_02-24-2020.pdf", (None, date(2020, 2, 24))),
        ("RETAIL-Price-Monitoring-Sum-Market_04SEPT19.pdf", (None, date(2019, 9, 4))),
        ("REVISEDRETAIL-Price-Monitoring-Sum-Market_09SEPT19_2.pdf", (None, date(2019, 9, 9))),
        ("RETAILPrice-Monitoring-Report_16NOV19.pdf", (None, date(2019, 11, 16))),
        ("DailyApril042018.pdf", (None, date(2018, 4, 4))),
        ("DailyMar282018.pdf", (None, date(2018, 3, 28))),
        ("Weekly-Average-Prices-October-12-18-2026.pdf", (date(2026, 10, 12), date(2026, 10, 18))),
        (
            "Weekly-Average-Prices-September-28-October-4-2026.pdf",
            (date(2026, 9, 28), date(2026, 10, 4)),
        ),
        (
            "Weekly-Average-Prices-December-29-2025-January-3-2026.pdf",
            (date(2025, 12, 29), date(2026, 1, 3)),
        ),
        ("Weeky-Average-Prices-June-1-7-2025.pdf", (date(2025, 6, 1), date(2025, 6, 7))),
    ],
)
def test_date_from_filename(file_name: str, expected: tuple) -> None:
    assert date_from_filename(file_name) == expected


@pytest.mark.parametrize(
    "file_name", ["DA-NPC-Registration-Certificate.pdf", "Price-Monitoring-February-30-2024.pdf"]
)
def test_date_from_filename_none(file_name: str) -> None:
    assert date_from_filename(file_name) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("October 9, 2026", (None, date(2026, 10, 9))),
        ("May 17 2019", (None, date(2019, 5, 17))),
        ("Marhc 20, 2025", (None, date(2025, 3, 20))),
        ("JUne 6, 2026", (None, date(2026, 6, 6))),
        ("October 12-18, 2026", (date(2026, 10, 12), date(2026, 10, 18))),
        ("Janauary 19-24, 2026", (date(2026, 1, 19), date(2026, 1, 24))),
        ("September 28-October 4, 2026", (date(2026, 9, 28), date(2026, 10, 4))),
        ("December 29, 2025 - January 3, 2026", (date(2025, 12, 29), date(2026, 1, 3))),
    ],
)
def test_date_from_link_text(text: str, expected: tuple) -> None:
    assert date_from_link_text(text) == expected


@pytest.mark.parametrize("text", ["", "2026 Daily Price Index", "October 18-12, 2026"])
def test_date_from_link_text_none(text: str) -> None:
    assert date_from_link_text(text) is None


@pytest.mark.parametrize(
    ("section", "file_name", "expected"),
    [
        ("Daily Retail Price Range", "Price-Watch-May-17-2019.pdf", PRICE_WATCH),
        ("Daily Retail Price Range", "DailyApril042018.pdf", PRICE_WATCH),
        (
            "Daily Retail Price Range",
            "RETAILPrice-Monitoring-Report_07OCT19.pdf",
            RETAIL_MONITORING,
        ),
        ("Daily Retail Price Range", "Retail-Price-Monitoring-Jan-2-2020.pdf", RETAIL_MONITORING),
        ("Daily Retail Price Range", "Revised-Price-Monitoring-March-1-2025.pdf", PRICE_MONITORING),
        ("Daily Price Index", "October-24-2026-DPI-AFC.pdf", DAILY_INDEX),
        ("Weekly Average Retail Prices", "Weeky-Average-Prices-June-1-7-2025.pdf", WEEKLY_AVG),
        ("Daily Cigarette Price Monitoring", "Daily-Cigarette-Price-Monitoring.pdf", None),
        ("FPA Facebook Page", "DA-NPC-Registration-Certificate.pdf", None),
    ],
)
def test_series_of(section: str, file_name: str, expected: str | None) -> None:
    assert series_of(section, file_name) == expected


@pytest.mark.parametrize(
    ("file_name", "level"),
    [
        ("Price-Monitoring-May-22-2023.pdf", 0),
        ("Revised-Price-Monitoring-May-22-2023.pdf", 1),
        ("Price-Monitoring-May-22-2023-Revised.pdf", 1),
        ("REVISEDRETAIL-Price-Monitoring-Sum-Market_09SEPT19_2.pdf", 1),
        ("Updated-Price-Monitoring-May-22-2023.pdf", 1),
        ("2nd-Revision-Price-Monitoring-November-6-2025.pdf", 2),
        ("Price-Monitoring-May-22-2023-Final-Version.pdf", 9),
    ],
)
def test_revision_level(file_name: str, level: int) -> None:
    assert revision_level(file_name) == level


def _report(file_name: str, url_folder: str = "2026/10") -> Report:
    return Report(
        source_url=f"https://www.da.gov.ph/wp-content/uploads/{url_folder}/{file_name}",
        file_name=file_name,
        section="Daily Retail Price Range",
        link_text="",
        series=PRICE_MONITORING,
        report_date=date(2025, 11, 6),
        period_start=None,
        date_check="agree",
        revision_level=revision_level(file_name),
        revision_rank=0,
    )


def test_rank_revisions_orders_versions_of_the_same_report() -> None:
    reports = [
        _report("2nd-Revision-Price-Monitoring-November-6-2025.pdf"),
        _report("Price-Monitoring-November-6-2025.pdf"),
        _report("Price-Monitoring-November-6-2025-1.pdf"),
        _report("Revised-Price-Monitoring-November-6-2025.pdf"),
    ]
    ranks = {r.file_name: r.revision_rank for r in rank_revisions(reports)}
    assert ranks == {
        "Price-Monitoring-November-6-2025.pdf": 0,
        "Price-Monitoring-November-6-2025-1.pdf": 1,
        "Revised-Price-Monitoring-November-6-2025.pdf": 2,
        "2nd-Revision-Price-Monitoring-November-6-2025.pdf": 3,
    }


def test_parse_listing_keeps_section_and_normalizes_text() -> None:
    links = parse_listing(LISTING)
    assert links[0].section == "Weekly Average Retail Prices"
    assert links[0].text == "October 12-18, 2026"
    assert [link.text for link in links if "Revised-Daily" in link.url] == ["October 7, 2026"]
    assert all(link.url.endswith(".pdf") for link in links)  # the banner .png is ignored


def test_discover_on_fixture_page() -> None:
    reports = {r.file_name: r for r in discover(LISTING)}
    assert len(reports) == 9  # cigarettes, the stray certificate and a duplicate link dropped
    weekly = reports["Weekly-Average-Prices-December-29-2025-January-3-2026.pdf"]
    assert (weekly.series, weekly.period_start, weekly.report_date) == (
        WEEKLY_AVG,
        date(2025, 12, 29),
        date(2026, 1, 3),
    )
    # December 2018 report in the February 2019 upload folder keeps its own date
    assert reports["Price-Watch-December-3-2018.pdf"].report_date == date(2018, 12, 3)
    # Filename wins over a disagreeing link label, and the report is flagged
    december = reports["Price-Monitoring-December-23-2024.pdf"]
    assert (december.report_date, december.date_check) == (date(2024, 12, 23), "mismatch")
    assert reports["October-24-2026-DPI-AFC.pdf"].date_check == "agree"


def test_file_name_of_decodes_url() -> None:
    url = "https://www.da.gov.ph/wp-content/uploads/2026/10/Price%20Monitoring.pdf"
    assert file_name_of(url) == "Price Monitoring.pdf"
