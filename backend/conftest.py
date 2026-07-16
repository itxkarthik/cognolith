"""Pytest bootstrap that isolates integration tests from development data."""

import os

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlmodel import Session, SQLModel

TEST_DATABASE = os.getenv("POSTGRES_TEST_DB", "knowledge_assistant_test")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")


def _recreate_test_database() -> None:
    admin_url = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/postgres"
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (TEST_DATABASE,),
        )
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(TEST_DATABASE))
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DATABASE)))


_recreate_test_database()
os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{TEST_DATABASE}"
)

from app.core.database import create_db_and_tables, engine  # noqa: E402
from app.models import chat, document, note, user  # noqa: E402, F401

with engine.begin() as connection:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

create_db_and_tables()


@pytest.fixture
def session():
    """Provide a clean database session for integration and performance tests."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
