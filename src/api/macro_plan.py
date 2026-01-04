"""
Macro Planning API endpoints for generating trip skeletons.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel
from src.application.macro_planner import MacroPlanner
from src.domain.schemas import MacroPlanResponse
from src.auth.dependencies import (
    get_auth_context,
    AuthContext,
    check_trip_ownership,
    require_device_id_for_guest,
)


router = APIRouter(prefix="/trips", tags=["macro-planning"])


@router.post(
    "/{trip_id}/macro-plan",
    response_model=MacroPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate macro plan for trip",
    description="Generate a high-level trip skeleton with themed days and time blocks using AI."
)
async def create_macro_plan(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> MacroPlanResponse:
    """
    Generate macro plan (skeleton) for a trip.

    The AI planner analyzes the trip details and creates a day-by-day structure with:
    - Daily themes
    - Time blocks for meals, activities, nightlife
    - Desired POI categories for each block

    This skeleton is used by later stages (POI selection, route optimization).

    Args:
        trip_id: UUID of the trip to plan

    Returns:
        MacroPlanResponse with day skeletons

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

    planner = MacroPlanner()

    try:
        macro_plan = await planner.generate_macro_plan(trip_id, db)
        return macro_plan

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
                detail=f"Failed to generate macro plan: {error_msg}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during planning: {str(e)}"
        )


@router.get(
    "/{trip_id}/macro-plan",
    response_model=MacroPlanResponse,
    summary="Get macro plan for trip",
    description="Fetch the stored macro plan (skeleton) for a trip."
)
async def get_macro_plan(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> MacroPlanResponse:
    """
    Get stored macro plan for a trip.

    Returns the previously generated trip skeleton if it exists.

    Args:
        trip_id: UUID of the trip

    Returns:
        MacroPlanResponse with day skeletons

    Raises:
        HTTPException 404 if trip or macro plan not found
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

    planner = MacroPlanner()
    macro_plan = await planner.get_macro_plan(trip_id, db)

    if not macro_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No macro plan found for trip {trip_id}"
        )

    return macro_plan
