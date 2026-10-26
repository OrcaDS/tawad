"""What page extractors return: ``Item`` rows (raw cell text; the runner adds the report's
lineage), or ``Unsupported`` for a layout they can't read yet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    layout: str  # the page's header cells, " | "-joined, so silver can tell variants apart
    commodity_raw: str | None
    category_header_raw: str | None = None
    specification_raw: str | None = None
    unit_raw: str | None = None
    market_raw: str | None = None  # None for NCR-wide rows
    price_low_raw: str | None = None
    price_high_raw: str | None = None
    price_prevailing_raw: str | None = None
    price_average_raw: str | None = None


class Unsupported(Exception):
    """A layout the extractor can't read yet: the report waits instead of failing."""
