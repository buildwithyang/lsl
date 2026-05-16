from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.material.schema import (
    ApiResponse,
    GenerateMaterialSessionData,
    GenerateMaterialSessionRequest,
    MaterialGenerationData,
)
from lsl.modules.material.service import MaterialService

router = APIRouter(prefix="/materials", tags=["materials"])


def get_material_service(request: Request) -> MaterialService:
    service = getattr(request.app.state, "material_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Material service is not initialized")
    return cast(MaterialService, service)


@router.post("/generate-session", response_model=ApiResponse[GenerateMaterialSessionData])
def generate_material_session(
    payload: GenerateMaterialSessionRequest,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.create_from_url(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/generations/{generation_id}", response_model=ApiResponse[MaterialGenerationData])
def get_material_generation(
    generation_id: str,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.get_generation(generation_id=generation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data)
