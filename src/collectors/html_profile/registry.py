"""Registry for domain profiles."""

from threading import Lock
from urllib.parse import urlparse

import structlog

from src.collectors.html_profile.models import DomainProfile
from src.collectors.html_profile.profiles import get_builtin_profile_for_url


logger = structlog.get_logger()


# Module-level singleton state
_registry_instance: "ProfileRegistry | None" = None
_registry_lock: Lock = Lock()


class ProfileRegistry:
    """Thread-safe registry for domain profiles.

    Manages domain profiles and provides lookup by URL or domain.
    Use get_instance() for singleton access.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._profiles: dict[str, DomainProfile] = {}
        self._lock = Lock()
        self._log = logger.bind(component="html_profile")

    @classmethod
    def get_instance(cls) -> "ProfileRegistry":
        """Get the singleton instance (thread-safe).

        Returns:
            The shared ProfileRegistry instance.
        """
        global _registry_instance  # noqa: PLW0603
        if _registry_instance is None:
            with _registry_lock:
                if _registry_instance is None:
                    _registry_instance = cls()
        return _registry_instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        global _registry_instance  # noqa: PLW0603
        with _registry_lock:
            _registry_instance = None

    def register(self, profile: DomainProfile) -> None:
        """Register a domain profile.

        Args:
            profile: The profile to register.
        """
        with self._lock:
            self._profiles[profile.domain] = profile
            self._log.debug(
                "profile_registered",
                domain=profile.domain,
                name=profile.name,
            )

    def unregister(self, domain: str) -> bool:
        """Unregister a domain profile.

        Args:
            domain: The domain to unregister.

        Returns:
            True if the profile was unregistered, False if not found.
        """
        with self._lock:
            if domain in self._profiles:
                del self._profiles[domain]
                self._log.debug("profile_unregistered", domain=domain)
                return True
            return False

    def get_by_domain(self, domain: str) -> DomainProfile | None:
        """Get a profile by domain name.

        Args:
            domain: The domain to look up.

        Returns:
            The profile if found, None otherwise.
        """
        with self._lock:
            # Try exact match first
            if domain in self._profiles:
                return self._profiles[domain]

            # Try parent domains
            parts = domain.split(".")
            for i in range(1, len(parts)):
                parent = ".".join(parts[i:])
                if parent in self._profiles:
                    return self._profiles[parent]

            return None

    def get_by_url(self, url: str) -> DomainProfile | None:
        """Get a profile that matches the given URL.

        Args:
            url: The URL to look up.

        Returns:
            The profile if found, None otherwise.
        """
        parsed = urlparse(url)
        domain = parsed.netloc

        profile = self.get_by_domain(domain)

        # Verify the profile matches the URL patterns
        if profile and profile.matches_url(url):
            return profile

        return profile  # Return even if URL patterns don't match, as default

    def get_or_default(self, url: str) -> DomainProfile:
        """Get a profile for the URL, or create a default one.

        Args:
            url: The URL to look up.

        Returns:
            The matching or default profile.
        """
        profile = self.get_by_url(url)

        if profile:
            return profile

        builtin = get_builtin_profile_for_url(url)
        if builtin is not None:
            return builtin

        # Create default profile for the domain
        parsed = urlparse(url)
        domain = parsed.netloc

        return DomainProfile(
            domain=domain,
            name=f"Default profile for {domain}",
        )

    def list_domains(self) -> list[str]:
        """List all registered domain names.

        Returns:
            List of registered domain names.
        """
        with self._lock:
            return list(self._profiles.keys())

    def count(self) -> int:
        """Get the number of registered profiles.

        Returns:
            Number of profiles.
        """
        with self._lock:
            return len(self._profiles)
