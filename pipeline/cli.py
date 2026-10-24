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

from config.settings import Settings, load_settings

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tawad", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show-config", help="Print the effective configuration").set_defaults(
        handler=_show_config
    )
    da = sub.add_parser("ingest-da", help="Discover, download and extract DA reports")
    da.add_argument("--since", metavar="YYYY-MM-DD", help="Backfill reports from this date")
    da.set_defaults(handler=_not_yet(3))
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
