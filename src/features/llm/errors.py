"""Domain-specific error types for the LLM module."""


class LlmAuthError(Exception):
    """OAuth token refresh failure."""


class LlmApiError(Exception):
    """CodeAssist API call failure.

    Attributes:
        status_code: HTTP status code from the API response.
    """

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlmProcessingError(Exception):
    """Response parsing or processing failure."""
