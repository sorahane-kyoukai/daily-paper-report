"""Constants for the configuration module."""

# Feature key used for evidence and state tracking
FEATURE_KEY = "add-yaml-config-contracts"

# Default status values
STATUS_P1_DONE = "P1_DONE_DEPLOYED"
STATUS_P2_E2E_PASSED = "P2_E2E_PASSED"
STATUS_P3_REFACTORED = "P3_REFACTORED_DEPLOYED"
STATUS_READY = "READY"

# Validation result values
VALIDATION_PASSED = "PASSED"
VALIDATION_FAILED = "FAILED"

# Log component names
COMPONENT_CONFIG = "config"
COMPONENT_CLI = "cli"
COMPONENT_EVIDENCE = "evidence"

# Supported URL schemes
VALID_URL_SCHEMES = ("http://", "https://")

# File type identifiers
FILE_TYPE_SOURCES = "sources"
FILE_TYPE_ENTITIES = "entities"
FILE_TYPE_TOPICS = "topics"
