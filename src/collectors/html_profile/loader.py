"""YAML-based profile loading for HTML domain profiles.

This module provides functions to load domain profiles from YAML files,
enabling configuration-driven profile management.
"""

from pathlib import Path
from typing import Any

import structlog
import yaml

from src.collectors.html_profile.exceptions import ProfileNotFoundError
from src.collectors.html_profile.models import (
    DateExtractionRule,
    DomainProfile,
    LinkExtractionRule,
)
from src.collectors.html_profile.registry import ProfileRegistry


logger = structlog.get_logger()


def load_profiles_from_yaml(
    source: str | Path | dict[str, Any] | list[dict[str, Any]],
    *,
    register: bool = True,
    registry: ProfileRegistry | None = None,
) -> list[DomainProfile]:
    """Load domain profiles from YAML source.

    Supports loading from:
    - File path (str or Path)
    - Dictionary (already parsed YAML)

    Args:
        source: YAML file path or parsed dictionary.
        register: Whether to register profiles with the registry.
        registry: Registry to use (defaults to singleton).

    Returns:
        List of loaded DomainProfile objects.

    Raises:
        ProfileNotFoundError: If file not found or empty.
        yaml.YAMLError: If YAML parsing fails.
        ValueError: If profile configuration is invalid.
    """
    log = logger.bind(component="profile_loader")

    # Parse YAML if source is a path
    if isinstance(source, str | Path):
        path = Path(source)
        if not path.exists():
            raise ProfileNotFoundError(
                f"Profile file not found: {path}",
                url=str(path),
            )

        log.debug("loading_profiles_from_file", path=str(path))
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    else:
        data = source

    if not data:
        raise ProfileNotFoundError(
            "Empty or invalid profile configuration",
        )

    # Handle both single profile and list of profiles
    profiles_data: list[dict[str, Any]]
    if isinstance(data, list):
        profiles_data = data
    elif isinstance(data, dict) and "profiles" in data:
        profiles_data = data["profiles"]
    elif isinstance(data, dict):
        profiles_data = [data]
    else:
        raise ValueError(f"Invalid profile configuration format: {type(data)}")

    # Parse profiles
    profiles: list[DomainProfile] = []
    for profile_dict in profiles_data:
        profile = _parse_profile(profile_dict)
        profiles.append(profile)
        log.debug("profile_loaded", domain=profile.domain, name=profile.name)

    # Register if requested
    if register:
        reg = registry or ProfileRegistry.get_instance()
        for profile in profiles:
            reg.register(profile)
        log.info(
            "profiles_registered",
            count=len(profiles),
            domains=[p.domain for p in profiles],
        )

    return profiles


def _parse_profile(data: dict[str, Any]) -> DomainProfile:
    """Parse a single profile from dictionary.

    Args:
        data: Profile configuration dictionary.

    Returns:
        Parsed DomainProfile.

    Raises:
        ValueError: If required fields are missing.
    """
    # Extract nested rules if present
    link_rules_data = data.pop("link_rules", None)
    date_rules_data = data.pop("date_rules", None)

    # Build nested models
    link_rules = LinkExtractionRule(**link_rules_data) if link_rules_data else None
    date_rules = DateExtractionRule(**date_rules_data) if date_rules_data else None

    # Build profile with optional rules
    profile_kwargs: dict[str, Any] = dict(data)
    if link_rules:
        profile_kwargs["link_rules"] = link_rules
    if date_rules:
        profile_kwargs["date_rules"] = date_rules

    return DomainProfile(**profile_kwargs)


def load_profiles_from_directory(
    directory: str | Path,
    *,
    pattern: str = "*.yaml",
    register: bool = True,
    registry: ProfileRegistry | None = None,
) -> list[DomainProfile]:
    """Load all profiles from a directory.

    Args:
        directory: Directory path to scan.
        pattern: Glob pattern for YAML files.
        register: Whether to register profiles.
        registry: Registry to use.

    Returns:
        List of all loaded profiles.
    """
    log = logger.bind(component="profile_loader")
    dir_path = Path(directory)

    if not dir_path.exists():
        log.warning("profile_directory_not_found", path=str(dir_path))
        return []

    all_profiles: list[DomainProfile] = []
    for yaml_file in sorted(dir_path.glob(pattern)):
        try:
            profiles = load_profiles_from_yaml(
                yaml_file,
                register=register,
                registry=registry,
            )
            all_profiles.extend(profiles)
        except Exception:
            log.exception(
                "profile_load_failed",
                path=str(yaml_file),
            )

    return all_profiles
