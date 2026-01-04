"""
Authentication module for the Trip Planning backend.
Provides JWT-based auth with Apple, Google, and Email OTP providers.
"""
from src.auth.models import (
    UserModel,
    AuthIdentityModel,
    SessionModel,
    GuestDeviceModel,
    OTPChallengeModel,
)
from src.auth.schemas import (
    UserResponse,
    SessionResponse,
    AppleAuthRequest,
    GoogleAuthRequest,
    EmailStartRequest,
    EmailVerifyRequest,
    RefreshRequest,
)
from src.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_device_id,
    require_device_id,
)
from src.auth.jwt import create_access_token, create_refresh_token, verify_token

__all__ = [
    # Models
    "UserModel",
    "AuthIdentityModel",
    "SessionModel",
    "GuestDeviceModel",
    "OTPChallengeModel",
    # Schemas
    "UserResponse",
    "SessionResponse",
    "AppleAuthRequest",
    "GoogleAuthRequest",
    "EmailStartRequest",
    "EmailVerifyRequest",
    "RefreshRequest",
    # Dependencies
    "get_current_user",
    "get_current_user_optional",
    "get_device_id",
    "require_device_id",
    # JWT
    "create_access_token",
    "create_refresh_token",
    "verify_token",
]
