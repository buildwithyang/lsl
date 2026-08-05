from __future__ import annotations

from enum import IntEnum
from typing import Iterator, Protocol

from pydantic import BaseModel, Field


class TranslationStatus(IntEnum):
    PENDING = 0
    GENERATING = 1
    COMPLETED = 2
    FAILED = 3
    PARTIAL = 4


class TranslationItemStatus(IntEnum):
    PENDING = 0
    GENERATING = 1
    COMPLETED = 2
    FAILED = 3


def translation_status_to_name(status_code: int) -> str:
    mapping = {
        int(TranslationStatus.PENDING): "pending",
        int(TranslationStatus.GENERATING): "generating",
        int(TranslationStatus.COMPLETED): "completed",
        int(TranslationStatus.FAILED): "failed",
        int(TranslationStatus.PARTIAL): "partial",
    }
    return mapping.get(int(status_code), "unknown")


def translation_item_status_to_name(status_code: int) -> str:
    mapping = {
        int(TranslationItemStatus.PENDING): "pending",
        int(TranslationItemStatus.GENERATING): "generating",
        int(TranslationItemStatus.COMPLETED): "completed",
        int(TranslationItemStatus.FAILED): "failed",
    }
    return mapping.get(int(status_code), "unknown")


class TranslationSourceItem(BaseModel):
    source_item_key: str
    source_seq: int | None = None
    speaker: str | None = None
    source_text: str


class TranslationGenerateRequest(BaseModel):
    translation_id: str
    source_type: str
    source_entity_id: str
    source_language: str | None = None
    target_language: str = "zh-CN"
    items: list[TranslationSourceItem] = Field(default_factory=list)


class TranslationSuggestion(BaseModel):
    source_item_key: str
    translated_text: str


class TranslationGenerator(Protocol):
    provider_name: str

    def generate(self, req: TranslationGenerateRequest) -> list[TranslationSuggestion]:
        ...

    def generate_progressively(self, req: TranslationGenerateRequest) -> Iterator[list[TranslationSuggestion]]:
        ...
