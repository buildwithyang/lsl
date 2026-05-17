from __future__ import annotations

import logging
import uuid
from typing import Callable

from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobRunResult, JobStatus
from lsl.modules.material.extractor.base import ExtractedContent, SourceInput, WebpageSourceInput
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.schema import (
    GenerateMaterialSessionData,
    GenerateMaterialSessionRequest,
    MaterialGenerationData,
)
from lsl.modules.script.service import ScriptService
from lsl.modules.session.schema import CreateSessionRequest, UpdateSessionRequest
from lsl.modules.session.service import SessionService

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "Podcast from webpage"
_MIN_EXTRACTED_TEXT_CHARS = 200


class MaterialService:
    def __init__(
        self,
        *,
        repository: MaterialRepository,
        session_service: SessionService,
        script_service: ScriptService,
        job_service: JobService,
        extractor_factory: Callable[[SourceInput], object],
    ) -> None:
        self._repository = repository
        self._session_service = session_service
        self._script_service = script_service
        self._job_service = job_service
        self._extractor_factory = extractor_factory

    def create_from_url(self, payload: GenerateMaterialSessionRequest) -> GenerateMaterialSessionData:
        session = self._session_service.create_session(
            CreateSessionRequest(
                title=payload.title or _DEFAULT_TITLE,
                description=payload.description,
                target_language=payload.target_language,
                f_type=2,
            )
        )
        generation_id = uuid.uuid4().hex
        self._repository.create_generation(
            generation_id=generation_id,
            session_id=session.session.session_id,
            source_type=payload.source.type,
            source_payload=self._source_to_payload(payload.source),
            request_payload=self._serialize_request(payload),
        )
        job = self._job_service.create_job(
            job_type=MaterialJobHandler.job_type,
            entity_type="material_generation",
            entity_id=generation_id,
            payload={"generation_id": generation_id},
        )
        self._repository.set_job_id(generation_id=generation_id, job_id=job.job_id)
        logger.info(
            "Material generation session created generation_id=%s session_id=%s job_id=%s source_type=%s",
            generation_id,
            session.session.session_id,
            job.job_id,
            payload.source.type,
        )
        generation = self._repository.get_by_id(generation_id)
        if generation is None:
            raise RuntimeError("material generation disappeared after creation")
        session = self._session_service.get_session(session.session.session_id, auto_refresh=False)
        return GenerateMaterialSessionData(
            session=session,
            material_generation=generation,
            job=job,
        )

    def get_generation(self, *, generation_id: str) -> MaterialGenerationData:
        row = self._repository.get_by_id(generation_id)
        if row is None:
            raise ValueError("material generation not found")
        return row

    def run_extract_job(self, *, generation_id: str) -> JobRunResult:
        """Phase 1 of the podcast flow: extract content from the source.

        Stops at `status=extracted`. The user must explicitly call
        `confirm_and_generate` to trigger script generation, or `cancel_generation`
        to abandon. This prevents wasted LLM spend when extraction is poor.
        """
        row = self._repository.get_by_id(generation_id)
        if row is None:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MATERIAL_GENERATION_NOT_FOUND",
                error_message="material generation not found",
            )
        if row.status_name in ("extracted", "completed", "cancelled"):
            return JobRunResult(status=JobStatus.COMPLETED, progress=100)

        self._repository.mark_extracting(generation_id=generation_id)
        try:
            source_input = self._build_source_input(row.source_type, row.source_payload)
            extractor = self._extractor_factory(source_input)
            extracted: ExtractedContent = extractor.extract(source_input)
        except Exception as exc:
            logger.exception("Material extraction failed generation_id=%s", generation_id)
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="EXTRACTION_FAILED",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="EXTRACTION_FAILED", error_message=str(exc))

        if len(extracted.main_text or "") < _MIN_EXTRACTED_TEXT_CHARS:
            message = "Extracted content is empty or too short"
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="EXTRACTION_EMPTY",
                error_message=message,
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="EXTRACTION_EMPTY", error_message=message)

        self._repository.mark_extracted(
            generation_id=generation_id,
            title=extracted.title,
            text=extracted.main_text,
            meta=extracted.meta,
        )
        if extracted.title:
            request_payload = row.request_payload
            self._session_service.update_session(
                session_id=row.session_id,
                payload=UpdateSessionRequest(
                    title=extracted.title,
                    description=request_payload.get("description"),
                    target_language=request_payload.get("target_language"),
                    f_type=2,
                ),
            )

        logger.info(
            "Material extract phase done generation_id=%s text_len=%s — awaiting user confirmation",
            generation_id,
            len(extracted.main_text or ""),
        )
        return JobRunResult(status=JobStatus.COMPLETED, progress=100)

    def confirm_and_generate(self, *, generation_id: str) -> MaterialGenerationData:
        """Phase 2: kick off script generation after the user has reviewed the
        extracted content."""
        row = self._repository.get_by_id(generation_id)
        if row is None:
            raise ValueError("material generation not found")
        status = row.status_name
        if status == "completed":
            return row
        if status != "extracted":
            raise ValueError(
                f"cannot confirm in status {status!r}; extraction must complete first"
            )

        request_payload = row.request_payload
        extracted = ExtractedContent(
            title=row.extracted_title,
            main_text=row.extracted_text or "",
            canonical_url=row.source_payload.get("url"),
            meta=row.extracted_meta,
        )
        prompt = self._build_prompt(
            extracted=extracted,
            user_steering=request_payload.get("prompt"),
        )

        try:
            script_generation, _job = self._script_service.start_generation_from_material(
                session_id=row.session_id,
                material_generation_id=generation_id,
                title=extracted.title or request_payload.get("title") or _DEFAULT_TITLE,
                description=request_payload.get("description"),
                target_language=request_payload.get("target_language"),
                cue_language=request_payload.get("cue_language"),
                prompt=prompt,
                turn_count=int(request_payload.get("turn_count") or 8),
                speaker_count=int(request_payload.get("speaker_count") or 2),
                difficulty=request_payload.get("difficulty"),
                cue_style=request_payload.get("cue_style"),
                must_include=list(request_payload.get("must_include") or []),
            )
        except Exception as exc:
            logger.exception("Script-from-material chain failed generation_id=%s", generation_id)
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="SCRIPT_GENERATION_FAILED",
                error_message=str(exc),
            )
            raise

        self._repository.set_script_generation_id(
            generation_id=generation_id,
            script_generation_id=script_generation.generation_id,
        )
        self._repository.mark_completed(generation_id=generation_id)
        logger.info(
            "Material confirmed and script generation started generation_id=%s script_generation_id=%s",
            generation_id,
            script_generation.generation_id,
        )
        return self.get_generation(generation_id=generation_id)

    def cancel_generation(self, *, generation_id: str) -> MaterialGenerationData:
        """User decided the extracted content isn't worth generating. Mark as
        cancelled. The session row is kept so the user can revisit / delete from
        the dashboard."""
        row = self._repository.get_by_id(generation_id)
        if row is None:
            raise ValueError("material generation not found")
        status = row.status_name
        if status in ("completed", "cancelled"):
            return row
        self._repository.mark_cancelled(generation_id=generation_id)
        logger.info("Material generation cancelled by user generation_id=%s", generation_id)
        return self.get_generation(generation_id=generation_id)

    @staticmethod
    def _build_source_input(source_type: str, payload: dict):
        if source_type == "webpage":
            return WebpageSourceInput(type="webpage", url=payload.get("url"))
        raise ValueError(f"Unsupported source type: {source_type!r}")

    @staticmethod
    def _build_prompt(*, extracted: ExtractedContent, user_steering: str | None) -> str:
        parts: list[str] = []
        if extracted.title:
            parts.append(f"Webpage title: {extracted.title}")
        if extracted.canonical_url:
            parts.append(f"Source URL: {extracted.canonical_url}")
        parts.append("Generate a two-host podcast-style dialogue that discusses the content below.")
        if user_steering:
            parts.append(f"Additional instructions: {user_steering}")
        parts.append("Webpage content:")
        parts.append(extracted.main_text)
        return "\n\n".join(parts)

    @staticmethod
    def _source_to_payload(source) -> dict[str, str]:
        if isinstance(source, WebpageSourceInput) or getattr(source, "type", None) == "webpage":
            return {"url": str(source.url)}
        raise ValueError(f"Unsupported source type: {getattr(source, 'type', None)!r}")

    @staticmethod
    def _serialize_request(payload: GenerateMaterialSessionRequest) -> dict:
        return {
            "title": payload.title,
            "description": payload.description,
            "target_language": payload.target_language,
            "cue_language": payload.cue_language,
            "prompt": payload.prompt,
            "turn_count": payload.turn_count,
            "speaker_count": payload.speaker_count,
            "difficulty": payload.difficulty,
            "cue_style": payload.cue_style,
            "must_include": list(payload.must_include),
        }


class MaterialJobHandler:
    job_type = "material_extraction"

    def __init__(self, *, material_service: MaterialService) -> None:
        self._material_service = material_service

    def run(self, job: JobData) -> JobRunResult:
        generation_id = str(job.payload.get("generation_id") or job.entity_id or "").strip()
        if not generation_id:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MISSING_GENERATION_ID",
                error_message="generation_id is required",
            )
        return self._material_service.run_extract_job(generation_id=generation_id)
