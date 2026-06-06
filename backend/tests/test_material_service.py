from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.config import Settings
from lsl.core.db import Base
import lsl.modules.script.model  # noqa: F401
from lsl.modules.asset.providers import FakeStorageProvider
from lsl.modules.asset.service import AssetService
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.material.extractor.base import ExtractedContent
from lsl.modules.material.schema import CreatePodcastSessionRequest, ExtractMaterialRequest
from lsl.modules.material.service import MaterialService
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
        result=ExtractedContent(
            title="The Cat Care Guide",
            main_text="Cats need daily care. " * 50,
            canonical_url="https://example.com/cats",
        )
    )
    material_service = MaterialService(
        script_service=script_service,
        extractor_factory=lambda payload: extractor,
    )
    return material_service, job_service, extractor


def test_extract_returns_main_text_and_metadata(services):
    material_service, _job_service, extractor = services
    req = ExtractMaterialRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}}
    )
    data = material_service.extract(req)

    assert data.title == "The Cat Care Guide"
    assert data.main_text.startswith("Cats need daily care.")
    assert data.canonical_url == "https://example.com/cats"
    assert data.char_count == len(data.main_text)
    assert data.truncated is False
    assert len(extractor.calls) == 1


def test_extract_raises_when_text_too_short(services):
    material_service, _job_service, extractor = services
    extractor._result = ExtractedContent(
        title="Tiny",
        main_text="Short",
        canonical_url="https://example.com/x",
    )
    req = ExtractMaterialRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/x"}}
    )
    with pytest.raises(ValueError, match="empty or too short"):
        material_service.extract(req)


def test_extract_propagates_extractor_exception(services):
    material_service, _job_service, extractor = services
    extractor._exc = RuntimeError("boom")
    req = ExtractMaterialRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}}
    )
    with pytest.raises(RuntimeError, match="boom"):
        material_service.extract(req)


def test_extract_reports_truncated_when_extractor_flag_set(services):
    material_service, _job_service, extractor = services
    extractor._result = ExtractedContent(
        title="Big",
        main_text="a" * 600,
        canonical_url="https://example.com/big",
        meta={"truncated": True},
    )
    req = ExtractMaterialRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/big"}}
    )
    data = material_service.extract(req)
    assert data.truncated is True


def test_create_session_delegates_to_script_service(services):
    material_service, job_service, _extractor = services
    extracted_text = "Cats need daily care. " * 60
    req = CreatePodcastSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "extracted_title": "The Cat Care Guide",
            "extracted_text": extracted_text,
            "target_language": "en-US",
            "cue_language": "zh-CN",
            "prompt": "用初学者口吻",
            "turn_count": 8,
        }
    )
    data = material_service.create_session(req)

    assert data.session.session.session_id
    assert data.generation.generation_id
    assert data.generation.title == "The Cat Care Guide"
    assert data.generation.target_language == "en-US"
    assert data.generation.cue_language == "zh-CN"
    assert data.generation.turn_count == 8
    assert "Webpage title: The Cat Care Guide" in data.generation.prompt
    assert "Source URL: https://example.com/cats" in data.generation.prompt
    assert extracted_text.strip() in data.generation.prompt
    assert "用初学者口吻" in data.generation.prompt
    assert "Ignore reference lists" in data.generation.prompt

    # Job is wired and runnable.
    assert data.job.job_id
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)


def test_create_session_uses_default_title_when_missing(services):
    material_service, _job_service, _extractor = services
    req = CreatePodcastSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "extracted_text": "Cats need daily care. " * 60,
            "target_language": "en-US",
        }
    )
    data = material_service.create_session(req)
    # No explicit title / extracted_title — fallback to module default.
    assert data.generation.title == "Podcast from webpage"
