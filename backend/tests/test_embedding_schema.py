import asyncio

import pytest
from sqlalchemy import Connection

from app.ai import embedding_validation
from app.ai.vectorstore import EmbeddingDimensionMismatchError, check_embedding_dimensions
from app.core.config import settings
from app.models.embedding import EMBEDDING_TABLES, Vector


def test_configured_size_is_accepted() -> None:
    check_embedding_dimensions(settings.EMBEDDING_DIMENSIONS)


def test_other_sizes_point_to_the_reindex_command() -> None:
    with pytest.raises(EmbeddingDimensionMismatchError, match="reindex_embeddings"):
        check_embedding_dimensions(settings.EMBEDDING_DIMENSIONS + 1)


def test_embedding_tables_use_the_configured_vector_size() -> None:
    for table in EMBEDDING_TABLES:
        column_type = table.c.embedding.type
        assert isinstance(column_type, Vector)
        assert column_type.get_col_spec() == f"vector({settings.EMBEDDING_DIMENSIONS})"


class _FakeConnection:
    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _FakeEngine:
    def connect(self) -> _FakeConnection:
        return _FakeConnection()


def _stored(sizes: dict[str, int | None]):
    def fake(_: Connection) -> dict[str, int | None]:
        return sizes

    return fake


def _all_tables(size: int | None) -> dict[str, int | None]:
    return {table.name: size for table in EMBEDDING_TABLES}


def test_startup_rejects_tables_built_for_another_model(monkeypatch) -> None:
    monkeypatch.setattr(embedding_validation, "engine", _FakeEngine())
    monkeypatch.setattr(
        embedding_validation,
        "stored_embedding_dimensions",
        _stored(_all_tables(settings.EMBEDDING_DIMENSIONS + 256)),
    )

    with pytest.raises(EmbeddingDimensionMismatchError, match="EMBEDDING_DIMENSIONS"):
        asyncio.run(embedding_validation.validate_embedding_setup())


def test_startup_rejects_missing_tables(monkeypatch) -> None:
    monkeypatch.setattr(embedding_validation, "engine", _FakeEngine())
    monkeypatch.setattr(
        embedding_validation, "stored_embedding_dimensions", _stored(_all_tables(None))
    )

    with pytest.raises(RuntimeError, match="migrations"):
        asyncio.run(embedding_validation.validate_embedding_setup())


def test_startup_rejects_a_model_with_another_size(monkeypatch) -> None:
    class WrongSizeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def embed_texts(self, *, texts, model) -> list[list[float]]:
            return [[0.0] * (settings.EMBEDDING_DIMENSIONS * 2)]

    monkeypatch.setattr(embedding_validation, "engine", _FakeEngine())
    monkeypatch.setattr(
        embedding_validation,
        "stored_embedding_dimensions",
        _stored(_all_tables(settings.EMBEDDING_DIMENSIONS)),
    )
    monkeypatch.setattr(embedding_validation, "OllamaEmbeddingClient", WrongSizeClient)

    with pytest.raises(EmbeddingDimensionMismatchError):
        asyncio.run(embedding_validation.validate_embedding_setup())


def test_startup_tolerates_an_unreachable_model(monkeypatch) -> None:
    class DownClient:
        def __init__(self, **_: object) -> None:
            pass

        async def embed_texts(self, *, texts, model) -> list[list[float]]:
            raise ConnectionError("ollama is starting")

    monkeypatch.setattr(embedding_validation, "engine", _FakeEngine())
    monkeypatch.setattr(
        embedding_validation,
        "stored_embedding_dimensions",
        _stored(_all_tables(settings.EMBEDDING_DIMENSIONS)),
    )
    monkeypatch.setattr(embedding_validation, "OllamaEmbeddingClient", DownClient)

    asyncio.run(embedding_validation.validate_embedding_setup())
