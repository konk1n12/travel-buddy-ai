"""
JWT token utilities for creating and verifying access/refresh tokens.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
import jwt

from src.auth.config import auth_settings


class TokenError(Exception):
    """Base exception for token-related errors."""
    pass


class TokenExpiredError(TokenError):
    """Token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Token is invalid or malformed."""
    pass


def create_access_token(
    user_id: UUID,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a short-lived access token for API authentication.

    Args:
        user_id: The user's UUID
        additional_claims: Optional additional claims to include in token

    Returns:
        Encoded JWT access token string
    """
    now = datetime.utcnow()
    expires = now + timedelta(minutes=auth_settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        auth_settings.jwt_secret_key,
        algorithm=auth_settings.jwt_algorithm
    )


def create_refresh_token(
    user_id: UUID,
    session_id: UUID,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a long-lived refresh token for obtaining new access tokens.

    Args:
        user_id: The user's UUID
        session_id: The session UUID (used for revocation)
        additional_claims: Optional additional claims to include in token

    Returns:
        Encoded JWT refresh token string
    """
    now = datetime.utcnow()
    expires = now + timedelta(days=auth_settings.refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "sid": str(session_id),  # Session ID for revocation
        "type": "refresh",
        "iat": now,
        "exp": expires,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(
        payload,
        auth_settings.jwt_secret_key,
        algorithm=auth_settings.jwt_algorithm
    )


def verify_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        Decoded token payload

    Raises:
        TokenExpiredError: If token has expired
        TokenInvalidError: If token is invalid or wrong type
    """
    try:
        payload = jwt.decode(
            token,
            auth_settings.jwt_secret_key,
            algorithms=[auth_settings.jwt_algorithm]
        )

        # Verify token type
        if payload.get("type") != expected_type:
            raise TokenInvalidError(f"Expected {expected_type} token, got {payload.get('type')}")

        return payload

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise TokenInvalidError(f"Invalid token: {str(e)}")


def hash_token(token: str) -> str:
    """
    Create a hash of a token for storage (used for refresh tokens).
    We don't store raw tokens in the database.

    Args:
        token: The token string to hash

    Returns:
        Hashed token string
    """
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def get_token_expiry_seconds() -> int:
    """Get access token expiration time in seconds."""
    return auth_settings.access_token_expire_minutes * 60
