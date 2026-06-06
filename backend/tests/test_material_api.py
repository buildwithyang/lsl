from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_material_service import (
    FakeScriptGenerator,
    NoopRevisionGenerator,
    StubExtractor,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from lsl.core.config import Settings
from lsl.core.db import Base
import lsl.modules.script.model  # noqa: F401
from lsl.modules.asset.providers import FakeStorageProvider
from lsl.modules.asset.service import AssetService
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.material.extractor.base import ExtractedContent
from lsl.modules.material.service import MaterialService
from lsl.modules.revision.repo import RevisionRepository
from lsl.modules.revision.service import RevisionService
from lsl.modules.script.repo import ScriptRepository
from lsl.modules.script.service import ScriptJobHandler, ScriptService
from lsl.modules.session.repo import SessionRepository
from lsl.modules.session.service import SessionService
from lsl.modules.transcript.repo import TranscriptRepository
from lsl.modules.transcript.service import TranscriptService


@pytest.fixture()
def material_service_and_extractor():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
            title="T",
            main_text="x" * 500,
            canonical_url="https://example.com/x",
        )
    )
    material_service = MaterialService(
        script_service=script_service,
        extractor_factory=lambda payload: extractor,
    )
    return material_service, extractor


def _build_app(material_service):
    from lsl.modules.material.api import router

    app = FastAPI()
    app.include_router(router)
    app.state.material_service = material_service
    return TestClient(app)


def test_post_extract_returns_content(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/extract",
        json={"source": {"type": "webpage", "url": "https://example.com/cats"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["main_text"]
    assert body["data"]["char_count"] == len(body["data"]["main_text"])
    assert body["data"]["canonical_url"] == "https://example.com/x"


def test_post_extract_rejects_invalid_url(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/extract",
        json={"source": {"type": "webpage", "url": "not-a-url"}},
    )
    assert resp.status_code == 422


def test_post_extract_returns_400_when_extracted_text_too_short(material_service_and_extractor):
    material_service, extractor = material_service_and_extractor
    extractor._result = ExtractedContent(title="T", main_text="short", canonical_url="https://example.com/x")
    client = _build_app(material_service)
    resp = client.post(
        "/materials/extract",
        json={"source": {"type": "webpage", "url": "https://example.com/x"}},
    )
    assert resp.status_code == 400


def test_post_create_session_returns_script_session(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/create-session",
        json={
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "extracted_title": "Cats",
            "extracted_text": "Cats need daily care. " * 60,
            "target_language": "en-US",
            "title": "Cat care",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["session"]["session"]["session_id"]
    assert body["data"]["generation"]["generation_id"]
    assert body["data"]["job"]["job_id"]


def test_post_create_session_rejects_missing_target_language(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/create-session",
        json={
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "extracted_text": "Cats need daily care. " * 60,
        },
    )
    assert resp.status_code == 422


def test_post_create_session_rejects_missing_extracted_text(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/create-session",
        json={
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
        },
    )
    assert resp.status_code == 422
