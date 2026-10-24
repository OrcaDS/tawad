"""Single entry point for the pipeline: `tawad <subcommand>` (also the Docker entrypoint).

Subcommands are wired up milestone by milestone; until then they exit with code 2 so a
scheduled run can never silently pass while doing nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

from config.settings import Settings, load_settings
from ingestion.common import manifest
from ingestion.common.storage import get_storage
from ingestion.da_prices import discover, download

logger = logging.getLogger("tawad")


def _not_yet(milestone: int) -> Callable[[argparse.Namespace, Settings], int]:
    def handler(args: argparse.Namespace, settings: Settings) -> int:
        logger.error("'%s' is not implemented yet (milestone %d).", args.command, milestone)
        return 2

    return handler


def _show_config(args: argparse.Namespace, settings: Settings) -> int:
    """Log the effective configuration (no secrets are held in Settings)."""
    for field in dataclasses.fields(settings):
        logger.info("%s = %s", field.name, getattr(settings, field.name))
    return 0


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from None


def _positive(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"expected a positive whole number, got {value!r}")
    return int(value)


def _ingest_da(args: argparse.Namespace, settings: Settings) -> int:
    """Discover DA reports, update the manifest, and download what is missing."""
    storage = get_storage(settings)
    fetch = download.make_fetcher(settings)
    reports = discover.discover(download.fetch_listing(fetch, settings))
    entries = manifest.merge(manifest.load(storage), reports, datetime.now(UTC))
    manifest.save(storage, entries)
    if args.discover_only:
        return 0
    download.download_pending(storage, entries, fetch, since=args.since, limit=args.limit)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tawad", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show-config", help="Print the effective configuration").set_defaults(
        handler=_show_config
    )
    da = sub.add_parser("ingest-da", help="Discover, download and extract DA reports")
    da.add_argument(
        "--since", metavar="YYYY-MM-DD", type=_since, help="Only download reports from this date"
    )
    da.add_argument("--limit", metavar="N", type=_positive, help="Download at most N files")
    da.add_argument(
        "--discover-only", action="store_true", help="Update the manifest without downloading"
    )
    da.set_defaults(handler=_ingest_da)
    sub.add_parser("ingest-primary", help="Pull my Google Form responses").set_defaults(
        handler=_not_yet(6)
    )
    sub.add_parser("ingest-psa", help="Pull PSA CPI and retail price tables").set_defaults(
        handler=_not_yet(7)
    )
    sub.add_parser("transform", help="dbt build: silver and gold").set_defaults(handler=_not_yet(4))
    sub.add_parser("export-bq", help="Load gold tables to BigQuery").set_defaults(
        handler=_not_yet(8)
    )
    sub.add_parser("run-all", help="Run every stage in order").set_defaults(handler=_not_yet(9))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ValueError as exc:  # bad env var: report it plainly, not as a traceback
        logging.basicConfig(format="%(levelname)s tawad: %(message)s")
        logger.error("Configuration error: %s", exc)
        return 2
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.handler(args, settings)


if __name__ == "__main__":
    sys.exit(main())
