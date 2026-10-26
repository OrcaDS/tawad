"""Tests for the character helpers, and the `chars` builder other extractor tests use."""

from ingestion.da_prices.extract import layout
from ingestion.da_prices.extract.layout import Char

WIDTH = 2.4  # a digit in DA's 2024-2026 tables


def chars(text: str, x0: float, top: float, width: float = WIDTH) -> list[Char]:
    """``text`` as characters from ``x0``, touching (0.03 apart) except at spaces."""
    out, x = [], x0
    for ch in text:
        if ch == " ":
            x += 2.0
            continue
        out.append(Char(ch, x, x + width, top, top + 7))
        x += width + 0.03
    return out


def test_text_puts_spaces_at_gaps_only() -> None:
    assert layout.text(chars("NOT AVAILABLE", 10, 100)) == "NOT AVAILABLE"
    glued = chars("100.00", 10, 100) + chars("100.00", 10 + 6 * WIDTH + 0.2, 100)
    assert layout.text(glued) == "100.00100.00"  # 0.2 pt apart: pdfplumber's words glue these


def test_lines_and_words() -> None:
    page = chars("Pritil Market", 46, 200.4) + chars("48.00", 122, 200.0) + chars("Paco", 46, 217)
    assert [layout.text(line) for line in layout.lines(page)] == ["Pritil Market 48.00", "Paco"]
    assert [w.text for w in layout.words(page)] == ["Pritil", "Market", "48.00", "Paco"]
