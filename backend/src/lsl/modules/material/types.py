from __future__ import annotations

from enum import IntEnum, Enum


class SourceType(str, Enum):
    WEBPAGE = "webpage"


class MaterialGenerationStatus(IntEnum):
    PENDING = 0
    EXTRACTING = 1
    EXTRACTED = 2
    COMPLETED = 3
    FAILED = 4


def material_generation_status_to_name(status: int) -> str:
    mapping = {
        int(MaterialGenerationStatus.PENDING): "pending",
        int(MaterialGenerationStatus.EXTRACTING): "extracting",
        int(MaterialGenerationStatus.EXTRACTED): "extracted",
        int(MaterialGenerationStatus.COMPLETED): "completed",
        int(MaterialGenerationStatus.FAILED): "failed",
    }
    return mapping.get(int(status), "pending")
