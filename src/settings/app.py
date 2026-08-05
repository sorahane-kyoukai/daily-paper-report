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
        extra="ignore",
    )

    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    hf_token: str | None = Field(default=None, validation_alias="HF_TOKEN")
    openreview_token: str | None = Field(
        default=None, validation_alias="OPENREVIEW_TOKEN"
    )
    semantic_scholar_api_key: str | None = Field(
        default=None, validation_alias="SEMANTIC_SCHOLAR_API_KEY"
    )
    deepseek_api_key: str | None = Field(
        default=None, validation_alias="DEEPSEEK_API_KEY"
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash", validation_alias="DEEPSEEK_MODEL"
    )
    deepseek_max_tokens: int = Field(
        default=8192, validation_alias="DEEPSEEK_MAX_TOKENS"
    )
    fulltext_cache_dir: str | None = Field(
        default=None, validation_alias="FULLTEXT_CACHE_DIR"
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
