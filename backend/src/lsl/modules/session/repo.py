from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.session.model import SessionModel


class SessionRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_session(
        self,
        *,
        session_id: str,
        title: str,
        description: str | None,
        target_language: str | None,
        f_type: int,
        asset_object_key: str | None,
        current_transcript_id: str | None,
    ) -> None:
        normalized_session_id = self._require_uuid(session_id, field_name="session_id")
        normalized_transcript_id = (
            self._require_uuid(current_transcript_id, field_name="current_transcript_id")
            if current_transcript_id
            else None
        )

        model = SessionModel(
            session_id=normalized_session_id,
            title=title,
            description=description,
            target_language=target_language,
            f_type=f_type,
            asset_object_key=asset_object_key,
            current_transcript_id=normalized_transcript_id,
        )

        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create session: {exc}") from exc

    def get_session_by_id(self, session_id: str) -> SessionModel | None:
        normalized_session_id = self._parse_uuid_str(session_id)
        if normalized_session_id is None:
            return None

        stmt = select(SessionModel).where(SessionModel.session_id == normalized_session_id).limit(1)

        try:
            with self._session_scope() as db:
                return db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query session by id: {exc}") from exc

    def list_sessions(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> list[SessionModel]:
        stmt = select(SessionModel)

        if query:
            like_value = f"%{query}%"
            stmt = stmt.where(
                or_(
                    SessionModel.title.ilike(like_value),
                    func.coalesce(SessionModel.description, "").ilike(like_value),
                    func.coalesce(SessionModel.asset_object_key, "").ilike(like_value),
                )
            )

        stmt = stmt.order_by(SessionModel.created_at.desc()).limit(limit).offset(offset)

        try:
            with self._session_scope() as db:
                return list(db.execute(stmt).scalars().all())
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list sessions: {exc}") from exc

    def update_session(self, *, session_id: str, updates: dict[str, Any]) -> None:
        if not updates:
            return

        normalized_session_id = self._parse_uuid_str(session_id)
        if normalized_session_id is None:
            return

        try:
            with self._session_scope() as db:
                model = db.get(SessionModel, normalized_session_id)
                if model is None:
                    return

                for key, value in updates.items():
                    if key == "current_transcript_id":
                        if value is None:
                            setattr(model, key, None)
                        elif isinstance(value, uuid.UUID):
                            setattr(model, key, value.hex)
                        elif isinstance(value, str):
                            setattr(model, key, self._require_uuid(value, field_name="current_transcript_id"))
                        else:
                            raise RuntimeError("Invalid current_transcript_id")
                    else:
                        setattr(model, key, value)

                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to update session: {exc}") from exc

    def delete_session(self, session_id: str) -> bool:
        normalized_session_id = self._parse_uuid_str(session_id)
        if normalized_session_id is None:
            return False
        try:
            with self._session_scope() as db:
                model = db.get(SessionModel, normalized_session_id)
                if model is None:
                    return False
                db.delete(model)
                db.commit()
                return True
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to delete session: {exc}") from exc

    def get_session_id_by_asset_object_key(self, object_key: str) -> str | None:
        stmt = select(SessionModel.session_id).where(SessionModel.asset_object_key == object_key).limit(1)

        try:
            with self._session_scope() as db:
                value = db.execute(stmt).scalar_one_or_none()
                return str(value) if value is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query session by asset_object_key: {exc}") from exc

    def get_session_id_by_current_transcript_id(self, transcript_id: str) -> str | None:
        normalized_transcript_id = self._parse_uuid_str(transcript_id)
        if normalized_transcript_id is None:
            return None

        stmt = select(SessionModel.session_id).where(SessionModel.current_transcript_id == normalized_transcript_id).limit(1)

        try:
            with self._session_scope() as db:
                value = db.execute(stmt).scalar_one_or_none()
                return str(value) if value is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query session by current_transcript_id: {exc}") from exc

    @staticmethod
    def _parse_uuid_str(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, *, field_name: str) -> str:
        parsed = SessionRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed
