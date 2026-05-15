from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.material.model import MaterialGenerationModel
from lsl.modules.material.types import MaterialGenerationStatus, material_generation_status_to_name


class MaterialRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_generation(
        self,
        *,
        generation_id: str,
        session_id: str,
        source_type: str,
        source_payload: dict[str, Any],
    ) -> dict[str, Any]:
        model = MaterialGenerationModel(
            generation_id=self._require_uuid(generation_id, "generation_id"),
            session_id=self._require_uuid(session_id, "session_id"),
            source_type=source_type,
            source_payload_json=dict(source_payload),
            status=int(MaterialGenerationStatus.PENDING),
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create material generation: {exc}") from exc

    def set_job_id(self, *, generation_id: str, job_id: str) -> None:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.job_id = self._require_uuid(job_id, "job_id")
            db.commit()

    def get_by_id(self, generation_id: str) -> dict[str, Any] | None:
        normalized = self._parse_uuid(generation_id)
        if normalized is None:
            return None
        stmt = select(MaterialGenerationModel).where(MaterialGenerationModel.generation_id == normalized).limit(1)
        with self._session_scope() as db:
            model = db.execute(stmt).scalar_one_or_none()
            return self._to_row(model) if model is not None else None

    def mark_extracting(self, *, generation_id: str) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.EXTRACTING)
            model.error_code = None
            model.error_message = None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def mark_extracted(
        self,
        *,
        generation_id: str,
        title: str | None,
        text: str,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.EXTRACTED)
            model.extracted_title = title
            model.extracted_text = text
            model.extracted_meta_json = dict(meta) if meta else None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def set_script_generation_id(self, *, generation_id: str, script_generation_id: str) -> None:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.script_generation_id = self._require_uuid(script_generation_id, "script_generation_id")
            db.commit()

    def mark_completed(self, *, generation_id: str) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.COMPLETED)
            model.error_code = None
            model.error_message = None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def mark_failed(
        self,
        *,
        generation_id: str,
        error_code: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.FAILED)
            model.error_code = error_code
            model.error_message = error_message
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def _get_required(self, db: OrmSession, generation_id: str) -> MaterialGenerationModel:
        normalized = self._require_uuid(generation_id, "generation_id")
        model = db.get(MaterialGenerationModel, normalized)
        if model is None:
            raise RuntimeError("Material generation not found")
        return model

    @staticmethod
    def _parse_uuid(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, field_name: str) -> str:
        parsed = MaterialRepository._parse_uuid(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed

    @staticmethod
    def _to_row(model: MaterialGenerationModel) -> dict[str, Any]:
        status = int(model.status)
        return {
            "generation_id": model.generation_id,
            "session_id": model.session_id,
            "source_type": model.source_type,
            "source_payload": dict(model.source_payload_json or {}),
            "extracted_title": model.extracted_title,
            "extracted_text": model.extracted_text,
            "extracted_meta": dict(model.extracted_meta_json or {}),
            "script_generation_id": model.script_generation_id,
            "job_id": model.job_id,
            "status": status,
            "status_name": material_generation_status_to_name(status),
            "error_code": model.error_code,
            "error_message": model.error_message,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
