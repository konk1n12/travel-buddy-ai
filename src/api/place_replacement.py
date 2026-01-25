"""
Place Replacement API endpoints for in-route place substitution.

Provides endpoints for:
1. Getting 3-5 alternative places for replacement
2. Applying replacement atomically with version control
"""
import logging
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.auth.dependencies import get_auth_context, AuthContext
from src.application.place_replacement_service import PlaceReplacementService
from src.i18n import t


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trips", tags=["place-replacement"])


# MARK: - Request/Response Models

class ReplacementConstraintsDTO(BaseModel):
    """Constraints for finding replacement options."""
    max_distance_m: int = Field(default=3000, description="Maximum distance from original place in meters")
    same_category: bool = Field(default=True, description="Only show places in same category")
    exclude_existing_in_day: bool = Field(default=True, description="Exclude places already in this day")
    exclude_place_ids: Optional[List[str]] = Field(default=None, description="Additional place IDs to exclude")


class ReplacementOptionsRequestDTO(BaseModel):
    """Request for getting replacement options."""
    day_index: int = Field(description="Day index (0-based)")
    block_index: int = Field(description="Block index within day (0-based)")
    place_id: str = Field(description="Current place ID to replace")
    category: str = Field(description="Place category")
    lat: float = Field(description="Current place latitude")
    lng: float = Field(description="Current place longitude")
    constraints: Optional[ReplacementConstraintsDTO] = Field(default=None)
    limit: int = Field(default=5, ge=3, le=10, description="Number of alternatives to return")


class ReplacementOptionDTO(BaseModel):
    """A single replacement option."""
    place_id: str = Field(description="Place ID")
    name: str = Field(description="Place name")
    category: str = Field(description="Place category")
    area: Optional[str] = Field(default=None, description="Area/neighborhood name")
    distance_m: int = Field(description="Distance from original place in meters")
    rating: Optional[float] = Field(default=None, description="Rating (0-5)")
    reviews_count: Optional[int] = Field(default=None, description="Number of reviews")
    photo_url: Optional[str] = Field(default=None, description="Photo URL")
    reason: Optional[str] = Field(default=None, description="Why this place was suggested")
    lat: float = Field(description="Latitude")
    lng: float = Field(description="Longitude")
    address: Optional[str] = Field(default=None, description="Address")
    tags: Optional[List[str]] = Field(default=None, description="Tags")


class ReplacementOptionsResponseDTO(BaseModel):
    """Response with replacement options."""
    options: List[ReplacementOptionDTO] = Field(description="List of replacement options")
    request_id: str = Field(description="Request ID for debugging")


class ApplyReplacementRequestDTO(BaseModel):
    """Request to apply a replacement."""
    day_index: int = Field(description="Day index (0-based)")
    block_index: int = Field(description="Block index within day (0-based)")
    old_place_id: str = Field(description="Current place ID")
    new_place_id: str = Field(description="New place ID to set")
    idempotency_key: str = Field(description="Idempotency key (UUID)")
    client_route_version: Optional[int] = Field(default=None, description="Client's current route version")


class ReplacementAppliedResponseDTO(BaseModel):
    """Response after applying replacement."""
    success: bool = Field(description="Whether replacement was successful")
    updated_block: dict = Field(description="Updated block data")
    route_version: int = Field(description="New route version")
    message: Optional[str] = Field(default=None, description="Optional message")


# MARK: - Endpoints

@router.post(
    "/{trip_id}/route/replacements/options",
    response_model=ReplacementOptionsResponseDTO,
    summary="Get replacement options for a place",
    description="Returns 3-5 alternative places similar to the current one."
)
async def get_replacement_options(
    trip_id: UUID,
    request: ReplacementOptionsRequestDTO,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ReplacementOptionsResponseDTO:
    """
    Get replacement options for a specific place in the route.

    Returns 3-5 alternatives based on:
    - Same category (if constraints.same_category=true)
    - Close proximity (within constraints.max_distance_m)
    - Similar rating and quality
    - Not already in the day/route

    Args:
        trip_id: Trip UUID
        request: Replacement request with constraints

    Returns:
        List of replacement options sorted by relevance

    Raises:
        HTTPException 404 if trip/day/block not found
        HTTPException 403 if access denied
    """
    service = PlaceReplacementService()

    try:
        result = await service.get_replacement_options(
            trip_id=trip_id,
            day_index=request.day_index,
            block_index=request.block_index,
            current_place_id=request.place_id,
            current_category=request.category,
            current_lat=request.lat,
            current_lng=request.lng,
            constraints=request.constraints.model_dump() if request.constraints else {},
            limit=request.limit,
            auth=auth,
            db=db
        )

        return ReplacementOptionsResponseDTO(
            options=[ReplacementOptionDTO(**opt) for opt in result["options"]],
            request_id=result["request_id"]
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post(
    "/{trip_id}/route/replacements/apply",
    response_model=ReplacementAppliedResponseDTO,
    summary="Apply place replacement",
    description="Atomically replaces a place in the route with version control."
)
async def apply_replacement(
    trip_id: UUID,
    request: ApplyReplacementRequestDTO,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ReplacementAppliedResponseDTO:
    """
    Apply a place replacement atomically.

    Uses optimistic locking via route_version to handle concurrent edits.
    Idempotency key prevents duplicate applications.

    Args:
        trip_id: Trip UUID
        request: Replacement request with old/new place IDs

    Returns:
        Updated block and new route version

    Raises:
        HTTPException 404 if trip/day/block not found
        HTTPException 403 if access denied
        HTTPException 409 if version conflict (concurrent edit)
        HTTPException 422 if old_place_id doesn't match current
    """
    service = PlaceReplacementService()

    try:
        result = await service.apply_replacement(
            trip_id=trip_id,
            day_index=request.day_index,
            block_index=request.block_index,
            old_place_id=request.old_place_id,
            new_place_id=request.new_place_id,
            idempotency_key=request.idempotency_key,
            client_route_version=request.client_route_version,
            auth=auth,
            db=db
        )

        return ReplacementAppliedResponseDTO(
            success=True,
            updated_block=result["updated_block"],
            route_version=result["route_version"],
            message=result.get("message")
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except RuntimeError as e:
        # Version conflict
        if "conflict" in str(e).lower() or "version" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        # Invalid state (old_place_id mismatch)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
