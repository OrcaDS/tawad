"""Tests for the Daily Price Index extractor. Table rows are real pdfplumber output."""

from ingestion.da_prices.extract import markets_covered
from ingestion.da_prices.extract.daily_index import items_from_pages

HEADER_2026 = ["COMMODITY", "SPECIFICATION", "PREVAILING RETAIL\nPRICE PER UNIT\n(P/UNIT)"]
FRAGMENT = [["PREVAILING RETAIL"], ["PRICE PER UNIT"], ["(P/UNIT)"]]  # read as a second table


def rows(pages):
    return [
        (n, i.category_header_raw, i.commodity_raw, i.specification_raw, i.price_prevailing_raw)
        for n, i in items_from_pages(pages)
    ]


def test_2026_layout_carries_categories_across_pages() -> None:
    page1 = [
        HEADER_2026,
        ["IMPORTED COMMERCIAL RICE", "", ""],
        ["Basmati Rice", "", "170.00"],
        ["LOCAL COMMERCIAL RICE", "", ""],
        ["Other Special Rice", "White Rice", "58.10"],
    ]
    page2 = [HEADER_2026, ["Beef Fore Limb, Imported", "", "n/a"]]
    assert rows([(1, [page1, FRAGMENT]), (2, [page2, FRAGMENT])]) == [
        (1, "IMPORTED COMMERCIAL RICE", "Basmati Rice", "", "170.00"),
        (1, "LOCAL COMMERCIAL RICE", "Other Special Rice", "White Rice", "58.10"),
        (2, "LOCAL COMMERCIAL RICE", "Beef Fore Limb, Imported", "", "n/a"),  # n/a kept raw
    ]
    item = items_from_pages([(1, [page1])])[0][1]
    assert item.layout == "COMMODITY | SPECIFICATION | PREVAILING RETAIL PRICE PER UNIT (P/UNIT)"
    assert item.unit_raw is None


def test_2025_split_cells_unit_column_and_wrapped_category() -> None:
    table = [
        [
            "COMMODITY",
            None,
            None,
            "SPECIFICATION",
            None,
            None,
            "UNIT",
            None,
            None,
            "PREVAILING RETAIL\nPRICE (P/UNIT)",
            None,
            None,
        ],  # fmt: skip
        ["", "IMPORTED COMMERCIAL RICE", "", "", "", "", "", "", "", "", "", ""],
        ["Special", None, None, "White Rice", None, None, "kg", None, None, "58.38", None, None],
        ["", "LIVESTOCK & POULTRY", "", "", None, None, "", None, None, "", None, None],
        [None, "PRODUCTS", None, None, None, None, None, None, None, None, None, None],
        ["", "Ampalaya", "", "4-5 pcs/kg", None, None, "kg", None, None, "128.33", None, None],
    ]
    items = [i for _, i in items_from_pages([(1, [table])])]
    assert [
        (i.category_header_raw, i.commodity_raw, i.unit_raw, i.price_prevailing_raw) for i in items
    ] == [  # fmt: skip
        ("IMPORTED COMMERCIAL RICE", "Special", "kg", "58.38"),
        ("LIVESTOCK & POULTRY\nPRODUCTS", "Ampalaya", "kg", "128.33"),  # text off the grid
    ]


def test_mid_2025_row_numbers_and_category_letters_are_dropped() -> None:
    table = [
        [
            "COMMODITY",
            None,
            None,
            None,
            None,
            None,
            "SPECIFICATION",
            None,
            None,
            "PREVAILING RETAIL\nPRICE PER UNIT\n(P/UNIT)",
            None,
            None,
        ],  # fmt: skip
        ["", "A", "", "", "IMPORTED COMMERCIAL RICE", "", "", "", "", "", "", ""],
        ["1", None, None, "Fancy", None, None, "White Rice", None, None, "61.50", None, None],
    ]
    assert rows([(1, [table])]) == [(1, "IMPORTED COMMERCIAL RICE", "Fancy", "White Rice", "61.50")]


def test_blank_commodity_header_july_2025() -> None:
    table = [
        [
            "",
            None,
            None,
            None,
            None,
            None,
            "SPECIFICATION",
            None,
            None,
            "PREVAILING RETAIL\nPRICE PER UNIT\n(P/UNIT)",
            None,
            None,
        ],  # fmt: skip
        ["1", None, None, "Fancy", None, None, "White Rice", None, None, "55.28", None, None],
    ]
    assert rows([(1, [table])]) == [(1, None, "Fancy", "White Rice", "55.28")]


def test_header_wrapped_onto_a_second_row() -> None:
    table = [
        ["COMMODITY", "SPECIFICATION", "RETAIL PRICE"],
        ["", "", "PER UNIT (P/UNIT)"],
        ["Basmati Rice", "", "170.00"],
    ]
    (_, item), *_ = items_from_pages([(1, [table])])
    assert item.layout == "COMMODITY | SPECIFICATION | RETAIL PRICE PER UNIT (P/UNIT)"
    assert item.commodity_raw == "Basmati Rice"


def test_rows_without_a_price_continue_the_item_above_even_across_pages() -> None:
    page1 = [
        HEADER_2026,
        ["Habichuelas/Baguio Beans,", "", "130.21"],
        ["Local", None, None],
        ["Beef Brisket, Local", "Punta y pecho; The point", "430.00"],
    ]
    page2 = [HEADER_2026, ["", "end brisket is composed of", ""], ["Pechay Baguio", "", "86.08"]]
    assert rows([(1, [page1]), (2, [page2])]) == [
        (1, None, "Habichuelas/Baguio Beans,\nLocal", "", "130.21"),
        (
            1,
            None,
            "Beef Brisket, Local",
            "Punta y pecho; The point\nend brisket is composed of",
            "430.00",
        ),  # fmt: skip
        (2, None, "Pechay Baguio", "", "86.08"),
    ]


def test_tables_without_a_header_give_nothing() -> None:
    assert items_from_pages([(1, [FRAGMENT])]) == []
    assert items_from_pages([]) == []


def test_markets_covered_counts_the_numbered_list() -> None:
    lines = [
        "b) n/a - not available in the market/establishment",
        "- Eggs: Peso per Piece",
        "d) Covered market",
        "1. Agora Public Market 19. Murphy Public Market",
        "14. Mandaluyong Public Market II 33. Trabajo Market",
        "18. Muñoz Market",
        "Page 8 of 8",
    ]
    assert markets_covered(lines) == 33
    assert markets_covered(["c) Covered wet markets and supermarkets:", "1. Quinta Market"]) == 1
    assert markets_covered(lines[:2]) is None
