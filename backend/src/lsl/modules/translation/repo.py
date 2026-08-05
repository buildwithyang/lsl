from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload, sessionmaker

from lsl.modules.translation.model import TranslationItemModel, TranslationModel
from lsl.modules.translation.schema import TranslationData, TranslationItemData
from lsl.modules.translation.types import (
    TranslationItemStatus,
    TranslationSourceItem,
    TranslationStatus,
    translation_item_status_to_name,
    translation_status_to_name,
)


class TranslationRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def get_translation_by_id(self, translation_id: str) -> TranslationData | None:
        normalized_translation_id = self._parse_uuid_str(translation_id)
        if normalized_translation_id is None:
            return None
        stmt = (
            select(TranslationModel)
            .options(selectinload(TranslationModel.items))
            .where(TranslationModel.translation_id == normalized_translation_id)
            .limit(1)
        )
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_data(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query translation by id: {exc}") from exc

    def get_translation_by_source(
        self,
        *,
        source_type: str,
        source_entity_id: str,
        target_language: str,
    ) -> TranslationData | None:
        stmt = (
            select(TranslationModel)
            .options(selectinload(TranslationModel.items))
            .where(
                TranslationModel.source_type == source_type,
                TranslationModel.source_entity_id == source_entity_id,
                TranslationModel.target_language == target_language,
            )
            .limit(1)
        )
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_data(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query translation by source: {exc}") from exc

    def upsert_translation(
        self,
        *,
        translation_id: str,
        session_id: str | None,
        source_type: str,
        source_entity_id: str,
        source_language: str | None,
        target_language: str,
        provider: str,
        model_name: str | None,
        source_items: list[TranslationSourceItem],
        remove_missing: bool = True,
    ) -> TranslationData:
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        normalized_session_id = self._require_uuid(session_id, field_name="session_id") if session_id else None
        try:
            with self._session_scope() as db:
                stmt = (
                    select(TranslationModel)
                    .options(selectinload(TranslationModel.items))
                    .where(
                        TranslationModel.source_type == source_type,
                        TranslationModel.source_entity_id == source_entity_id,
                        TranslationModel.target_language == target_language,
                    )
                    .limit(1)
                )
                model = db.execute(stmt).scalar_one_or_none()
                if model is None:
                    model = TranslationModel(
                        translation_id=normalized_translation_id,
                        source_type=source_type,
                        source_entity_id=source_entity_id,
                        target_language=target_language,
                        provider=provider,
                    )
                    db.add(model)

                model.session_id = normalized_session_id or model.session_id
                model.source_language = source_language
                model.provider = provider
                model.model = model_name
                model.error_code = None
                model.error_message = None

                existing_by_key = {item.source_item_key: item for item in model.items}
                incoming_keys = {item.source_item_key for item in source_items}
                if remove_missing:
                    for item in list(model.items):
                        if item.source_item_key not in incoming_keys:
                            model.items.remove(item)

                for source_item in source_items:
                    item = existing_by_key.get(source_item.source_item_key)
                    if item is None:
                        model.items.append(
                            TranslationItemModel(
                                item_id=uuid.uuid4().hex,
                                translation_id=model.translation_id,
                                source_item_key=source_item.source_item_key,
                                source_seq=source_item.source_seq,
                                speaker=source_item.speaker,
                                source_text=source_item.source_text,
                                status=int(TranslationItemStatus.PENDING),
                            )
                        )
                        continue

                    changed = (item.source_text or "").strip() != (source_item.source_text or "").strip()
                    item.source_seq = source_item.source_seq
                    item.speaker = source_item.speaker
                    item.source_text = source_item.source_text
                    if changed:
                        item.translated_text = None
                        item.status = int(TranslationItemStatus.PENDING)
                        item.error_code = None
                        item.error_message = None

                self._refresh_counts(model)
                db.commit()
                db.refresh(model)
                _ = list(model.items)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to upsert translation: {exc}") from exc

    def set_job_id(self, *, translation_id: str, job_id: str | None, status: int) -> TranslationData:
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        normalized_job_id = self._require_uuid(job_id, field_name="job_id") if job_id is not None else None
        try:
            with self._session_scope() as db:
                model = self._get_required_translation(db, normalized_translation_id)
                model.job_id = normalized_job_id
                model.status = int(status)
                model.error_code = None
                model.error_message = None
                db.commit()
                db.refresh(model)
                _ = list(model.items)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to set translation job id: {exc}") from exc

    def mark_items_generating(self, *, translation_id: str, source_item_keys: list[str]) -> None:
        if not source_item_keys:
            return
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        try:
            with self._session_scope() as db:
                model = self._get_required_translation(db, normalized_translation_id)
                keys = set(source_item_keys)
                for item in model.items:
                    if item.source_item_key in keys:
                        item.status = int(TranslationItemStatus.GENERATING)
                        item.error_code = None
                        item.error_message = None
                self._refresh_counts(model)
                model.status = int(TranslationStatus.GENERATING)
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark translation items generating: {exc}") from exc

    def apply_suggestions(
        self,
        *,
        translation_id: str,
        suggestions: dict[str, str],
    ) -> TranslationData:
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        try:
            with self._session_scope() as db:
                model = self._get_required_translation(db, normalized_translation_id)
                for item in model.items:
                    text = suggestions.get(item.source_item_key)
                    if text is None:
                        continue
                    item.translated_text = text
                    item.status = int(TranslationItemStatus.COMPLETED)
                    item.error_code = None
                    item.error_message = None
                self._refresh_counts(model)
                db.commit()
                db.refresh(model)
                _ = list(model.items)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to apply translation suggestions: {exc}") from exc

    def mark_items_failed(
        self,
        *,
        translation_id: str,
        source_item_keys: list[str],
        error_code: str,
        error_message: str | None,
    ) -> TranslationData:
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        try:
            with self._session_scope() as db:
                model = self._get_required_translation(db, normalized_translation_id)
                keys = set(source_item_keys)
                for item in model.items:
                    if item.source_item_key in keys:
                        item.status = int(TranslationItemStatus.FAILED)
                        item.error_code = error_code
                        item.error_message = error_message
                self._refresh_counts(model)
                db.commit()
                db.refresh(model)
                _ = list(model.items)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark translation items failed: {exc}") from exc

    def mark_completed(self, *, translation_id: str, raw_result: dict[str, Any] | None = None) -> TranslationData:
        return self._mark_terminal(
            translation_id=translation_id,
            status=int(TranslationStatus.COMPLETED),
            error_code=None,
            error_message=None,
            raw_result=raw_result,
        )

    def mark_partial(self, *, translation_id: str, error_message: str | None = None) -> TranslationData:
        return self._mark_terminal(
            translation_id=translation_id,
            status=int(TranslationStatus.PARTIAL),
            error_code="translation_partial",
            error_message=error_message,
            raw_result=None,
        )

    def mark_failed(self, *, translation_id: str, error_code: str, error_message: str | None) -> TranslationData:
        return self._mark_terminal(
            translation_id=translation_id,
            status=int(TranslationStatus.FAILED),
            error_code=error_code,
            error_message=error_message,
            raw_result=None,
        )

    def _mark_terminal(
        self,
        *,
        translation_id: str,
        status: int,
        error_code: str | None,
        error_message: str | None,
        raw_result: dict[str, Any] | None,
    ) -> TranslationData:
        normalized_translation_id = self._require_uuid(translation_id, field_name="translation_id")
        try:
            with self._session_scope() as db:
                model = self._get_required_translation(db, normalized_translation_id)
                model.job_id = None
                model.error_code = error_code
                model.error_message = error_message
                if raw_result is not None:
                    model.raw_result_json = raw_result
                if int(status) in {int(TranslationStatus.FAILED), int(TranslationStatus.PARTIAL)}:
                    for item in model.items:
                        if int(item.status) != int(TranslationItemStatus.COMPLETED):
                            item.status = int(TranslationItemStatus.FAILED)
                            item.error_code = error_code
                            item.error_message = error_message
                self._refresh_counts(model)
                if int(status) == int(TranslationStatus.COMPLETED):
                    if model.item_count > 0 and model.completed_count == model.item_count:
                        model.status = int(TranslationStatus.COMPLETED)
                    else:
                        model.status = int(TranslationStatus.PARTIAL)
                        model.error_code = "translation_incomplete"
                        model.error_message = "translation completed without all items"
                else:
                    model.status = int(status)
                db.commit()
                db.refresh(model)
                _ = list(model.items)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark translation terminal: {exc}") from exc

    def _get_required_translation(self, db: OrmSession, translation_id: str) -> TranslationModel:
        model = db.get(TranslationModel, self._require_uuid(translation_id, field_name="translation_id"))
        if model is None:
            raise RuntimeError("Translation not found")
        _ = list(model.items)
        return model

    @staticmethod
    def _refresh_counts(model: TranslationModel) -> None:
        model.item_count = len(model.items)
        model.completed_count = sum(1 for item in model.items if int(item.status) == int(TranslationItemStatus.COMPLETED))
        pending_count = sum(1 for item in model.items if int(item.status) == int(TranslationItemStatus.PENDING))
        generating_count = sum(1 for item in model.items if int(item.status) == int(TranslationItemStatus.GENERATING))
        failed_count = sum(1 for item in model.items if int(item.status) == int(TranslationItemStatus.FAILED))
        unfinished_count = pending_count + generating_count + failed_count
        if model.item_count > 0 and model.completed_count == model.item_count:
            model.status = int(TranslationStatus.COMPLETED)
        elif model.job_id is not None and unfinished_count > 0:
            model.status = int(TranslationStatus.GENERATING)
        elif failed_count > 0 and unfinished_count == failed_count:
            model.status = int(TranslationStatus.FAILED)
        elif model.completed_count > 0 or failed_count > 0:
            model.status = int(TranslationStatus.PARTIAL)
        elif model.item_count > 0:
            model.status = int(TranslationStatus.PENDING)

    @staticmethod
    def _to_data(model: TranslationModel) -> TranslationData:
        status = int(model.status)
        return TranslationData(
            translation_id=model.translation_id,
            session_id=model.session_id,
            source_type=model.source_type,
            source_entity_id=model.source_entity_id,
            source_language=model.source_language,
            target_language=model.target_language,
            job_id=model.job_id,
            provider=model.provider,
            model=model.model,
            status=status,
            status_name=translation_status_to_name(status),
            item_count=int(model.item_count),
            completed_count=int(model.completed_count),
            error_code=model.error_code,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            items=[
                TranslationItemData(
                    item_id=item.item_id,
                    translation_id=item.translation_id,
                    source_item_key=item.source_item_key,
                    source_seq=item.source_seq,
                    speaker=item.speaker,
                    source_text=item.source_text,
                    translated_text=item.translated_text,
                    status=int(item.status),
                    status_name=translation_item_status_to_name(int(item.status)),
                    error_code=item.error_code,
                    error_message=item.error_message,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in sorted(model.items, key=lambda value: (value.source_seq is None, value.source_seq or 0, value.source_item_key))
            ],
        )

    @staticmethod
    def _parse_uuid_str(value: str | None) -> str | None:
        try:
            return uuid.UUID(str(value)).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str | None, *, field_name: str) -> str:
        parsed = TranslationRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed
