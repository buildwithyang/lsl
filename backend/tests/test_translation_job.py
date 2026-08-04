from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.db import Base
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobStatus
from lsl.modules.translation.provider import FakeTranslationGenerator
from lsl.modules.translation.repo import TranslationRepository
from lsl.modules.translation.service import TranslationJobHandler, TranslationService
from lsl.modules.translation.types import TranslationSourceItem


def _build_services() -> tuple[TranslationService, JobService]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)

    job_service = JobService(repository=JobRepository(factory), lock_ttl_seconds=30)
    translation_service = TranslationService(
        repository=TranslationRepository(factory),
        generator=FakeTranslationGenerator(),
        job_service=job_service,
    )
    job_service.register_handler(TranslationJobHandler(translation_service=translation_service))
    return translation_service, job_service


def _items(*texts: str) -> list[TranslationSourceItem]:
    return [
        TranslationSourceItem(
            source_item_key=str(index),
            source_seq=index,
            speaker="A",
            start_time=index * 1000,
            end_time=(index + 1) * 1000,
            source_text=text,
        )
        for index, text in enumerate(texts)
    ]


def test_translation_generation_job_updates_items() -> None:
    translation_service, job_service = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there", "nice to meet you"),
        target_language="zh-CN",
    )
    assert created.status_name == "generating"
    assert created.job_id is not None
    assert [item.status_name for item in created.items] == ["pending", "pending"]

    completed = job_service.run_job(job_id=created.job_id, worker_id="test-worker")
    assert completed.status == int(JobStatus.COMPLETED)

    translation = translation_service.get_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        target_language="zh-CN",
    )
    assert translation.status_name == "completed"
    assert [item.translated_text for item in translation.items] == [
        "译文：hello there",
        "译文：nice to meet you",
    ]


def test_translation_uses_explicit_target_language() -> None:
    translation_service, _ = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-zh",
        items=_items("你好"),
        source_language="zh-CN",
        target_language="en",
    )

    assert created.source_language == "zh-CN"
    assert created.target_language == "en"


def test_revision_translation_keeps_pushed_source_language() -> None:
    translation_service, _ = _build_services()

    created = translation_service.create_translation(
        source_type="revision",
        source_entity_id="revision-1",
        items=_items("[自然地打招呼] 你好"),
        source_language="zh-CN",
        target_language="en",
    )

    assert created.source_type == "revision"
    assert created.source_language == "zh-CN"
    assert created.target_language == "en"


def test_omitted_translation_target_falls_back_to_configured_language() -> None:
    translation_service, _ = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there"),
        target_language=None,
    )

    assert created.target_language == "zh-CN"


def test_translation_retry_recovers_generating_items() -> None:
    translation_service, job_service = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there"),
        target_language="zh-CN",
    )
    translation_service._repository.mark_items_generating(
        translation_id=created.translation_id,
        source_item_keys=[created.items[0].source_item_key],
    )

    retried = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there"),
        target_language="zh-CN",
        force=True,
    )
    assert retried.job_id is not None

    completed = job_service.run_job(job_id=retried.job_id, worker_id="test-worker")
    assert completed.status == int(JobStatus.COMPLETED)

    translation = translation_service.get_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        target_language="zh-CN",
    )
    assert translation.status_name == "completed"
    assert translation.items[0].status_name == "completed"
    assert translation.items[0].translated_text == "译文：hello there"


def test_active_translation_job_stays_generating_after_read_refresh() -> None:
    translation_service, _ = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there", "nice to meet you"),
        target_language="zh-CN",
    )
    translation_service._repository.mark_items_generating(
        translation_id=created.translation_id,
        source_item_keys=[item.source_item_key for item in created.items],
    )
    translation_service._repository.apply_suggestions(
        translation_id=created.translation_id,
        suggestions={created.items[0].source_item_key: "译文：hello there"},
    )

    translation = translation_service.get_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        target_language="zh-CN",
    )
    assert translation.status_name == "generating"
    assert translation.job_id == created.job_id
    assert [item.status_name for item in translation.items] == ["completed", "generating"]


def test_pushing_changed_text_resets_item_to_pending() -> None:
    translation_service, job_service = _build_services()

    created = translation_service.create_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        items=_items("hello there"),
        target_language="zh-CN",
    )
    job_service.run_job(job_id=created.job_id, worker_id="test-worker")
    completed = translation_service.get_translation(
        source_type="transcript",
        source_entity_id="transcript-1",
        target_language="zh-CN",
    )
    assert completed.status_name == "completed"
    assert completed.items[0].translated_text == "译文：hello there"

    # Re-pushing the same key with edited text drops the old translation and
    # marks the item pending so it can be translated again. No stale state.
    updated = translation_service._repository.upsert_translation(
        translation_id=completed.translation_id,
        session_id=None,
        source_type="transcript",
        source_entity_id="transcript-1",
        source_language="en-US",
        target_language="zh-CN",
        provider="fake",
        model_name=None,
        source_items=[
            TranslationSourceItem(
                source_item_key="0",
                source_seq=0,
                speaker="A",
                start_time=0,
                end_time=1000,
                source_text="hello there again",
            )
        ],
    )

    assert updated.status_name == "pending"
    assert updated.items[0].status_name == "pending"
    assert updated.items[0].translated_text is None


def test_translate_single_item_runs_without_job() -> None:
    translation_service, _ = _build_services()

    translation = translation_service.translate_item(
        source_type="transcript",
        source_entity_id="transcript-1",
        item=TranslationSourceItem(
            source_item_key="1",
            source_seq=1,
            speaker="B",
            start_time=1000,
            end_time=2000,
            source_text="nice to meet you",
        ),
        target_language="zh-CN",
    )

    assert translation.job_id is None
    assert translation.status_name == "completed"
    assert [item.source_item_key for item in translation.items] == ["1"]
    assert translation.items[0].translated_text == "译文：nice to meet you"
