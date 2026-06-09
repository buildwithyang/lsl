from __future__ import annotations

from datetime import timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.asset.schema import (
    ApiResponse,
    AssetListResponseData,
    CompleteUploadRequest,
    CompleteUploadResponseData,
    UploadUrlRequest,
    UploadUrlResponseData,
)
from lsl.modules.asset.service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


def get_asset_service(request: Request) -> AssetService:
    service = getattr(request.app.state, "asset_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Asset service is not initialized")
    return cast(AssetService, service)


@router.post("/upload-url", response_model=ApiResponse[UploadUrlResponseData])
def generate_upload_url(
    payload: UploadUrlRequest,
    asset_service: AssetService = Depends(get_asset_service),
):
    object_key = asset_service.generate_object_key(
        category=payload.category,
        entity_id=payload.entity_id,
        filename=payload.filename,
    )

    upload_url = asset_service.generate_upload_url(
        object_key=object_key,
        content_type=payload.content_type,
        expires=timedelta(minutes=10),
    )
    asset_url = asset_service.build_asset_url(object_key)

    return ApiResponse(
        data=UploadUrlResponseData(
            object_key=object_key,
            upload_url=upload_url,
            asset_url=asset_url,
        )
    )


@router.get("", response_model=ApiResponse[AssetListResponseData])
def list_assets(
    limit: int = 20,
    category: str | None = None,
    entity_id: str | None = None,
    asset_service: AssetService = Depends(get_asset_service),
):
    try:
        items = asset_service.list_assets(
            limit=limit,
            category=category,
            entity_id=entity_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ApiResponse(data=AssetListResponseData(items=items))


@router.post("/complete-upload", response_model=ApiResponse[CompleteUploadResponseData])
def complete_upload(
    payload: CompleteUploadRequest,
    asset_service: AssetService = Depends(get_asset_service),
):
    try:
        asset_service.complete_upload(
            object_key=payload.object_key,
            category=payload.category,
            entity_id=payload.entity_id,
            filename=payload.filename,
            content_type=payload.content_type,
            file_size=payload.file_size,
            etag=payload.etag,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ApiResponse(
        data=CompleteUploadResponseData(
            object_key=payload.object_key,
            asset_url=asset_service.build_asset_url(payload.object_key),
            status="acknowledged",
        )
    )
