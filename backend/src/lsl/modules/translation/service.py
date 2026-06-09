from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobRunResult, JobStatus
from lsl.modules.translation.repo import TranslationRepository
from lsl.modules.translation.schema import TranslationData
from lsl.modules.translation.types import (
    TranslationGenerateRequest,
    TranslationGenerator,
    TranslationItemStatus,
    TranslationRequestItem,
    TranslationSourceItem,
    TranslationStatus,
)
from lsl.modules.transcript.service import TranscriptService

if TYPE_CHECKING:
    from lsl.modules.revision.repo import RevisionRepository


class TranslationService:
    def __init__(
        self,
        *,
        repository: TranslationRepository,
        generator: TranslationGenerator,
        transcript_service: TranscriptService,
        revision_repository: RevisionRepository,
        job_service: JobService | None = None,
        default_target_language: str = "zh-CN",
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._transcript_service = transcript_service
        self._revision_repository = revision_repository
        self._job_service = job_service
        self._default_target_language = default_target_language.strip() or "zh-CN"

    def get_translation(
        self,
        *,
        source_type: str,
        source_entity_id: str,
        target_language: str | None = None,
    ) -> TranslationData:
        normalized_source_type = self._normalize_source_type(source_type)
        source = self._load_source_items(source_type=normalized_source_type, source_entity_id=source_entity_id)
        target = self._normalize_language(target_language)
        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        if existing is None:
            raise ValueError("translation not found")
        return self._repository.upsert_translation(
            translation_id=existing.translation_id,
            session_id=existing.session_id,
            source_type=existing.source_type,
            source_entity_id=existing.source_entity_id,
            source_language=source.source_language,
            target_language=existing.target_language,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=source.items,
        )

    def create_translation(
        self,
        *,
        source_type: str,
        source_entity_id: str,
        session_id: str | None = None,
        target_language: str | None = None,
        force: bool = False,
    ) -> TranslationData:
        if self._job_service is None:
            raise RuntimeError("Job service is not initialized")
        normalized_source_type = self._normalize_source_type(source_type)
        source = self._load_source_items(source_type=normalized_source_type, source_entity_id=source_entity_id)
        target = self._normalize_language(target_language)
        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        translation = self._repository.upsert_translation(
            translation_id=existing.translation_id if existing else uuid.uuid4().hex,
            session_id=session_id or source.session_id,
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            source_language=source.source_language,
            target_language=target,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=source.items,
        )
        if not force and translation.status_name in {"pending", "generating"} and translation.job_id:
            return translation
        if (
            not force
            and translation.status_name == "completed"
            and translation.stale_count == 0
            and translation.completed_count == translation.item_count
        ):
            return translation

        job = self._job_service.create_job(
            job_type=TranslationJobHandler.job_type,
            entity_type="translation",
            entity_id=translation.translation_id,
            payload={
                "translation_id": translation.translation_id,
                "source_type": normalized_source_type,
                "source_entity_id": source_entity_id,
                "target_language": target,
            },
        )
        return self._repository.set_job_id(
            translation_id=translation.translation_id,
            job_id=job.job_id,
            status=int(TranslationStatus.GENERATING),
        )

    def translate_item(
        self,
        *,
        source_type: str,
        source_entity_id: str,
        source_item_key: str,
        session_id: str | None = None,
        target_language: str | None = None,
    ) -> TranslationData:
        normalized_source_type = self._normalize_source_type(source_type)
        source = self._load_source_items(source_type=normalized_source_type, source_entity_id=source_entity_id)
        target = self._normalize_language(target_language)
        if not any(item.source_item_key == source_item_key for item in source.items):
            raise ValueError("translation source item not found")

        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        translation = self._repository.upsert_translation(
            translation_id=existing.translation_id if existing else uuid.uuid4().hex,
            session_id=session_id or source.session_id,
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            source_language=source.source_language,
            target_language=target,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=source.items,
        )
        item = next((it for it in translation.items if it.source_item_key == source_item_key), None)
        if item is None:
            raise ValueError("translation source item not found")

        self._repository.mark_items_generating(
            translation_id=translation.translation_id,
            source_item_keys=[source_item_key],
        )
        req = TranslationGenerateRequest(
            translation_id=translation.translation_id,
            source_type=translation.source_type,
            source_entity_id=translation.source_entity_id,
            source_language=translation.source_language,
            target_language=translation.target_language,
            items=[
                TranslationRequestItem(
                    source_item_key=item.source_item_key,
                    source_seq=item.source_seq,
                    speaker=item.speaker,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    source_text=item.source_text,
                    source_text_hash=item.source_text_hash,
                )
            ],
        )
        try:
            suggestions = {
                suggestion.source_item_key: suggestion.translated_text
                for suggestion in self._generator.generate(req)
                if suggestion.source_item_key == source_item_key
            }
            if source_item_key not in suggestions:
                raise RuntimeError("translation provider returned no item result")

            final = self._repository.apply_suggestions(
                translation_id=translation.translation_id,
                suggestions=suggestions,
            )
            if final.item_count > 0 and final.completed_count == final.item_count:
                final = self._repository.mark_completed(
                    translation_id=translation.translation_id,
                    raw_result={"translated_count": 1},
                )
            return final
        except Exception as exc:
            self._repository.mark_items_failed(
                translation_id=translation.translation_id,
                source_item_keys=[source_item_key],
                error_code="translation_item_generation_failed",
                error_message=str(exc),
            )
            raise RuntimeError(f"Failed to translate item: {exc}") from exc

    def run_generation_job(self, *, translation_id: str, job_id: str) -> JobRunResult:
        translation = self._repository.get_translation_by_id(translation_id)
        if translation is None:
            return JobRunResult(status=JobStatus.FAILED, error_code="TRANSLATION_NOT_FOUND", error_message="translation not found")
        if (translation.job_id or "") != job_id:
            return JobRunResult(status=JobStatus.CANCELED, error_message="translation job superseded")

        source = self._load_source_items(source_type=translation.source_type, source_entity_id=translation.source_entity_id)
        translation = self._repository.upsert_translation(
            translation_id=translation.translation_id,
            session_id=translation.session_id or source.session_id,
            source_type=translation.source_type,
            source_entity_id=translation.source_entity_id,
            source_language=source.source_language,
            target_language=translation.target_language,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=source.items,
        )
        pending_items = [
            item
            for item in translation.items
            if item.status in {
                int(TranslationItemStatus.PENDING),
                int(TranslationItemStatus.GENERATING),
                int(TranslationItemStatus.STALE),
                int(TranslationItemStatus.FAILED),
            }
        ]
        if not pending_items:
            if translation.item_count > 0 and translation.completed_count == translation.item_count:
                self._repository.mark_completed(translation_id=translation_id)
                return JobRunResult(status=JobStatus.COMPLETED, progress=100)
            self._repository.mark_partial(
                translation_id=translation_id,
                error_message="translation has no runnable items but is not complete",
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="TRANSLATION_INCOMPLETE", error_message="translation has no runnable items but is not complete")

        self._repository.mark_items_generating(
            translation_id=translation_id,
            source_item_keys=[item.source_item_key for item in pending_items],
        )
        req = TranslationGenerateRequest(
            translation_id=translation_id,
            source_type=translation.source_type,
            source_entity_id=translation.source_entity_id,
            source_language=translation.source_language,
            target_language=translation.target_language,
            items=[
                TranslationRequestItem(
                    source_item_key=item.source_item_key,
                    source_seq=item.source_seq,
                    speaker=item.speaker,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    source_text=item.source_text,
                    source_text_hash=item.source_text_hash,
                )
                for item in pending_items
            ],
        )
        try:
            all_suggestions: dict[str, str] = {}
            for suggestions in self._generator.generate_progressively(req):
                batch = {suggestion.source_item_key: suggestion.translated_text for suggestion in suggestions}
                all_suggestions.update(batch)
                self._repository.apply_suggestions(translation_id=translation_id, suggestions=batch)

            final = self._repository.get_translation_by_id(translation_id)
            if final is None:
                return JobRunResult(status=JobStatus.FAILED, error_code="TRANSLATION_NOT_FOUND", error_message="translation not found")
            if final.completed_count == final.item_count:
                self._repository.mark_completed(translation_id=translation_id, raw_result={"translated_count": len(all_suggestions)})
                return JobRunResult(status=JobStatus.COMPLETED, progress=100)

            self._repository.mark_partial(translation_id=translation_id, error_message="some items were not translated")
            return JobRunResult(status=JobStatus.COMPLETED, progress=100)
        except Exception as exc:
            self._repository.mark_failed(
                translation_id=translation_id,
                error_code="translation_generation_failed",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="TRANSLATION_GENERATION_FAILED", error_message=str(exc))

    def _load_source_items(self, *, source_type: str, source_entity_id: str) -> "_TranslationSource":
        if source_type == "transcript":
            transcript = self._transcript_service.get_transcript(transcript_id=source_entity_id)
            return _TranslationSource(
                session_id=None,
                source_language=transcript.language,
                items=[
                    TranslationSourceItem(
                        source_item_key=str(item.seq),
                        source_seq=int(item.seq),
                        speaker=item.speaker,
                        start_time=int(item.start_time),
                        end_time=int(item.end_time),
                        source_text=item.text,
                    )
                    for item in transcript.utterances
                ],
            )

        if source_type == "revision":
            revision = self._revision_repository.get_revision_by_id(source_entity_id)
            if revision is None:
                raise ValueError("revision not found")
            transcript = self._transcript_service.get_transcript(transcript_id=str(revision.transcript_id), include_raw=False)
            return _TranslationSource(
                session_id=str(revision.session_id),
                source_language=transcript.language,
                items=[
                    TranslationSourceItem(
                        source_item_key=str(item.item_id),
                        source_seq=int(item.source_seq_start),
                        speaker=item.speaker,
                        start_time=int(item.start_time),
                        end_time=int(item.end_time),
                        source_text=(item.draft_text or item.suggested_text or "").strip(),
                    )
                    for item in revision.items
                    if (item.draft_text or item.suggested_text or "").strip()
                ],
            )

        raise ValueError(f"unsupported translation source_type: {source_type}")

    def _normalize_language(self, value: str | None) -> str:
        return (value or self._default_target_language).strip() or "zh-CN"

    @staticmethod
    def _normalize_source_type(value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"transcript", "revision"}:
            raise ValueError(f"unsupported translation source_type: {value}")
        return normalized

    def _provider_name(self) -> str:
        return getattr(self._generator, "provider_name", "unknown")

    def _model_name(self) -> str | None:
        value = getattr(self._generator, "_model", None)
        return str(value) if value else None


class _TranslationSource:
    def __init__(
        self,
        *,
        session_id: str | None,
        source_language: str | None,
        items: list[TranslationSourceItem],
    ) -> None:
        self.session_id = session_id
        self.source_language = source_language
        self.items = items


class TranslationJobHandler:
    job_type = "translation_generation"

    def __init__(self, *, translation_service: TranslationService) -> None:
        self._translation_service = translation_service

    def run(self, job: JobData) -> JobRunResult:
        translation_id = str(job.payload.get("translation_id") or job.entity_id or "").strip()
        if not translation_id:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MISSING_TRANSLATION_ID",
                error_message="translation_id is required",
            )
        return self._translation_service.run_generation_job(translation_id=translation_id, job_id=job.job_id)
