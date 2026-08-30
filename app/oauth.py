"""Google OAuth 2.0 / OIDC (backend-mediated) helpers.

The client secret lives only on the server. PKCE is used as defense-in-depth
on top of the authorization code flow.
"""

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import OAuthPendingState

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
SCOPES = "openid email profile"
PENDING_TTL_SECONDS = 600

# ---------------------------------------------------------------------------
# JWKS cache — Google rotates keys infrequently; cache for 1 hour to avoid
# hammering their endpoint on every token validation.
# ---------------------------------------------------------------------------
_jwks_cache: dict | None = None
_jwks_cached_at: float = 0.0
_JWKS_TTL_SECONDS = 3600


def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cached_at
    if _jwks_cache is None or time.monotonic() - _jwks_cached_at > _JWKS_TTL_SECONDS:
        with httpx.Client(timeout=15) as client:
            _jwks_cache = client.get(JWKS_URL).raise_for_status().json()
        _jwks_cached_at = time.monotonic()
    return _jwks_cache


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# ---------------------------------------------------------------------------
# State management — DB-backed so it survives restarts and multiple workers
# ---------------------------------------------------------------------------

def create_authorize_url(device_id: str, loopback_callback: str, db: DBSession) -> str:
    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=PENDING_TTL_SECONDS)

    db.add(OAuthPendingState(
        state=state,
        device_id=device_id,
        verifier=verifier,
        loopback_callback=loopback_callback,
        expires_at=expires_at,
    ))
    db.commit()

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def consume_state(state: str, db: DBSession) -> dict:
    """Pop and return the pending state entry, raising if missing or expired."""
    entry: OAuthPendingState | None = db.get(OAuthPendingState, state)
    if entry is None:
        raise ValueError("invalid or expired state")

    db.delete(entry)
    db.commit()

    if datetime.now(timezone.utc) > entry.expires_at:
        raise ValueError("invalid or expired state")

    return {
        "device_id": entry.device_id,
        "verifier": entry.verifier,
        "loopback_callback": entry.loopback_callback,
    }


# ---------------------------------------------------------------------------
# Token exchange & validation
# ---------------------------------------------------------------------------

def exchange_code(code: str, verifier: str) -> dict:
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(TOKEN_URL, data=payload)
        resp.raise_for_status()
        return resp.json()


def validate_id_token(id_token: str) -> dict:
    header = pyjwt.get_unverified_header(id_token)
    jwks = _get_jwks()
    key = next((k for k in jwks["keys"] if k.get("kid") == header.get("kid")), None)
    if key is None:
        # Key not in cache — force a refresh once in case Google just rotated
        global _jwks_cache
        _jwks_cache = None  # invalidate so _get_jwks() fetches fresh
        jwks = _get_jwks()
        key = next((k for k in jwks["keys"] if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise ValueError("unable to find signing key for id_token")

    rsa_key = RSAAlgorithm.from_jwk(json.dumps(key))
    claims = pyjwt.decode(
        id_token,
        rsa_key,
        algorithms=["RS256"],
        audience=settings.google_client_id,
        issuer="https://accounts.google.com",
    )
    return claims
