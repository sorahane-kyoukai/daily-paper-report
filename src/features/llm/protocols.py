"""Protocol interface for LLM clients."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmClient(Protocol):
    """Protocol for LLM content generation clients.

    Any client that implements ``generate_content`` with the matching
    signature can be used interchangeably by processors, regardless
    of the underlying authentication mechanism (OAuth or API key).
    """

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        """Generate text from a prompt.

        Args:
            prompt: User prompt text.
            system_instruction: Optional system-level instruction.

        Returns:
            Generated text from the model.

        Raises:
            LlmApiError: If the API call fails.
        """
        ...
