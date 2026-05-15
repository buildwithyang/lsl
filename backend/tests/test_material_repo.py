from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.db import Base
import lsl.modules.material.model  # noqa: F401 - register table
import lsl.modules.script.model  # noqa: F401 - register table
from lsl.modules.material.repo import MaterialRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)


def test_create_and_get_generation(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    row = repo.create_generation(
        generation_id=gen_id,
        session_id=session_id,
        source_type="webpage",
        source_payload={"url": "https://example.com"},
    )
    assert row["generation_id"] == gen_id
    assert row["status_name"] == "pending"
    assert row["source_payload"] == {"url": "https://example.com"}

    fetched = repo.get_by_id(gen_id)
    assert fetched is not None
    assert fetched["session_id"] == session_id


def _seed_generation(repo: MaterialRepository) -> str:
    gen_id = uuid.uuid4().hex
    repo.create_generation(
        generation_id=gen_id,
        session_id=uuid.uuid4().hex,
        source_type="webpage",
        source_payload={"url": "https://example.com"},
    )
    return gen_id


def test_mark_extracting_then_extracted_then_completed(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)

    repo.mark_extracting(generation_id=gen_id)
    assert repo.get_by_id(gen_id)["status_name"] == "extracting"

    repo.mark_extracted(generation_id=gen_id, title="Cats", text="Hello cats", meta={"truncated": False})
    row = repo.get_by_id(gen_id)
    assert row["status_name"] == "extracted"
    assert row["extracted_title"] == "Cats"
    assert row["extracted_text"] == "Hello cats"

    repo.mark_completed(generation_id=gen_id)
    assert repo.get_by_id(gen_id)["status_name"] == "completed"


def test_mark_failed_records_error_code_and_message(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)
    repo.mark_failed(generation_id=gen_id, error_code="FETCH_TIMEOUT", error_message="timeout 15s")
    row = repo.get_by_id(gen_id)
    assert row["status_name"] == "failed"
    assert row["error_code"] == "FETCH_TIMEOUT"
    assert row["error_message"] == "timeout 15s"


def test_set_script_generation_id_persists(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)
    script_gen_id = uuid.uuid4().hex
    repo.set_script_generation_id(generation_id=gen_id, script_generation_id=script_gen_id)
    assert repo.get_by_id(gen_id)["script_generation_id"] == script_gen_id


def test_get_by_id_returns_none_for_invalid_uuid(session_factory):
    repo = MaterialRepository(session_factory)
    assert repo.get_by_id("not-a-uuid") is None
