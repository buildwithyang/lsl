from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from lsl.modules.job.repo import JobRepository
from lsl.modules.job.types import JobData, JobHandler, JobRunResult, JobStatus

logger = logging.getLogger(__name__)


class JobService:
    """
    通用异步任务编排层：
    - 管理 job 生命周期与锁
    - 通过 job_type 分发到业务模块注册的 handler
    - 不持久化业务主结果，只保存 job 状态和轻量元数据
    """

    def __init__(
        self,
        *,
        repository: JobRepository,
        lock_ttl_seconds: int = 300,
    ) -> None:
        self._repository = repository
        self._lock_ttl_seconds = lock_ttl_seconds
        self._handlers: dict[str, JobHandler] = {}

    def register_handler(self, handler: JobHandler) -> None:
        job_type = handler.job_type.strip()
        if not job_type:
            raise ValueError("job_type is required")
        if job_type in self._handlers:
            raise ValueError(f"job handler already registered: {job_type}")
        self._handlers[job_type] = handler

    def create_job(
        self,
        *,
        job_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        next_run_at: datetime | None = None,
    ) -> JobData:
        normalized_job_type = job_type.strip()
        if not normalized_job_type:
            raise ValueError("job_type is required")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than 0")

        return self._repository.create_job(
            job_id=uuid.uuid4().hex,
            job_type=normalized_job_type,
            entity_type=self._normalize_optional(entity_type),
            entity_id=self._normalize_optional(entity_id),
            payload=dict(payload or {}),
            priority=int(priority),
            max_attempts=int(max_attempts),
            next_run_at=next_run_at,
        )

    def get_job(self, *, job_id: str) -> JobData:
        job = self._repository.get_job_by_id(job_id)
        if job is None:
            raise ValueError("job not found")
        return job

    def list_jobs(
        self,
        *,
        limit: int = 20,
        status: int | None = None,
        job_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[JobData]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 100:
            raise ValueError("limit must be less than or equal to 100")
        return self._repository.list_jobs(
            limit=limit,
            status=status,
            job_type=self._normalize_optional(job_type),
            entity_type=self._normalize_optional(entity_type),
            entity_id=self._normalize_optional(entity_id),
        )

    def run_job(self, *, job_id: str, worker_id: str | None = None) -> JobData:
        resolved_worker_id = self._resolve_worker_id(worker_id)
        job = self._repository.claim_job(
            job_id=job_id,
            worker_id=resolved_worker_id,
            lock_ttl_seconds=self._lock_ttl_seconds,
        )
        if job is None:
            raise ValueError("job not found or not runnable")
        return self._run_claimed_job(job)

    def run_due_jobs(self, *, limit: int = 10, worker_id: str | None = None) -> list[JobData]:
        return [self.run_claimed_job(job) for job in self.claim_due_jobs(limit=limit, worker_id=worker_id)]

    def claim_due_jobs(self, *, limit: int = 10, worker_id: str | None = None) -> list[JobData]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 100:
            raise ValueError("limit must be less than or equal to 100")
        resolved_worker_id = self._resolve_worker_id(worker_id)
        return self._repository.claim_due_jobs(
            worker_id=resolved_worker_id,
            limit=limit,
            lock_ttl_seconds=self._lock_ttl_seconds,
        )

    def run_claimed_job(self, job: JobData) -> JobData:
        return self._run_claimed_job(job)

    def _run_claimed_job(self, job: JobData) -> JobData:
        handler = self._handlers.get(job.job_type)
        if handler is None:
            return self._repository.mark_failed(
                job_id=job.job_id,
                error_code="JOB_HANDLER_NOT_FOUND",
                error_message=f"job handler is not registered: {job.job_type}",
            )

        try:
            result = handler.run(job)
        except Exception as exc:
            logger.exception("Job handler failed job_id=%s job_type=%s", job.job_id, job.job_type)
            return self._repository.mark_failed(
                job_id=job.job_id,
                error_code="JOB_HANDLER_ERROR",
                error_message=str(exc),
            )

        return self._apply_run_result(job=job, result=result)

    def _apply_run_result(self, *, job: JobData, result: JobRunResult) -> JobData:
        if result.status == JobStatus.COMPLETED:
            return self._repository.mark_completed(
                job_id=job.job_id,
                progress=result.progress,
                result=result.result,
                entity_type=result.entity_type,
                entity_id=result.entity_id,
            )

        if result.status == JobStatus.FAILED:
            return self._repository.mark_failed(
                job_id=job.job_id,
                progress=result.progress,
                error_code=result.error_code or "JOB_FAILED",
                error_message=result.error_message,
            )

        if result.status == JobStatus.CANCELED:
            return self._repository.mark_canceled(job_id=job.job_id, error_message=result.error_message)

        if result.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return self._repository.mark_running(
                job_id=job.job_id,
                progress=result.progress,
                next_run_at=result.next_run_at,
                entity_type=result.entity_type,
                entity_id=result.entity_id,
            )

        return self._repository.mark_failed(
            job_id=job.job_id,
            error_code="INVALID_JOB_RESULT",
            error_message=f"unsupported job result status: {result.status}",
        )

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _resolve_worker_id(worker_id: str | None) -> str:
        normalized = (worker_id or "").strip()
        return normalized or f"worker-{uuid.uuid4().hex[:12]}"
