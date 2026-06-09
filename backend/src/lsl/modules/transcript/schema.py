from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class TranscriptUtteranceData(BaseModel):
    seq: int
    text: str
    speaker: str | None = None
    start_time: int
    end_time: int
    additions: dict[str, Any] = Field(default_factory=dict)


class TranscriptData(BaseModel):
    transcript_id: str
    source_type: str
    source_entity_id: str | None = None
    language: str | None = None
    duration_ms: int | None = None
    duration_sec: float | None = None
    full_text: str | None = None
    raw_result: dict[str, Any] | None = None
    status: int
    status_name: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    utterances: list[TranscriptUtteranceData] = Field(default_factory=list)


class TranscriptListResponseData(BaseModel):
    items: list[TranscriptData]


class TranscriptUtteranceListResponseData(BaseModel):
    items: list[TranscriptUtteranceData]
