from __future__ import annotations

import logging
from typing import Callable

from lsl.modules.material.extractor.base import ExtractedContent, SourceExtractor, SourceInput, WebpageSourceInput
from lsl.modules.material.schema import (
    CreatePodcastSessionRequest,
    ExtractMaterialRequest,
    ExtractedContentData,
)
from lsl.modules.script.schema import GenerateScriptSessionData, GenerateScriptSessionRequest
from lsl.modules.script.service import ScriptService

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "Podcast from webpage"
_MIN_EXTRACTED_TEXT_CHARS = 200


class MaterialService:
    def __init__(
        self,
        *,
        script_service: ScriptService,
        extractor_factory: Callable[[SourceInput], SourceExtractor],
    ) -> None:
        self._script_service = script_service
        self._extractor_factory = extractor_factory

    def extract(self, payload: ExtractMaterialRequest) -> ExtractedContentData:
        source = payload.source
        extractor = self._extractor_factory(source)
        extracted: ExtractedContent = extractor.extract(source)
        text = (extracted.main_text or "").strip()
        if len(text) < _MIN_EXTRACTED_TEXT_CHARS:
            raise ValueError("Extracted content is empty or too short")
        truncated = bool((extracted.meta or {}).get("truncated"))
        logger.info(
            "Material extracted source_type=%s url=%s text_len=%s truncated=%s",
            getattr(source, "type", None),
            self._canonical_source_url(source),
            len(text),
            truncated,
        )
        return ExtractedContentData(
            title=extracted.title,
            main_text=text,
            canonical_url=extracted.canonical_url or self._canonical_source_url(source),
            truncated=truncated,
            char_count=len(text),
        )

    def create_session(self, payload: CreatePodcastSessionRequest) -> GenerateScriptSessionData:
        title = payload.title or payload.extracted_title or _DEFAULT_TITLE
        prompt = self._build_prompt(
            extracted_title=payload.extracted_title,
            canonical_url=self._canonical_source_url(payload.source),
            extracted_text=payload.extracted_text,
            user_steering=payload.prompt,
        )
        script_request = GenerateScriptSessionRequest(
            title=title,
            description=payload.description,
            target_language=payload.target_language,
            cue_language=payload.cue_language,
            prompt=prompt,
            turn_count=payload.turn_count,
            speaker_count=payload.speaker_count,
            difficulty=payload.difficulty,
            cue_style=payload.cue_style,
            must_include=payload.must_include,
        )
        result = self._script_service.generate_session(script_request)
        logger.info(
            "Podcast session created session_id=%s script_generation_id=%s url=%s",
            result.session.session.session_id,
            result.generation.generation_id,
            self._canonical_source_url(payload.source),
        )
        return result

    @staticmethod
    def _canonical_source_url(source: SourceInput) -> str | None:
        if isinstance(source, WebpageSourceInput) or getattr(source, "type", None) == "webpage":
            url = getattr(source, "url", None)
            return str(url) if url is not None else None
        return None

    @staticmethod
    def _build_prompt(
        *,
        extracted_title: str | None,
        canonical_url: str | None,
        extracted_text: str,
        user_steering: str | None,
    ) -> str:
        parts: list[str] = []
        if extracted_title:
            parts.append(f"Webpage title: {extracted_title}")
        if canonical_url:
            parts.append(f"Source URL: {canonical_url}")
        parts.append("Generate a two-host podcast-style dialogue that discusses the content below.")
        parts.append(
            "Focus on the substantive ideas. Ignore reference lists, citations such as [1] or (Smith 2020), "
            "navigation links, headers, footers, share buttons, cookie notices, and other boilerplate that "
            "may appear in the extracted text."
        )
        if user_steering:
            parts.append(f"Additional instructions: {user_steering}")
        parts.append("Webpage content:")
        parts.append(extracted_text)
        return "\n\n".join(parts)
