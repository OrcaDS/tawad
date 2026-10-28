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


def test_cli_unimplemented_stage_fails_loudly() -> None:
    assert main(["run-all"]) == 2


def test_cli_config_error_exits_2_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    assert main(["show-config"]) == 2
