from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.script.model import ScriptGenerationModel
from lsl.modules.script.types import ScriptGenerationStatus, script_generation_status_to_name


class ScriptRepository:
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
        provider: str,
        title: str,
        description: str | None,
        target_language: str | None,
        cue_language: str | None,
        prompt: str,
        turn_count: int,
        speaker_count: int,
        difficulty: str | None,
        cue_style: str | None,
        must_include: list[str],
    ) -> dict[str, Any]:
        model = ScriptGenerationModel(
            generation_id=self._require_uuid(generation_id, field_name="generation_id"),
            session_id=self._require_uuid(session_id, field_name="session_id"),
            provider=provider,
            title=title,
            description=description,
            target_language=target_language,
            cue_language=cue_language,
            prompt=prompt,
            turn_count=int(turn_count),
            speaker_count=int(speaker_count),
            difficulty=difficulty,
            cue_style=cue_style,
            must_include_json=list(must_include),
            status=int(ScriptGenerationStatus.PENDING),
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create script generation: {exc}") from exc

    def set_job_id(self, *, generation_id: str, job_id: str) -> None:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                model.job_id = self._require_uuid(job_id, field_name="job_id")
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to set script generation job id: {exc}") from exc

    def get_generation_by_id(self, generation_id: str) -> dict[str, Any] | None:
        normalized = self._parse_uuid_str(generation_id)
        if normalized is None:
            return None
        stmt = select(ScriptGenerationModel).where(ScriptGenerationModel.generation_id == normalized).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_row(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query script generation: {exc}") from exc

    def mark_generating(self, *, generation_id: str) -> dict[str, Any]:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                model.status = int(ScriptGenerationStatus.GENERATING)
                model.preview_items_json = []
                model.plan_sections_json = []
                model.raw_result_json = {"stage": "planning"}
                model.error_code = None
                model.error_message = None
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark script generation running: {exc}") from exc

    def save_plan_sections(
        self,
        *,
        generation_id: str,
        sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                current_raw_result = model.raw_result_json if isinstance(model.raw_result_json, dict) else {}
                model.plan_sections_json = self._normalize_plan_sections(sections)
                model.raw_result_json = {**current_raw_result, "stage": "generating"}
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to save script generation plan sections: {exc}") from exc

    def save_preview_item(
        self,
        *,
        generation_id: str,
        seq: int,
        speaker: str,
        cue: str,
        text: str,
    ) -> list[dict[str, Any]]:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                item = {
                    "seq": int(seq),
                    "speaker": speaker,
                    "cue": cue,
                    "text": text,
                }
                items = self._normalize_preview_items(model.preview_items_json)
                items_by_seq = {int(existing["seq"]): existing for existing in items}
                items_by_seq[int(seq)] = item
                model.preview_items_json = [items_by_seq[key] for key in sorted(items_by_seq)]
                db.commit()
                db.refresh(model)
                return self._normalize_preview_items(model.preview_items_json)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to save script generation preview item: {exc}") from exc

    def get_generation_preview_items(self, *, generation_id: str) -> list[dict[str, Any]] | None:
        normalized = self._parse_uuid_str(generation_id)
        if normalized is None:
            return None
        stmt = select(ScriptGenerationModel).where(ScriptGenerationModel.generation_id == normalized).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._normalize_preview_items(model.preview_items_json) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query script generation preview items: {exc}") from exc

    def mark_completed(
        self,
        *,
        generation_id: str,
        transcript_id: str,
        raw_result_json: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                model.status = int(ScriptGenerationStatus.COMPLETED)
                model.transcript_id = self._require_uuid(transcript_id, field_name="transcript_id")
                model.raw_result_json = raw_result_json
                model.error_code = None
                model.error_message = None
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark script generation completed: {exc}") from exc

    def mark_failed(self, *, generation_id: str, error_code: str | None, error_message: str | None) -> dict[str, Any]:
        try:
            with self._session_scope() as db:
                model = self._get_required_generation(db, generation_id)
                model.status = int(ScriptGenerationStatus.FAILED)
                model.error_code = error_code
                model.error_message = error_message
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark script generation failed: {exc}") from exc

    def _get_required_generation(self, db: OrmSession, generation_id: str) -> ScriptGenerationModel:
        normalized = self._require_uuid(generation_id, field_name="generation_id")
        model = db.get(ScriptGenerationModel, normalized)
        if model is None:
            raise RuntimeError("Script generation not found")
        return model

    @staticmethod
    def _to_row(model: ScriptGenerationModel) -> dict[str, Any]:
        status = int(model.status)
        return {
            "generation_id": model.generation_id,
            "session_id": model.session_id,
            "transcript_id": model.transcript_id,
            "job_id": model.job_id,
            "provider": model.provider,
            "title": model.title,
            "description": model.description,
            "target_language": model.target_language,
            "cue_language": model.cue_language,
            "prompt": model.prompt,
            "turn_count": int(model.turn_count),
            "speaker_count": int(model.speaker_count),
            "difficulty": model.difficulty,
            "cue_style": model.cue_style,
            "must_include": list(model.must_include_json or []),
            "preview_items": ScriptRepository._normalize_preview_items(model.preview_items_json),
            "plan_sections": ScriptRepository._normalize_plan_sections(model.plan_sections_json),
            "raw_result": model.raw_result_json,
            "status": status,
            "status_name": script_generation_status_to_name(status),
            "error_code": model.error_code,
            "error_message": model.error_message,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }

    @staticmethod
    def _parse_uuid_str(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, *, field_name: str) -> str:
        parsed = ScriptRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed

    @staticmethod
    def _normalize_preview_items(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, Any]] = []
        for raw_item in value:
            if not isinstance(raw_item, dict):
                continue
            try:
                seq = int(raw_item.get("seq"))
            except (TypeError, ValueError):
                continue
            speaker = str(raw_item.get("speaker") or "").strip()
            cue = str(raw_item.get("cue") or "").strip()
            text = str(raw_item.get("text") or "").strip()
            if not text:
                continue
            items.append(
                {
                    "seq": seq,
                    "speaker": speaker,
                    "cue": cue,
                    "text": text,
                }
            )
        return sorted(items, key=lambda item: int(item["seq"]))

    @staticmethod
    def _normalize_plan_sections(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        sections: list[dict[str, Any]] = []
        for raw_section in value:
            if not isinstance(raw_section, dict):
                continue
            try:
                section_index = int(raw_section.get("section_index"))
                target_turn_count = int(raw_section.get("target_turn_count"))
            except (TypeError, ValueError):
                continue
            if section_index <= 0 or target_turn_count <= 0:
                continue
            sections.append(
                {
                    "section_index": section_index,
                    "title": str(raw_section.get("title") or "").strip(),
                    "summary": str(raw_section.get("summary") or "").strip(),
                    "target_turn_count": target_turn_count,
                }
            )
        return sorted(sections, key=lambda item: int(item["section_index"]))
