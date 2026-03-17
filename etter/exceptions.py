"""
Custom exceptions for parsing and validation.
"""


class GeoFilterError(Exception):
    """Base exception for all GeoFilter errors."""

    pass


class ParsingError(GeoFilterError):
    """LLM failed to parse query into valid structure."""

    def __init__(self, message: str, raw_response: str = "", original_error: Exception | None = None):
        """
        Initialize parsing error.

        Args:
            message: Error description
            raw_response: Raw response from LLM
            original_error: Original exception that caused parsing failure
        """
        self.raw_response = raw_response
        self.original_error = original_error
        super().__init__(message)


class ValidationError(GeoFilterError):
    """Structured output is valid but fails business logic validation."""

    def __init__(self, message: str, field: str | None = None, detail: str | None = None):
        """
        Initialize validation error.

        Args:
            message: Error description
            field: Field name that failed validation
            detail: Additional detail about the validation failure
        """
        self.field = field
        self.detail = detail
        super().__init__(message)


class UnknownRelationError(ValidationError):
    """Spatial relation is not registered in configuration."""

    def __init__(self, message: str, relation_name: str):
        """
        Initialize unknown relation error.

        Args:
            message: Error description
            relation_name: The unknown relation name
        """
        self.relation_name = relation_name
        super().__init__(message, field="spatial_relation")


class LowConfidenceError(GeoFilterError):
    """Query confidence is below threshold (strict mode)."""

    def __init__(self, message: str, confidence: float, reasoning: str | None = None):
        """
        Initialize low confidence error.

        Args:
            message: Error description
            confidence: Confidence score (0-1)
            reasoning: Optional explanation for low confidence
        """
        self.confidence = confidence
        self.reasoning = reasoning
        super().__init__(message)


class LowConfidenceWarning(UserWarning):
    """Query confidence is below threshold (permissive mode)."""

    def __init__(self, confidence: float, message: str = ""):
        """
        Initialize low confidence warning.

        Args:
            confidence: Confidence score (0-1)
            message: Warning message
        """
        self.confidence = confidence
        super().__init__(message)
