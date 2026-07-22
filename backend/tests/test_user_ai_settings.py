from unittest import TestCase

from app.api.routes.user import _parse_chat_models
from app.models.user import UserSettings
from app.schemas.settings import UserAISettingsUpdate


class UserAISettingsTests(TestCase):
    def test_model_options_exclude_the_embedding_model(self) -> None:
        payload = {
            "models": [
                {"name": "nomic-embed-text:latest", "size": 274},
                {"name": "llama3.2:1b", "size": 1300},
                {"name": "gemma3:1b", "size": 815},
            ]
        }

        models = _parse_chat_models(payload, "nomic-embed-text")

        self.assertEqual([model.name for model in models], ["gemma3:1b", "llama3.2:1b"])

    def test_diagnostics_default_to_disabled(self) -> None:
        preferences = UserSettings(user_id=999)

        self.assertFalse(preferences.rag_diagnostics_enabled)


def test_ai_settings_update_accepts_diagnostics_without_model() -> None:
    update = UserAISettingsUpdate(rag_diagnostics_enabled=True)

    assert update.llm_model is None
    assert update.rag_diagnostics_enabled is True
