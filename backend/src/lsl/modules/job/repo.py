from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.job.model import JobModel
from lsl.modules.job.types import JobData, JobStatus, job_status_to_name


class JobRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_job(
        self,
        *,
        job_id: str,
        job_type: str,
        entity_type: str | None,
        entity_id: str | None,
        payload: dict[str, Any],
        priority: int,
        max_attempts: int,
        next_run_at: datetime | None,
    ) -> JobData:
        normalized_job_id = self._require_uuid(job_id, field_name="job_id")
        model = JobModel(
            job_id=normalized_job_id,
            job_type=job_type,
            status=int(JobStatus.QUEUED),
            entity_type=entity_type,
            entity_id=entity_id,
            priority=priority,
            progress=0,
            attempts=0,
            max_attempts=max_attempts,
            payload_json=payload,
            next_run_at=next_run_at,
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create job: {exc}") from exc

    def get_job_by_id(self, job_id: str) -> JobData | None:
        normalized_job_id = self._parse_uuid_str(job_id)
        if normalized_job_id is None:
            return None

        stmt = select(JobModel).where(JobModel.job_id == normalized_job_id).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_data(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query job by id: {exc}") from exc

    def list_jobs(
        self,
        *,
        limit: int,
        status: int | None = None,
        job_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[JobData]:
        stmt = select(JobModel)
        if status is not None:
            stmt = stmt.where(JobModel.status == int(status))
        if job_type:
            stmt = stmt.where(JobModel.job_type == job_type)
        if entity_type:
            stmt = stmt.where(JobModel.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(JobModel.entity_id == entity_id)
        stmt = stmt.order_by(JobModel.created_at.desc()).limit(limit)

        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list jobs: {exc}") from exc

    def claim_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        lock_ttl_seconds: int,
    ) -> JobData | None:
        normalized_job_id = self._parse_uuid_str(job_id)
        if normalized_job_id is None:
            return None

        now = datetime.now(timezone.utc)
        stmt = (
            select(JobModel)
            .where(JobModel.job_id == normalized_job_id)
            .where(JobModel.status.in_([int(JobStatus.QUEUED), int(JobStatus.RUNNING)]))
            .where(or_(JobModel.locked_until.is_(None), JobModel.locked_until <= now))
            .limit(1)
        )
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                if model is None:
                    return None
                self._claim_model(model, worker_id=worker_id, lock_ttl_seconds=lock_ttl_seconds, now=now)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to claim job: {exc}") from exc

    def claim_due_jobs(
        self,
        *,
        worker_id: str,
        limit: int,
        lock_ttl_seconds: int,
    ) -> list[JobData]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(JobModel)
            .where(JobModel.status.in_([int(JobStatus.QUEUED), int(JobStatus.RUNNING)]))
            .where(or_(JobModel.next_run_at.is_(None), JobModel.next_run_at <= now))
            .where(or_(JobModel.locked_until.is_(None), JobModel.locked_until <= now))
            .order_by(JobModel.priority.desc(), JobModel.next_run_at.asc(), JobModel.created_at.asc())
            .limit(limit)
        )
        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                for model in rows:
                    self._claim_model(model, worker_id=worker_id, lock_ttl_seconds=lock_ttl_seconds, now=now)
                db.commit()
                for model in rows:
                    db.refresh(model)
                return [self._to_data(model) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to claim due jobs: {exc}") from exc

    def mark_running(
        self,
        *,
        job_id: str,
        progress: int | None,
        next_run_at: datetime | None,
        entity_type: str | None,
        entity_id: str | None,
    ) -> JobData:
        try:
            with self._session_scope() as db:
                model = self._get_required_job(db, job_id)
                model.status = int(JobStatus.RUNNING)
                if progress is not None:
                    model.progress = self._normalize_progress(progress)
                if entity_type is not None:
                    model.entity_type = entity_type
                if entity_id is not None:
                    model.entity_id = entity_id
                model.next_run_at = next_run_at
                model.locked_by = None
                model.locked_until = None
                model.error_code = None
                model.error_message = None
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark job as running: {exc}") from exc

    def mark_completed(
        self,
        *,
        job_id: str,
        progress: int | None,
        result: dict[str, Any] | None,
        entity_type: str | None,
        entity_id: str | None,
    ) -> JobData:
        try:
            with self._session_scope() as db:
                model = self._get_required_job(db, job_id)
                model.status = int(JobStatus.COMPLETED)
                model.progress = self._normalize_progress(progress if progress is not None else 100)
                model.result_json = result
                if entity_type is not None:
                    model.entity_type = entity_type
                if entity_id is not None:
                    model.entity_id = entity_id
                model.error_code = None
                model.error_message = None
                model.locked_by = None
                model.locked_until = None
                model.next_run_at = None
                model.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark job as completed: {exc}") from exc

    def mark_failed(
        self,
        *,
        job_id: str,
        error_code: str | None,
        error_message: str | None,
        progress: int | None = None,
    ) -> JobData:
        try:
            with self._session_scope() as db:
                model = self._get_required_job(db, job_id)
                model.status = int(JobStatus.FAILED)
                if progress is not None:
                    model.progress = self._normalize_progress(progress)
                model.error_code = error_code
                model.error_message = error_message
                model.locked_by = None
                model.locked_until = None
                model.next_run_at = None
                model.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to mark job as failed: {exc}") from exc

    def mark_canceled(self, *, job_id: str, error_message: str | None = None) -> JobData:
        try:
            with self._session_scope() as db:
                model = self._get_required_job(db, job_id)
                model.status = int(JobStatus.CANCELED)
                model.error_code = "JOB_CANCELED"
                model.error_message = error_message
                model.locked_by = None
                model.locked_until = None
                model.next_run_at = None
                model.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(model)
                return self._to_data(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to cancel job: {exc}") from exc

    def _claim_model(
        self,
        model: JobModel,
        *,
        worker_id: str,
        lock_ttl_seconds: int,
        now: datetime,
    ) -> None:
        model.status = int(JobStatus.RUNNING)
        model.attempts = int(model.attempts) + 1
        model.locked_by = worker_id
        model.locked_until = now + timedelta(seconds=lock_ttl_seconds)
        model.next_run_at = None
        if model.started_at is None:
            model.started_at = now

    def _get_required_job(self, db: OrmSession, job_id: str) -> JobModel:
        normalized_job_id = self._require_uuid(job_id, field_name="job_id")
        model = db.get(JobModel, normalized_job_id)
        if model is None:
            raise RuntimeError("Job not found")
        return model

    @staticmethod
    def _to_data(model: JobModel) -> JobData:
        status = int(model.status)
        return JobData(
            job_id=model.job_id,
            job_type=model.job_type,
            status=status,
            status_name=job_status_to_name(status),
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            priority=int(model.priority),
            progress=int(model.progress),
            attempts=int(model.attempts),
            max_attempts=int(model.max_attempts),
            payload=model.payload_json or {},
            result=model.result_json,
            error_code=model.error_code,
            error_message=model.error_message,
            locked_by=model.locked_by,
            locked_until=model.locked_until,
            next_run_at=model.next_run_at,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _normalize_progress(value: int) -> int:
        return max(0, min(100, int(value)))

    @staticmethod
    def _parse_uuid_str(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, *, field_name: str) -> str:
        parsed = JobRepository._parse_uuid_str(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed
