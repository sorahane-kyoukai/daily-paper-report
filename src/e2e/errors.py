"""Custom exception types for E2E harness.

Provides specific exception types for different E2E failure scenarios,
enabling better error handling and observability.
"""


class E2EError(Exception):
    """Base exception for all E2E harness errors.

    All E2E-specific exceptions inherit from this class.
    """

    def __init__(self, message: str, run_id: str | None = None) -> None:
        """Initialize E2E error.

        Args:
            message: Error message.
            run_id: Optional run ID for context.
        """
        self.run_id = run_id
        super().__init__(message)


class E2EStateTransitionError(E2EError):
    """Invalid state transition in E2E state machine.

    Raised when attempting a state transition that violates
    the defined workflow order.
    """

    def __init__(
        self,
        message: str,
        from_state: str,
        to_state: str,
        run_id: str | None = None,
    ) -> None:
        """Initialize state transition error.

        Args:
            message: Error message.
            from_state: State we tried to transition from.
            to_state: State we tried to transition to.
            run_id: Optional run ID for context.
        """
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(message, run_id)


class E2EClearDataError(E2EError):
    """Error during clear-data step.

    Raised when database deletion, output cleanup,
    or cache clearing fails.
    """

    def __init__(
        self,
        message: str,
        errors: list[str],
        run_id: str | None = None,
    ) -> None:
        """Initialize clear-data error.

        Args:
            message: Error message.
            errors: List of individual errors that occurred.
            run_id: Optional run ID for context.
        """
        self.errors = errors
        super().__init__(message, run_id)


class E2EValidationError(E2EError):
    """Error during validation step.

    Raised when database, JSON, or HTML validation fails.
    """

    def __init__(
        self,
        message: str,
        validator_type: str,
        details: dict[str, object] | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            validator_type: Type of validator that failed (db, json, html).
            details: Additional validation details.
            run_id: Optional run ID for context.
        """
        self.validator_type = validator_type
        self.details = details or {}
        super().__init__(message, run_id)


class E2EPipelineError(E2EError):
    """Error during pipeline execution.

    Raised when the pipeline run fails.
    """

    def __init__(
        self,
        message: str,
        sources_failed: list[str] | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialize pipeline error.

        Args:
            message: Error message.
            sources_failed: List of source IDs that failed.
            run_id: Optional run ID for context.
        """
        self.sources_failed = sources_failed or []
        super().__init__(message, run_id)


class E2EEvidenceError(E2EError):
    """Error during evidence archiving.

    Raised when evidence capture or writing fails.
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialize evidence error.

        Args:
            message: Error message.
            file_path: Path to file that failed.
            run_id: Optional run ID for context.
        """
        self.file_path = file_path
        super().__init__(message, run_id)
