"""Structured execution errors for engine/runtime failures."""

from typing import Dict, Optional


class ExecutionError(Exception):
    """Raised when a run fails in a structured, API-safe way."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, object]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, object]:
        return {
            "error_type": self.code,
            "detail": self.message,
            "details": self.details,
        }
