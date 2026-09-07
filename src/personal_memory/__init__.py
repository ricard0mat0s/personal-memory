"""Public interface for the Personal Memory offline core."""

from personal_memory._errors import MemoryRetrievalError, MemoryValidationError
from personal_memory._retrieval import RetrievalRequest, SearchResult
from personal_memory.workspace import MemoryWorkspace

__all__ = [
    "MemoryValidationError",
    "MemoryRetrievalError",
    "MemoryWorkspace",
    "RetrievalRequest",
    "SearchResult",
]
