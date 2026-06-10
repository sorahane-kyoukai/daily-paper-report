"""Unit tests for error mapper module."""

from src.collectors.errors import CollectorErrorClass
from src.features.status.error_mapper import (
    map_fetch_error_to_reason_code,
    map_http_status_to_reason_code,
    map_parse_error_to_reason_code,
)
from src.features.status.models import ReasonCode


class TestMapFetchErrorToReasonCode:
    """Tests for map_fetch_error_to_reason_code."""

    def test_generic_fetch_error(self) -> None:
        """Generic fetch error maps to FETCH_NETWORK_ERROR."""
        result = map_fetch_error_to_reason_code(CollectorErrorClass.FETCH)
        assert result == ReasonCode.FETCH_NETWORK_ERROR

    def test_timeout_in_message(self) -> None:
        """Timeout in error message maps to FETCH_TIMEOUT."""
        result = map_fetch_error_to_reason_code(
            CollectorErrorClass.FETCH, "Connection timeout after 30s"
        )
        assert result == ReasonCode.FETCH_TIMEOUT

    def test_ssl_in_message(self) -> None:
        """SSL error in message maps to FETCH_SSL_ERROR."""
        result = map_fetch_error_to_reason_code(
            CollectorErrorClass.FETCH, "SSL certificate verify failed"
        )
        assert result == ReasonCode.FETCH_SSL_ERROR

    def test_certificate_in_message(self) -> None:
        """Certificate error in message maps to FETCH_SSL_ERROR."""
        result = map_fetch_error_to_reason_code(
            CollectorErrorClass.FETCH, "Certificate expired"
        )
        assert result == ReasonCode.FETCH_SSL_ERROR

    def test_too_large_in_message(self) -> None:
        """Too large in message maps to FETCH_TOO_LARGE."""
        result = map_fetch_error_to_reason_code(
            CollectorErrorClass.FETCH, "Response too large"
        )
        assert result == ReasonCode.FETCH_TOO_LARGE

    def test_size_limit_in_message(self) -> None:
        """Size limit in message maps to FETCH_TOO_LARGE."""
        result = map_fetch_error_to_reason_code(
            CollectorErrorClass.FETCH, "Exceeded size limit"
        )
        assert result == ReasonCode.FETCH_TOO_LARGE

    def test_non_fetch_error_class(self) -> None:
        """Non-fetch error class returns FETCH_NETWORK_ERROR."""
        result = map_fetch_error_to_reason_code(CollectorErrorClass.PARSE)
        assert result == ReasonCode.FETCH_NETWORK_ERROR

    def test_none_error_class(self) -> None:
        """None error class returns FETCH_NETWORK_ERROR."""
        result = map_fetch_error_to_reason_code(None)
        assert result == ReasonCode.FETCH_NETWORK_ERROR


class TestMapHttpStatusToReasonCode:
    """Tests for map_http_status_to_reason_code."""

    def test_4xx_status(self) -> None:
        """4xx status maps to FETCH_HTTP_4XX."""
        for status in [400, 401, 403, 404, 429, 499]:
            result = map_http_status_to_reason_code(status)
            assert result == ReasonCode.FETCH_HTTP_4XX, f"Failed for {status}"

    def test_5xx_status(self) -> None:
        """5xx status maps to FETCH_HTTP_5XX."""
        for status in [500, 502, 503, 504, 599]:
            result = map_http_status_to_reason_code(status)
            assert result == ReasonCode.FETCH_HTTP_5XX, f"Failed for {status}"

    def test_none_status(self) -> None:
        """None status returns FETCH_NETWORK_ERROR."""
        result = map_http_status_to_reason_code(None)
        assert result == ReasonCode.FETCH_NETWORK_ERROR

    def test_success_status_returns_network_error(self) -> None:
        """Success status (not an error) returns FETCH_NETWORK_ERROR."""
        result = map_http_status_to_reason_code(200)
        assert result == ReasonCode.FETCH_NETWORK_ERROR


class TestMapParseErrorToReasonCode:
    """Tests for map_parse_error_to_reason_code."""

    def test_schema_error_class(self) -> None:
        """Schema error class maps to PARSE_SCHEMA_ERROR."""
        result = map_parse_error_to_reason_code(CollectorErrorClass.SCHEMA)
        assert result == ReasonCode.PARSE_SCHEMA_ERROR

    def test_xml_in_message(self) -> None:
        """XML in error message maps to PARSE_XML_ERROR."""
        result = map_parse_error_to_reason_code(
            CollectorErrorClass.PARSE, "Failed to parse XML document"
        )
        assert result == ReasonCode.PARSE_XML_ERROR

    def test_json_in_message(self) -> None:
        """JSON in error message maps to PARSE_JSON_ERROR."""
        result = map_parse_error_to_reason_code(
            CollectorErrorClass.PARSE, "Invalid JSON format"
        )
        assert result == ReasonCode.PARSE_JSON_ERROR

    def test_no_items_in_message(self) -> None:
        """No items in message maps to PARSE_NO_ITEMS."""
        result = map_parse_error_to_reason_code(
            CollectorErrorClass.PARSE, "No items found in response"
        )
        assert result == ReasonCode.PARSE_NO_ITEMS

    def test_empty_in_message(self) -> None:
        """Empty in message maps to PARSE_NO_ITEMS."""
        result = map_parse_error_to_reason_code(
            CollectorErrorClass.PARSE, "Response was empty"
        )
        assert result == ReasonCode.PARSE_NO_ITEMS

    def test_generic_parse_error(self) -> None:
        """Generic parse error maps to PARSE_HTML_ERROR."""
        result = map_parse_error_to_reason_code(CollectorErrorClass.PARSE)
        assert result == ReasonCode.PARSE_HTML_ERROR

    def test_none_error_class(self) -> None:
        """None error class returns PARSE_HTML_ERROR."""
        result = map_parse_error_to_reason_code(None)
        assert result == ReasonCode.PARSE_HTML_ERROR
