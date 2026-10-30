"""Single entry point for the pipeline: `tawad <subcommand>` (also the Docker entrypoint).

Subcommands are wired up milestone by milestone; until then they exit with code 2 so a
scheduled run can never silently pass while doing nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from config.settings import Settings, load_settings
from ingestion.common import lake_release, manifest
from ingestion.common.storage import get_storage
from ingestion.da_prices import discover, download, extract
from ingestion.psa import openstat

logger = logging.getLogger("tawad")
TRANSFORM_DIR = Path("transform")  # the dbt project; commands run from the repo root (or /app)
PSA_EVERY = timedelta(days=7)  # PSA publishes monthly; a full pull takes ~3 min


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
    download.download_pending(
        storage,
        entries,
        fetch,
        since=args.since,
        limit=args.limit,
        refetch_missing=not args.new_only,
    )
    return 0


def _extract_da(args: argparse.Namespace, settings: Settings) -> int:
    """Extract downloaded DA reports into bronze rows (no network)."""
    storage = get_storage(settings)
    extract.extract_pending(
        storage, manifest.load(storage), series=args.series, redo=args.redo, limit=args.limit
    )
    return 0


def _ingest_psa(args: argparse.Namespace, settings: Settings) -> int:
    """Pull PSA CPI and retail price tables into bronze."""
    failed = openstat.ingest(
        get_storage(settings), download.make_fetcher(settings), settings.psa_api_base
    )
    return 1 if failed else 0


def _psa_due(settings: Settings) -> bool:
    path = openstat.bronze_path("psa_cpi", openstat.CPI_TABLE)
    storage = get_storage(settings)
    if not storage.exists(path):
        return True
    last = max(storage.read_parquet(path).column("pulled_at").to_pylist())
    return datetime.now(UTC) - last >= PSA_EVERY


def _ingest_psa_if_due(args: argparse.Namespace, settings: Settings) -> int:
    if not _psa_due(settings):
        logger.info("PSA pulled less than %d days ago; skipped", PSA_EVERY.days)
    elif _ingest_psa(args, settings):  # failed tables keep their last pull; carry on
        logger.warning("Some PSA tables failed; using their previous pull")
    return 0


def _lake_push(args: argparse.Namespace, settings: Settings) -> int:
    """Upload changed lake assets (bronze tables, manifest, PDFs) to the GitHub release."""
    lake_release.push(settings.lake_root, lake_release.GhRelease())
    return 0


def _lake_pull(args: argparse.Namespace, settings: Settings) -> int:
    """Restore the lake from the GitHub release."""
    lake_release.pull(settings.lake_root, lake_release.GhRelease(), pdfs=args.pdfs)
    return 0


def _transform(args: argparse.Namespace, settings: Settings) -> int:
    """Build silver and gold with dbt (models, seeds and tests) over the local bronze."""
    from dbt.cli.main import dbtRunner  # slow import; only this command needs it

    dbt_vars = {
        "lake_root": settings.lake_root.resolve().as_posix(),
        "duckdb_path": settings.duckdb_path.resolve().as_posix(),
    }
    result = dbtRunner().invoke(
        [
            "build",
            "--project-dir",
            str(TRANSFORM_DIR),
            "--profiles-dir",
            str(TRANSFORM_DIR),
            "--vars",
            json.dumps(dbt_vars),
        ]
    )
    return 0 if result.success else 1


def _export_bq(args: argparse.Namespace, settings: Settings) -> int:
    """Export gold from DuckDB to Parquet and load what is due to BigQuery."""
    from google.cloud import bigquery  # slow import; only this command needs it

    from warehouse import export_to_bigquery as bq

    if not settings.gcp_project_id:
        logger.error("GCP_PROJECT_ID is not set")
        return 2
    exports = bq.export_gold(
        settings.duckdb_path,
        settings.lake_root / "gold",
        bq.gold_tables(),
    )
    client = bigquery.Client(project=settings.gcp_project_id)
    return bq.export_to_bigquery(
        client, f"{settings.gcp_project_id}.{settings.bq_dataset}", exports, force=args.force
    )


def _publish_data(args: argparse.Namespace, settings: Settings) -> int:
    """Publish gold as a "Latest" GitHub Release (CSV + Parquet), if it changed."""
    from warehouse import export_to_bigquery as bq
    from warehouse import publish_data

    out_dir = settings.lake_root / "gold"
    exports = bq.export_gold(settings.duckdb_path, out_dir, bq.gold_tables())
    publish_data.publish(exports, out_dir, datetime.now(UTC).date())
    return 0


def _run_all(args: argparse.Namespace, settings: Settings) -> int:
    """The daily run on a fresh machine: the lake release is the only state."""
    da = argparse.Namespace(since=None, limit=None, discover_only=False, new_only=True)
    ex = argparse.Namespace(series=None, redo=False, limit=None)
    steps = [
        ("lake-pull", _lake_pull, argparse.Namespace(pdfs=False)),
        ("ingest-da", _ingest_da, da),
        ("extract-da", _extract_da, ex),
        ("ingest-psa", _ingest_psa_if_due, args),
        # Push the lake once gold builds, so a BigQuery or release hiccup can't lose new PDFs
        ("transform", _transform, args),
        ("lake-push", _lake_push, args),
        ("export-bq", _export_bq, argparse.Namespace(force=False)),
        ("publish-data", _publish_data, args),
    ]
    for name, handler, step_args in steps:
        logger.info("run-all: %s", name)
        if code := handler(step_args, settings):
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tawad", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show-config", help="Print the effective configuration").set_defaults(
        handler=_show_config
    )
    da = sub.add_parser("ingest-da", help="Discover and download DA reports")
    da.add_argument(
        "--since", metavar="YYYY-MM-DD", type=_since, help="Only download reports from this date"
    )
    da.add_argument("--limit", metavar="N", type=_positive, help="Download at most N files")
    da.add_argument(
        "--discover-only", action="store_true", help="Update the manifest without downloading"
    )
    da.add_argument(
        "--new-only",
        action="store_true",
        help="Skip reports already downloaded, even if their PDF is not in this lake",
    )
    da.set_defaults(handler=_ingest_da)
    ex = sub.add_parser("extract-da", help="Extract downloaded DA reports into bronze rows")
    ex.add_argument("--series", choices=discover.SERIES, help="Only this report series")
    ex.add_argument("--redo", action="store_true", help="Also redo extracted and failed reports")
    ex.add_argument("--limit", metavar="N", type=_positive, help="Extract at most N reports")
    ex.set_defaults(handler=_extract_da)
    sub.add_parser("lake-push", help="Upload changed lake files to the release").set_defaults(
        handler=_lake_push
    )
    pull = sub.add_parser("lake-pull", help="Restore bronze tables and manifest from the release")
    pull.add_argument("--pdfs", action="store_true", help="Also restore every DA PDF (~3 GB)")
    pull.set_defaults(handler=_lake_pull)
    sub.add_parser("ingest-psa", help="Pull PSA CPI and retail price tables").set_defaults(
        handler=_ingest_psa
    )
    sub.add_parser("transform", help="dbt build: silver and gold").set_defaults(handler=_transform)
    bqp = sub.add_parser("export-bq", help="Load gold tables to BigQuery (about monthly)")
    bqp.add_argument("--force", action="store_true", help="Reload every table now")
    bqp.set_defaults(handler=_export_bq)
    sub.add_parser("publish-data", help="Release gold as open data if it changed").set_defaults(
        handler=_publish_data
    )
    sub.add_parser("run-all", help="Run every stage in order (the daily run)").set_defaults(
        handler=_run_all
    )
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
