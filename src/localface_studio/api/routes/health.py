"""Privacy-safe health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Minimal public health response without host information."""

    status: Literal["ok"] = "ok"


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the API process is ready to receive local requests."""
    return HealthResponse()
