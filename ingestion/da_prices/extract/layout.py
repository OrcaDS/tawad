"""Characters and table boxes as plain values, for extractors that read by position.

pdfplumber's words can't be trusted on DA's tighter tables: it glues neighbouring cells into
one word (``100.00100.00``, ``NOT AVAILABLE160.00``). Characters inside a word sit 0.0-0.1
pt apart and separate words at least 1.1 pt, so extractors place single characters in
columns first and only then join them into text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pdfplumber.page import Page

Box = tuple[float, float, float, float]  # x0, top, x1, bottom

LINE_GAP = 3.0  # characters whose tops differ by less than this share a line
SPACE_GAP = 0.5  # a wider gap between two characters is a space


@dataclass(frozen=True)
class Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class Table:
    bbox: Box
    cells: Sequence[Sequence[Box | None]]  # per row, per column (None where cells merge)
    text: Sequence[Sequence[str | None]]


def page_chars(page: Page) -> list[Char]:
    return [
        Char(c["text"], c["x0"], c["x1"], c["top"], c["bottom"])
        for c in page.chars
        if c["text"].strip()
    ]


def page_tables(page: Page) -> list[Table]:
    return [Table(t.bbox, [row.cells for row in t.rows], t.extract()) for t in page.find_tables()]


def lines(chars: Sequence[Char]) -> list[list[Char]]:
    """Characters grouped into lines from the top down, each line left to right."""
    result: list[list[Char]] = []
    for char in sorted(chars, key=lambda c: (c.top, c.x0)):
        if result and char.top - result[-1][0].top < LINE_GAP:
            result[-1].append(char)
        else:
            result.append([char])
    return [sorted(line, key=lambda c: c.x0) for line in result]


def words(chars: Sequence[Char]) -> list[Char]:
    """Characters joined into words (split at every gap), line by line."""
    result: list[Char] = []
    for line in lines(chars):
        word = [line[0]]
        for char in line[1:]:
            if char.x0 - word[-1].x1 > SPACE_GAP:
                result.append(_join(word))
                word = []
            word.append(char)
        result.append(_join(word))
    return result


def _join(chars: Sequence[Char]) -> Char:
    return Char(
        "".join(c.text for c in chars),
        chars[0].x0,
        chars[-1].x1,
        min(c.top for c in chars),
        max(c.bottom for c in chars),
    )


def text(chars: Sequence[Char]) -> str:
    """One line's characters (left to right) as text, with a space at every gap."""
    out = ""
    for prev, char in zip([None, *chars], chars, strict=False):
        if prev is not None and char.x0 - prev.x1 > SPACE_GAP:
            out += " "
        out += char.text
    return out
