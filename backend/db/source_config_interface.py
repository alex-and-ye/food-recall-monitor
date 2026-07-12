from __future__ import annotations

from abc import ABC, abstractmethod

from models.source_registry import SourceRegistryDocument


class ScraperSourceConfigDBInterface(ABC):
    @abstractmethod
    def list_sources(self) -> list[SourceRegistryDocument]:
        pass

    @abstractmethod
    def list_source_names(self) -> list[str]:
        pass

    @abstractmethod
    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        pass

    @abstractmethod
    def upsert_source(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        pass

    @abstractmethod
    def delete_source(self, source_name: str) -> bool:
        pass

    @abstractmethod
    def count_sources(self) -> int:
        pass
