
from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.translation.schema import (
    ApiResponse,
    CreateTranslationRequest,
    TranslateTranslationItemRequest,
    TranslationData,
    TranslationSourceItemPayload,
)
from lsl.modules.translation.service import TranslationService
from lsl.modules.translation.types import TranslationSourceItem


def _to_source_item(payload: TranslationSourceItemPayload) -> TranslationSourceItem:
    return TranslationSourceItem(
        source_item_key=payload.source_item_key,
        source_seq=payload.source_seq,
        speaker=payload.speaker,
        source_text=payload.source_text,
    )

router = APIRouter(prefix="/translations", tags=["translations"])


def get_translation_service(request: Request) -> TranslationService:
    service = getattr(request.app.state, "translation_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Translation service is not initialized")
    return cast(TranslationService, service)


@router.post("", response_model=ApiResponse[TranslationData])
def create_translation(
    payload: CreateTranslationRequest,
    translation_service: TranslationService = Depends(get_translation_service),
):
    try:
        translation = translation_service.create_translation(
            source_type=payload.source_type,
            source_entity_id=payload.source_entity_id,
            items=[_to_source_item(item) for item in payload.items],
            session_id=payload.session_id,
            source_language=payload.source_language,
            target_language=payload.target_language,
            force=payload.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=translation)


@router.post("/items/translate", response_model=ApiResponse[TranslationData])
def translate_item(
    payload: TranslateTranslationItemRequest,
    translation_service: TranslationService = Depends(get_translation_service),
):
    try:
        translation = translation_service.translate_item(
            source_type=payload.source_type,
            source_entity_id=payload.source_entity_id,
            item=_to_source_item(payload.item),
            session_id=payload.session_id,
            source_language=payload.source_language,
            target_language=payload.target_language,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "translation source item not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse[TranslationData](data=translation)


@router.get("", response_model=ApiResponse[TranslationData])
def get_translation(
    source_type: str,
    source_entity_id: str,
    target_language: str | None = None,
    translation_service: TranslationService = Depends(get_translation_service),
):
    try:
        translation = translation_service.get_translation(
            source_type=source_type,
            source_entity_id=source_entity_id,
            target_language=target_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse[TranslationData](data=translation)
