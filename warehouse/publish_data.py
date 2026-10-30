"""Publish gold as open data: a GitHub Release marked "Latest", only when gold changed.

Assets: each gold table as Parquet, every table as CSV in one zip, and the data dictionary.
The Parquet files are written in a stable row order (``export_gold``), so their sha256 tells
whether anything changed since the latest release.
"""

from __future__ import annotations

import json
import logging
import subprocess
import zipfile
from datetime import date
from pathlib import Path

import duckdb

from warehouse.export_to_bigquery import Export

logger = logging.getLogger(__name__)

DICTIONARY = Path("docs/data_dictionary.md")
CSV_ZIP = "tawad_gold_csv.zip"
NOTES = """\
Metro Manila retail food prices, cleaned and standardized. Each gold table comes as Parquet \
(`<table>.parquet`) and as CSV (all tables in `{csv_zip}`). Columns, units and grain: \
`data_dictionary.md`.

**Source:** Department of Agriculture Bantay Presyo reports. Cleaned and standardized by tawad. \
Not an official DA product. Consumer price index and PSA retail prices: Philippine Statistics \
Authority, OpenSTAT.

**Disclaimer:** provided as is. DA's own typos are kept and flagged (`is_outlier`), and parsing \
may contain errors.

**Licenses:** the DA-derived tables are Philippine government data (no copyright under RA 8293 \
§176; commercial users should check with DA). PSA data is under PSA's terms. The code is MIT.

Tables: {tables}
"""


def changed(exports: list[Export], published: dict[str, str]) -> bool:
    """True if any gold table differs from the latest release (or it has none of them)."""
    return any(published.get(f"{e.table}.parquet") != e.sha256 for e in exports)


def csv_zip(exports: list[Export], out: Path) -> Path:
    """Write every table as CSV into one zip (fct_prices alone is ~100 MB as plain CSV)."""
    with duckdb.connect() as con, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in exports:
            csv = out.parent / f"{e.table}.csv"
            con.execute(
                f"COPY (FROM read_parquet('{e.path.as_posix()}')) TO '{csv.as_posix()}' (HEADER)"
            )
            zf.write(csv, csv.name)
            csv.unlink()
    return out


def _gh(*args: str) -> str:
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as exc:
        exc.add_note(f"gh stderr: {exc.stderr.strip()}")
        raise


def latest_release() -> tuple[str | None, dict[str, str]]:
    """Tag and asset sha256s of the "Latest" release (never a prerelease such as ``lake``)."""
    try:
        release = json.loads(_gh("api", "repos/{owner}/{repo}/releases/latest"))
    except subprocess.CalledProcessError as exc:
        if "404" in exc.stderr:
            return None, {}
        raise
    digests = {
        a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in release["assets"]
    }
    return release["tag_name"], digests


def publish(exports: list[Export], work_dir: Path, today: date) -> bool:
    """Release gold if it changed since the latest release. Returns True if it published."""
    tag, published = latest_release()
    if not changed(exports, published):
        logger.info("Gold unchanged since release %s; not publishing", tag)
        return False
    files = [str(e.path) for e in exports]
    files += [str(csv_zip(exports, work_dir / CSV_ZIP)), str(DICTIONARY)]
    new_tag = f"data-{today:%Y-%m-%d}"
    if tag == new_tag:  # a second run on the same day replaces that day's files
        _gh("release", "upload", new_tag, *files, "--clobber")
    else:
        notes = NOTES.format(
            csv_zip=CSV_ZIP, tables=", ".join(f"{e.table} ({e.rows:,} rows)" for e in exports)
        )
        _gh(
            "release", "create", new_tag, *files, "--latest",
            "--title", f"Open data {today:%Y-%m-%d}", "--notes", notes,
        )  # fmt: skip
    logger.info("Published gold as release %s", new_tag)
    return True
