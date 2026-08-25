"""User resolution: map a provider identity to an application user.

Match order:
  1. Existing identity (provider + subject)  -> authoritative
  2. Verified email match                     -> attach identity to that user
  3. No match                                 -> JIT-provision a new user
"""

import uuid

from sqlalchemy.orm import Session

from app import models


def resolve_user(
    db: Session,
    provider: str,
    subject: str,
    email: str | None,
    display_name: str | None,
    avatar_url: str | None,
) -> tuple[models.User, bool]:
    """Return (user, is_new)."""
    identity = (
        db.query(models.Identity)
        .filter_by(provider=provider, provider_subject_id=subject)
        .first()
    )
    if identity is not None:
        return identity.user, False

    user: models.User | None = None
    if email:
        user = (
            db.query(models.User)
            .filter(models.User.email == email.strip().lower())
            .first()
        )

    if user is None:
        user = models.User(
            id=uuid.uuid4(),
            email=(email or f"{provider}:{subject}").strip().lower(),
            display_name=display_name,
            avatar_url=avatar_url,
        )
        db.add(user)
        db.flush()
        is_new = True
    else:
        if not user.display_name:
            user.display_name = display_name
        if not user.avatar_url:
            user.avatar_url = avatar_url
        is_new = False

    db.add(
        models.Identity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider=provider,
            provider_subject_id=subject,
        )
    )
    db.flush()
    return user, is_new
