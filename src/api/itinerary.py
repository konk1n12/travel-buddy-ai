"""
Itinerary API endpoints for full trip planning.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel, ItineraryModel
from src.application.trip_planner import TripPlannerOrchestrator
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


router = APIRouter(prefix="/trips", tags=["itinerary"])


@router.post(
    "/{trip_id}/plan",
    response_model=ItineraryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate complete trip plan",
    description="Execute full planning pipeline: macro plan → POI selection → route optimization."
)
async def plan_trip(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ItineraryResponse:
    """
    Generate complete trip plan.

    This endpoint orchestrates the full planning pipeline:
    1. Verifies trip exists
    2. Generates macro plan if missing (LLM-based day skeletons)
    3. Generates POI plan if missing (deterministic candidate selection)
    4. Generates final itinerary (deterministic POI selection + travel times)

    The endpoint is idempotent - it will reuse existing macro/POI plans
    if they already exist, and only regenerate the final itinerary.

    Args:
        trip_id: UUID of the trip to plan

    Returns:
        ItineraryResponse with complete itinerary

    Raises:
        HTTPException 404 if trip not found
        HTTPException 500 if planning fails
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

    orchestrator = TripPlannerOrchestrator()

    try:
        itinerary = await orchestrator.plan_trip(trip_id, db)
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
                detail=f"Failed to generate trip plan: {error_msg}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during planning: {str(e)}"
        )


@router.get(
    "/{trip_id}/itinerary",
    response_model=ItineraryResponse,
    summary="Get trip itinerary",
    description="Fetch the stored itinerary for a trip."
)
async def get_itinerary(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ItineraryResponse:
    """
    Get stored itinerary for a trip.

    Returns the previously generated complete itinerary if it exists.

    Args:
        trip_id: UUID of the trip

    Returns:
        ItineraryResponse with complete itinerary

    Raises:
        HTTPException 404 if trip or itinerary not found
    """
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

    orchestrator = TripPlannerOrchestrator()

    try:
        itinerary = await orchestrator.get_itinerary(trip_id, db)
        return apply_guest_content_limit(itinerary, auth.is_authenticated)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
