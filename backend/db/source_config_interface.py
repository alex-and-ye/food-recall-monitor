"""Abstract persistence contract for scraper source registry documents.

Defines the repository interface for listing, fetching, upserting, and
deleting configured scraper sources used by the recall ingestion pipeline.
"""

from abc import ABC, abstractmethod

from models.source_registry import SourceRegistryDocument

class ScraperSourceConfigDBInterface(ABC):
    """Repository interface for scraper source configuration persistence."""

    @abstractmethod
    def list_sources(self) -> list[SourceRegistryDocument]:
        """Return all registered scraper sources.

        Returns:
            All source registry documents, typically sorted by name.
        """
        pass

    @abstractmethod
    def list_source_names(self) -> list[str]:
        """Return the names of all registered sources.

        Returns:
            Source name strings in the same order as list_sources.
        """
        pass

    @abstractmethod
    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        """Fetch a source registry document by name.

        Args:
            source_name: Source name key (implementations may normalize case).

        Returns:
            The matching document, or None if not found.
        """
        pass

    @abstractmethod
    def upsert_source(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        """Insert or replace a source registry document.

        Args:
            document: Source registry payload to store.

        Returns:
            The stored document.
        """
        pass

    @abstractmethod
    def delete_source(self, source_name: str) -> bool:
        """Delete a source by name.

        Args:
            source_name: Source name key (implementations may normalize case).

        Returns:
            True if a record was deleted; False if not found.
        """
        pass

    @abstractmethod
    def count_sources(self) -> int:
        """Return the total number of registered sources.

        Returns:
            Count of sources in the store.
        """
        pass
