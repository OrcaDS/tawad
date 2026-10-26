"""Tests for the Weekly Average Price extractor. Table rows are real pdfplumber output."""

from ingestion.da_prices.extract import markets_covered
from ingestion.da_prices.extract.weekly_avg import items_from_pages

TITLE_BOX = [[""], [""]]  # read as a table of its own above the header
HEADER = [None, "COMMODITY", "SPECIFICATION", "UNIT", "WEEKLY AVERAGE PRICE"]


def rows(pages):
    return [
        (n, i.category_header_raw, i.commodity_raw, i.specification_raw, i.unit_raw)
        + (i.price_average_raw,)
        for n, i in items_from_pages(pages)
    ]


def test_continuation_tables_use_the_first_header_aligned_from_the_right() -> None:
    page1 = [
        ["", None, None, None, None],
        HEADER,
        [None, "IMPORTED COMMERCIAL RICE", "", "", ""],
        [None, "Premium", "5% broken", "kg", "55.39"],
    ]
    page2 = [  # keeps the empty first cell
        ["", "BEEF PRODUCTS", "", "", ""],
        [None, "Chicken Egg (White, Pewee)", "41-45 grams/pc", "pc", "6.64"],
    ]
    page3 = [  # drops it
        ["Red Onion, Imported", "", "kg", "-"],
        ["Cooking Oil (Palm)", "1 Liter/bottle", "L", "101.99"],
    ]
    assert rows([(1, [TITLE_BOX, page1]), (2, [page2]), (3, [page3])]) == [
        (1, "IMPORTED COMMERCIAL RICE", "Premium", "5% broken", "kg", "55.39"),
        (2, "BEEF PRODUCTS", "Chicken Egg (White, Pewee)", "41-45 grams/pc", "pc", "6.64"),
        (3, "BEEF PRODUCTS", "Red Onion, Imported", "", "kg", "-"),  # "-" (not sold) kept raw
        (3, "BEEF PRODUCTS", "Cooking Oil (Palm)", "1 Liter/bottle", "L", "101.99"),
    ]
    (_, item), *_ = items_from_pages([(1, [page1])])
    assert item.layout == "COMMODITY | SPECIFICATION | UNIT | WEEKLY AVERAGE PRICE"
    assert item.price_prevailing_raw is None


def test_stray_text_in_the_first_cell_does_not_hide_a_category() -> None:
    table = [
        HEADER,
        [None, "Tomato", "15-18 pcs/kg", "kg", "132.36"],
        ["x", "HIGHLAND VEGETABLES", "", "", ""],  # October 13-18, 2025
        ["", "Bell Pepper (Green)", "Medium (151-250gm/pc)", "kg", "289.35"],
    ]
    assert [r[1:3] for r in rows([(1, [table])])] == [
        (None, "Tomato"),
        ("HIGHLAND VEGETABLES", "Bell Pepper (Green)"),
    ]


def test_odd_cells_are_kept_raw() -> None:
    table = [
        HEADER,
        [None, "", "", "", "351.13"],  # December 8-13, 2025: a price without an item
        [None, "Bonito (Frigate Tuna)", "", "kg", "#DIV/0!"],
        [None, "Chicken Egg (Brown, Extra Large)", "Extra Large", "pc", "8.00*"],
    ]
    assert [r[2:] for r in rows([(1, [table])])] == [
        ("", "", "", "351.13"),
        ("Bonito (Frigate Tuna)", "", "kg", "#DIV/0!"),
        ("Chicken Egg (Brown, Extra Large)", "Extra Large", "pc", "8.00*"),
    ]


def test_tables_before_the_header_give_nothing() -> None:
    assert (
        items_from_pages([(1, [TITLE_BOX, [[None, "Premium", "5% broken", "kg", "55.39"]]])]) == []
    )
    assert items_from_pages([]) == []


def test_markets_covered_in_a_paragraph() -> None:
    stated = ["Markets Covered (29): Agora, Bicutan, Blumentritt, Cartimar,", "Taguig & Trabajo"]
    assert markets_covered(stated) == 29
    listed = [
        "Markets Covered: Agora Public Market, Alabang Central Market, Mega Q-",
        "Mart, Muñoz Market, Taguig People's Market, and Trabajo Market",
        "Source: DA Agribusiness and Marketing Assistance Service (DA-AMAS)",
        "Note: (-) not sold in the market",
    ]
    assert markets_covered(listed) == 6
    assert markets_covered(["Covered markets: Taguig & Trabajo"]) is None  # not this format
