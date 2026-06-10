"""Configuration models for the HTTP fetch layer."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.features.fetch.constants import DEFAULT_MAX_RESPONSE_SIZE_BYTES
from src.features.fetch.models import RetryPolicy


class DomainProfile(BaseModel):
    """Per-domain configuration for HTTP requests.

    Allows customizing headers, timeouts, and other settings per domain.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain_pattern: Annotated[
        str, Field(min_length=1, description="Regex pattern for matching domains")
    ]
    headers: dict[str, str] = Field(
        default_factory=dict, description="Headers to add for this domain"
    )
    timeout_seconds: Annotated[float, Field(ge=1.0, le=300.0)] = 30.0

    @field_validator("domain_pattern")
    @classmethod
    def validate_regex(cls, v: str) -> str:
        """Validate that domain_pattern is a valid regex."""
        try:
            re.compile(v)
        except re.error as e:
            msg = f"Invalid regex pattern: {e}"
            raise ValueError(msg) from e
        return v

    @field_validator("headers")
    @classmethod
    def validate_no_auth_headers(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure no Authorization headers are stored in config."""
        forbidden = {"authorization", "cookie", "x-api-key"}
        for key in v:
            if key.lower() in forbidden:
                msg = (
                    f"Header '{key}' must not be stored in config; "
                    "use environment variables"
                )
                raise ValueError(msg)
        return v

    def matches(self, domain: str) -> bool:
        """Check if this profile matches a domain.

        Args:
            domain: The domain to check.

        Returns:
            True if the pattern matches.
        """
        return bool(re.match(self.domain_pattern, domain))


class FetchConfig(BaseModel):
    """Configuration for the HTTP fetch layer.

    Central configuration for all HTTP fetch operations including
    timeouts, retry policy, and domain-specific settings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_agent: Annotated[str, Field(min_length=1, max_length=500)] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    default_timeout_seconds: Annotated[float, Field(ge=1.0, le=300.0)] = 30.0
    max_response_size_bytes: Annotated[int, Field(ge=1024, le=100 * 1024 * 1024)] = (
        DEFAULT_MAX_RESPONSE_SIZE_BYTES
    )
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    domain_profiles: list[DomainProfile] = Field(default_factory=list)
    fail_fast: bool = Field(
        default=False,
        description="If True, abort entire run on first fetch failure",
    )

    def get_profile_for_domain(self, domain: str) -> DomainProfile | None:
        """Get the domain profile that matches a domain.

        Args:
            domain: The domain to look up.

        Returns:
            Matching DomainProfile, or None if no match.
        """
        for profile in self.domain_profiles:
            if profile.matches(domain):
                return profile
        return None

    def get_timeout_for_domain(self, domain: str) -> float:
        """Get the timeout for a domain.

        Args:
            domain: The domain to look up.

        Returns:
            Timeout in seconds.
        """
        profile = self.get_profile_for_domain(domain)
        if profile:
            return profile.timeout_seconds
        return self.default_timeout_seconds

    def get_headers_for_domain(self, domain: str) -> dict[str, str]:
        """Get headers for a domain.

        Args:
            domain: The domain to look up.

        Returns:
            Dictionary of headers.
        """
        profile = self.get_profile_for_domain(domain)
        if profile:
            return dict(profile.headers)
        return {}
