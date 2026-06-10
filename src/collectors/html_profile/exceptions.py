"""Exception hierarchy for HTML profile parsing.

This module defines domain-specific exceptions for the html_profile
module, enabling better error handling and debugging.
"""


class HtmlProfileError(Exception):
    """Base exception for HTML profile operations.

    All html_profile exceptions inherit from this class,
    allowing callers to catch all module-specific errors.
    """

    def __init__(self, message: str, *, domain: str | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            domain: Domain associated with the error.
        """
        super().__init__(message)
        self.domain = domain


class ContentTypeError(HtmlProfileError):
    """Raised when content type is not allowed.

    This error occurs when a response has a content type that is not
    in the profile's allowed_content_types list (e.g., binary files).
    """

    def __init__(
        self,
        message: str,
        *,
        content_type: str,
        domain: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            content_type: The rejected content type.
            domain: Domain associated with the error.
        """
        super().__init__(message, domain=domain)
        self.content_type = content_type


class CrossDomainRedirectError(HtmlProfileError):
    """Raised when a cross-domain redirect is blocked.

    This error occurs when a response redirects to a domain that is
    not in the profile's allowed_redirect_domains list.
    """

    def __init__(
        self,
        message: str,
        *,
        from_domain: str,
        to_domain: str,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            from_domain: Original domain.
            to_domain: Blocked redirect target domain.
        """
        super().__init__(message, domain=from_domain)
        self.from_domain = from_domain
        self.to_domain = to_domain


class DateExtractionError(HtmlProfileError):
    """Raised when date extraction fails unexpectedly.

    This error occurs when date parsing fails due to malformed
    content or unexpected HTML structure.
    """

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        raw_date: str | None = None,
        domain: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            method: Extraction method that failed.
            raw_date: The raw date string that failed to parse.
            domain: Domain associated with the error.
        """
        super().__init__(message, domain=domain)
        self.method = method
        self.raw_date = raw_date


class ProfileNotFoundError(HtmlProfileError):
    """Raised when a required profile is not found.

    This error occurs when a profile lookup fails and no default
    profile is acceptable for the operation.
    """

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        domain: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            url: URL that triggered the lookup.
            domain: Domain that was looked up.
        """
        super().__init__(message, domain=domain)
        self.url = url


class ItemPageFetchError(HtmlProfileError):
    """Raised when item page fetch fails.

    This error occurs when fetching an item page for date recovery
    fails due to network errors, timeouts, or other issues.
    """

    def __init__(
        self,
        message: str,
        *,
        url: str,
        domain: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            url: URL that failed to fetch.
            domain: Domain associated with the error.
            cause: Underlying exception that caused the failure.
        """
        super().__init__(message, domain=domain)
        self.url = url
        self.cause = cause
