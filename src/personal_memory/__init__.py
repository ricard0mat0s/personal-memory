"""Public interface for the Personal Memory offline core."""

from personal_memory._errors import (
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
)
from personal_memory._proposals import ProposedUpdate
from personal_memory._retrieval import RetrievalRequest, SearchResult
from personal_memory.workspace import MemoryWorkspace

__all__ = [
    "MemoryValidationError",
    "MemoryProposalError",
    "MemoryRetrievalError",
    "MemoryWorkspace",
    "ProposedUpdate",
    "RetrievalRequest",
    "SearchResult",
]
