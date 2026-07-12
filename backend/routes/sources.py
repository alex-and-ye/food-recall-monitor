from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_sources_service
from models.source_registry import SourceCreateRequest, SourceRegistryDocument
from services.sources import SourcesService

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceRegistryDocument])
def list_sources(sources_service: SourcesService = Depends(get_sources_service)) -> list[SourceRegistryDocument]:
    return sources_service.list_sources()


@router.get("/{name}", response_model=SourceRegistryDocument)
def get_source(
    name: str,
    sources_service: SourcesService = Depends(get_sources_service),
) -> SourceRegistryDocument:
    document = sources_service.get_source(name)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {name}")
    return document


@router.post("", response_model=SourceRegistryDocument, status_code=status.HTTP_201_CREATED)
async def create_source(
    request: SourceCreateRequest,
    sources_service: SourcesService = Depends(get_sources_service),
) -> SourceRegistryDocument:
    try:
        return await sources_service.register_source(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Source discovery failed: {exc}",
        ) from exc


@router.post("/{name}/rediscover", response_model=SourceRegistryDocument)
async def rediscover_source(
    name: str,
    sources_service: SourcesService = Depends(get_sources_service),
) -> SourceRegistryDocument:
    try:
        return await sources_service.rediscover_source(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Source rediscovery failed: {exc}",
        ) from exc


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    name: str,
    sources_service: SourcesService = Depends(get_sources_service),
) -> None:
    deleted = sources_service.delete_source(name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {name}")
