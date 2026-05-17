from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from lsl.modules.job.types import JobData
from lsl.modules.material.extractor.base import SourceInput, WebpageSourceInput
from lsl.modules.material.types import material_generation_status_to_name
from lsl.modules.session.schema import SessionData


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class GenerateMaterialSessionRequest(BaseModel):
    source: SourceInput
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    target_language: str = Field(..., max_length=16)
    cue_language: str | None = Field(default=None, max_length=16)
    prompt: str | None = Field(default=None, max_length=4000)
    turn_count: int = Field(default=8, ge=2, le=24)
    speaker_count: int = Field(default=2, ge=2, le=4)
    difficulty: str | None = Field(default="intermediate", max_length=32)
    cue_style: str | None = Field(default="自然口语、便于 TTS 演绎", max_length=200)
    must_include: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("title", "description", "cue_language", "prompt", "difficulty", "cue_style")
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

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class MaterialGenerationData(BaseModel):
    """Pydantic projection of MaterialGenerationModel.

    Built via `model_validate(model)` (from_attributes=True). The `_json`
    suffix on JSON columns is stripped here through validation_alias so the
    API output is clean (e.g. `source_payload`, not `source_payload_json`).
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    generation_id: str
    session_id: str
    source_type: str
    source_payload: dict[str, Any] = Field(default_factory=dict, validation_alias="source_payload_json")
    request_payload: dict[str, Any] = Field(default_factory=dict, validation_alias="request_payload_json")
    extracted_title: str | None = None
    extracted_text: str | None = None
    extracted_meta: dict[str, Any] = Field(default_factory=dict, validation_alias="extracted_meta_json")
    script_generation_id: str | None = None
    job_id: str | None = None
    status: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("source_payload", "request_payload", "extracted_meta", mode="before")
    @classmethod
    def _coerce_none_to_empty_dict(cls, value: Any) -> Any:
        return value if value is not None else {}

    @computed_field  # type: ignore[misc]
    @property
    def status_name(self) -> str:
        return material_generation_status_to_name(self.status)


class GenerateMaterialSessionData(BaseModel):
    session: SessionData
    material_generation: MaterialGenerationData
    job: JobData


__all__ = [
    "ApiResponse",
    "GenerateMaterialSessionData",
    "GenerateMaterialSessionRequest",
    "MaterialGenerationData",
    "SourceInput",
    "WebpageSourceInput",
]
