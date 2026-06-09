from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class UploadUrlRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=128)


class CompleteUploadRequest(BaseModel):
    object_key: str = Field(..., min_length=1, max_length=1024)
    category: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=128)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=128)
    file_size: int | None = Field(default=None, ge=0)
    etag: str | None = Field(default=None, max_length=128)

    @field_validator("object_key")
    @classmethod
    def normalize_object_key(cls, value: str) -> str:
        normalized = value.strip().lstrip("/")
        if not normalized:
            raise ValueError("object_key is required")
        return normalized


class UploadUrlResponseData(BaseModel):
    object_key: str
    upload_url: str
    asset_url: str


class CompleteUploadResponseData(BaseModel):
    object_key: str
    asset_url: str
    status: str = "acknowledged"


class AssetData(BaseModel):
    object_key: str
    category: str
    entity_id: str
    filename: str | None = None
    content_type: str | None = None
    file_size: int | None = None
    etag: str | None = None
    upload_status: int
    created_at: datetime


class AssetListItemData(AssetData):
    asset_url: str


class AssetListResponseData(BaseModel):
    items: list[AssetListItemData]
