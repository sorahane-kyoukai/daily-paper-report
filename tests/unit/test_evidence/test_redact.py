"""Unit tests for evidence redaction utilities."""

from src.features.evidence.redact import (
    SecretMatch,
    contains_secrets,
    get_secret_patterns,
    redact_content,
    scan_for_secrets,
)


class TestScanForSecrets:
    """Tests for scan_for_secrets function."""

    def test_detects_sk_api_key(self) -> None:
        """Should detect OpenAI-style sk- API keys."""
        content = "My API key is sk-abcdefghijklmnopqrstuvwxyz1234"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "api_key_sk" for m in matches)

    def test_detects_github_token(self) -> None:
        """Should detect GitHub PAT tokens."""
        content = "Use this token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "github_classic" for m in matches)

    def test_detects_hf_token(self) -> None:
        """Should detect HuggingFace tokens."""
        content = "HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz12345678"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "hf_token" for m in matches)

    def test_detects_bearer_token(self) -> None:
        """Should detect Bearer tokens in headers."""
        content = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "bearer_token" for m in matches)

    def test_detects_password_assignment(self) -> None:
        """Should detect password assignments."""
        content = 'password = "supersecret123"'
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "password_value" for m in matches)

    def test_detects_secret_assignment(self) -> None:
        """Should detect secret assignments."""
        content = "secret: myverylongsecretvalue123456"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "secret_value" for m in matches)

    def test_detects_aws_access_key(self) -> None:
        """Should detect AWS access keys."""
        content = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "aws_access_key" for m in matches)

    def test_detects_authorization_header(self) -> None:
        """Should detect Authorization headers."""
        content = "Authorization: Basic dXNlcjpwYXNz"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "auth_header" for m in matches)

    def test_detects_cookie_header(self) -> None:
        """Should detect Cookie headers."""
        content = "Cookie: session=abc123; user=john"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "cookie_header" for m in matches)

    def test_detects_google_oauth_access_token(self) -> None:
        """Should detect Google OAuth access tokens (ya29.*)."""
        content = "Token: ya29.a0ARrdaM_test-token-value_here.long"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "google_oauth_access" for m in matches)

    def test_detects_google_oauth_refresh_token(self) -> None:
        """Should detect Google OAuth refresh tokens (1//...)."""
        content = "REFRESH=1//0eFQmRBV3xkz-test-refresh-token"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "google_oauth_refresh" for m in matches)

    def test_returns_empty_for_safe_content(self) -> None:
        """Should return empty list for content without secrets."""
        content = "This is a normal log message with no secrets."
        matches = scan_for_secrets(content)
        assert len(matches) == 0

    def test_returns_match_positions(self) -> None:
        """Should return correct match positions."""
        content = "key: sk-abcdefghijklmnopqrstuvwxyz1234"
        matches = scan_for_secrets(content)
        assert len(matches) >= 1
        match = next(m for m in matches if m.pattern_name == "api_key_sk")
        assert match.start >= 0
        assert match.end > match.start
        assert content[match.start : match.end] == match.matched_text


class TestRedactContent:
    """Tests for redact_content function."""

    def test_redacts_sk_api_key(self) -> None:
        """Should redact sk- API keys."""
        content = "Key: sk-abcdefghijklmnopqrstuvwxyz1234"
        redacted = redact_content(content)
        assert "sk-" not in redacted
        assert "[REDACTED]" in redacted

    def test_redacts_github_token(self) -> None:
        """Should redact GitHub tokens."""
        content = "Token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        redacted = redact_content(content)
        assert "ghp_" not in redacted
        assert "[REDACTED]" in redacted

    def test_redacts_multiple_secrets(self) -> None:
        """Should redact multiple different secrets."""
        content = """
        API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234
        HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz12345678
        """
        redacted = redact_content(content)
        assert "sk-" not in redacted
        assert "hf_" not in redacted
        assert redacted.count("[REDACTED]") >= 2

    def test_preserves_safe_content(self) -> None:
        """Should not modify content without secrets."""
        content = "This is a normal log with run_id=abc123"
        redacted = redact_content(content)
        assert redacted == content

    def test_redacts_google_oauth_access_token(self) -> None:
        """Should redact Google OAuth access tokens."""
        content = "Token: ya29.a0ARrdaM_test-token-value.long"
        redacted = redact_content(content)
        assert "ya29." not in redacted
        assert "[REDACTED]" in redacted

    def test_redacts_google_oauth_refresh_token(self) -> None:
        """Should redact Google OAuth refresh tokens."""
        content = "REFRESH=1//0eFQmRBV3xkz-test-refresh"
        redacted = redact_content(content)
        assert "1//" not in redacted
        assert "[REDACTED]" in redacted

    def test_redacts_authorization_header(self) -> None:
        """Should redact entire Authorization header."""
        content = "Authorization: Bearer abc123.xyz.789"
        redacted = redact_content(content)
        assert "abc123" not in redacted
        assert "[REDACTED]" in redacted


class TestContainsSecrets:
    """Tests for contains_secrets function."""

    def test_returns_true_for_secrets(self) -> None:
        """Should return True when secrets are present."""
        content = "key: sk-abcdefghijklmnopqrstuvwxyz1234"
        assert contains_secrets(content) is True

    def test_returns_false_for_safe_content(self) -> None:
        """Should return False when no secrets are present."""
        content = "Normal log message: run completed successfully"
        assert contains_secrets(content) is False


class TestGetSecretPatterns:
    """Tests for get_secret_patterns function."""

    def test_returns_pattern_names(self) -> None:
        """Should return list of pattern names."""
        patterns = get_secret_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(isinstance(p, str) for p in patterns)

    def test_includes_common_patterns(self) -> None:
        """Should include common secret pattern names."""
        patterns = get_secret_patterns()
        assert "api_key_sk" in patterns
        assert "github_token" in patterns
        assert "hf_token" in patterns
        assert "bearer_token" in patterns
        assert "google_oauth_access" in patterns
        assert "google_oauth_refresh" in patterns


class TestSecretMatch:
    """Tests for SecretMatch named tuple."""

    def test_creates_valid_match(self) -> None:
        """Should create a valid SecretMatch."""
        match = SecretMatch(
            pattern_name="api_key_sk",
            matched_text="sk-abc123",
            start=10,
            end=20,
        )
        assert match.pattern_name == "api_key_sk"
        assert match.matched_text == "sk-abc123"
        assert match.start == 10
        assert match.end == 20
