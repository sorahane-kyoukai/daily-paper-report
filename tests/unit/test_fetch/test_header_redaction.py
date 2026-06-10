"""Unit tests for header redaction."""

import pytest

from src.features.fetch.redact import (
    REDACTED_VALUE,
    is_sensitive_header,
    redact_headers,
    redact_url_credentials,
)


class TestRedactHeaders:
    """Tests for header redaction."""

    def test_redacts_authorization(self) -> None:
        """Test that Authorization header is redacted."""
        headers = {
            "Authorization": "Bearer secret-token-12345",
            "Content-Type": "application/json",
        }

        result = redact_headers(headers)

        assert result["Authorization"] == REDACTED_VALUE
        assert result["Content-Type"] == "application/json"

    def test_redacts_authorization_case_insensitive(self) -> None:
        """Test that authorization header is redacted regardless of case."""
        headers_variants = [
            {"authorization": "Bearer token"},
            {"AUTHORIZATION": "Bearer token"},
            {"Authorization": "Bearer token"},
        ]

        for headers in headers_variants:
            result = redact_headers(headers)
            key = list(headers.keys())[0]
            assert result[key] == REDACTED_VALUE

    def test_redacts_cookie(self) -> None:
        """Test that Cookie header is redacted."""
        headers = {
            "Cookie": "session=abc123; user_id=456",
            "Accept": "text/html",
        }

        result = redact_headers(headers)

        assert result["Cookie"] == REDACTED_VALUE
        assert result["Accept"] == "text/html"

    def test_redacts_set_cookie(self) -> None:
        """Test that Set-Cookie header is redacted."""
        headers = {
            "Set-Cookie": "session=abc123; HttpOnly; Secure",
        }

        result = redact_headers(headers)

        assert result["Set-Cookie"] == REDACTED_VALUE

    def test_redacts_x_api_key(self) -> None:
        """Test that X-API-Key header is redacted."""
        headers = {
            "X-API-Key": "my-secret-api-key",
            "X-Request-Id": "12345",
        }

        result = redact_headers(headers)

        assert result["X-API-Key"] == REDACTED_VALUE
        assert result["X-Request-Id"] == "12345"

    def test_redacts_x_auth_token(self) -> None:
        """Test that X-Auth-Token header is redacted."""
        headers = {
            "X-Auth-Token": "auth-token-value",
        }

        result = redact_headers(headers)

        assert result["X-Auth-Token"] == REDACTED_VALUE

    def test_redacts_proxy_authorization(self) -> None:
        """Test that Proxy-Authorization header is redacted."""
        headers = {
            "Proxy-Authorization": "Basic dXNlcjpwYXNz",
        }

        result = redact_headers(headers)

        assert result["Proxy-Authorization"] == REDACTED_VALUE

    def test_preserves_non_sensitive_headers(self) -> None:
        """Test that non-sensitive headers are preserved."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MyApp/1.0",
            "Cache-Control": "no-cache",
            "X-Request-Id": "abc123",
        }

        result = redact_headers(headers)

        assert result == headers

    def test_returns_new_dict(self) -> None:
        """Test that redaction returns a new dictionary."""
        headers = {"Authorization": "Bearer token"}

        result = redact_headers(headers)

        assert result is not headers
        # Original unchanged
        assert headers["Authorization"] == "Bearer token"

    def test_empty_headers(self) -> None:
        """Test redaction of empty headers dict."""
        result = redact_headers({})
        assert result == {}

    def test_multiple_sensitive_headers(self) -> None:
        """Test redaction of multiple sensitive headers."""
        headers = {
            "Authorization": "Bearer token",
            "Cookie": "session=abc",
            "X-API-Key": "api-key",
            "Content-Type": "text/plain",
        }

        result = redact_headers(headers)

        assert result["Authorization"] == REDACTED_VALUE
        assert result["Cookie"] == REDACTED_VALUE
        assert result["X-API-Key"] == REDACTED_VALUE
        assert result["Content-Type"] == "text/plain"


class TestIsSensitiveHeader:
    """Tests for is_sensitive_header function."""

    @pytest.mark.parametrize(
        "header",
        [
            "authorization",
            "Authorization",
            "AUTHORIZATION",
            "cookie",
            "Cookie",
            "COOKIE",
            "x-api-key",
            "X-API-Key",
            "X-AUTH-TOKEN",
            "x-auth-token",
            "proxy-authorization",
            "set-cookie",
        ],
    )
    def test_sensitive_headers_detected(self, header: str) -> None:
        """Test that sensitive headers are detected."""
        assert is_sensitive_header(header) is True

    @pytest.mark.parametrize(
        "header",
        [
            "Content-Type",
            "Accept",
            "User-Agent",
            "Cache-Control",
            "X-Request-Id",
            "ETag",
            "Last-Modified",
            "If-None-Match",
        ],
    )
    def test_non_sensitive_headers_not_detected(self, header: str) -> None:
        """Test that non-sensitive headers are not flagged."""
        assert is_sensitive_header(header) is False


class TestRedactUrlCredentials:
    """Tests for URL credential redaction."""

    def test_redacts_basic_auth_in_url(self) -> None:
        """Test redacting user:password in URL."""
        url = "https://user:password@example.com/path"

        result = redact_url_credentials(url)

        assert result == "https://[REDACTED]:[REDACTED]@example.com/path"

    def test_redacts_http_url(self) -> None:
        """Test redacting credentials in HTTP URL."""
        url = "http://admin:secret123@localhost:8080/api"

        result = redact_url_credentials(url)

        assert result == "http://[REDACTED]:[REDACTED]@localhost:8080/api"

    def test_preserves_url_without_credentials(self) -> None:
        """Test that URLs without credentials are unchanged."""
        url = "https://example.com/path?query=value"

        result = redact_url_credentials(url)

        assert result == url

    def test_preserves_url_with_at_symbol_in_path(self) -> None:
        """Test that @ in path doesn't trigger redaction."""
        url = "https://example.com/user@domain/resource"

        result = redact_url_credentials(url)

        # This URL has @ but not in credentials format
        assert "@" in result

    def test_complex_password_characters(self) -> None:
        """Test redaction with special characters in password."""
        url = "https://user:p@ss:w0rd!@example.com/path"

        result = redact_url_credentials(url)

        assert "[REDACTED]" in result
        assert "p@ss:w0rd!" not in result
