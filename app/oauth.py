"""Google OAuth 2.0 / OIDC (backend-mediated) helpers.

The client secret lives only on the server. PKCE is used as defense-in-depth
on top of the authorization code flow.
"""

import base64
import hashlib
import json
import secrets
import time

import httpx
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm

from app.config import settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
SCOPES = "openid email profile"
PENDING_TTL_SECONDS = 600

# state -> {device_id, verifier, loopback_callback, created}
_pending: dict[str, dict] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def create_authorize_url(device_id: str, loopback_callback: str) -> str:
    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce()
    _pending[state] = {
        "device_id": device_id,
        "verifier": verifier,
        "loopback_callback": loopback_callback,
        "created": time.time(),
    }
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
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def consume_state(state: str) -> dict:
    entry = _pending.pop(state, None)
    if not entry or time.time() - entry["created"] > PENDING_TTL_SECONDS:
        raise ValueError("invalid or expired state")
    return entry


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
    with httpx.Client(timeout=15) as client:
        jwks = client.get(JWKS_URL).raise_for_status().json()
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
