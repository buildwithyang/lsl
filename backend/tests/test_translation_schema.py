from __future__ import annotations

import pytest
from pydantic import ValidationError

from lsl.modules.translation.schema import (
    CreateTranslationRequest,
    TranslationSourceItemPayload,
)


def test_source_item_has_no_time_fields() -> None:
    # Translation is a pure leaf: the frontend owns the authoritative timestamps and
    # never reads them back, so the payload must not carry start_time/end_time.
    fields = TranslationSourceItemPayload.model_fields
    assert "start_time" not in fields
    assert "end_time" not in fields


def test_source_item_ignores_stray_time_fields() -> None:
    # Stale clients may still POST fractional start_time/end_time; extra keys must be
    # dropped, not rejected with a 422 (this was the original button-does-nothing bug).
    item = TranslationSourceItemPayload(
        source_item_key="1",
        source_text="Hello.",
        start_time=2.94,
        end_time=8.94,
    )
    assert not hasattr(item, "start_time")
    assert not hasattr(item, "end_time")


def test_create_request_validates_without_times() -> None:
    request = CreateTranslationRequest(
        source_type="transcript",
        source_entity_id="25a38167fe6c42dbbefa76803dc8e9e8",
        target_language="zh-CN",
        items=[
            {
                "source_item_key": "0",
                "source_seq": 0,
                "speaker": "user-2",
                "source_text": "Good morning. How can I help you?",
            }
        ],
    )
    assert request.items[0].source_text.startswith("Good morning")


def test_source_item_still_requires_text() -> None:
    with pytest.raises(ValidationError):
        TranslationSourceItemPayload(source_item_key="1", source_text="")
