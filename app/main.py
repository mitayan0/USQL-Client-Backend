"""USQL Client Backend — FastAPI entrypoint."""

from fastapi import FastAPI

from app.config import settings
from app.db import Base, engine
from app.routers import auth


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="USQL Client Backend API — resource-oriented REST interface.",
    servers=[
        {"url": "/v1", "description": "Current stable API version"},
    ],
)

# Dev convenience: create tables if missing.
Base.metadata.create_all(bind=engine)

app.include_router(auth.router)


@app.get("/health", tags=["system"], summary="Health check")
def health():
    """Returns service liveness status and the running version."""
    return {"status": "ok", "version": settings.version}
