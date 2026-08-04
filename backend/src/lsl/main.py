from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Generic, TypeVar

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from lsl.core import Settings, close_database_resources, configure_logging, create_database_resources
from lsl.core.session import CookieSessionMiddleware
from lsl.modules.asr import AsrJobHandler, AsrRepository, AsrService, create_asr_provider
from lsl.modules.asr.api import router as asr_router
from lsl.modules.auth import AuthService, UserRepository
from lsl.modules.auth.api import require_auth_user
from lsl.modules.auth.api import router as auth_router
from lsl.modules.asset import AssetRepository, AssetService, create_storage_provider
from lsl.modules.asset.api import router as asset_router
from lsl.modules.job import JobRepository, JobService
from lsl.modules.job.api import router as job_router
from lsl.modules.revision import RevisionJobHandler, RevisionRepository, RevisionService, create_revision_generator
from lsl.modules.revision.api import router as revision_router
from lsl.modules.script import ScriptJobHandler, ScriptRepository, ScriptService, create_script_generator
from lsl.modules.script.api import router as script_router
from lsl.modules.material import MaterialService, build_extractor
from lsl.modules.material.api import router as material_router
from lsl.modules.session import SessionRepository, SessionService
from lsl.modules.session.api import router as session_router
from lsl.modules.transcript import TranscriptRepository, TranscriptService
from lsl.modules.transcript.api import router as transcript_router
from lsl.modules.translation import TranslationJobHandler, TranslationRepository, TranslationService, create_translation_generator
from lsl.modules.translation.api import router as translation_router
from lsl.modules.tts import TtsCache, TtsJobHandler, TtsRepository, TtsService, create_tts_provider
from lsl.modules.tts.api import router as tts_router

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


class HealthData(BaseModel):
    status: str


configure_logging()
settings = Settings.from_env()


async def run_job_scheduler(
    *,
    job_service: JobService,
    settings: Settings,
) -> None:
    worker_id = "app-job-runner"
    executor = ThreadPoolExecutor(
        max_workers=settings.JOB_RUNNER_MAX_WORKERS,
        thread_name_prefix="job-runner",
    )
    loop = asyncio.get_running_loop()
    in_flight: set[asyncio.Future] = set()

    def _log_done(future: asyncio.Future) -> None:
        in_flight.discard(future)
        try:
            job = future.result()
            logger.info(
                "Job runner completed job_id=%s job_type=%s status=%s",
                job.job_id,
                job.job_type,
                job.status_name,
            )
        except Exception:
            logger.exception("Job runner worker failed")

    try:
        while True:
            capacity = max(0, settings.JOB_RUNNER_MAX_WORKERS - len(in_flight))
            if capacity > 0:
                limit = min(settings.JOB_RUNNER_BATCH_SIZE, capacity)
                try:
                    claim_started_at = time.monotonic()
                    jobs = await loop.run_in_executor(
                        None,
                        partial(
                            job_service.claim_due_jobs,
                            limit=limit,
                            worker_id=worker_id,
                        ),
                    )
                    if jobs:
                        logger.info(
                            "Job runner claimed jobs count=%s capacity=%s elapsed_ms=%s",
                            len(jobs),
                            capacity,
                            int((time.monotonic() - claim_started_at) * 1000),
                        )
                except Exception:
                    logger.exception("Job runner failed to claim due jobs")
                    jobs = []

                for job in jobs:
                    logger.info(
                        "Job runner submitting job_id=%s job_type=%s entity_type=%s entity_id=%s",
                        job.job_id,
                        job.job_type,
                        job.entity_type,
                        job.entity_id,
                    )
                    future = loop.run_in_executor(
                        executor,
                        partial(job_service.run_claimed_job, job),
                    )
                    in_flight.add(future)
                    future.add_done_callback(_log_done)

            await asyncio.sleep(settings.JOB_RUNNER_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Job runner scheduler stopped")
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_resources = create_database_resources(settings)

    asset_repository = (
        AssetRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    transcript_repository = (
        TranscriptRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    job_repository = (
        JobRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    asr_repository = (
        AsrRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    session_repository = (
        SessionRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    revision_repository = (
        RevisionRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    tts_repository = (
        TtsRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    script_repository = (
        ScriptRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    translation_repository = (
        TranslationRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
    user_repository = (
        UserRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )

    asset_service = AssetService(
        settings=settings,
        storage=create_storage_provider(settings),
        repository=asset_repository,
    )
    job_service = (
        JobService(repository=job_repository)
        if job_repository is not None
        else None
    )
    transcript_service = (
        TranscriptService(repository=transcript_repository)
        if transcript_repository is not None
        else None
    )
    session_service = (
        SessionService(
            repository=session_repository,
            asset_service=asset_service,
            transcript_service=transcript_service,
        )
        if session_repository is not None and transcript_service is not None
        else None
    )
    translation_service = (
        TranslationService(
            repository=translation_repository,
            generator=create_translation_generator(settings),
            job_service=job_service,
            default_target_language=settings.TRANSLATION_DEFAULT_TARGET_LANGUAGE,
        )
        if translation_repository is not None
        and job_service is not None
        else None
    )
    asr_service = (
        AsrService(
            repository=asr_repository,
            transcript_service=transcript_service,
            job_service=job_service,
            provider=create_asr_provider(settings),
            translation_service=translation_service,
        )
        if asr_repository is not None and transcript_service is not None and job_service is not None
        else None
    )
    revision_service = (
        RevisionService(
            repository=revision_repository,
            generator=create_revision_generator(settings),
            session_service=session_service,
            transcript_service=transcript_service,
            job_service=job_service,
            translation_service=translation_service,
        )
        if revision_repository is not None and session_service is not None and transcript_service is not None
        else None
    )
    tts_service = (
        TtsService(
            repository=tts_repository,
            provider=create_tts_provider(settings),
            cache=TtsCache(
                redis_url=settings.TTS_REDIS_URL,
                ttl_seconds=settings.TTS_CACHE_TTL_SECONDS,
            ),
            session_service=session_service,
            revision_service=revision_service,
            asset_service=asset_service,
            job_service=job_service,
            settings=settings,
        )
        if tts_repository is not None and session_service is not None and revision_service is not None and job_service is not None
        else None
    )
    script_service = (
        ScriptService(
            repository=script_repository,
            generator=create_script_generator(settings),
            session_service=session_service,
            transcript_service=transcript_service,
            revision_service=revision_service,
            job_service=job_service,
        )
        if script_repository is not None
        and session_service is not None
        and transcript_service is not None
        and revision_service is not None
        and job_service is not None
        else None
    )
    material_service = (
        MaterialService(
            script_service=script_service,
            extractor_factory=lambda payload: build_extractor(payload, settings=settings),
        )
        if script_service is not None
        else None
    )
    auth_service = AuthService(settings=settings, repository=user_repository)

    if job_service is not None:
        if asr_service is not None:
            job_service.register_handler(AsrJobHandler(asr_service=asr_service))
        if script_service is not None:
            job_service.register_handler(ScriptJobHandler(script_service=script_service))
        if revision_service is not None:
            # Revision job flow 4/5: register the handler that consumes revision_generation jobs.
            job_service.register_handler(RevisionJobHandler(revision_service=revision_service))
        if tts_service is not None:
            job_service.register_handler(TtsJobHandler(tts_service=tts_service))
        if translation_service is not None:
            job_service.register_handler(TranslationJobHandler(translation_service=translation_service))

    job_scheduler_task: asyncio.Task | None = None
    if job_service is not None and settings.JOB_RUNNER_ENABLED:
        job_scheduler_task = asyncio.create_task(
            run_job_scheduler(job_service=job_service, settings=settings)
        )

    app.state.settings = settings
    app.state.db_resources = db_resources
    app.state.auth_service = auth_service
    app.state.asset_service = asset_service
    app.state.job_service = job_service
    app.state.transcript_service = transcript_service
    app.state.asr_service = asr_service
    app.state.session_service = session_service
    app.state.revision_service = revision_service
    app.state.translation_service = translation_service
    app.state.tts_service = tts_service
    app.state.script_service = script_service
    app.state.material_service = material_service

    try:
        yield
    finally:
        if job_scheduler_task is not None:
            job_scheduler_task.cancel()
            try:
                await job_scheduler_task
            except asyncio.CancelledError:
                pass
        if tts_service is not None:
            tts_service.shutdown()
        if revision_service is not None:
            revision_service.shutdown()
        close_database_resources(db_resources)


app = FastAPI(title="LSL", lifespan=lifespan)
app.add_middleware(
    CookieSessionMiddleware,
    secret_key=settings.AUTH_SESSION_SECRET,
    same_site="lax",
    https_only=settings.AUTH_COOKIE_SECURE,
)
protected_router_dependencies = [Depends(require_auth_user)]
app.include_router(auth_router)
app.include_router(asset_router, dependencies=protected_router_dependencies)
app.include_router(job_router, dependencies=protected_router_dependencies)
app.include_router(transcript_router, dependencies=protected_router_dependencies)
app.include_router(asr_router, dependencies=protected_router_dependencies)
app.include_router(session_router, dependencies=protected_router_dependencies)
app.include_router(script_router, dependencies=protected_router_dependencies)
app.include_router(revision_router, dependencies=protected_router_dependencies)
app.include_router(translation_router, dependencies=protected_router_dependencies)
app.include_router(tts_router, dependencies=protected_router_dependencies)
app.include_router(material_router, dependencies=protected_router_dependencies)


@app.get("/health", response_model=ApiResponse[HealthData])
def health():
    return ApiResponse(data=HealthData(status="ok"))
