"""
Fast Draft API endpoint - optimized for p95 latency under 20 seconds.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel, ItineraryModel
from src.application.fast_draft_planner import FastDraftPlanner
from src.domain.schemas import ItineraryResponse
from src.auth.dependencies import (
    get_auth_context,
    AuthContext,
    check_trip_ownership,
    require_device_id_for_guest,
    get_or_create_guest_device,
    check_guest_trip_limit,
    apply_guest_content_limit,
)


router = APIRouter(prefix="/trips", tags=["fast-draft"])


@router.post(
    "/{trip_id}/fast-draft",
    response_model=ItineraryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate fast draft itinerary",
    description="Generate a draft itinerary with p95 latency under 20 seconds. "
                "Uses LLM with 15s timeout, falls back to template on timeout/error. "
                "Returns draft with placeholder POIs (no route optimization). "
                "Use ?debug=1 for extended trace with full generator params, provider calls, and ranking details."
)
async def generate_fast_draft(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    debug: int = Query(default=0, ge=0, le=1, description="Enable debug trace (0 or 1)"),
    auth: AuthContext = Depends(get_auth_context),
) -> ItineraryResponse:
    """
    Generate fast draft itinerary.

    This endpoint is optimized for speed over completeness:
    - 15-second hard timeout on LLM call
    - Template-based fallback if LLM times out or fails
    - Returns placeholder POIs (not verified from database)
    - No travel time calculation or route optimization
    - No critique/validation step

    Use this endpoint for initial loading animation, then optionally
    call /plan for full enrichment in the background.

    Args:
        trip_id: UUID of the trip to plan
        debug: 1 to enable extended trace with generator params, provider calls, ranking details

    Returns:
        ItineraryResponse with draft itinerary (and optional extended trace if debug=1)

    Raises:
        HTTPException 404 if trip not found
        HTTPException 500 if planning fails (should be rare due to fallback)
    """
    require_device_id_for_guest(auth)
    result = await db.execute(
        select(TripModel).where(TripModel.id == trip_id)
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    if not check_trip_ownership(trip, auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    itinerary_result = await db.execute(
        select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
    )
    itinerary_model = itinerary_result.scalar_one_or_none()
    is_first_generation = itinerary_model is None

    guest_device = None
    if not auth.is_authenticated and is_first_generation:
        guest_device = await get_or_create_guest_device(device_id=auth.device_id, db=db)
        await check_guest_trip_limit(guest_device)

    planner = FastDraftPlanner()

    try:
        enable_extended_trace = debug == 1
        itinerary = await planner.generate_fast_draft(
            trip_id,
            db,
            include_trace=True,  # always include basic trace
            enable_extended_trace=enable_extended_trace,  # extended trace only if debug=1
        )
        if guest_device:
            guest_device.generated_trips_count += 1
            await db.commit()
        return apply_guest_content_limit(itinerary, auth.is_authenticated)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate draft: {error_msg}"
            )

    except Exception as e:
        # This should be rare due to template fallback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during draft generation: {str(e)}"
        )
