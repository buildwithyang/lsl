from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from lsl.modules.job.types import JobData
from lsl.modules.transcript.schema import TranscriptData


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class CreateAsrRecognitionRequest(BaseModel):
    object_key: str = Field(..., min_length=1, max_length=1024)
    audio_url: str = Field(..., min_length=1, max_length=4096)
    target_language: str | None = Field(default=None, max_length=16)

    @field_validator("object_key")
    @classmethod
    def normalize_object_key(cls, value: str) -> str:
        normalized = value.strip().lstrip("/")
        if not normalized:
            raise ValueError("object_key is required")
        return normalized

    @field_validator("audio_url")
    @classmethod
    def normalize_audio_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("audio_url is required")
        return normalized


class AsrRecognitionData(BaseModel):
    recognition_id: str
    transcript_id: str
    job_id: str | None = None
    object_key: str
    audio_url: str
    target_language: str | None = None
    provider: str
    status: int
    status_name: str
    provider_request_id: str | None = None
    provider_resource_id: str | None = None
    x_tt_logid: str | None = None
    provider_status_code: str | None = None
    provider_message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    poll_count: int
    last_polled_at: datetime | None = None
    next_poll_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateAsrRecognitionData(BaseModel):
    recognition: AsrRecognitionData
    transcript: TranscriptData
    job: JobData


class AsrRecognitionListResponseData(BaseModel):
    items: list[AsrRecognitionData]
