"""Domain exceptions for the state store.

This module defines a hierarchy of exceptions for the state store layer,
separating infrastructure errors (database issues) from domain errors
(business rule violations).
"""


class StateStoreError(Exception):
    """Base exception for all state store errors.

    All exceptions raised by the state store should inherit from this class
    to enable consistent error handling at the application level.
    """


class ConnectionError(StateStoreError):
    """Raised when database connection fails or is not established.

    This exception indicates an infrastructure-level failure in connecting
    to or communicating with the SQLite database.
    """

    def __init__(self, message: str = "Database not connected") -> None:
        """Initialize the connection error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message)


class RunNotFoundError(StateStoreError):
    """Raised when a requested run record is not found.

    This is a domain-level error indicating that the specified run_id
    does not exist in the database.
    """

    def __init__(self, run_id: str) -> None:
        """Initialize the error with the missing run ID.

        Args:
            run_id: The run ID that was not found.
        """
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class ItemNotFoundError(StateStoreError):
    """Raised when a requested item is not found.

    This is a domain-level error indicating that the specified URL
    does not exist in the items table.
    """

    def __init__(self, url: str) -> None:
        """Initialize the error with the missing URL.

        Args:
            url: The canonical URL that was not found.
        """
        self.url = url
        super().__init__(f"Item not found: {url}")


class MigrationError(StateStoreError):
    """Raised when a schema migration fails.

    This exception indicates that a database migration could not be
    applied or rolled back successfully.
    """

    def __init__(self, version: int, message: str) -> None:
        """Initialize the migration error.

        Args:
            version: The migration version that failed.
            message: Human-readable error message.
        """
        self.version = version
        super().__init__(f"Migration {version} failed: {message}")
