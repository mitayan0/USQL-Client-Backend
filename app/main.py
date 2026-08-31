"""USQL Client Backend — FastAPI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import auth
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield




app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="USQL Client Backend API — resource-oriented REST interface.",
    lifespan=lifespan,
    servers=[
        {"url": "/v1", "description": "Current stable API version"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this in prod to specific domains (e.g. your web app URL)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health", tags=["system"], summary="Health check")
def health():
    """Returns service liveness status and the running version."""
    return {"status": "ok", "version": settings.version}
