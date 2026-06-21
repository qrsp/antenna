from __future__ import annotations

from fastapi import APIRouter, Request

from antenna import __version__
from antenna.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    db = request.app.state.db
    db.ping()
    return HealthResponse(status="ok", database="ok", version=__version__)
