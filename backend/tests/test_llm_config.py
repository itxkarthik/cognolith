from typing import cast
from unittest import TestCase

from sqlmodel import Session

from app.ai.llm import resolve_llm_config
from app.models.user import LlmProvider, UserSettings


class FakeSettingsSession:
    def __init__(self, settings: UserSettings) -> None:
        self.settings = settings

    def get(self, _: object, __: int) -> UserSettings:
        return self.settings


class LLMConfigTests(TestCase):
    def test_resolves_persisted_user_model_preference(self) -> None:
        preferences = UserSettings(
            user_id=7,
            llm_provider=LlmProvider.ollama,
            llm_model="gemma3:1b",
            embedding_model="nomic-embed-text",
        )

        config = resolve_llm_config(
            session=cast(Session, FakeSettingsSession(preferences)),
            user_id=7,
        )

        self.assertEqual(config.provider, "ollama")
        self.assertEqual(config.model, "gemma3:1b")
