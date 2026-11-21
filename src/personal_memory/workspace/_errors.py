"""Public failures raised by the offline memory contract."""


class MemoryValidationError(ValueError):
    """Raised when a file cannot be accepted as a Memory Page."""


class MemoryRetrievalError(ValueError):
    """Raised when a retrieval request cannot be served safely."""


class MemoryProposalError(ValueError):
    """Raised when a no-write memory proposal cannot be produced safely."""


class MemoryApplicationError(ValueError):
    """Raised when an approved memory proposal cannot be applied safely."""
