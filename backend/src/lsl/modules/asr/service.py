from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from lsl.modules.asr.repo import AsrRepository
from lsl.modules.asr.schema import AsrRecognitionData, CreateAsrRecognitionData
from lsl.modules.asr.types import (
    AsrJobRef,
    AsrJobStatus,
    AsrProvider,
    AsrRecognitionStatus,
    AsrSubmitRequest,
)
from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobHandler, JobRunResult, JobStatus
from lsl.modules.transcript.service import TranscriptService
from lsl.modules.transcript.types import TranscriptStatus, TranscriptUtterance

if TYPE_CHECKING:
    from lsl.modules.translation.service import TranslationService

logger = logging.getLogger(__name__)


class AsrService:
    def __init__(
        self,
        *,
        repository: AsrRepository,
        transcript_service: TranscriptService,
        job_service: JobService,
        provider: AsrProvider,
        translation_service: TranslationService | None = None,
    ) -> None:
        self._repository = repository
        self._transcript_service = transcript_service
        self._job_service = job_service
        self._provider = provider

    def create_recognition(
        self,
        *,
        object_key: str,
        audio_url: str,
        target_language: str | None,
    ) -> CreateAsrRecognitionData:
        normalized_object_key = object_key.strip().lstrip("/")
        if not normalized_object_key:
            raise ValueError("object_key is required")
        normalized_audio_url = audio_url.strip()
        if not normalized_audio_url:
            raise ValueError("audio_url is required")

        transcript = self._transcript_service.create_pending_transcript(
            source_type="asr",
            source_entity_id=None,
            language=target_language,
        )
        recognition_id = uuid.uuid4().hex
        recognition = self._repository.create_recognition(
            recognition_id=recognition_id,
            transcript_id=transcript.transcript_id,
            object_key=normalized_object_key,
            audio_url=normalized_audio_url,
            target_language=target_language,
            provider=self._provider_name(),
        )
        self._transcript_service.update_source_entity(
            transcript_id=transcript.transcript_id,
            source_entity_id=recognition.recognition_id,
        )
        job = self._job_service.create_job(
            job_type=AsrJobHandler.job_type,
            entity_type="asr_recognition",
            entity_id=recognition.recognition_id,
            payload={"recognition_id": recognition.recognition_id},
        )
        self._repository.set_job_id(recognition_id=recognition.recognition_id, job_id=job.job_id)
        recognition = self.get_recognition(recognition_id=recognition.recognition_id)
        transcript = self._transcript_service.get_transcript(transcript_id=transcript.transcript_id)
        return CreateAsrRecognitionData(recognition=recognition, transcript=transcript, job=job)

    def get_recognition(self, *, recognition_id: str) -> AsrRecognitionData:
        recognition = self._repository.get_recognition_by_id(recognition_id)
        if recognition is None:
            raise ValueError("asr recognition not found")
        return recognition

    def list_recognitions(self, *, limit: int = 20, status: int | None = None) -> list[AsrRecognitionData]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 100:
            raise ValueError("limit must be less than or equal to 100")
        return self._repository.list_recognitions(limit=limit, status=status)

    def run_recognition_job(self, *, recognition_id: str) -> JobRunResult:
        recognition = self.get_recognition(recognition_id=recognition_id)
        if recognition.status == int(AsrRecognitionStatus.COMPLETED):
            return JobRunResult(status=JobStatus.COMPLETED, progress=100)
        if recognition.status == int(AsrRecognitionStatus.FAILED):
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code=recognition.error_code,
                error_message=recognition.error_message,
            )

        if not recognition.provider_request_id:
            return self._submit_recognition(recognition)
        return self._query_recognition(recognition)

    def _submit_recognition(self, recognition: AsrRecognitionData) -> JobRunResult:
        try:
            submit_result = self._provider.submit(
                AsrSubmitRequest(
                    recognition_id=recognition.recognition_id,
                    audio_url=recognition.audio_url,
                    language=recognition.target_language,
                )
            )
        except NotImplementedError as exc:
            self._repository.mark_failed(
                recognition_id=recognition.recognition_id,
                error_code="PROVIDER_NOT_IMPLEMENTED",
                error_message=str(exc),
            )
            self._transcript_service.mark_failed(
                transcript_id=recognition.transcript_id,
                error_code="PROVIDER_NOT_IMPLEMENTED",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="PROVIDER_NOT_IMPLEMENTED", error_message=str(exc))
        except Exception as exc:
            self._repository.mark_failed(
                recognition_id=recognition.recognition_id,
                error_code="PROVIDER_SUBMIT_ERROR",
                error_message=str(exc),
            )
            self._transcript_service.mark_failed(
                transcript_id=recognition.transcript_id,
                error_code="PROVIDER_SUBMIT_ERROR",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="PROVIDER_SUBMIT_ERROR", error_message=str(exc))

        self._repository.mark_submitted(
            recognition_id=recognition.recognition_id,
            provider_request_id=submit_result.provider_request_id,
            provider_resource_id=submit_result.provider_resource_id,
            x_tt_logid=submit_result.x_tt_logid,
            next_poll_at=self._next_poll_time(poll_count=0),
        )
        return JobRunResult(status=JobStatus.RUNNING, progress=10, next_run_at=self._next_poll_time(poll_count=0))

    def _query_recognition(self, recognition: AsrRecognitionData) -> JobRunResult:
        query_ref = AsrJobRef(
            recognition_id=recognition.recognition_id,
            provider=recognition.provider,
            provider_request_id=recognition.provider_request_id or "",
            provider_resource_id=recognition.provider_resource_id,
            x_tt_logid=recognition.x_tt_logid,
        )
        try:
            query_result = self._provider.query(query_ref)
        except Exception as exc:
            self._repository.mark_failed(
                recognition_id=recognition.recognition_id,
                error_code="PROVIDER_QUERY_ERROR",
                error_message=str(exc),
            )
            self._transcript_service.mark_failed(
                transcript_id=recognition.transcript_id,
                error_code="PROVIDER_QUERY_ERROR",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="PROVIDER_QUERY_ERROR", error_message=str(exc))

        if query_result.status in (AsrJobStatus.QUEUED, AsrJobStatus.PROCESSING):
            next_poll_at = self._next_poll_time(poll_count=int(recognition.poll_count) + 1)
            self._repository.mark_processing(
                recognition_id=recognition.recognition_id,
                provider_status_code=query_result.provider_status_code,
                provider_message=query_result.provider_message,
                x_tt_logid=query_result.x_tt_logid,
                next_poll_at=next_poll_at,
            )
            return JobRunResult(status=JobStatus.RUNNING, progress=50, next_run_at=next_poll_at)

        if query_result.status == AsrJobStatus.FAILED:
            error_code = query_result.error_code or "PROVIDER_RECOGNITION_FAILED"
            error_message = query_result.error_message or query_result.provider_message
            self._repository.mark_failed(
                recognition_id=recognition.recognition_id,
                error_code=error_code,
                error_message=error_message,
                provider_status_code=query_result.provider_status_code,
                provider_message=query_result.provider_message,
                x_tt_logid=query_result.x_tt_logid,
            )
            self._transcript_service.mark_failed(
                transcript_id=recognition.transcript_id,
                error_code=error_code,
                error_message=error_message,
            )
            return JobRunResult(status=JobStatus.FAILED, error_code=error_code, error_message=error_message)

        if query_result.raw_result is None:
            error_message = "raw_result is missing on succeeded status"
            self._repository.mark_failed(
                recognition_id=recognition.recognition_id,
                error_code="INVALID_PROVIDER_RESULT",
                error_message=error_message,
                provider_status_code=query_result.provider_status_code,
                provider_message=query_result.provider_message,
                x_tt_logid=query_result.x_tt_logid,
            )
            self._transcript_service.mark_failed(
                transcript_id=recognition.transcript_id,
                error_code="INVALID_PROVIDER_RESULT",
                error_message=error_message,
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="INVALID_PROVIDER_RESULT", error_message=error_message)

        self._transcript_service.mark_completed(
            transcript_id=recognition.transcript_id,
            utterances=[
                TranscriptUtterance(
                    seq=item.seq,
                    text=item.text,
                    speaker=item.speaker,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    additions=item.additions,
                )
                for item in query_result.utterances
            ],
            full_text=query_result.full_text,
            duration_ms=query_result.duration_ms,
            raw_result=query_result.raw_result,
        )
        self._repository.mark_completed(
            recognition_id=recognition.recognition_id,
            provider_status_code=query_result.provider_status_code,
            provider_message=query_result.provider_message,
            x_tt_logid=query_result.x_tt_logid,
        )
        return JobRunResult(status=JobStatus.COMPLETED, progress=100)

    def _provider_name(self) -> str:
        return getattr(self._provider, "provider_name", "unknown")

    @staticmethod
    def _next_poll_time(*, poll_count: int) -> datetime:
        interval_sec = min(2 * max(1, poll_count + 1), 15)
        return datetime.now(timezone.utc) + timedelta(seconds=interval_sec)


class AsrJobHandler:
    job_type = "asr_recognition"

    def __init__(self, *, asr_service: AsrService) -> None:
        self._asr_service = asr_service

    def run(self, job: JobData) -> JobRunResult:
        recognition_id = str(job.payload.get("recognition_id") or job.entity_id or "").strip()
        if not recognition_id:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MISSING_RECOGNITION_ID",
                error_message="recognition_id is required",
            )
        return self._asr_service.run_recognition_job(recognition_id=recognition_id)
