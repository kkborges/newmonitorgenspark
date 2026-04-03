"""API v1 router — aggregates all endpoint modules."""
from fastapi import APIRouter
from app.api.v1.endpoints import (
    agents, ingest
)

api_router = APIRouter()

# Public ingest (token-authenticated, no session needed)
api_router.include_router(ingest.router)

# Agent management (session-authenticated)
api_router.include_router(agents.router)
