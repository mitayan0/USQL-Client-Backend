"""SQLAlchemy models: users, identities (SSO), refresh-token sessions, and OAuth pending state."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "usql_users"

    id: Mapped[uuid.UUID] = mapped_column("user_id", primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    identities: Mapped[list["Identity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Identity(Base):
    __tablename__ = "usql_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject_id", name="uq_usql_identity_provider_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column("identity_id", primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usql_users.user_id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    provider_subject_id: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="identities")


class Session(Base):
    __tablename__ = "usql_sessions"

    id: Mapped[uuid.UUID] = mapped_column("session_id", primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usql_users.user_id", ondelete="CASCADE"))
    device_id: Mapped[str] = mapped_column(String(255))
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")


class OAuthPendingState(Base):
    """Short-lived PKCE state entries created when the OAuth flow begins.

    Replaces the in-memory ``_pending`` dict so that state survives process
    restarts and is shared across multiple workers.  Rows are deleted on
    ``consume_state`` and can be bulk-purged by a periodic job or on startup.
    """

    __tablename__ = "usql_oauth_pending"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(255))
    verifier: Mapped[str] = mapped_column(String(128))
    loopback_callback: Mapped[str] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
