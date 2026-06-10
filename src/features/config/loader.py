"""Configuration loader with validation and state machine."""

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml
from pydantic import ValidationError

from src.features.config.schemas.entities import EntitiesConfig
from src.features.config.schemas.sources import SourcesConfig
from src.features.config.schemas.topics import TopicsConfig
from src.features.config.state_machine import ConfigState, ConfigStateMachine


if TYPE_CHECKING:
    from src.features.config.effective import EffectiveConfig

logger = structlog.get_logger()


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, errors: list[dict[str, str]], file_path: str) -> None:
        """Initialize the error.

        Args:
            errors: List of validation error details.
            file_path: Path to the file that failed validation.
        """
        self.errors = errors
        self.file_path = file_path
        super().__init__(f"Validation failed for {file_path}: {len(errors)} errors")


class ConfigLoader:
    """Loads and validates configuration files.

    Implements a state machine for configuration loading:
    UNLOADED -> LOADING -> VALIDATED -> READY

    Configuration is immutable once VALIDATED.
    """

    def __init__(self, run_id: str) -> None:
        """Initialize the loader.

        Args:
            run_id: Unique identifier for the current run.
        """
        self._run_id = run_id
        self._state_machine = ConfigStateMachine()
        self._sources: SourcesConfig | None = None
        self._entities: EntitiesConfig | None = None
        self._topics: TopicsConfig | None = None
        self._file_checksums: dict[str, str] = {}
        self._validation_errors: list[dict[str, str]] = []
        self._validation_duration_ms: float = 0

    @property
    def state(self) -> ConfigState:
        """Get the current loader state."""
        return self._state_machine.state

    @property
    def file_checksums(self) -> dict[str, str]:
        """Get SHA-256 checksums of loaded files."""
        return self._file_checksums.copy()

    @property
    def validation_errors(self) -> list[dict[str, str]]:
        """Get validation errors if any."""
        return self._validation_errors.copy()

    @property
    def validation_duration_ms(self) -> float:
        """Get validation duration in milliseconds."""
        return self._validation_duration_ms

    def _compute_checksum(self, content: bytes) -> str:
        """Compute SHA-256 checksum of content."""
        return hashlib.sha256(content).hexdigest()

    def _load_yaml_file(self, file_path: Path) -> tuple[dict[str, object], str]:
        """Load a YAML file and compute its checksum.

        Args:
            file_path: Path to the YAML file.

        Returns:
            Tuple of (parsed content, checksum).

        Raises:
            FileNotFoundError: If file does not exist.
            yaml.YAMLError: If YAML parsing fails.
        """
        content_bytes = file_path.read_bytes()
        checksum = self._compute_checksum(content_bytes)
        content_str = content_bytes.decode("utf-8")
        parsed: dict[str, object] = yaml.safe_load(content_str) or {}
        return parsed, checksum

    def load(
        self,
        sources_path: Path,
        entities_path: Path,
        topics_path: Path,
    ) -> "EffectiveConfig":
        """Load and validate all configuration files.

        Args:
            sources_path: Path to sources.yaml.
            entities_path: Path to entities.yaml.
            topics_path: Path to topics.yaml.

        Returns:
            EffectiveConfig with all validated configurations.

        Raises:
            ConfigValidationError: If validation fails.
            ConfigStateError: If called in invalid state.
        """
        from src.features.config.effective import EffectiveConfig

        start_time = time.perf_counter()

        # Transition to LOADING state
        self._state_machine.transition(ConfigState.LOADING)

        log = logger.bind(
            run_id=self._run_id,
            component="config",
            phase="LOADING",
        )

        try:
            # Load sources.yaml
            log.info(
                "loading_config_file",
                file_path=str(sources_path),
                file_type="sources",
            )
            sources_data, sources_checksum = self._load_yaml_file(sources_path)
            self._file_checksums[str(sources_path.resolve())] = sources_checksum
            self._sources = SourcesConfig.model_validate(sources_data)
            log.info(
                "config_file_loaded",
                file_path=str(sources_path),
                file_sha256=sources_checksum,
                source_count=len(self._sources.sources),
            )

            # Load entities.yaml
            log.info(
                "loading_config_file",
                file_path=str(entities_path),
                file_type="entities",
            )
            entities_data, entities_checksum = self._load_yaml_file(entities_path)
            self._file_checksums[str(entities_path.resolve())] = entities_checksum
            self._entities = EntitiesConfig.model_validate(entities_data)
            log.info(
                "config_file_loaded",
                file_path=str(entities_path),
                file_sha256=entities_checksum,
                entity_count=len(self._entities.entities),
            )

            # Load topics.yaml
            log.info(
                "loading_config_file",
                file_path=str(topics_path),
                file_type="topics",
            )
            topics_data, topics_checksum = self._load_yaml_file(topics_path)
            self._file_checksums[str(topics_path.resolve())] = topics_checksum
            self._topics = TopicsConfig.model_validate(topics_data)
            log.info(
                "config_file_loaded",
                file_path=str(topics_path),
                file_sha256=topics_checksum,
                topic_count=len(self._topics.topics),
            )

            # Transition to VALIDATED
            self._state_machine.transition(ConfigState.VALIDATED)

            end_time = time.perf_counter()
            self._validation_duration_ms = (end_time - start_time) * 1000

            log.info(
                "config_validation_complete",
                phase="VALIDATED",
                validation_error_count=0,
                config_validation_duration_ms=self._validation_duration_ms,
            )

            # Create effective config and transition to READY
            effective = EffectiveConfig(
                sources=self._sources,
                entities=self._entities,
                topics=self._topics,
                file_checksums=self._file_checksums.copy(),
                run_id=self._run_id,
            )

            self._state_machine.transition(ConfigState.READY)
            log.info("config_ready", phase="READY")

            return effective

        except ValidationError as e:
            self._handle_validation_error(e, log)
            raise

        except FileNotFoundError as e:
            self._handle_file_error(e, log)
            raise

        except yaml.YAMLError as e:
            self._handle_yaml_error(e, log)
            raise

    def _handle_validation_error(
        self,
        error: ValidationError,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Handle Pydantic validation error."""
        self._state_machine.transition(ConfigState.FAILED)

        for err in error.errors():
            self._validation_errors.append(
                {
                    "loc": ".".join(str(loc) for loc in err["loc"]),
                    "msg": err["msg"],
                    "type": err["type"],
                }
            )

        log.error(
            "config_validation_failed",
            phase="FAILED",
            validation_error_count=len(self._validation_errors),
            errors=self._validation_errors,
        )

    def _handle_file_error(
        self,
        error: FileNotFoundError,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Handle file not found error."""
        self._state_machine.transition(ConfigState.FAILED)
        self._validation_errors.append(
            {
                "loc": "file",
                "msg": str(error),
                "type": "file_not_found",
            }
        )
        log.error(
            "config_file_not_found",
            phase="FAILED",
            error=str(error),
        )

    def _handle_yaml_error(
        self,
        error: yaml.YAMLError,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        """Handle YAML parsing error."""
        self._state_machine.transition(ConfigState.FAILED)
        self._validation_errors.append(
            {
                "loc": "yaml",
                "msg": str(error),
                "type": "yaml_parse_error",
            }
        )
        log.error(
            "config_yaml_parse_error",
            phase="FAILED",
            error=str(error),
        )

    def get_validation_summary(self) -> dict[str, object]:
        """Get a summary of the validation process.

        Returns:
            Dictionary with validation summary.
        """
        return {
            "run_id": self._run_id,
            "state": self._state_machine.state.name,
            "file_checksums": self._file_checksums,
            "validation_error_count": len(self._validation_errors),
            "validation_errors": self._validation_errors,
            "validation_duration_ms": self._validation_duration_ms,
        }

    def get_validation_summary_json(self) -> str:
        """Get validation summary as JSON string with stable ordering."""
        return json.dumps(self.get_validation_summary(), sort_keys=True, indent=2)
