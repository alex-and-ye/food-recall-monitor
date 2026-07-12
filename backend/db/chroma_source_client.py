from __future__ import annotations

import json
from datetime import datetime
from typing import cast

import chromadb
from chromadb.api.types import Metadata

from db.source_config_interface import ScraperSourceConfigDBInterface
from models.scraper_config import ScraperSourceConfig
from models.source_registry import DiscoveryStatus, SourceRegistryDocument


class ScraperSourceConfigChromaClient(ScraperSourceConfigDBInterface):
    COLLECTION_NAME = "scraper_sources_collection"

    def __init__(self, host: str = "localhost", port: int = 8000) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=ScraperSourceConfigChromaClient.COLLECTION_NAME
        )

    def list_sources(self) -> list[SourceRegistryDocument]:
        results = self.collection.get(include=["documents", "metadatas"])
        ids = results.get("ids") or []
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        sources: list[SourceRegistryDocument] = []
        for source_id, document, metadata in zip(ids, documents, metadatas, strict=False):
            parsed = self._parse_record(source_id, document, metadata)
            if parsed is not None:
                sources.append(parsed)
        sources.sort(key=lambda item: item.source_name)
        return sources

    def list_source_names(self) -> list[str]:
        return [source.source_name for source in self.list_sources()]

    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        key = source_name.strip().lower()
        if not key:
            return None
        results = self.collection.get(ids=[key], include=["documents", "metadatas"])
        ids = results.get("ids") or []
        if not ids:
            return None
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        document = documents[0] if documents else None
        metadata = metadatas[0] if metadatas else None
        return self._parse_record(ids[0], document, metadata)

    def upsert_source(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        payload = document.model_dump(mode="json")
        metadata = cast(
            Metadata,
            {
                "source_name": document.source_name,
                "homepage_url": document.homepage_url,
                "country_source": document.country_source,
                "discovery_status": document.discovery_status,
                "discovery_reason": document.discovery_reason,
                "discovered_at": _isoformat(document.discovered_at),
                "updated_at": _isoformat(document.updated_at),
            },
        )
        self.collection.upsert(
            ids=[document.source_name],
            documents=[json.dumps(payload)],
            metadatas=[metadata],
        )
        return document

    def delete_source(self, source_name: str) -> bool:
        key = source_name.strip().lower()
        existing = self.get_source(key)
        if existing is None:
            return False
        self.collection.delete(ids=[key])
        return True

    def count_sources(self) -> int:
        results = self.collection.get(include=[])
        return len(results.get("ids") or [])

    def _parse_record(
        self,
        source_id: str,
        document: str | None,
        metadata: Metadata | None,
    ) -> SourceRegistryDocument | None:
        if document:
            try:
                payload = json.loads(document)
                if isinstance(payload, dict):
                    return SourceRegistryDocument.model_validate(payload)
            except (json.JSONDecodeError, ValueError):
                pass

        if not metadata:
            return None

        config_raw = metadata.get("config_json")
        config: ScraperSourceConfig
        if isinstance(config_raw, str) and config_raw.strip():
            try:
                config = ScraperSourceConfig.model_validate(json.loads(config_raw))
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            return None

        status_raw = str(metadata.get("discovery_status") or "ready")
        status: DiscoveryStatus
        if status_raw in {"ready", "failed", "stale", "pending"}:
            status = status_raw  # type: ignore[assignment]
        else:
            status = "ready"

        return SourceRegistryDocument(
            source_name=str(metadata.get("source_name") or source_id),
            homepage_url=str(metadata.get("homepage_url") or config.base_url),
            country_source=str(metadata.get("country_source") or source_id),
            config=config,
            discovery_status=status,
            discovery_reason=str(metadata.get("discovery_reason") or ""),
            discovered_at=_parse_datetime(metadata.get("discovered_at")),
            updated_at=_parse_datetime(metadata.get("updated_at")),
        )


class InMemoryScraperSourceConfigStore(ScraperSourceConfigDBInterface):
    """Test double and offline fallback for source registry persistence."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceRegistryDocument] = {}

    def list_sources(self) -> list[SourceRegistryDocument]:
        return sorted(self._sources.values(), key=lambda item: item.source_name)

    def list_source_names(self) -> list[str]:
        return [source.source_name for source in self.list_sources()]

    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        return self._sources.get(source_name.strip().lower())

    def upsert_source(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        self._sources[document.source_name] = document
        return document

    def delete_source(self, source_name: str) -> bool:
        key = source_name.strip().lower()
        if key not in self._sources:
            return False
        del self._sources[key]
        return True

    def count_sources(self) -> int:
        return len(self._sources)


def _isoformat(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
