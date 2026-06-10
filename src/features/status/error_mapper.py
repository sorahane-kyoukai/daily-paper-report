"""Error mapping for source status classification.

Maps collector errors to machine-readable reason codes.
Follows Open/Closed Principle: extend by adding new mappings,
not by modifying existing code.
"""

from src.collectors.errors import CollectorErrorClass
from src.features.status.models import ReasonCode


# HTTP status code boundaries (standard ranges)
_HTTP_CLIENT_ERROR_MIN = 400
_HTTP_CLIENT_ERROR_MAX = 500
_HTTP_SERVER_ERROR_MIN = 500
_HTTP_SERVER_ERROR_MAX = 600


def map_fetch_error_to_reason_code(
    error_class: CollectorErrorClass | None,
    error_message: str | None = None,
) -> ReasonCode:
    """Map a fetch error to an appropriate reason code.

    Args:
        error_class: Error class from collector.
        error_message: Optional error message for more specific mapping.

    Returns:
        Appropriate reason code for the fetch error.
    """
    if error_class != CollectorErrorClass.FETCH:
        return ReasonCode.FETCH_NETWORK_ERROR

    if error_message:
        msg_lower = error_message.lower()
        if "timeout" in msg_lower:
            return ReasonCode.FETCH_TIMEOUT
        if "ssl" in msg_lower or "certificate" in msg_lower:
            return ReasonCode.FETCH_SSL_ERROR
        if "too large" in msg_lower or "size limit" in msg_lower:
            return ReasonCode.FETCH_TOO_LARGE
        if "rate limit" in msg_lower or "429" in msg_lower:
            return ReasonCode.FETCH_HTTP_4XX

    return ReasonCode.FETCH_NETWORK_ERROR


def map_http_status_to_reason_code(status_code: int | None) -> ReasonCode:
    """Map an HTTP status code to an appropriate reason code.

    Args:
        status_code: HTTP status code (4xx or 5xx).

    Returns:
        Appropriate reason code for the HTTP status.
    """
    if status_code is None:
        return ReasonCode.FETCH_NETWORK_ERROR

    if _HTTP_CLIENT_ERROR_MIN <= status_code < _HTTP_CLIENT_ERROR_MAX:
        return ReasonCode.FETCH_HTTP_4XX

    if _HTTP_SERVER_ERROR_MIN <= status_code < _HTTP_SERVER_ERROR_MAX:
        return ReasonCode.FETCH_HTTP_5XX

    return ReasonCode.FETCH_NETWORK_ERROR


def map_parse_error_to_reason_code(
    error_class: CollectorErrorClass | None,
    error_message: str | None = None,
) -> ReasonCode:
    """Map a parse error to an appropriate reason code.

    Args:
        error_class: Error class from collector.
        error_message: Optional error message for more specific mapping.

    Returns:
        Appropriate reason code for the parse error.
    """
    if error_class == CollectorErrorClass.SCHEMA:
        return ReasonCode.PARSE_SCHEMA_ERROR

    if error_message:
        msg_lower = error_message.lower()
        if "xml" in msg_lower:
            return ReasonCode.PARSE_XML_ERROR
        if "json" in msg_lower:
            return ReasonCode.PARSE_JSON_ERROR
        if "no items" in msg_lower or "empty" in msg_lower:
            return ReasonCode.PARSE_NO_ITEMS

    return ReasonCode.PARSE_HTML_ERROR
