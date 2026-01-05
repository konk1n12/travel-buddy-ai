"""
FastAPI dependencies for authentication and authorization.
"""
from typing import Optional
from uuid import UUID
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.auth.models import UserModel, GuestDeviceModel
from src.infrastructure.models import TripModel
from src.auth.jwt import verify_token, TokenExpiredError, TokenInvalidError
from src.auth.config import auth_settings


# Optional bearer token scheme (doesn't require auth, just extracts if present)
optional_bearer = HTTPBearer(auto_error=False)

# Required bearer token scheme
required_bearer = HTTPBearer(auto_error=True)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[UserModel]:
    """
    Get the current authenticated user if a valid token is provided.
    Returns None if no token or invalid token.

    Use this for endpoints that work for both guests and authenticated users.
    """
    if not credentials:
        return None

    try:
        payload = verify_token(credentials.credentials, expected_type="access")
        user_id = UUID(payload["sub"])

        result = await db.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()
        return user

    except (TokenExpiredError, TokenInvalidError, ValueError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(required_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    """
    Get the current authenticated user. Raises 401 if not authenticated.

    Use this for endpoints that require authentication.
    """
    try:
        payload = verify_token(credentials.credentials, expected_type="access")
        user_id = UUID(payload["sub"])

        result = await db.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_device_id(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
) -> Optional[str]:
    """
    Get the device ID from X-Device-Id header.
    Returns None if header is not present.
    """
    return x_device_id


def require_device_id(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
) -> str:
    """
    Require the device ID from X-Device-Id header.
    Raises 400 if header is not present.

    Use this for endpoints that require device tracking (guest functionality).
    """
    if not x_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Device-Id header is required",
        )
    return x_device_id


async def get_or_create_guest_device(
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> GuestDeviceModel:
    """
    Get or create a guest device record for the given device ID.
    """
    result = await db.execute(
        select(GuestDeviceModel).where(GuestDeviceModel.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        device = GuestDeviceModel(device_id=device_id)
        db.add(device)
        await db.flush()

    return device


async def check_guest_trip_limit(
    device: GuestDeviceModel,
) -> None:
    """
    Check if guest has reached trip generation limit.
    Raises 402 PAYWALL_REQUIRED if limit reached.

    Skipped if FREEMIUM_ENABLED=false in settings.
    """
    # Skip limit check if freemium is disabled
    if not auth_settings.freemium_enabled:
        return

    if device.generated_trips_count >= auth_settings.guest_max_trips:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "PAYWALL_REQUIRED",
                "message": "Trip generation limit reached. Please sign in to continue.",
                "trips_generated": device.generated_trips_count,
                "limit": auth_settings.guest_max_trips,
            }
        )


class AuthContext:
    """
    Combined authentication context containing user and/or device info.
    Useful for endpoints that need to check both.
    """
    def __init__(
        self,
        user: Optional[UserModel] = None,
        device_id: Optional[str] = None,
        guest_device: Optional[GuestDeviceModel] = None,
    ):
        self.user = user
        self.device_id = device_id
        self.guest_device = guest_device

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def user_id(self) -> Optional[UUID]:
        return self.user.id if self.user else None


def require_device_id_for_guest(auth: AuthContext) -> None:
    """
    Require X-Device-Id for unauthenticated requests.
    """
    if not auth.is_authenticated and not auth.device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "DEVICE_ID_REQUIRED",
                "message": "X-Device-Id is required for guest requests",
            },
        )


def check_trip_ownership(
    trip: TripModel,
    auth: AuthContext,
) -> bool:
    """
    Check if the current user/guest owns the trip.
    """
    if auth.is_authenticated:
        return trip.user_id == auth.user.id
    if auth.device_id:
        return trip.device_id == auth.device_id
    return bool(getattr(trip, "is_legacy_public", False))


async def get_auth_context(
    user: Optional[UserModel] = Depends(get_current_user_optional),
    device_id: Optional[str] = Depends(get_device_id),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    Get combined authentication context with user and/or device info.
    """
    guest_device = None

    if device_id and not user:
        # Only look up guest device if not authenticated
        result = await db.execute(
            select(GuestDeviceModel).where(GuestDeviceModel.device_id == device_id)
        )
        guest_device = result.scalar_one_or_none()

    return AuthContext(
        user=user,
        device_id=device_id,
        guest_device=guest_device,
    )


def apply_guest_content_limit(itinerary, is_authenticated: bool):
    """
    Apply Day 1 only limit for unauthenticated guests.

    Args:
        itinerary: ItineraryResponse object with days
        is_authenticated: Whether the user is authenticated

    Returns:
        Modified itinerary with only Day 1 and is_locked=True for guests,
        or unchanged itinerary for authenticated users.

    Note: Skipped if FREEMIUM_ENABLED=false in settings.
    """
    # Skip content limit if freemium is disabled
    if not auth_settings.freemium_enabled:
        return itinerary

    if is_authenticated:
        return itinerary

    # Guest: show only Day 1, mark as locked
    limited_days = [day for day in itinerary.days if day.day_number == 1] or itinerary.days[:1]
    return itinerary.model_copy(update={"days": limited_days, "is_locked": True})
