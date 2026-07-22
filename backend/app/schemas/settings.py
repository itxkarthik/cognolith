from datetime import datetime

from pydantic import BaseModel, Field


class OllamaModelOption(BaseModel):
    name: str
    size: int = 0
    modified_at: datetime | None = None


class UserAISettingsResponse(BaseModel):
    llm_model: str
    embedding_model: str
    ollama_available: bool
    available_models: list[OllamaModelOption] = Field(default_factory=list)
    rag_diagnostics_enabled: bool = False


class UserAISettingsUpdate(BaseModel):
    llm_model: str | None = Field(default=None, min_length=1, max_length=100)
    rag_diagnostics_enabled: bool | None = None
