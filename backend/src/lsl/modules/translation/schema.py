from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class CreateTranslationRequest(BaseModel):
    source_type: str = Field(..., min_length=1, max_length=32)
    source_entity_id: str = Field(..., min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=64)
    target_language: str | None = Field(default=None, min_length=2, max_length=16)
    force: bool = False

    @field_validator("source_type", "source_entity_id")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("session_id", "target_language")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TranslateTranslationItemRequest(BaseModel):
    source_type: str = Field(..., min_length=1, max_length=32)
    source_entity_id: str = Field(..., min_length=1, max_length=128)
    source_item_key: str = Field(..., min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=64)
    target_language: str | None = Field(default=None, min_length=2, max_length=16)

    @field_validator("source_type", "source_entity_id", "source_item_key")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("session_id", "target_language")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TranslationItemData(BaseModel):
    item_id: str
    translation_id: str
    source_item_key: str
    source_seq: int | None = None
    speaker: str | None = None
    start_time: int | None = None
    end_time: int | None = None
    source_text: str
    source_text_hash: str
    translated_text: str | None = None
    status: int
    status_name: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TranslationData(BaseModel):
    translation_id: str
    session_id: str | None = None
    source_type: str
    source_entity_id: str
    source_language: str | None = None
    target_language: str
    job_id: str | None = None
    provider: str
    model: str | None = None
    status: int
    status_name: str
    item_count: int
    completed_count: int
    stale_count: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[TranslationItemData] = Field(default_factory=list)
