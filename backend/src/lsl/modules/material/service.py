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
        )
        job = self._job_service.create_job(
            job_type=MaterialJobHandler.job_type,
            entity_type="material_generation",
            entity_id=generation_id,
            payload={
                "generation_id": generation_id,
                "request": self._serialize_request(payload),
            },
        )
        self._repository.set_job_id(generation_id=generation_id, job_id=job.job_id)
        logger.info(
            "Material generation session created generation_id=%s session_id=%s job_id=%s source_type=%s",
            generation_id,
            session.session.session_id,
            job.job_id,
            payload.source.type,
        )
        generation = MaterialGenerationData.from_row(self._repository.get_by_id(generation_id))
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
        return MaterialGenerationData.from_row(row)

    def run_material_job(self, *, generation_id: str, request_payload: dict) -> JobRunResult:
        raise NotImplementedError("run_material_job is implemented in Task 11")

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
    job_type = "script_from_material"

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
        request_payload = job.payload.get("request") or {}
        return self._material_service.run_material_job(
            generation_id=generation_id,
            request_payload=dict(request_payload),
        )
