"""Tests for configuration loading and the CLI skeleton.

The autouse fixture in conftest.py clears all settings env vars before each test.
"""

import pytest

from config.settings import load_settings
from pipeline.cli import main


def test_defaults_need_no_environment() -> None:
    s = load_settings()
    assert s.request_delay_seconds == 5
    assert s.bq_dataset == "palengke_gold"
    assert s.log_level == "INFO"


def test_empty_env_value_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BQ_DATASET", "")
    assert load_settings().bq_dataset == "palengke_gold"


@pytest.mark.parametrize(
    ("value", "message"),
    [("0.1", "polite"), ("nan", "finite"), ("inf", "finite"), ("5s", "REQUEST_DELAY_SECONDS")],
)
def test_request_delay_validated(monkeypatch: pytest.MonkeyPatch, value: str, message: str) -> None:
    monkeypatch.setenv("REQUEST_DELAY_SECONDS", value)
    with pytest.raises(ValueError, match=message):
        load_settings()


def test_log_level_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        load_settings()
    monkeypatch.setenv("LOG_LEVEL", "debug")  # case-insensitive
    assert load_settings().log_level == "DEBUG"


def test_cli_show_config_succeeds() -> None:
    assert main(["show-config"]) == 0


def test_run_all_stops_at_first_failing_step(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline import cli

    def boom(*_):
        raise AssertionError("ran a step after a failure")

    monkeypatch.setattr(cli, "_lake_pull", lambda *_: 3)
    monkeypatch.setattr(cli, "_ingest_da", boom)
    assert main(["run-all"]) == 3


def test_run_all_carries_on_when_da_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from pipeline import cli

    def da_down(*_):
        raise urllib.error.URLError(TimeoutError("timed out"))

    ran = []
    for name in ["_lake_pull", "_extract_da", "_ingest_psa_if_due", "_lake_push", "_transform"]:
        monkeypatch.setattr(cli, name, lambda *_, n=name: ran.append(n) or 0)
    monkeypatch.setattr(cli, "_export_bq", lambda *_: 0)
    monkeypatch.setattr(cli, "_publish_data", lambda *_: 0)
    monkeypatch.setattr(cli, "_ingest_da", da_down)
    assert main(["run-all"]) == 0
    assert "_transform" in ran


def test_run_all_fails_when_da_answers_with_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from pipeline import cli

    def moved(*_):
        raise urllib.error.HTTPError("https://example.test", 404, "Not Found", {}, None)

    monkeypatch.setattr(cli, "_lake_pull", lambda *_: 0)
    monkeypatch.setattr(cli, "_ingest_da", moved)
    with pytest.raises(urllib.error.HTTPError):
        main(["run-all"])


def test_psa_due_after_a_week(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from datetime import UTC, datetime, timedelta

    import pyarrow as pa

    from ingestion.common.storage import get_storage
    from ingestion.psa import openstat
    from pipeline.cli import _psa_due

    monkeypatch.setenv("LAKE_ROOT", str(tmp_path))
    settings = load_settings()
    assert _psa_due(settings)  # never pulled
    path = openstat.bronze_path("psa_cpi", openstat.CPI_TABLE)
    for days, due in [(3, False), (8, True)]:
        row = dict.fromkeys(openstat.SCHEMA.names, "x")
        row["pulled_at"] = datetime.now(UTC) - timedelta(days=days)
        table = pa.Table.from_pylist([row], schema=openstat.SCHEMA)
        get_storage(settings).write_parquet(path, table, openstat.SCHEMA)
        assert _psa_due(settings) is due


def test_cli_config_error_exits_2_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    assert main(["show-config"]) == 2
