"""Public interface for the Personal Memory offline core."""

from personal_memory._errors import (
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
)
from personal_memory._proposals import (
    AppliedUpdate,
    ExplicitApproval,
    ProposedUpdate,
)
from personal_memory._retrieval import RetrievalRequest, SearchResult
from personal_memory.workspace import MemoryWorkspace

__all__ = [
    "AppliedUpdate",
    "ExplicitApproval",
    "MemoryApplicationError",
    "MemoryValidationError",
    "MemoryProposalError",
    "MemoryRetrievalError",
    "MemoryWorkspace",
    "ProposedUpdate",
    "RetrievalRequest",
    "SearchResult",
]
