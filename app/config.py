"""USQL Client Backend — SSO (Sign in with Google) service.

Provides the backend-mediated Google OAuth flow that the desktop app calls.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "USQL Client Backend"
    version: str = "0.1.0"

    database_url: str  # required — set DATABASE_URL in .env

    google_client_id: str  # required — set GOOGLE_CLIENT_ID in .env
    google_client_secret: str  # required — set GOOGLE_CLIENT_SECRET in .env
    google_redirect_uri: str = "http://localhost:8000/auth/callback"

    # App session tokens
    jwt_secret: str  # required — set JWT_SECRET in .env
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30


settings = Settings()
