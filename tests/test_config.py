"""Must run with no config at all, and let config override the code defaults."""
from __future__ import annotations

from smsledger import config


def test_defaults_load_without_any_config_file() -> None:
    assert config.fx_settings()["fee_rate"] > 1.0
    assert isinstance(config.sources().get("sms"), list)


def test_account_tails_comes_from_config_not_code() -> None:
    """The original hardcoded its own account tails. These must come from config."""
    config.load.cache_clear()
    assert all(isinstance(t, str) for t in config.account_tails())
