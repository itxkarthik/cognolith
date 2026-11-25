"""
Rebuild the embedding tables after changing the embedding model or its vector size.

Set EMBEDDING_DIMENSIONS (and OLLAMA_EMBEDDING_MODEL) to the new values first, then:

    python -m scripts.reindex_embeddings --yes

The tables are dropped and recreated at EMBEDDING_DIMENSIONS, then every user's
documents, notes and chats are embedded again. With --no-backfill only the tables
are rebuilt; embeddings are then filled in lazily on each user's next chat or search.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlmodel import Session, select

from app.ai.embeddings import OllamaEmbeddingClient, resolve_embedding_model
from app.ai.rag import ensure_workspace_embeddings
from app.ai.vectorstore import PgVectorStore, check_embedding_dimensions
from app.core.config import settings
from app.core.database import engine
from app.models.embedding import EMBEDDING_TABLES
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument(
        "--yes", action="store_true", help="Confirm dropping all stored embeddings"
    )
    parser.add_argument(
        "--no-backfill",
        action="store_true",
        help="Only rebuild the tables; embed lazily on next use",
    )
    return parser.parse_args()


def _probe_default_model() -> None:
    vectors = asyncio.run(
        OllamaEmbeddingClient().embed_texts(
            texts=["dimension check"], model=settings.OLLAMA_EMBEDDING_MODEL
        )
    )
    check_embedding_dimensions(len(vectors[0]))


def rebuild_tables() -> None:
    with engine.begin() as connection:
        for table in reversed(EMBEDDING_TABLES):
            table.drop(connection, checkfirst=True)
        for table in EMBEDDING_TABLES:
            table.create(connection)


def backfill() -> None:
    with Session(engine) as session:
        user_ids = [user_id for user_id in session.exec(select(User.id)).all() if user_id is not None]
    for user_id in user_ids:
        with Session(engine) as session:
            model = resolve_embedding_model(session=session, user_id=user_id)
            ensure_workspace_embeddings(
                session=session,
                vector_store=PgVectorStore(session=session),
                user_id=user_id,
                embedding_model=model,
                include_documents=True,
                include_notes=True,
                include_chats=True,
            )
            session.commit()
        print(f"Re-embedded workspace for user {user_id} with {model}")


def main() -> None:
    args = parse_args()
    if not args.yes:
        raise SystemExit(
            "This drops every stored embedding. Re-run with --yes to continue "
            f"(new size: EMBEDDING_DIMENSIONS={settings.EMBEDDING_DIMENSIONS})."
        )

    # Refuse before dropping anything if the model doesn't produce the configured size
    _probe_default_model()
    rebuild_tables()
    print(f"Rebuilt embedding tables at {settings.EMBEDDING_DIMENSIONS} dimensions")
    if not args.no_backfill:
        backfill()


if __name__ == "__main__":
    main()
