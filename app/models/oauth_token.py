import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # AES-256-GCM encrypted JSON blob: token, refresh_token, token_uri, client_id, client_secret, scopes
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="oauth_tokens")  # noqa: F821
