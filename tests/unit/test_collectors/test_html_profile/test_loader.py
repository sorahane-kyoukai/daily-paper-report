"""Tests for YAML profile loader."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from src.collectors.html_profile.exceptions import ProfileNotFoundError
from src.collectors.html_profile.loader import (
    load_profiles_from_directory,
    load_profiles_from_yaml,
)
from src.collectors.html_profile.registry import ProfileRegistry


class TestLoadProfilesFromYaml:
    """Tests for load_profiles_from_yaml function."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        ProfileRegistry.reset()

    def test_load_from_dict_single_profile(self) -> None:
        """Test loading a single profile from dict."""
        data = {
            "domain": "example.com",
            "name": "Example Profile",
        }
        profiles = load_profiles_from_yaml(data, register=False)
        assert len(profiles) == 1
        assert profiles[0].domain == "example.com"
        assert profiles[0].name == "Example Profile"

    def test_load_from_dict_list_of_profiles(self) -> None:
        """Test loading multiple profiles from list."""
        data = [
            {"domain": "a.com", "name": "Profile A"},
            {"domain": "b.com", "name": "Profile B"},
        ]
        profiles = load_profiles_from_yaml(data, register=False)
        assert len(profiles) == 2
        assert profiles[0].domain == "a.com"
        assert profiles[1].domain == "b.com"

    def test_load_from_dict_with_profiles_key(self) -> None:
        """Test loading from dict with 'profiles' key."""
        data = {
            "profiles": [
                {"domain": "x.com", "name": "X"},
                {"domain": "y.com", "name": "Y"},
            ]
        }
        profiles = load_profiles_from_yaml(data, register=False)
        assert len(profiles) == 2

    def test_load_with_nested_rules(self) -> None:
        """Test loading profile with nested rules."""
        data = {
            "domain": "blog.example.com",
            "name": "Blog Profile",
            "link_rules": {
                "container_selector": ".post",
                "link_selector": "a.title",
            },
            "date_rules": {
                "time_selector": "time.published",
            },
        }
        profiles = load_profiles_from_yaml(data, register=False)
        assert len(profiles) == 1
        profile = profiles[0]
        assert profile.link_rules.container_selector == ".post"
        assert profile.date_rules.time_selector == "time.published"

    def test_load_from_file(self) -> None:
        """Test loading from YAML file."""
        with TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "profiles.yaml"
            data = {"domain": "test.com", "name": "Test"}
            yaml_path.write_text(yaml.dump(data))

            profiles = load_profiles_from_yaml(yaml_path, register=False)
            assert len(profiles) == 1
            assert profiles[0].domain == "test.com"

    def test_load_and_register(self) -> None:
        """Test that profiles are registered when register=True."""
        data = {"domain": "registered.com", "name": "Registered"}
        registry = ProfileRegistry()

        load_profiles_from_yaml(data, register=True, registry=registry)

        assert registry.get_by_domain("registered.com") is not None

    def test_file_not_found(self) -> None:
        """Test error when file not found."""
        with pytest.raises(ProfileNotFoundError):
            load_profiles_from_yaml("/nonexistent/path.yaml")

    def test_empty_data(self) -> None:
        """Test error when data is empty."""
        with pytest.raises(ProfileNotFoundError):
            load_profiles_from_yaml({}, register=False)


class TestLoadProfilesFromDirectory:
    """Tests for load_profiles_from_directory function."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        ProfileRegistry.reset()

    def test_load_multiple_files(self) -> None:
        """Test loading profiles from multiple YAML files."""
        with TemporaryDirectory() as tmpdir:
            # Create multiple YAML files
            (Path(tmpdir) / "a.yaml").write_text(
                yaml.dump({"domain": "a.com", "name": "A"})
            )
            (Path(tmpdir) / "b.yaml").write_text(
                yaml.dump({"domain": "b.com", "name": "B"})
            )

            profiles = load_profiles_from_directory(tmpdir, register=False)
            assert len(profiles) == 2
            domains = {p.domain for p in profiles}
            assert domains == {"a.com", "b.com"}

    def test_nonexistent_directory(self) -> None:
        """Test returns empty list for nonexistent directory."""
        profiles = load_profiles_from_directory("/nonexistent/dir", register=False)
        assert profiles == []

    def test_custom_pattern(self) -> None:
        """Test custom file pattern."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "profile.yaml").write_text(
                yaml.dump({"domain": "yaml.com", "name": "YAML"})
            )
            (Path(tmpdir) / "profile.yml").write_text(
                yaml.dump({"domain": "yml.com", "name": "YML"})
            )

            # Only .yaml files
            profiles = load_profiles_from_directory(
                tmpdir, pattern="*.yaml", register=False
            )
            assert len(profiles) == 1
            assert profiles[0].domain == "yaml.com"
