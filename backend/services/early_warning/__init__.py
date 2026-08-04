"""Public exports for the early-warning discovery services package.

Re-exports Brave Search and query-generation entry points used by the rest
of the backend without requiring deep import paths.
"""

from services.early_warning.brave_search import BraveSearchClient, BraveSearchError
from services.early_warning.query_generator import QueryGenerator, generate_queries

__all__ = [
    "BraveSearchClient",
    "BraveSearchError",
    "QueryGenerator",
    "generate_queries",
]
