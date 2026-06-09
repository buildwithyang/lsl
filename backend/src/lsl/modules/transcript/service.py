from __future__ import annotations

import re
import uuid
from typing import Any

from lsl.modules.transcript.repo import TranscriptRepository
from lsl.modules.transcript.schema import TranscriptData, TranscriptUtteranceData
from lsl.modules.transcript.types import TranscriptStatus, TranscriptUtterance


class TranscriptService:
    def __init__(self, *, repository: TranscriptRepository) -> None:
        self._repository = repository

    def create_pending_transcript(
        self,
        *,
        source_type: str,
        source_entity_id: str | None = None,
        language: str | None = None,
    ) -> TranscriptData:
        transcript = self._repository.create_transcript(
            transcript_id=uuid.uuid4().hex,
            source_type=self._normalize_required(source_type, "source_type"),
            source_entity_id=self._normalize_optional(source_entity_id),
            language=self._normalize_optional(language),
            status=int(TranscriptStatus.PENDING),
        )
        return self._mask_raw(transcript, include_raw=False)

    def create_completed_transcript(
        self,
        *,
        source_type: str,
        source_entity_id: str | None,
        language: str | None,
        utterances: list[TranscriptUtterance],
        full_text: str | None = None,
        duration_ms: int | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> TranscriptData:
        transcript = self.create_pending_transcript(
            source_type=source_type,
            source_entity_id=source_entity_id,
            language=language,
        )
        return self.mark_completed(
            transcript_id=transcript.transcript_id,
            utterances=utterances,
            full_text=full_text,
            duration_ms=duration_ms,
            raw_result=raw_result,
        )

    def update_source_entity(self, *, transcript_id: str, source_entity_id: str) -> None:
        self._repository.update_source_entity(
            transcript_id=transcript_id,
            source_entity_id=self._normalize_required(source_entity_id, "source_entity_id"),
        )

    def mark_completed(
        self,
        *,
        transcript_id: str,
        utterances: list[TranscriptUtterance],
        full_text: str | None = None,
        duration_ms: int | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> TranscriptData:
        normalized = self._normalize_utterances(utterances)
        if not normalized:
            raise ValueError("utterances are required")
        resolved_full_text = (full_text or "\n".join(item.text for item in normalized)).strip()
        resolved_duration_ms = duration_ms if duration_ms is not None else max(int(item.end_time) for item in normalized)
        return self._repository.mark_completed(
            transcript_id=transcript_id,
            duration_ms=resolved_duration_ms,
            full_text=resolved_full_text,
            raw_result_json=raw_result,
            utterances=[item.model_dump() for item in normalized],
        )

    def mark_failed(
        self,
        *,
        transcript_id: str,
        error_code: str | None,
        error_message: str | None,
    ) -> TranscriptData:
        transcript = self._repository.mark_failed(
            transcript_id=transcript_id,
            error_code=error_code,
            error_message=error_message,
        )
        return self._mask_raw(transcript, include_raw=False)

    def get_transcript(self, *, transcript_id: str, include_raw: bool = False) -> TranscriptData:
        transcript = self._repository.get_transcript_by_id(transcript_id, include_utterances=True)
        if transcript is None:
            raise ValueError("transcript not found")
        return self._mask_raw(transcript, include_raw=include_raw)

    def list_transcripts(
        self,
        *,
        limit: int = 20,
        status: int | None = None,
        source_type: str | None = None,
        source_entity_id: str | None = None,
    ) -> list[TranscriptData]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 100:
            raise ValueError("limit must be less than or equal to 100")
        transcripts = self._repository.list_transcripts(
            limit=limit,
            status=status,
            source_type=self._normalize_optional(source_type),
            source_entity_id=self._normalize_optional(source_entity_id),
        )
        return [self._mask_raw(transcript, include_raw=False) for transcript in transcripts]

    def list_transcripts_by_ids(self, transcript_ids: list[str]) -> dict[str, TranscriptData]:
        normalized = sorted({item.strip() for item in transcript_ids if item and item.strip()})
        if not normalized:
            return {}
        transcripts = self._repository.list_transcripts_by_ids(normalized)
        return {
            transcript.transcript_id: self._mask_raw(transcript, include_raw=False)
            for transcript in transcripts
        }

    def list_utterances(self, *, transcript_id: str) -> list[TranscriptUtteranceData]:
        return self.get_transcript(transcript_id=transcript_id).utterances

    @staticmethod
    def _mask_raw(transcript: TranscriptData, *, include_raw: bool) -> TranscriptData:
        if include_raw or transcript.raw_result is None:
            return transcript
        return transcript.model_copy(update={"raw_result": None})

    @staticmethod
    def _normalize_utterances(utterances: list[TranscriptUtterance]) -> list[TranscriptUtterance]:
        normalized: list[TranscriptUtterance] = []
        for item in sorted(utterances, key=lambda value: int(value.seq)):
            text = re.sub(r"\s+", " ", item.text.strip()).strip()
            if not text:
                raise ValueError("utterance text is required")
            start_time = int(item.start_time)
            end_time = int(item.end_time)
            if end_time < start_time:
                raise ValueError("utterance end_time must be greater than or equal to start_time")
            normalized.append(
                TranscriptUtterance(
                    seq=int(item.seq),
                    text=text,
                    speaker=(item.speaker or "").strip() or None,
                    start_time=start_time,
                    end_time=end_time,
                    additions=dict(item.additions or {}),
                )
            )

        if not normalized:
            return []
        seqs = [int(item.seq) for item in normalized]
        expected = list(range(seqs[0], seqs[0] + len(seqs)))
        if seqs != expected:
            raise ValueError("utterance seqs must be contiguous")
        return normalized

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_required(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} is required")
        return normalized
