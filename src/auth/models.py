"""
SQLAlchemy ORM models for authentication tables.
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from src.infrastructure.database import Base
from src.infrastructure.db_types import GUID


class UserModel(Base):
    """
    User account model.
    A user can have multiple auth identities (Apple, Google, Email).
    """
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=True, index=True)  # May be null for Apple users who hide email
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    identities = relationship("AuthIdentityModel", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")


class AuthIdentityModel(Base):
    """
    Authentication identity - links a user to an auth provider.
    A user can have multiple identities (e.g., Apple + Google + Email).
    """
    __tablename__ = "auth_identities"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Provider info
    provider = Column(String, nullable=False)  # "apple", "google", "email"
    provider_subject = Column(String, nullable=False)  # Provider's unique user ID (or email for email auth)

    # Email associated with this identity (may differ from user.email)
    email = Column(String, nullable=True)

    # Provider-specific data (JSON serialized if needed)
    provider_data = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one identity per provider+subject
    __table_args__ = (
        Index("ix_auth_identities_provider_subject", "provider", "provider_subject", unique=True),
    )

    # Relationships
    user = relationship("UserModel", back_populates="identities")


class SessionModel(Base):
    """
    User session - stores refresh token hash for token refresh/revocation.
    """
    __tablename__ = "sessions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Refresh token hash (we don't store the actual token)
    refresh_token_hash = Column(String, nullable=False, unique=True)

    # Device/client info for session management
    device_id = Column(String, nullable=True, index=True)  # From X-Device-Id header
    device_name = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("UserModel", back_populates="sessions")

    @property
    def is_valid(self) -> bool:
        """Check if session is still valid (not expired, not revoked)."""
        now = datetime.utcnow()
        return self.revoked_at is None and self.expires_at > now


class GuestDeviceModel(Base):
    """
    Guest device tracking for freemium limits.
    Tracks how many trips a guest device has generated.
    """
    __tablename__ = "guest_devices"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    device_id = Column(String, nullable=False, unique=True, index=True)  # From X-Device-Id header

    generated_trips_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class OTPChallengeModel(Base):
    """
    Email OTP challenge for passwordless email authentication.
    """
    __tablename__ = "otp_challenges"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, index=True)

    # We store hashed code for security
    code_hash = Column(String, nullable=False)

    attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    @property
    def is_valid(self) -> bool:
        """Check if challenge is still valid (not expired, not verified, attempts left)."""
        from src.auth.config import auth_settings
        now = datetime.utcnow()
        return (
            self.verified_at is None
            and self.expires_at > now
            and self.attempts < auth_settings.otp_max_attempts
        )
