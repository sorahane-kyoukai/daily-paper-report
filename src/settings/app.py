"""Application settings powered by Pydantic BaseSettings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Centralized environment configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )

    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    hf_token: str | None = Field(default=None, validation_alias="HF_TOKEN")
    openreview_token: str | None = Field(
        default=None, validation_alias="OPENREVIEW_TOKEN"
    )
    semantic_scholar_api_key: str | None = Field(
        default=None, validation_alias="SEMANTIC_SCHOLAR_API_KEY"
    )
    gemini_refresh_token: str | None = Field(
        default=None, validation_alias="GEMINI_REFRESH_TOKEN"
    )
    gemini_oauth_client_id: str | None = Field(
        default=None, validation_alias="GEMINI_OAUTH_CLIENT_ID"
    )
    gemini_oauth_client_secret: str | None = Field(
        default=None, validation_alias="GEMINI_OAUTH_CLIENT_SECRET"
    )
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    llm_provider: str | None = Field(default=None, validation_alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(
        default=None, validation_alias="OPENAI_BASE_URL"
    )
    openai_model: str | None = Field(default=None, validation_alias="OPENAI_MODEL")
    openai_reasoning_effort: str | None = Field(
        default=None, validation_alias="OPENAI_REASONING_EFFORT"
    )
    openai_thinking_type: str | None = Field(
        default=None, validation_alias="OPENAI_THINKING_TYPE"
    )
    openai_max_tokens: int | None = Field(
        default=None, validation_alias="OPENAI_MAX_TOKENS"
    )
    deepseek_api_key: str | None = Field(
        default=None, validation_alias="DEEPSEEK_API_KEY"
    )

    def auth_token_for_platform(self, platform: str) -> str | None:
        """Return auth token for a platform identifier."""
        tokens = {
            "github": self.github_token,
            "huggingface": self.hf_token,
            "openreview": self.openreview_token,
            "semantic_scholar": self.semantic_scholar_api_key,
        }
        return tokens.get(platform)


def get_settings() -> AppSettings:
    """Get a settings instance."""
    return AppSettings()
