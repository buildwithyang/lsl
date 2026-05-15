from __future__ import annotations

from lsl.core.config import Settings
from lsl.modules.material.extractor.base import SourceExtractor, WebpageSourceInput
from lsl.modules.material.extractor.webpage import WebpageExtractor


def build_extractor(payload, *, settings: Settings) -> SourceExtractor:
    if isinstance(payload, WebpageSourceInput) or getattr(payload, "type", None) == "webpage":
        return WebpageExtractor(
            timeout_seconds=settings.MATERIAL_WEBPAGE_TIMEOUT_SECONDS,
            max_body_bytes=settings.MATERIAL_WEBPAGE_MAX_BODY_BYTES,
            max_chars=settings.MATERIAL_EXTRACTED_TEXT_MAX_CHARS,
        )
    raise ValueError(f"Unsupported source type: {getattr(payload, 'type', payload)!r}")
