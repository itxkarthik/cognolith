"""Several workers need state they share: Redis rate limits and a fixed SECRET_KEY (issue #29)."""

import pytest
from pydantic import ValidationError

from app.core import rate_limit
from app.core.config import Settings, settings


def test_one_process_counts_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BACKEND_WORKERS", 1)
    monkeypatch.setattr(settings, "REDIS_URL", None)

    assert rate_limit.get_storage_uri() == "memory://"


def test_several_workers_without_redis_refuse_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BACKEND_WORKERS", 4)
    monkeypatch.setattr(settings, "REDIS_URL", None)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        rate_limit.get_storage_uri()


def test_several_workers_with_unreachable_redis_refuse_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BACKEND_WORKERS", 2)
    # Nothing listens on port 1
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")

    with pytest.raises(RuntimeError, match="unreachable"):
        rate_limit.get_storage_uri()


@pytest.mark.filterwarnings("ignore:The value of .* is a known placeholder")
def test_several_workers_need_a_fixed_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="with 2 workers"):
        Settings(_env_file=None, ENVIRONMENT="local", SECRET_KEY="", BACKEND_WORKERS=2)  # pyright: ignore[reportCallIssue]
    # One local process may sign with a key of its own
    with pytest.warns(UserWarning, match="ephemeral key"):
        one_process = Settings(
            _env_file=None, ENVIRONMENT="local", SECRET_KEY="", BACKEND_WORKERS=1
        )  # pyright: ignore[reportCallIssue]
    assert one_process.SECRET_KEY
