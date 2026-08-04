from __future__ import annotations

import json

from lsl.modules.translation.provider import LLMTranslationGenerator
from lsl.modules.translation.types import TranslationGenerateRequest, TranslationSourceItem


def test_translation_prompt_keeps_and_translates_bracket_cues() -> None:
    req = TranslationGenerateRequest(
        translation_id="translation-1",
        source_type="revision",
        source_entity_id="revision-1",
        source_language="en-US",
        target_language="zh-CN",
        items=[
            TranslationSourceItem(
                source_item_key="item-1",
                source_seq=0,
                speaker="user-1",
                start_time=0,
                end_time=1000,
                source_text="[Open with relaxed curiosity] What did you do last weekend?",
            )
        ],
    )

    messages = LLMTranslationGenerator._build_messages(req)

    system_message = next(item for item in messages if item["role"] == "system")
    assert "translate that CUE into target_language" in system_message["content"]
    assert "keep it at the front in square brackets" in system_message["content"]

    user_message = next(item for item in messages if item["role"] == "user")
    payload = json.loads(user_message["content"].split("Input JSON:\n", 1)[1])
    assert payload["target_language"] == "zh-CN"
    assert payload["items"][0]["text"].startswith("[Open with relaxed curiosity]")
