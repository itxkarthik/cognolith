"""Startup check that the embedding tables, configuration and model agree on vector size."""

import asyncio
import logging

from app.ai.embeddings import OllamaEmbeddingClient
from app.ai.vectorstore import (
    REINDEX_HINT,
    EmbeddingDimensionMismatchError,
    check_embedding_dimensions,
    stored_embedding_dimensions,
)
from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger(__name__)

MODEL_PROBE_TIMEOUT_SECONDS = 15.0


async def validate_embedding_setup() -> None:
    """
    Raise if the embedding columns don't match EMBEDDING_DIMENSIONS, or if the
    default embedding model produces a different size. An unreachable model is
    only logged: Ollama may still be starting or pulling models.
    """
    with engine.connect() as connection:
        stored = stored_embedding_dimensions(connection)

    missing = sorted(name for name, size in stored.items() if size is None)
    if missing:
        raise RuntimeError(
            f"Embedding tables are missing ({', '.join(missing)}). "
            "Run the database migrations (alembic upgrade head)."
        )
    mismatched = {name: size for name, size in stored.items() if size != settings.EMBEDDING_DIMENSIONS}
    if mismatched:
        sizes = ", ".join(f"{name}={size}" for name, size in sorted(mismatched.items()))
        raise EmbeddingDimensionMismatchError(
            f"EMBEDDING_DIMENSIONS is {settings.EMBEDDING_DIMENSIONS} but the embedding tables "
            f"store {sizes}. {REINDEX_HINT}"
        )

    try:
        vectors = await asyncio.wait_for(
            OllamaEmbeddingClient(timeout_seconds=MODEL_PROBE_TIMEOUT_SECONDS).embed_texts(
                texts=["dimension check"], model=settings.OLLAMA_EMBEDDING_MODEL
            ),
            timeout=MODEL_PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "Could not verify the vector size of embedding model %s: %s",
            settings.OLLAMA_EMBEDDING_MODEL,
            exc,
        )
        return

    check_embedding_dimensions(len(vectors[0]))
    logger.info(
        "Embedding model %s matches EMBEDDING_DIMENSIONS=%s",
        settings.OLLAMA_EMBEDDING_MODEL,
        settings.EMBEDDING_DIMENSIONS,
    )
