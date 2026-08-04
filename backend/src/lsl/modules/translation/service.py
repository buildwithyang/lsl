from __future__ import annotations

import uuid

from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobRunResult, JobStatus
from lsl.modules.translation.repo import TranslationRepository
from lsl.modules.translation.schema import TranslationData, TranslationItemData
from lsl.modules.translation.types import (
    TranslationGenerateRequest,
    TranslationGenerator,
    TranslationItemStatus,
    TranslationSourceItem,
    TranslationStatus,
)


class TranslationService:
    """Pure push-based translation store.

    The frontend pushes the source sentences to translate; this service never
    reads transcript or revision data back. Staleness ("re-translate after an
    edit") is decided entirely on the frontend, so there is no source
    reconciliation here.
    """

    def __init__(
        self,
        *,
        repository: TranslationRepository,
        generator: TranslationGenerator,
        job_service: JobService | None = None,
        default_target_language: str = "zh-CN",
    ) -> None:
        self._repository = repository
        self._generator = generator
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
        target = self._normalize_language(target_language)
        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        if existing is None:
            raise ValueError("translation not found")
        return existing

    def create_translation(
        self,
        *,
        source_type: str,
        source_entity_id: str,
        items: list[TranslationSourceItem],
        session_id: str | None = None,
        source_language: str | None = None,
        target_language: str | None = None,
        force: bool = False,
    ) -> TranslationData:
        if self._job_service is None:
            raise RuntimeError("Job service is not initialized")
        normalized_source_type = self._normalize_source_type(source_type)
        target = self._normalize_language(target_language)
        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        translation = self._repository.upsert_translation(
            translation_id=existing.translation_id if existing else uuid.uuid4().hex,
            session_id=session_id or (existing.session_id if existing else None),
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            source_language=source_language,
            target_language=target,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=items,
        )
        if translation.item_count == 0:
            return translation
        if not force and translation.status_name in {"pending", "generating"} and translation.job_id:
            return translation
        if (
            not force
            and translation.status_name == "completed"
            and translation.completed_count == translation.item_count
        ):
            return translation

        job = self._job_service.create_job(
            job_type=TranslationJobHandler.job_type,
            entity_type="translation",
            entity_id=translation.translation_id,
            payload={"translation_id": translation.translation_id},
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
        item: TranslationSourceItem,
        session_id: str | None = None,
        source_language: str | None = None,
        target_language: str | None = None,
    ) -> TranslationData:
        normalized_source_type = self._normalize_source_type(source_type)
        target = self._normalize_language(target_language)
        existing = self._repository.get_translation_by_source(
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            target_language=target,
        )
        translation = self._repository.upsert_translation(
            translation_id=existing.translation_id if existing else uuid.uuid4().hex,
            session_id=session_id or (existing.session_id if existing else None),
            source_type=normalized_source_type,
            source_entity_id=source_entity_id,
            source_language=source_language,
            target_language=target,
            provider=self._provider_name(),
            model_name=self._model_name(),
            source_items=[item],
            remove_missing=False,
        )
        stored = next((it for it in translation.items if it.source_item_key == item.source_item_key), None)
        if stored is None:
            raise ValueError("translation source item not found")

        self._repository.mark_items_generating(
            translation_id=translation.translation_id,
            source_item_keys=[item.source_item_key],
        )
        req = TranslationGenerateRequest(
            translation_id=translation.translation_id,
            source_type=translation.source_type,
            source_entity_id=translation.source_entity_id,
            source_language=translation.source_language,
            target_language=translation.target_language,
            items=[self._to_source_item(stored)],
        )
        try:
            suggestions = {
                suggestion.source_item_key: suggestion.translated_text
                for suggestion in self._generator.generate(req)
                if suggestion.source_item_key == item.source_item_key
            }
            if item.source_item_key not in suggestions:
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
                source_item_keys=[item.source_item_key],
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

        pending_items = [
            item
            for item in translation.items
            if item.status in {
                int(TranslationItemStatus.PENDING),
                int(TranslationItemStatus.GENERATING),
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
            items=[self._to_source_item(item) for item in pending_items],
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

    @staticmethod
    def _to_source_item(item: TranslationItemData) -> TranslationSourceItem:
        return TranslationSourceItem(
            source_item_key=item.source_item_key,
            source_seq=item.source_seq,
            speaker=item.speaker,
            start_time=item.start_time,
            end_time=item.end_time,
            source_text=item.source_text,
        )

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
