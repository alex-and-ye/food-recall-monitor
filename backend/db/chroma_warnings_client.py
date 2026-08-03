from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import cast

import chromadb
from chromadb.api.types import Metadata

from db.warnings_interface import PipelineWarningsDBInterface
from models.pipeline_warning import (
    MAX_WARNINGS_RETAINED,
    WARNING_CATEGORIES,
    PipelineWarning,
    PipelineWarningCreate,
    WarningCategory,
)

class PipelineWarningsChromaClient(PipelineWarningsDBInterface):
    COLLECTION_NAME = "pipeline_warnings_collection"

    def __init__(self, host: str, port: int) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=PipelineWarningsChromaClient.COLLECTION_NAME
        )

    def create(self, warning: PipelineWarningCreate) -> PipelineWarning:
        created = PipelineWarning(
            warning_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            category=warning.category,
            message=warning.message,
            source=warning.source,
            acknowledged=False,
            run_id=warning.run_id,
        )
        self._upsert(created)
        self._prune_oldest()
        return created

    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        warnings = self._all_warnings()
        if acknowledged is not None:
            warnings = [item for item in warnings if item.acknowledged is acknowledged]
        warnings.sort(key=lambda item: item.created_at, reverse=True)
        return warnings

    def get_warning(self, warning_id: str) -> PipelineWarning | None:
        key = warning_id.strip()
        if not key:
            return None
        results = self.collection.get(ids=[key], include=["documents", "metadatas"])
        ids = results.get("ids") or []
        if not ids:
            return None
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        return self._parse_record(ids[0], documents[0] if documents else None, metadatas[0] if metadatas else None)

    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        existing = self.get_warning(warning_id)
        if existing is None:
            return None
        updated = existing.model_copy(update={"acknowledged": True})
        self._upsert(updated)
        return updated

    def acknowledge_all(self) -> int:
        updated_count = 0
        for warning in self._all_warnings():
            if warning.acknowledged:
                continue
            self._upsert(warning.model_copy(update={"acknowledged": True}))
            updated_count += 1
        return updated_count

    def count_unacknowledged(self) -> int:
        return sum(1 for warning in self._all_warnings() if not warning.acknowledged)

    def delete(self, warning_id: str) -> bool:
        existing = self.get_warning(warning_id)
        if existing is None:
            return False
        self.collection.delete(ids=[existing.warning_id])
        return True

    def _all_warnings(self) -> list[PipelineWarning]:
        results = self.collection.get(include=["documents", "metadatas"])
        ids = results.get("ids") or []
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        warnings: list[PipelineWarning] = []
        for warning_id, document, metadata in zip(ids, documents, metadatas, strict=False):
            parsed = self._parse_record(warning_id, document, metadata)
            if parsed is not None:
                warnings.append(parsed)
        return warnings

    def _upsert(self, warning: PipelineWarning) -> None:
        payload = warning.model_dump(mode="json")
        metadata = cast(
            Metadata,
            {
                "warning_id": warning.warning_id,
                "created_at": warning.created_at.isoformat(),
                "category": warning.category,
                "message": warning.message,
                "source": warning.source or "",
                "acknowledged": str(warning.acknowledged).lower(),
                "run_id": warning.run_id or "",
            },
        )
        self.collection.upsert(
            ids=[warning.warning_id],
            documents=[json.dumps(payload)],
            metadatas=[metadata],
        )

    def _prune_oldest(self) -> None:
        warnings = self._all_warnings()
        if len(warnings) <= MAX_WARNINGS_RETAINED:
            return
        warnings.sort(key=lambda item: item.created_at, reverse=True)
        for stale in warnings[MAX_WARNINGS_RETAINED:]:
            self.collection.delete(ids=[stale.warning_id])

    def _parse_record(
        self,
        warning_id: str,
        document: str | None,
        metadata: Metadata | None,
    ) -> PipelineWarning | None:
        if document:
            try:
                payload = json.loads(document)
                if isinstance(payload, dict):
                    return PipelineWarning.model_validate(payload)
            except (json.JSONDecodeError, ValueError):
                pass

        if not metadata:
            return None

        created_at = _parse_datetime(metadata.get("created_at"))
        if created_at is None:
            return None

        category = str(metadata.get("category") or "")
        if category not in WARNING_CATEGORIES:
            return None

        source_raw = str(metadata.get("source") or "").strip()
        run_id_raw = str(metadata.get("run_id") or "").strip()
        acknowledged_raw = str(metadata.get("acknowledged") or "false").lower()

        return PipelineWarning(
            warning_id=str(metadata.get("warning_id") or warning_id),
            created_at=created_at,
            category=WarningCategory(category),
            message=str(metadata.get("message") or "Pipeline warning"),
            source=source_raw or None,
            acknowledged=acknowledged_raw in {"true", "1", "yes"},
            run_id=run_id_raw or None,
        )

class InMemoryPipelineWarningsStore(PipelineWarningsDBInterface):
    """Test double and offline fallback for pipeline warnings persistence."""

    def __init__(self) -> None:
        self._warnings: dict[str, PipelineWarning] = {}

    def create(self, warning: PipelineWarningCreate) -> PipelineWarning:
        created = PipelineWarning(
            warning_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            category=warning.category,
            message=warning.message,
            source=warning.source,
            acknowledged=False,
            run_id=warning.run_id,
        )
        self._warnings[created.warning_id] = created
        self._prune_oldest()
        return created

    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        warnings = list(self._warnings.values())
        if acknowledged is not None:
            warnings = [item for item in warnings if item.acknowledged is acknowledged]
        warnings.sort(key=lambda item: item.created_at, reverse=True)
        return warnings

    def get_warning(self, warning_id: str) -> PipelineWarning | None:
        return self._warnings.get(warning_id.strip())

    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        existing = self.get_warning(warning_id)
        if existing is None:
            return None
        updated = existing.model_copy(update={"acknowledged": True})
        self._warnings[updated.warning_id] = updated
        return updated

    def acknowledge_all(self) -> int:
        updated_count = 0
        for warning_id, warning in list(self._warnings.items()):
            if warning.acknowledged:
                continue
            self._warnings[warning_id] = warning.model_copy(update={"acknowledged": True})
            updated_count += 1
        return updated_count

    def count_unacknowledged(self) -> int:
        return sum(1 for warning in self._warnings.values() if not warning.acknowledged)

    def delete(self, warning_id: str) -> bool:
        key = warning_id.strip()
        if key not in self._warnings:
            return False
        del self._warnings[key]
        return True

    def _prune_oldest(self) -> None:
        if len(self._warnings) <= MAX_WARNINGS_RETAINED:
            return
        ordered = sorted(self._warnings.values(), key=lambda item: item.created_at, reverse=True)
        keep_ids = {item.warning_id for item in ordered[:MAX_WARNINGS_RETAINED]}
        self._warnings = {
            warning_id: warning
            for warning_id, warning in self._warnings.items()
            if warning_id in keep_ids
        }

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
