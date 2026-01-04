"""
Trips API endpoints for creating and managing trip specifications.
Updated with authentication and freemium gating.
"""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel
from src.application.trip_spec import TripSpecCollector
from src.domain.schemas import TripCreateRequest, TripUpdateRequest, TripResponse
from src.auth.dependencies import (
    get_auth_context,
    AuthContext,
    check_trip_ownership,
    require_device_id_for_guest,
)
from src.auth.models import UserModel, GuestDeviceModel
from src.auth.config import auth_settings


router = APIRouter(prefix="/trips", tags=["trips"])


async def _get_or_create_guest_device(
    device_id: str,
    db: AsyncSession,
) -> GuestDeviceModel:
    """Get or create a guest device record."""
    result = await db.execute(
        select(GuestDeviceModel).where(GuestDeviceModel.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        device = GuestDeviceModel(device_id=device_id)
        db.add(device)
        await db.flush()

    return device


@router.post(
    "",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new trip",
    description="Create a new trip from form inputs. Returns the trip with a unique ID."
)
async def create_trip(
    request: TripCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TripResponse:
    """
    Create a new trip from form data.

    For guests:
    - X-Device-Id header is required
    - Only ONE trip can be generated (enforced on generation, not creation)
    - Trip is linked to device_id

    For authenticated users:
    - Trip is linked to user_id
    - Unlimited trips allowed
    """
    require_device_id_for_guest(auth)
    collector = TripSpecCollector()
    trip_response = await collector.create_trip(request, db)

    # Link trip to user or device
    result = await db.execute(
        select(TripModel).where(TripModel.id == trip_response.id)
    )
    trip = result.scalar_one()

    if auth.is_authenticated:
        trip.user_id = auth.user.id
    elif auth.device_id:
        trip.device_id = auth.device_id
        # Ensure guest device record exists (for tracking)
        await _get_or_create_guest_device(auth.device_id, db)

    await db.commit()

    return trip_response


@router.get(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Get trip by ID",
    description="Fetch an existing trip's current TripSpec state."
)
async def get_trip(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TripResponse:
    """
    Get an existing trip by ID.

    Ownership check:
    - Authenticated user: must be trip owner
    - Guest: device_id must match
    """
    collector = TripSpecCollector()
    trip_response = await collector.get_trip(trip_id, db)

    if not trip_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    # Check ownership
    result = await db.execute(
        select(TripModel).where(TripModel.id == trip_id)
    )
    trip = result.scalar_one()

    if not check_trip_ownership(trip, auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    return trip_response


@router.patch(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Update trip",
    description="Update an existing trip's TripSpec with new form data (partial updates)."
)
async def update_trip(
    trip_id: UUID,
    request: TripUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TripResponse:
    """
    Update an existing trip with new form data.

    Ownership check enforced.
    """
    # Check ownership first
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

    collector = TripSpecCollector()
    trip_response = await collector.update_trip(trip_id, request, db)

    if not trip_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    return trip_response
