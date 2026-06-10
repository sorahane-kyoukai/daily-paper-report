"""Tests for profile registry."""

from src.collectors.html_profile.models import DomainProfile
from src.collectors.html_profile.registry import ProfileRegistry


class TestProfileRegistry:
    """Tests for ProfileRegistry class."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        ProfileRegistry.reset()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        ProfileRegistry.reset()

    def test_singleton_instance(self) -> None:
        """Test singleton pattern."""
        instance1 = ProfileRegistry.get_instance()
        instance2 = ProfileRegistry.get_instance()

        assert instance1 is instance2

    def test_register_profile(self) -> None:
        """Test registering a profile."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")

        registry.register(profile)

        assert registry.count() == 1
        assert "example.com" in registry.list_domains()

    def test_get_by_domain_exact_match(self) -> None:
        """Test getting profile by exact domain match."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")
        registry.register(profile)

        result = registry.get_by_domain("example.com")

        assert result is not None
        assert result.domain == "example.com"

    def test_get_by_domain_subdomain_fallback(self) -> None:
        """Test getting profile for subdomain falls back to parent."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")
        registry.register(profile)

        result = registry.get_by_domain("blog.example.com")

        assert result is not None
        assert result.domain == "example.com"

    def test_get_by_domain_not_found(self) -> None:
        """Test getting non-existent domain returns None."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")
        registry.register(profile)

        result = registry.get_by_domain("other.com")

        assert result is None

    def test_get_by_url(self) -> None:
        """Test getting profile by URL."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="blog.example.com", name="Blog Profile")
        registry.register(profile)

        result = registry.get_by_url("https://blog.example.com/posts/123")

        assert result is not None
        assert result.domain == "blog.example.com"

    def test_get_or_default_existing(self) -> None:
        """Test get_or_default returns existing profile."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")
        registry.register(profile)

        result = registry.get_or_default("https://example.com/page")

        assert result.domain == "example.com"
        assert result.name == "Example Profile"

    def test_get_or_default_creates_default(self) -> None:
        """Test get_or_default creates default for unknown domain."""
        registry = ProfileRegistry()

        result = registry.get_or_default("https://unknown.com/page")

        assert result.domain == "unknown.com"
        assert "Default profile" in result.name

    def test_unregister_profile(self) -> None:
        """Test unregistering a profile."""
        registry = ProfileRegistry()
        profile = DomainProfile(domain="example.com", name="Example Profile")
        registry.register(profile)

        success = registry.unregister("example.com")

        assert success is True
        assert registry.count() == 0
        assert registry.get_by_domain("example.com") is None

    def test_unregister_nonexistent(self) -> None:
        """Test unregistering non-existent profile returns False."""
        registry = ProfileRegistry()

        success = registry.unregister("nonexistent.com")

        assert success is False

    def test_list_domains(self) -> None:
        """Test listing registered domains."""
        registry = ProfileRegistry()
        registry.register(DomainProfile(domain="a.com", name="A"))
        registry.register(DomainProfile(domain="b.com", name="B"))
        registry.register(DomainProfile(domain="c.com", name="C"))

        domains = registry.list_domains()

        assert len(domains) == 3
        assert "a.com" in domains
        assert "b.com" in domains
        assert "c.com" in domains

    def test_register_overwrites_existing(self) -> None:
        """Test that registering same domain overwrites."""
        registry = ProfileRegistry()
        profile1 = DomainProfile(domain="example.com", name="Profile 1")
        profile2 = DomainProfile(domain="example.com", name="Profile 2")

        registry.register(profile1)
        registry.register(profile2)

        result = registry.get_by_domain("example.com")
        assert result is not None
        assert result.name == "Profile 2"
        assert registry.count() == 1
