"""Public failures raised by the offline memory contract."""


class MemoryValidationError(ValueError):
    """Raised when a file cannot be accepted as a Memory Page."""


class MemoryRetrievalError(ValueError):
    """Raised when a retrieval request cannot be served safely."""
