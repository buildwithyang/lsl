from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.config import Settings
from lsl.core.db import Base
import lsl.modules.material.model  # noqa: F401
import lsl.modules.script.model  # noqa: F401
from lsl.modules.asset.providers import FakeStorageProvider
from lsl.modules.asset.service import AssetService
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.material.extractor.base import ExtractedContent, WebpageSourceInput
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.schema import GenerateMaterialSessionRequest
from lsl.modules.material.service import MaterialJobHandler, MaterialService
from lsl.modules.revision.repo import RevisionRepository
from lsl.modules.revision.service import RevisionService
from lsl.modules.revision.types import RevisionGenerateRequest, RevisionSuggestion
from lsl.modules.script.repo import ScriptRepository
from lsl.modules.script.service import ScriptJobHandler, ScriptService
from lsl.modules.script.types import GeneratedScript, GeneratedScriptTurn, ScriptGenerateRequest
from lsl.modules.session.repo import SessionRepository
from lsl.modules.session.service import SessionService
from lsl.modules.transcript.repo import TranscriptRepository
from lsl.modules.transcript.service import TranscriptService


class StubExtractor:
    def __init__(self, *, result: ExtractedContent | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls: list = []

    def extract(self, payload):
        self.calls.append(payload)
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeScriptGenerator:
    provider_name = "fake-script"

    def generate(self, req: ScriptGenerateRequest) -> GeneratedScript:
        return GeneratedScript(
            utterances=[
                GeneratedScriptTurn(speaker="user-1", cue="calm", text="Hello cats."),
                GeneratedScriptTurn(speaker="user-2", cue="warm", text="Yes, lovely creatures."),
            ]
        )

    def generate_progressively(self, req: ScriptGenerateRequest) -> Iterator[GeneratedScriptTurn]:
        yield from self.generate(req).utterances


class NoopRevisionGenerator:
    provider_name = "noop"

    def generate(self, req: RevisionGenerateRequest) -> list[RevisionSuggestion]:
        return []

    def generate_progressively(self, req):
        return iter(())


@pytest.fixture()
def services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)
    settings = Settings(STORAGE_PROVIDER="fake", ASSET_BASE_URL="http://assets.test")
    asset_service = AssetService(settings=settings, storage=FakeStorageProvider(), repository=None)
    job_service = JobService(repository=JobRepository(factory), lock_ttl_seconds=30)
    transcript_service = TranscriptService(repository=TranscriptRepository(factory))
    session_service = SessionService(
        repository=SessionRepository(factory),
        asset_service=asset_service,
        transcript_service=transcript_service,
    )
    revision_service = RevisionService(
        repository=RevisionRepository(factory),
        generator=NoopRevisionGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
    )
    script_service = ScriptService(
        repository=ScriptRepository(factory),
        generator=FakeScriptGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
        revision_service=revision_service,
        job_service=job_service,
    )
    job_service.register_handler(ScriptJobHandler(script_service=script_service))

    extractor = StubExtractor(
        result=ExtractedContent(title="The Cat Care Guide", main_text="Cats need daily care." * 50, canonical_url="https://example.com/cats")
    )
    material_service = MaterialService(
        repository=MaterialRepository(factory),
        session_service=session_service,
        script_service=script_service,
        job_service=job_service,
        extractor_factory=lambda payload: extractor,
    )
    job_service.register_handler(MaterialJobHandler(material_service=material_service))
    return material_service, job_service, extractor


def test_create_from_url_creates_session_generation_and_job(services):
    material_service, _job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
            "cue_language": "zh-CN",
            "title": "Cat care",
        }
    )
    data = material_service.create_from_url(req)
    assert data.session.session.session_id
    assert data.material_generation.status_name == "pending"
    assert data.material_generation.source_payload == {"url": "https://example.com/cats"}
    assert data.job.job_id


def test_extract_job_stops_at_extracted_awaiting_confirmation(services):
    material_service, job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
            "title": "Cat care",
        }
    )
    data = material_service.create_from_url(req)

    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "extracted"
    assert refreshed.script_generation_id is None
    assert refreshed.extracted_title == "The Cat Care Guide"
    assert refreshed.extracted_text and len(refreshed.extracted_text) > 0


def test_confirm_kicks_off_script_generation(services):
    material_service, job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
        }
    )
    data = material_service.create_from_url(req)
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    confirmed = material_service.confirm_and_generate(
        generation_id=data.material_generation.generation_id,
    )
    assert confirmed.status_name == "completed"
    assert confirmed.script_generation_id is not None


def test_confirm_rejected_before_extraction_finishes(services):
    material_service, _job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    # Do not run the extract job — status stays "pending".
    with pytest.raises(ValueError, match="extraction must complete first"):
        material_service.confirm_and_generate(generation_id=data.material_generation.generation_id)


def test_cancel_marks_status_cancelled_and_deletes_session(services):
    material_service, job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    session_id = data.session.session.session_id
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    cancelled = material_service.cancel_generation(
        generation_id=data.material_generation.generation_id,
    )
    assert cancelled.status_name == "cancelled"
    assert cancelled.script_generation_id is None

    # Session row should be gone so it doesn't litter the dashboard.
    with pytest.raises(ValueError, match="session not found"):
        material_service._session_service.get_session(session_id)


def test_run_material_job_marks_failed_on_extractor_exception(services):
    material_service, job_service, extractor = services
    extractor._exc = RuntimeError("boom")
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "failed"
    assert refreshed.error_code == "EXTRACTION_FAILED"
    assert "boom" in (refreshed.error_message or "")


def test_run_material_job_marks_failed_when_text_too_short(services):
    material_service, job_service, extractor = services
    extractor._result = ExtractedContent(title="Tiny", main_text="Short", canonical_url="https://example.com/x")
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/x"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "failed"
    assert refreshed.error_code == "EXTRACTION_EMPTY"
