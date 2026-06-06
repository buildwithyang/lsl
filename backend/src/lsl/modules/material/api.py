from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.material.schema import (
    ApiResponse,
    CreatePodcastSessionRequest,
    ExtractMaterialRequest,
    ExtractedContentData,
    GenerateScriptSessionData,
)
from lsl.modules.material.service import MaterialService

router = APIRouter(prefix="/materials", tags=["materials"])


def get_material_service(request: Request) -> MaterialService:
    service = getattr(request.app.state, "material_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Material service is not initialized")
    return cast(MaterialService, service)


@router.post("/extract", response_model=ApiResponse[ExtractedContentData])
def extract_material(
    payload: ExtractMaterialRequest,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.extract(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/create-session", response_model=ApiResponse[GenerateScriptSessionData])
def create_podcast_session(
    payload: CreatePodcastSessionRequest,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.create_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=data)
