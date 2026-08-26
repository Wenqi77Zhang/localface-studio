"""Privacy-safe health endpoint."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Minimal public health response without host information."""

    status: Literal["ok"] = "ok"


class CapabilitiesResponse(BaseModel):
    """Public product readiness without local paths or device identifiers."""

    workflow_backend: Literal["comfyui", "native-research", "simulation"]
    model_files_present: bool
    model_integrity_verified: bool
    runtime_loaded: bool
    execution_provider: Literal["not_loaded", "cuda", "cpu"]
    research_only: bool


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the API process is ready to receive local requests."""
    return HealthResponse()


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(request: Request) -> CapabilitiesResponse:
    """Distinguish process health from actual local workflow readiness."""
    snapshot: object = request.app.state.backend_capabilities()
    return CapabilitiesResponse.model_validate(snapshot)
