from __future__ import annotations

import logging
from typing import Any

import requests

from lsl.core.config import Settings
from lsl.modules.asr.types import (
    AsrJobRef,
    AsrJobStatus,
    AsrQueryResult,
    AsrSubmitRequest,
    AsrUtterance,
)

logger = logging.getLogger(__name__)


class VolcAsrProvider:
    provider_name = "volc"

    _STATUS_SUCCEEDED = "20000000"
    _STATUS_QUEUED = "20000001"
    _STATUS_PROCESSING = "20000002"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.VOLC_API_KEY
        self._resource_id = settings.VOLC_RESOURCE_ID
        self._submit_url = settings.VOLC_SUBMIT_URL
        self._query_url = settings.VOLC_QUERY_URL
        self._model_name = settings.VOLC_MODEL_NAME
        self._uid = settings.VOLC_UID
        self._timeout = settings.VOLC_HTTP_TIMEOUT
        self._validate_settings()

    def submit(self, req: AsrSubmitRequest) -> AsrJobRef:
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": req.recognition_id,
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }
        payload = {
            "user": {"uid": self._uid},
            "audio": {
                "url": req.audio_url,
                "language": req.language or "en-US",
            },
            "request": {
                "model_name": self._model_name,
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "enable_speaker_info": True,
                "enable_emotion_detection": True,
                "enable_gender_detection": True,
            },
        }

        response = self._post_json(
            url=self._submit_url,
            payload=payload,
            headers=headers,
            action="submit",
            request_id=req.recognition_id,
        )
        status_code = self._header(response.headers, "X-Api-Status-Code")
        message = self._header(response.headers, "X-Api-Message")
        x_tt_logid = self._header(response.headers, "X-Tt-Logid")

        if status_code != self._STATUS_SUCCEEDED:
            logger.error(
                "Volc submit business failed: request_id=%s status_code=%s message=%s response_body=%s",
                req.recognition_id,
                status_code,
                message,
                self._safe_response_text(response),
            )
            raise RuntimeError(f"Volc submit failed: code={status_code}, message={message}")

        return AsrJobRef(
            recognition_id=req.recognition_id,
            provider=self.provider_name,
            provider_request_id=req.recognition_id,
            provider_resource_id=self._resource_id,
            x_tt_logid=x_tt_logid,
        )

    def query(self, ref: AsrJobRef) -> AsrQueryResult:
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": ref.provider_resource_id or self._resource_id,
            "X-Api-Request-Id": ref.provider_request_id,
            "Content-Type": "application/json",
        }
        if ref.x_tt_logid:
            headers["X-Tt-Logid"] = ref.x_tt_logid

        response = self._post_json(
            url=self._query_url,
            payload={},
            headers=headers,
            action="query",
            request_id=ref.provider_request_id,
        )

        status_code = self._header(response.headers, "X-Api-Status-Code")
        message = self._header(response.headers, "X-Api-Message")
        x_tt_logid = self._header(response.headers, "X-Tt-Logid")

        if status_code == self._STATUS_QUEUED:
            return AsrQueryResult(
                status=AsrJobStatus.QUEUED,
                provider_status_code=status_code,
                provider_message=message,
                x_tt_logid=x_tt_logid,
            )
        if status_code == self._STATUS_PROCESSING:
            return AsrQueryResult(
                status=AsrJobStatus.PROCESSING,
                provider_status_code=status_code,
                provider_message=message,
                x_tt_logid=x_tt_logid,
            )
        if status_code != self._STATUS_SUCCEEDED:
            logger.error(
                "Volc query business failed: request_id=%s status_code=%s message=%s x_tt_logid=%s response_body=%s",
                ref.provider_request_id,
                status_code,
                message,
                x_tt_logid,
                self._safe_response_text(response),
            )
            return AsrQueryResult(
                status=AsrJobStatus.FAILED,
                provider_status_code=status_code,
                provider_message=message,
                error_code=status_code,
                error_message=message,
                x_tt_logid=x_tt_logid,
            )

        payload = response.json()
        return AsrQueryResult(
            status=AsrJobStatus.SUCCEEDED,
            provider_status_code=status_code,
            provider_message=message,
            duration_ms=self._extract_duration_ms(payload),
            full_text=self._extract_full_text(payload),
            utterances=self._extract_utterances(payload),
            raw_result=payload if isinstance(payload, dict) else {},
            x_tt_logid=x_tt_logid,
        )

    def _validate_settings(self) -> None:
        if not self._api_key:
            raise ValueError("VOLC_API_KEY is required when ASR_PROVIDER=volc")
        if not self._submit_url:
            raise ValueError("VOLC_SUBMIT_URL is required when ASR_PROVIDER=volc")
        if not self._query_url:
            raise ValueError("VOLC_QUERY_URL is required when ASR_PROVIDER=volc")

    def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        action: str,
        request_id: str,
    ) -> requests.Response:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.exception(
                "Volc %s transport error: request_id=%s url=%s headers=%s payload=%s",
                action,
                request_id,
                url,
                self._safe_headers(headers),
                payload,
            )
            raise RuntimeError(f"Volc {action} request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "Volc %s http failed: request_id=%s url=%s status=%s headers=%s payload=%s response_headers=%s response_body=%s",
                action,
                request_id,
                url,
                response.status_code,
                self._safe_headers(headers),
                payload,
                dict(response.headers),
                self._safe_response_text(response),
            )
            raise RuntimeError(f"Volc {action} http failed: status={response.status_code}")
        return response

    @staticmethod
    def _header(headers: Any, key: str) -> str | None:
        value = headers.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
        safe = dict(headers)
        api_key = safe.get("X-Api-Key")
        if api_key:
            safe["X-Api-Key"] = f"{api_key[:4]}***{api_key[-4:]}" if len(api_key) > 8 else "***"
        return safe

    @staticmethod
    def _safe_response_text(response: requests.Response, limit: int = 1200) -> str:
        text = response.text or ""
        if len(text) <= limit:
            return text
        return f"{text[:limit]}...(truncated)"

    @staticmethod
    def _extract_duration_ms(payload: dict[str, Any]) -> int | None:
        audio_info = payload.get("audio_info", {})
        duration = audio_info.get("duration")
        if isinstance(duration, int):
            return duration

        additions = payload.get("result", {}).get("additions", {})
        fallback = additions.get("duration")
        if isinstance(fallback, str) and fallback.isdigit():
            return int(fallback)
        if isinstance(fallback, int):
            return fallback
        return None

    @staticmethod
    def _extract_full_text(payload: dict[str, Any]) -> str | None:
        text = payload.get("result", {}).get("text")
        return text if isinstance(text, str) else None

    @staticmethod
    def _extract_utterances(payload: dict[str, Any]) -> list[AsrUtterance]:
        items = payload.get("result", {}).get("utterances", [])
        result: list[AsrUtterance] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            text = item.get("text")
            start_time = item.get("start_time")
            end_time = item.get("end_time")
            additions = item.get("additions") or {}

            if not isinstance(text, str) or not text.strip():
                continue
            if not isinstance(start_time, int) or not isinstance(end_time, int):
                continue

            speaker = None
            clean_additions: dict[str, Any] = {}
            if isinstance(additions, dict):
                speaker_value = additions.get("speaker")
                if isinstance(speaker_value, str):
                    speaker = f'user-{speaker_value}'
                clean_additions = {
                    "emotion": additions.get("emotion"),
                    "emotion_degree": additions.get("emotion_degree"),
                    "emotion_score": additions.get("emotion_score"),
                    "emotion_degree_score": additions.get("emotion_degree_score"),
                    "gender": additions.get("gender"),
                    "gender_score": additions.get("gender_score"),
                }
                clean_additions = {key: value for key, value in clean_additions.items() if value is not None}

            result.append(
                AsrUtterance(
                    seq=idx,
                    text=text,
                    speaker=speaker,
                    start_time=start_time,
                    end_time=end_time,
                    additions=clean_additions,
                )
            )
        return result
