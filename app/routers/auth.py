"""Authentication routes: Google OAuth (backend-mediated), sessions, /me."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, oauth, security
from app.config import settings
from app.db import get_db
from app.schemas import AccessTokenResponse, UserOut
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    user_id = security.decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid or expired access token")
    user = db.get(models.User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user


@router.get("/google")
def google_login(
    device_id: str = Query(...),
    callback: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Start the Google OAuth flow. Redirects the browser to Google."""
    url = oauth.create_authorize_url(device_id, callback, db)
    return RedirectResponse(url)


def _error_redirect(callback: str, message: str):
    separator = "&" if "?" in callback else "?"
    return RedirectResponse(f"{callback}{separator}{urlencode({'error': message})}")


@router.get("/callback")
def google_callback(
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Google redirects here after consent. Issues app session tokens and
    delivers them to the desktop loopback URL."""
    try:
        entry = oauth.consume_state(state, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid or expired state") from exc

    if error or not code:
        message = "Google sign-in was cancelled." if error == "access_denied" else "Google did not return an authorization code."
        return _error_redirect(entry["loopback_callback"], message)

    try:
        tokens = oauth.exchange_code(code, entry["verifier"])
    except Exception:
        return _error_redirect(entry["loopback_callback"], "Google token exchange failed.")

    id_token = tokens.get("id_token")
    if not id_token:
        return _error_redirect(entry["loopback_callback"], "Google did not return an identity token.")

    try:
        claims = oauth.validate_id_token(id_token)
    except Exception:
        return _error_redirect(entry["loopback_callback"], "Google identity validation failed.")

    user, _ = user_service.resolve_user(
        db,
        provider="google",
        subject=str(claims.get("sub")),
        email=claims.get("email"),
        display_name=claims.get("name"),
        avatar_url=claims.get("picture"),
    )

    access_token = security.create_access_token(str(user.id))
    raw_refresh, refresh_hash = security.generate_refresh_token()
    db.add(
        models.Session(
            user_id=user.id,
            device_id=entry["device_id"],
            refresh_token_hash=refresh_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    redirect_to = entry["loopback_callback"] or "http://127.0.0.1:40000/callback"
    sep = "&" if "?" in redirect_to else "?"
    return RedirectResponse(
        f"{redirect_to}{sep}{urlencode({'access_token': access_token, 'refresh_token': raw_refresh})}"
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    session = db.scalars(
        select(models.Session).filter_by(refresh_token_hash=security.hash_refresh_token(refresh_token))
    ).first()
    if session is None or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    session.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return AccessTokenResponse(access_token=security.create_access_token(str(session.user_id)))


@router.post("/logout")
def logout(refresh_token: str, db: Session = Depends(get_db)):
    session = db.scalars(
        select(models.Session).filter_by(refresh_token_hash=security.hash_refresh_token(refresh_token))
    ).first()
    if session is not None:
        db.delete(session)
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
