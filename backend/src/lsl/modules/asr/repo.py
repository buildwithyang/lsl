from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.asr.model import AsrRecognitionModel
from lsl.modules.asr.schema import AsrRecognitionData
from lsl.modules.asr.types import AsrRecognitionStatus, asr_recognition_status_to_name


class AsrRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_recognition(
        self,
        *,
        recognition_id: str,
        transcript_id: str,
        object_key: str,
        audio_url: str,
        target_language: str | None,
        provider: str,
    ) -> AsrRecognitionData:
        normalized_recognition_id = self._require_uuid(recognition_id, field_name="recognition_id")
        model = AsrRecognitionModel(
            recognition_id=normalized_recognition_id,
            transcript_id=self._require_uuid(transcript_id, field_name="transcript_id"),
            object_key=object_key,
            audio_url=audio_url,
            target_language=target_language,
            provider=provider,
            status=int(AsrRecognitionStatus.PENDING),
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create ASR recognition: {exc}") from exc

    def set_job_id(self, *, recognition_id: str, job_id: str) -> None:
        try:
            with self._session_scope() as db:
                model = self._get_required_recognition(db, recognition_id)
                model.job_id = self._require_uuid(job_id, field_name="job_id")
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to set ASR recognition job id: {exc}") from exc

    def get_recognition_by_id(self, recognition_id: str) -> AsrRecognitionData | None:
        normalized = self._parse_uuid_str(recognition_id)
        if normalized is None:
            return None
        stmt = select(AsrRecognitionModel).where(AsrRecognitionModel.recognition_id == normalized).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_data(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query ASR recognition: {exc}") from exc

    def list_recognitions(self, *, limit: int, status: int | None = None) -> list[AsrRecognitionData]:
        stmt = select(AsrRecognitionModel)
        if status is not None:
            stmt = stmt.where(AsrRecognitionModel.status == int(status))
        stmt = stmt.order_by(AsrRecognitionModel.created_at.desc()).limit(limit)
        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list ASR recognitions: {exc}") from exc

    def mark_submitted(
        self,
        *,
        recognition_id: str,
        provider_request_id: str,
        provider_resource_id: str | None,
        x_tt_logid: str | None,
        next_poll_at: datetime,
    ) -> AsrRecognitionData:
        try:
            with self._session_scope() as db:
                model = self._get_required_recognition(db, recognition_id)
                model.status = int(AsrRecognitionStatus.SUBMITTED)
                model.provider_request_id = provider_request_id
                model.provider_resource_id = provider_resource_id
                model.x_tt_logid = x_tt_logid
                model.next_poll_at = next_poll_at
                model.error_code = None
                model.error_message = None
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark ASR recognition submitted: {exc}") from exc

    def mark_processing(
        self,
        *,
        recognition_id: str,
        provider_status_code: str | None,
        provider_message: str | None,
        x_tt_logid: str | None,
        next_poll_at: datetime,
    ) -> AsrRecognitionData:
        try:
            with self._session_scope() as db:
                model = self._get_required_recognition(db, recognition_id)
                model.status = int(AsrRecognitionStatus.PROCESSING)
                model.provider_status_code = provider_status_code
                model.provider_message = provider_message
                model.x_tt_logid = x_tt_logid or model.x_tt_logid
                model.poll_count = int(model.poll_count) + 1
                model.last_polled_at = datetime.now(timezone.utc)
                model.next_poll_at = next_poll_at
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark ASR recognition processing: {exc}") from exc

    def mark_completed(
        self,
        *,
        recognition_id: str,
        provider_status_code: str | None,
        provider_message: str | None,
        x_tt_logid: str | None,
    ) -> AsrRecognitionData:
        try:
            with self._session_scope() as db:
                model = self._get_required_recognition(db, recognition_id)
                model.status = int(AsrRecognitionStatus.COMPLETED)
                model.provider_status_code = provider_status_code
                model.provider_message = provider_message
                model.x_tt_logid = x_tt_logid or model.x_tt_logid
                model.error_code = None
                model.error_message = None
                model.last_polled_at = datetime.now(timezone.utc)
                model.next_poll_at = None
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark ASR recognition completed: {exc}") from exc

    def mark_failed(
        self,
        *,
        recognition_id: str,
        error_code: str | None,
        error_message: str | None,
        provider_status_code: str | None = None,
        provider_message: str | None = None,
        x_tt_logid: str | None = None,
    ) -> AsrRecognitionData:
        try:
            with self._session_scope() as db:
                model = self._get_required_recognition(db, recognition_id)
                model.status = int(AsrRecognitionStatus.FAILED)
                model.error_code = error_code
                model.error_message = error_message
                model.provider_status_code = provider_status_code
                model.provider_message = provider_message
                model.x_tt_logid = x_tt_logid or model.x_tt_logid
                model.last_polled_at = datetime.now(timezone.utc)
                model.next_poll_at = None
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark ASR recognition failed: {exc}") from exc

    def _get_required_recognition(self, db: OrmSession, recognition_id: str) -> AsrRecognitionModel:
        normalized = self._require_uuid(recognition_id, field_name="recognition_id")
        model = db.get(AsrRecognitionModel, normalized)
        if model is None:
            raise RuntimeError("ASR recognition not found")
        return model

    @staticmethod
    def _to_data(model: AsrRecognitionModel) -> AsrRecognitionData:
        status = int(model.status)
        return AsrRecognitionData(
            recognition_id=model.recognition_id,
            transcript_id=model.transcript_id,
            job_id=model.job_id,
            object_key=model.object_key,
            audio_url=model.audio_url,
            target_language=model.target_language,
            provider=model.provider,
            status=status,
            status_name=asr_recognition_status_to_name(status),
            provider_request_id=model.provider_request_id,
            provider_resource_id=model.provider_resource_id,
            x_tt_logid=model.x_tt_logid,
            provider_status_code=model.provider_status_code,
            provider_message=model.provider_message,
            error_code=model.error_code,
            error_message=model.error_message,
            poll_count=int(model.poll_count),
            last_polled_at=model.last_polled_at,
            next_poll_at=model.next_poll_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _parse_uuid_str(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, *, field_name: str) -> str:
        parsed = AsrRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed
