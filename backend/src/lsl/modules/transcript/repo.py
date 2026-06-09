from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.transcript.model import TranscriptModel, TranscriptUtteranceModel
from lsl.modules.transcript.schema import TranscriptData, TranscriptUtteranceData
from lsl.modules.transcript.types import TranscriptStatus, transcript_status_to_name


class TranscriptRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_transcript(
        self,
        *,
        transcript_id: str,
        source_type: str,
        source_entity_id: str | None,
        language: str | None,
        status: int,
    ) -> TranscriptData:
        normalized_transcript_id = self._require_uuid(transcript_id, field_name="transcript_id")
        model = TranscriptModel(
            transcript_id=normalized_transcript_id,
            source_type=source_type,
            source_entity_id=source_entity_id,
            language=language,
            status=int(status),
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_data(model, utterances=[])
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create transcript: {exc}") from exc

    def update_source_entity(self, *, transcript_id: str, source_entity_id: str) -> None:
        try:
            with self._session_scope() as db:
                model = self._get_required_transcript(db, transcript_id)
                model.source_entity_id = source_entity_id
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to update transcript source entity: {exc}") from exc

    def get_transcript_by_id(self, transcript_id: str, *, include_utterances: bool = True) -> TranscriptData | None:
        normalized_transcript_id = self._parse_uuid_str(transcript_id)
        if normalized_transcript_id is None:
            return None

        stmt = select(TranscriptModel).where(TranscriptModel.transcript_id == normalized_transcript_id).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                if model is None:
                    return None
                utterances = self._load_utterances(db, normalized_transcript_id) if include_utterances else []
                return self._to_data(model, utterances=utterances)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query transcript by id: {exc}") from exc

    def list_transcripts(
        self,
        *,
        limit: int,
        status: int | None = None,
        source_type: str | None = None,
        source_entity_id: str | None = None,
    ) -> list[TranscriptData]:
        stmt = select(TranscriptModel)
        if status is not None:
            stmt = stmt.where(TranscriptModel.status == int(status))
        if source_type:
            stmt = stmt.where(TranscriptModel.source_type == source_type)
        if source_entity_id:
            stmt = stmt.where(TranscriptModel.source_entity_id == source_entity_id)
        stmt = stmt.order_by(TranscriptModel.created_at.desc()).limit(limit)

        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model, utterances=[]) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list transcripts: {exc}") from exc

    def list_transcripts_by_ids(self, transcript_ids: list[str]) -> list[TranscriptData]:
        normalized = [self._parse_uuid_str(item) for item in transcript_ids]
        filtered = [item for item in normalized if item is not None]
        if not filtered:
            return []
        stmt = select(TranscriptModel).where(TranscriptModel.transcript_id.in_(filtered))
        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model, utterances=[]) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query transcripts by ids: {exc}") from exc

    def mark_completed(
        self,
        *,
        transcript_id: str,
        duration_ms: int | None,
        full_text: str | None,
        raw_result_json: dict[str, Any] | None,
        utterances: list[dict[str, Any]],
    ) -> TranscriptData:
        normalized_transcript_id = self._require_uuid(transcript_id, field_name="transcript_id")
        try:
            with self._session_scope() as db:
                model = self._get_required_transcript(db, normalized_transcript_id)
                model.status = int(TranscriptStatus.COMPLETED)
                model.duration_ms = duration_ms
                model.full_text = full_text
                model.raw_result_json = raw_result_json
                model.error_code = None
                model.error_message = None

                db.execute(
                    delete(TranscriptUtteranceModel).where(
                        TranscriptUtteranceModel.transcript_id == normalized_transcript_id
                    )
                )
                for item in utterances:
                    db.add(
                        TranscriptUtteranceModel(
                            transcript_id=normalized_transcript_id,
                            seq=int(item["seq"]),
                            text=item["text"],
                            speaker=item.get("speaker"),
                            start_time=int(item["start_time"]),
                            end_time=int(item["end_time"]),
                            additions_json=item.get("additions") or {},
                        )
                    )
                db.commit()
                db.refresh(model)
                loaded = self._load_utterances(db, normalized_transcript_id)
                return self._to_data(model, utterances=loaded)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to complete transcript: {exc}") from exc

    def mark_failed(
        self,
        *,
        transcript_id: str,
        error_code: str | None,
        error_message: str | None,
    ) -> TranscriptData:
        try:
            with self._session_scope() as db:
                model = self._get_required_transcript(db, transcript_id)
                model.status = int(TranscriptStatus.FAILED)
                model.error_code = error_code
                model.error_message = error_message
                db.commit()
                db.refresh(model)
                return self._to_data(model, utterances=[])
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark transcript as failed: {exc}") from exc

    def _get_required_transcript(self, db: OrmSession, transcript_id: str) -> TranscriptModel:
        normalized_transcript_id = self._require_uuid(transcript_id, field_name="transcript_id")
        model = db.get(TranscriptModel, normalized_transcript_id)
        if model is None:
            raise RuntimeError("Transcript not found")
        return model

    @staticmethod
    def _load_utterances(db: OrmSession, transcript_id: str) -> list[TranscriptUtteranceModel]:
        stmt = (
            select(TranscriptUtteranceModel)
            .where(TranscriptUtteranceModel.transcript_id == transcript_id)
            .order_by(TranscriptUtteranceModel.seq.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def _to_data(model: TranscriptModel, *, utterances: list[TranscriptUtteranceModel]) -> TranscriptData:
        status = int(model.status)
        duration_ms = int(model.duration_ms) if model.duration_ms is not None else None
        return TranscriptData(
            transcript_id=model.transcript_id,
            source_type=model.source_type,
            source_entity_id=model.source_entity_id,
            language=model.language,
            duration_ms=duration_ms,
            duration_sec=(duration_ms / 1000) if duration_ms is not None else None,
            full_text=model.full_text,
            raw_result=model.raw_result_json,
            status=status,
            status_name=transcript_status_to_name(status),
            error_code=model.error_code,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            utterances=[
                TranscriptUtteranceData(
                    seq=int(item.seq),
                    text=item.text,
                    speaker=item.speaker,
                    start_time=int(item.start_time),
                    end_time=int(item.end_time),
                    additions=item.additions_json or {},
                )
                for item in utterances
            ],
        )

    @staticmethod
    def _parse_uuid_str(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, *, field_name: str) -> str:
        parsed = TranscriptRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed
