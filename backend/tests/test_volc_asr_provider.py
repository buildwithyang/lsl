from __future__ import annotations

import pytest

from lsl.core.config import Settings
from lsl.modules.asr.providers.volc_asr import VolcAsrProvider
from lsl.modules.asr.types import AsrJobStatus, AsrSubmitRequest


class _FakeResponse:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def _build_settings() -> Settings:
    return Settings(
        VOLC_API_KEY="test-api-key",
        VOLC_RESOURCE_ID="volc.seedasr.auc",
        VOLC_SUBMIT_URL="https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
        VOLC_QUERY_URL="https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
    )


def test_default_resource_id_uses_model_2_0() -> None:
    assert Settings.VOLC_RESOURCE_ID == "volc.seedasr.auc"


def test_submit_and_query_use_api_key_authentication(monkeypatch) -> None:
    provider = VolcAsrProvider(_build_settings())
    requests: list[dict[str, object]] = []
    responses = iter(
        [
            _FakeResponse(
                {
                    "X-Api-Status-Code": "20000000",
                    "X-Api-Message": "OK",
                    "X-Tt-Logid": "test-log-id",
                }
            ),
            _FakeResponse(
                {
                    "X-Api-Status-Code": "20000001",
                    "X-Api-Message": "Processing",
                }
            ),
        ]
    )

    def fake_post_json(**kwargs):
        requests.append(kwargs)
        return next(responses)

    monkeypatch.setattr(provider, "_post_json", fake_post_json)

    ref = provider.submit(
        AsrSubmitRequest(
            recognition_id="test-request-id",
            audio_url="https://example.com/audio.mp3",
        )
    )
    result = provider.query(ref)

    assert result.status == AsrJobStatus.QUEUED
    assert [request["url"] for request in requests] == [
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
    ]
    for request in requests:
        headers = request["headers"]
        assert isinstance(headers, dict)
        assert headers["X-Api-Key"] == "test-api-key"
        assert headers["X-Api-Resource-Id"] == "volc.seedasr.auc"
        assert "X-Api-App-Key" not in headers
        assert "X-Api-Access-Key" not in headers


def test_api_key_is_required() -> None:
    with pytest.raises(ValueError, match="VOLC_API_KEY is required"):
        VolcAsrProvider(Settings())


def test_api_key_is_masked_in_logs() -> None:
    assert VolcAsrProvider._safe_headers({"X-Api-Key": "1234567890"}) == {
        "X-Api-Key": "1234***7890"
    }
