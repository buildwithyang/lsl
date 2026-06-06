from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from lsl.modules.material.extractor.base import SourceInput, WebpageSourceInput
from lsl.modules.script.schema import GenerateScriptSessionData


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class ExtractMaterialRequest(BaseModel):
    source: SourceInput


class ExtractedContentData(BaseModel):
    title: str | None = None
    main_text: str
    canonical_url: str | None = None
    truncated: bool = False
    char_count: int


class CreatePodcastSessionRequest(BaseModel):
    source: SourceInput
    extracted_title: str | None = Field(default=None, max_length=500)
    extracted_text: str = Field(..., min_length=1)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    target_language: str = Field(..., max_length=16)
    cue_language: str | None = Field(default=None, max_length=16)
    prompt: str | None = Field(default=None, max_length=4000)
    turn_count: int = Field(default=16, ge=2, le=36)
    speaker_count: int = Field(default=2, ge=2, le=4)
    difficulty: str | None = Field(default="intermediate", max_length=32)
    cue_style: str | None = Field(default="自然口语、便于 TTS 演绎", max_length=200)
    must_include: list[str] = Field(default_factory=list, max_length=12)

    @field_validator(
        "extracted_title",
        "title",
        "description",
        "cue_language",
        "prompt",
        "difficulty",
        "cue_style",
    )
    @classmethod
    def normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("target_language")
    @classmethod
    def normalize_target_language(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_language is required")
        return normalized

    @field_validator("extracted_text")
    @classmethod
    def normalize_extracted_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("extracted_text is required")
        return normalized

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


__all__ = [
    "ApiResponse",
    "CreatePodcastSessionRequest",
    "ExtractMaterialRequest",
    "ExtractedContentData",
    "GenerateScriptSessionData",
    "SourceInput",
    "WebpageSourceInput",
]
