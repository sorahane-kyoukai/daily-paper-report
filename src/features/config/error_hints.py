"""Error hints for configuration validation errors.

Provides user-friendly hints with actionable remediation steps
for common validation errors.
"""

from typing import Final


# Mapping of error types to user-friendly hints
ERROR_HINTS: Final[dict[str, str]] = {
    # Missing field errors
    "missing": "This field is required. Please add it to your configuration.",
    # Type errors
    "enum": "Check the allowed values in the documentation.",
    "int_type": "This field must be an integer (whole number).",
    "float_type": "This field must be a number.",
    "string_type": "This field must be a text string.",
    "bool_type": "This field must be true or false.",
    "list_type": "This field must be a list/array.",
    "dict_type": "This field must be an object/mapping.",
    # Value constraint errors
    "greater_than_equal": "The value is too small. Check the minimum allowed.",
    "less_than_equal": "The value is too large. Check the maximum allowed.",
    "string_too_short": "The text is too short. Check minimum length requirement.",
    "string_too_long": "The text is too long. Check maximum length requirement.",
    "string_pattern_mismatch": "The format is invalid. Use lowercase letters, numbers, hyphens, or underscores only.",
    # URL errors
    "value_error": "Check the value format. URLs must start with http:// or https://.",
    # Uniqueness errors
    "unique_items": "Duplicate items found. Each item must be unique.",
    # File errors
    "file_not_found": "The file does not exist. Check the file path.",
    "yaml_parse_error": "Invalid YAML syntax. Check for proper indentation and formatting.",
}

# Field-specific hints for more context
FIELD_HINTS: Final[dict[str, str]] = {
    "id": "Use lowercase letters, numbers, hyphens, or underscores (e.g., 'my-source-1').",
    "url": "Must be a valid HTTP/HTTPS URL (e.g., 'https://example.com/feed.xml').",
    "tier": "Must be 0 (highest priority), 1, or 2 (lowest priority).",
    "method": "Must be one of: rss_atom, arxiv_api, openreview_venue, github_releases, hf_org, html_list, html_single, status_only.",
    "kind": "Must be one of: blog, paper, release, news, model, dataset.",
    "region": "Must be 'cn' (China) or 'intl' (International).",
    "keywords": "Must be a non-empty list of search keywords.",
    "prefer_links": "Must be a list of link types: paper, code, model, demo, blog, news, video.",
    "max_items": "Must be between 0 and 1000.",
    "weight": "Must be between 0.0 and 5.0.",
}


def get_error_hint(error_type: str, field_name: str | None = None) -> str:
    """Get a user-friendly hint for a validation error.

    Args:
        error_type: The Pydantic error type (e.g., 'missing', 'enum').
        field_name: Optional field name for field-specific hints.

    Returns:
        A user-friendly hint string.
    """
    # Check for field-specific hint first
    if field_name:
        # Extract the last part of the field path (e.g., 'sources.0.id' -> 'id')
        simple_field = field_name.split(".")[-1]
        if simple_field in FIELD_HINTS:
            return FIELD_HINTS[simple_field]

    # Fall back to error type hint
    return ERROR_HINTS.get(
        error_type, "Check the configuration documentation for valid values."
    )


def format_validation_error(
    location: str,
    message: str,
    error_type: str,
    *,
    include_hint: bool = True,
) -> str:
    """Format a validation error with optional hint.

    Args:
        location: The error location (e.g., 'sources.0.url').
        message: The original error message.
        error_type: The error type.
        include_hint: Whether to include a hint.

    Returns:
        Formatted error string.
    """
    base = f"{location}: {message}"
    if include_hint:
        hint = get_error_hint(error_type, location)
        return f"{base}\n    Hint: {hint}"
    return base
