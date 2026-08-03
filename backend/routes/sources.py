"""HTTP routes for scraper source registry management.

Supports listing, lookup, registration, rediscovery, and deletion of
official recall scraper sources.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_sources_service
from models.source_registry import SourceCreateRequest, SourceRegistryDocument
from services.sources import SourcesService

# FastAPI router for scraper source endpoints
router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceRegistryDocument])
def list_sources(
    sources_service: SourcesService = Depends(get_sources_service),
) -> list[SourceRegistryDocument]:
    """List all registered scraper sources.

    Args:
        sources_service: Injected sources service.

    Returns:
        List of ``SourceRegistryDocument`` entries.
    """
    return sources_service.list_sources()


@router.get("/{name}", response_model=SourceRegistryDocument)
def get_source(
    name: str,
    sources_service: SourcesService = Depends(get_sources_service),
) -> SourceRegistryDocument:
    """Fetch a single scraper source by registry name.

    Args:
        name: Source registry key.
        sources_service: Injected sources service.

    Returns:
        Matching ``SourceRegistryDocument``.

    Raises:
        HTTPException: 404 if the source name is unknown.
    """
    document = sources_service.get_source(name)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {name}")
    return document


@router.post("", response_model=SourceRegistryDocument, status_code=status.HTTP_201_CREATED)
async def create_source(
    request: SourceCreateRequest,
    sources_service: SourcesService = Depends(get_sources_service),
) -> SourceRegistryDocument:
    """Register a new scraper source and run discovery.

    Args:
        request: Create payload with source name and entry URL.
        sources_service: Injected sources service.

    Returns:
        Newly registered ``SourceRegistryDocument``.

    Raises:
        HTTPException: 409 on conflict; 502 if discovery fails.
    """
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
    """Re-run scraper discovery for an existing source.

    Args:
        name: Source registry key.
        sources_service: Injected sources service.

    Returns:
        Updated ``SourceRegistryDocument`` after rediscovery.

    Raises:
        HTTPException: 404 if unknown; 502 if rediscovery fails.
    """
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
    """Delete a registered scraper source.

    Args:
        name: Source registry key.
        sources_service: Injected sources service.

    Raises:
        HTTPException: 404 if the source name is unknown.
    """
    deleted = sources_service.delete_source(name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {name}")
