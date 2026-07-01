from __future__ import annotations

import argparse

from sqlmodel import Session, select

from app.core.database import engine
from app.models.user import LlmProvider, User, UserSettings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set Ollama model preferences for one user.")
    parser.add_argument("--email", required=True, help="Account email address")
    parser.add_argument("--chat-model", required=True, help="Installed Ollama chat model")
    parser.add_argument(
        "--embedding-model",
        help="Installed embedding model; keeps the current preference when omitted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if user is None or user.id is None:
            raise SystemExit(f"User not found: {args.email}")

        preferences = session.get(UserSettings, user.id)
        if preferences is None:
            preferences = UserSettings(user_id=user.id)

        preferences.llm_provider = LlmProvider.ollama
        preferences.llm_model = args.chat_model
        if args.embedding_model:
            preferences.embedding_model = args.embedding_model

        embedding_model = preferences.embedding_model
        session.add(preferences)
        session.commit()

    print(f"Updated {args.email}: chat={args.chat_model}, embedding={embedding_model}")


if __name__ == "__main__":
    main()
