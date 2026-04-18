from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session

from app.ai.http_client import get_embedding_client
from app.core.config import settings
from app.models.user import UserSettings

DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"


def resolve_embedding_model(
    *, session: Session, user_id: int, override_model: str | None = None
) -> str:
    if override_model:
        return override_model

    user_settings = session.get(UserSettings, user_id)
    if user_settings and user_settings.embedding_model:
        return user_settings.embedding_model

    return DEFAULT_EMBEDDING_MODEL


class OllamaEmbeddingClient:
    def __init__(self, *, base_url: str | None = None, timeout_seconds: float = 120.0) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def embed_texts(self, *, texts: Sequence[str], model: str) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "model": model,
            "input": list(texts),
        }

        # Use pooled HTTP client instead of creating new one per request
        client = await get_embedding_client(timeout=self.timeout_seconds)
        response = await client.post(f"{self.base_url}/api/embed", json=payload)
        response.raise_for_status()
        data = response.json()

        embeddings = data.get("embeddings")
        if embeddings is None and data.get("embedding") is not None:
            embeddings = [data["embedding"]]

        if not isinstance(embeddings, list):
            raise ValueError("Invalid Ollama embed response: missing embeddings list")

        normalized: list[list[float]] = []
        for item in embeddings:
            if not isinstance(item, list):
                raise ValueError("Invalid Ollama embed response: embedding item must be a list")
            normalized.append([float(value) for value in item])

        if len(normalized) != len(texts):
            raise ValueError("Embedding response count does not match input text count")

        return normalized


async def generate_embeddings(
    *,
    session: Session,
    user_id: int,
    texts: Sequence[str],
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[list[list[float]], str]:
    resolved_model = resolve_embedding_model(session=session, user_id=user_id, override_model=model)
    client = OllamaEmbeddingClient(base_url=base_url)
    vectors = await client.embed_texts(texts=texts, model=resolved_model)
    return vectors, resolved_model


async def generate_embedding(
    *,
    session: Session,
    user_id: int,
    text: str,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[list[float], str]:
    vectors, resolved_model = await generate_embeddings(
        session=session,
        user_id=user_id,
        texts=[text],
        model=model,
        base_url=base_url,
    )
    return vectors[0], resolved_model
