from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from lsl.modules.job.types import JobData
from lsl.modules.revision.schema import RevisionData
from lsl.modules.session.schema import SessionData


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class GenerateScriptSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    target_language: str | None = Field(default="en-US", max_length=16)
    cue_language: str | None = Field(default=None, max_length=16)
    prompt: str = Field(..., min_length=1, max_length=4000)
    turn_count: int = Field(default=8, ge=2, le=36)
    speaker_count: int = Field(default=2, ge=2, le=4)
    difficulty: str | None = Field(default="intermediate", max_length=32)
    cue_style: str | None = Field(default="自然口语、便于 TTS 演绎", max_length=200)
    must_include: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("target_language", "cue_language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt is required")
        return normalized

    @field_validator("difficulty")
    @classmethod
    def normalize_difficulty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("cue_style")
    @classmethod
    def normalize_cue_style(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized:
                result.append(normalized)
        return result


class ScriptGenerationData(BaseModel):
    generation_id: str
    session_id: str
    transcript_id: str | None = None
    job_id: str | None = None
    material_generation_id: str | None = None
    provider: str
    title: str
    description: str | None = None
    target_language: str | None = None
    cue_language: str | None = None
    prompt: str
    turn_count: int
    speaker_count: int
    difficulty: str | None = None
    cue_style: str | None = None
    must_include: list[str]
    plan_sections: list[dict[str, Any]] = Field(default_factory=list)
    raw_result: dict[str, Any] | None = None
    status: int
    status_name: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ScriptGenerationData":
        return cls(**row)


class ScriptGenerationPreviewItemData(BaseModel):
    seq: int
    speaker: str
    cue: str
    text: str


class ScriptGenerationPreviewData(BaseModel):
    generation: ScriptGenerationData
    items: list[ScriptGenerationPreviewItemData]


class GenerateScriptSessionData(BaseModel):
    session: SessionData
    generation: ScriptGenerationData
    job: JobData
    revision: RevisionData | None = None
