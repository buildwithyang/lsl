from __future__ import annotations

import logging
import re
import time
import uuid

from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobRunResult, JobStatus
from lsl.modules.revision.service import RevisionService
from lsl.modules.revision.types import GeneratedRevisionItem
from lsl.modules.script.repo import ScriptRepository
from lsl.modules.script.schema import (
    GenerateScriptSessionData,
    GenerateScriptSessionRequest,
    ScriptGenerationData,
    ScriptGenerationPreviewData,
    ScriptGenerationPreviewItemData,
)
from lsl.modules.script.types import GeneratedScriptTurn, ScriptGenerateRequest, ScriptGenerator, ScriptSection
from lsl.modules.session.schema import CreateSessionRequest, UpdateSessionRequest
from lsl.modules.session.service import SessionService
from lsl.modules.transcript.service import TranscriptService
from lsl.modules.transcript.types import TranscriptUtterance

_WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
_SCRIPT_PLAN_TURN_THRESHOLD = 16
logger = logging.getLogger(__name__)


class ScriptService:
    def __init__(
        self,
        *,
        repository: ScriptRepository,
        generator: ScriptGenerator,
        session_service: SessionService,
        transcript_service: TranscriptService,
        revision_service: RevisionService,
        job_service: JobService,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._session_service = session_service
        self._transcript_service = transcript_service
        self._revision_service = revision_service
        self._job_service = job_service

    def generate_session(self, payload: GenerateScriptSessionRequest) -> GenerateScriptSessionData:
        session = self._session_service.create_session(
            CreateSessionRequest(
                title=payload.title,
                description=payload.description,
                target_language=payload.target_language,
                f_type=2,
            )
        )
        generation_id = uuid.uuid4().hex
        row = self._repository.create_generation(
            generation_id=generation_id,
            session_id=session.session.session_id,
            provider=self._generator.provider_name,
            title=payload.title,
            description=payload.description,
            target_language=payload.target_language,
            cue_language=payload.cue_language,
            prompt=payload.prompt,
            turn_count=payload.turn_count,
            speaker_count=payload.speaker_count,
            difficulty=payload.difficulty,
            cue_style=payload.cue_style,
            must_include=payload.must_include,
        )
        job = self._job_service.create_job(
            job_type=ScriptJobHandler.job_type,
            entity_type="script_generation",
            entity_id=generation_id,
            payload={"generation_id": generation_id},
        )
        self._repository.set_job_id(generation_id=generation_id, job_id=job.job_id)
        logger.info(
            "Script generation session created generation_id=%s session_id=%s job_id=%s turn_count=%s speaker_count=%s provider=%s",
            generation_id,
            session.session.session_id,
            job.job_id,
            payload.turn_count,
            payload.speaker_count,
            self._generator.provider_name,
        )
        generation = self.get_generation(generation_id=generation_id)
        session = self._session_service.get_session(session.session.session_id, auto_refresh=False)
        return GenerateScriptSessionData(session=session, generation=generation, job=job, revision=None)

    def get_generation(self, *, generation_id: str) -> ScriptGenerationData:
        row = self._repository.get_generation_by_id(generation_id)
        if row is None:
            raise ValueError("script generation not found")
        return ScriptGenerationData.from_row(row)

    def get_generation_preview(self, *, generation_id: str) -> ScriptGenerationPreviewData:
        row = self._repository.get_generation_by_id(generation_id)
        if row is None:
            raise ValueError("script generation not found")
        items = self._repository.get_generation_preview_items(generation_id=generation_id)
        if items is None:
            raise ValueError("script generation not found")
        return ScriptGenerationPreviewData(
            generation=ScriptGenerationData.from_row(row),
            items=[ScriptGenerationPreviewItemData(**item) for item in items],
        )

    def run_generation_job(self, *, generation_id: str) -> JobRunResult:
        started_at = time.monotonic()
        row = self._repository.get_generation_by_id(generation_id)
        if row is None:
            logger.warning("Script generation job missing generation_id=%s", generation_id)
            return JobRunResult(status=JobStatus.FAILED, error_code="GENERATION_NOT_FOUND", error_message="script generation not found")
        generation = ScriptGenerationData.from_row(row)
        if generation.transcript_id and generation.status_name == "completed":
            logger.info(
                "Script generation job already completed generation_id=%s transcript_id=%s",
                generation_id,
                generation.transcript_id,
            )
            return JobRunResult(status=JobStatus.COMPLETED, progress=100)

        logger.info(
            "Script generation job started generation_id=%s session_id=%s provider=%s turn_count=%s speaker_count=%s status=%s",
            generation.generation_id,
            generation.session_id,
            self._generator.provider_name,
            generation.turn_count,
            generation.speaker_count,
            generation.status_name,
        )
        self._repository.mark_generating(generation_id=generation_id)
        logger.info(
            "Script generation marked generating generation_id=%s elapsed_ms=%s",
            generation_id,
            int((time.monotonic() - started_at) * 1000),
        )
        req = ScriptGenerateRequest(
            title=generation.title,
            description=generation.description,
            target_language=generation.target_language,
            cue_language=generation.cue_language,
            prompt=generation.prompt,
            turn_count=generation.turn_count,
            speaker_count=generation.speaker_count,
            difficulty=generation.difficulty,
            cue_style=generation.cue_style,
            must_include=generation.must_include,
        )
        try:
            generated_turns: list[GeneratedScriptTurn] = []
            first_preview_logged = False
            plan_sections = self._resolve_plan_sections(req)
            if plan_sections:
                self._repository.save_plan_sections(
                    generation_id=generation_id,
                    sections=[self._serialize_section(section) for section in plan_sections],
                )
                logger.info(
                    "Script generation plan saved generation_id=%s sections=%s elapsed_ms=%s",
                    generation_id,
                    len(plan_sections),
                    int((time.monotonic() - started_at) * 1000),
                )

            turn_iter = (
                self._generate_from_plan_progressively(req=req, sections=plan_sections)
                if plan_sections
                else self._generator.generate_progressively(req)
            )
            for turn in turn_iter:
                if len(generated_turns) >= generation.turn_count:
                    break
                normalized_turn = GeneratedScriptTurn(
                    speaker=turn.speaker.strip() or f"user-{(len(generated_turns) % generation.speaker_count) + 1}",
                    cue=turn.cue.strip(),
                    text=turn.text.strip(),
                )
                if not normalized_turn.text:
                    continue
                generated_turns.append(normalized_turn)
                self._repository.save_preview_item(
                    generation_id=generation_id,
                    seq=len(generated_turns) - 1,
                    speaker=normalized_turn.speaker,
                    cue=normalized_turn.cue,
                    text=normalized_turn.text,
                )
                if not first_preview_logged:
                    first_preview_logged = True
                    logger.info(
                        "Script generation first preview saved generation_id=%s seq=%s elapsed_ms=%s text_len=%s cue_len=%s",
                        generation_id,
                        len(generated_turns) - 1,
                        int((time.monotonic() - started_at) * 1000),
                        len(normalized_turn.text),
                        len(normalized_turn.cue),
                    )
                else:
                    logger.info(
                        "Script generation preview saved generation_id=%s seq=%s elapsed_ms=%s text_len=%s cue_len=%s",
                        generation_id,
                        len(generated_turns) - 1,
                        int((time.monotonic() - started_at) * 1000),
                        len(normalized_turn.text),
                        len(normalized_turn.cue),
                    )

            logger.info(
                "Script generation generator finished generation_id=%s turn_count=%s elapsed_ms=%s",
                generation_id,
                len(generated_turns),
                int((time.monotonic() - started_at) * 1000),
            )

            if len(generated_turns) < 2:
                raise RuntimeError("Script generator returned too few valid utterances")

            # 构建转写
            transcript_utterances = self._build_transcript_utterances(generated_turns)
            # 构建 raw_result 用于存储生成器返回的原始结果
            raw_result = {
                "provider": self._generator.provider_name,
                "prompt": generation.prompt,
                "stage": "completed",
                "utterances": [
                    {
                        "speaker": item.speaker,
                        "cue": item.cue,
                        "text": item.text,
                    }
                    for item in generated_turns
                ],
            }
            transcript = self._transcript_service.create_completed_transcript(
                source_type="ai_script",
                source_entity_id=generation.generation_id,
                language=generation.target_language,
                utterances=transcript_utterances,
                full_text="\n".join(item.text for item in transcript_utterances),
                raw_result=raw_result,
            )
            logger.info(
                "Script generation transcript created generation_id=%s transcript_id=%s elapsed_ms=%s",
                generation_id,
                transcript.transcript_id,
                int((time.monotonic() - started_at) * 1000),
            )
            self._session_service.update_session(
                session_id=generation.session_id,
                payload=UpdateSessionRequest(
                    title=generation.title,
                    description=generation.description,
                    target_language=generation.target_language,
                    f_type=2,
                    current_transcript_id=transcript.transcript_id,
                ),
            )
            self._repository.mark_completed(
                generation_id=generation_id,
                transcript_id=transcript.transcript_id,
                raw_result_json=raw_result,
            )
            self._revision_service.create_generated_revision(
                session_id=generation.session_id,
                transcript_id=transcript.transcript_id,
                user_prompt=generation.prompt,
                cue_language=generation.cue_language,
                items=self._build_revision_items(
                    transcript_id=transcript.transcript_id,
                    transcript_utterances=transcript_utterances,
                    generated_turns=generated_turns,
                ),
            )
            logger.info(
                "Script generation job completed generation_id=%s transcript_id=%s turns=%s elapsed_ms=%s",
                generation_id,
                transcript.transcript_id,
                len(generated_turns),
                int((time.monotonic() - started_at) * 1000),
            )
        except Exception as exc:
            logger.exception(
                "Script generation job failed generation_id=%s elapsed_ms=%s",
                generation_id,
                int((time.monotonic() - started_at) * 1000),
            )
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="SCRIPT_GENERATION_FAILED",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="SCRIPT_GENERATION_FAILED", error_message=str(exc))

        return JobRunResult(status=JobStatus.COMPLETED, progress=100)

    def _resolve_plan_sections(self, req: ScriptGenerateRequest) -> list[ScriptSection]:
        if req.turn_count <= _SCRIPT_PLAN_TURN_THRESHOLD:
            return []

        planner = getattr(self._generator, "plan_sections", None)
        if callable(planner):
            sections = planner(req) or []
        else:
            sections = self._build_default_sections(turn_count=req.turn_count)
        return self._normalize_sections(sections=sections, turn_count=req.turn_count)

    def _generate_from_plan_progressively(
        self,
        *,
        req: ScriptGenerateRequest,
        sections: list[ScriptSection],
    ):
        generator = getattr(self._generator, "generate_from_plan_progressively", None)
        if callable(generator):
            yield from generator(req, sections)
            return
        yield from self._generator.generate_progressively(req)

    @staticmethod
    def _normalize_sections(*, sections: list[ScriptSection], turn_count: int) -> list[ScriptSection]:
        normalized: list[ScriptSection] = []
        remaining_turns = int(turn_count)
        for section in sections:
            if remaining_turns <= 0:
                break
            target_turn_count = max(1, min(int(section.target_turn_count), remaining_turns))
            normalized.append(
                ScriptSection(
                    section_index=len(normalized) + 1,
                    title=section.title.strip() or f"Section {len(normalized) + 1}",
                    summary=section.summary.strip(),
                    target_turn_count=target_turn_count,
                )
            )
            remaining_turns -= target_turn_count

        if not normalized or remaining_turns != 0:
            return ScriptService._build_default_sections(turn_count=turn_count)
        return normalized

    @staticmethod
    def _build_default_sections(*, turn_count: int) -> list[ScriptSection]:
        remaining = max(0, int(turn_count))
        sections: list[ScriptSection] = []
        while remaining > 0:
            section_turn_count = min(12, remaining)
            if remaining > 12 and remaining - section_turn_count < 4:
                section_turn_count = max(1, remaining // 2)
            sections.append(
                ScriptSection(
                    section_index=len(sections) + 1,
                    title=f"Section {len(sections) + 1}",
                    summary="Continue the dialogue naturally and move the scenario forward.",
                    target_turn_count=section_turn_count,
                )
            )
            remaining -= section_turn_count
        return sections

    @staticmethod
    def _serialize_section(section: ScriptSection) -> dict[str, object]:
        return {
            "section_index": int(section.section_index),
            "title": section.title,
            "summary": section.summary,
            "target_turn_count": int(section.target_turn_count),
        }

    @staticmethod
    def _build_transcript_utterances(
        generated_turns: list[GeneratedScriptTurn],
    ) -> list[TranscriptUtterance]:
        utterances: list[TranscriptUtterance] = []
        current_start_ms = 0
        for index, item in enumerate(generated_turns):
            duration_ms = ScriptService._estimate_duration_ms(item.text)
            utterances.append(
                TranscriptUtterance(
                    seq=index,
                    text=item.text.strip(),
                    speaker=item.speaker.strip() or f"user-{(index % 2) + 1}",
                    start_time=current_start_ms,
                    end_time=current_start_ms + duration_ms,
                    additions={"cue": item.cue.strip()},
                )
            )
            current_start_ms += duration_ms
        return utterances

    @staticmethod
    def _build_revision_items(
        *,
        transcript_id: str,
        transcript_utterances: list[TranscriptUtterance],
        generated_turns: list[GeneratedScriptTurn],
    ) -> list[GeneratedRevisionItem]:
        if len(transcript_utterances) != len(generated_turns):
            raise RuntimeError("Generated script and transcript utterances length mismatch")

        items: list[GeneratedRevisionItem] = []
        for transcript_item, generated_turn in zip(transcript_utterances, generated_turns, strict=True):
            suggested_text = ScriptService._compose_cue_script(
                cue=generated_turn.cue,
                text=generated_turn.text,
            )
            items.append(
                GeneratedRevisionItem(
                    transcript_id=transcript_id,
                    source_seq_start=int(transcript_item.seq),
                    source_seq_end=int(transcript_item.seq),
                    source_seq_count=1,
                    source_seqs=[int(transcript_item.seq)],
                    speaker=transcript_item.speaker,
                    start_time=int(transcript_item.start_time),
                    end_time=int(transcript_item.end_time),
                    original_text=transcript_item.text,
                    suggested_text=suggested_text,
                    draft_text=None,
                    score=100,
                    issue_tags="",
                    explanations="AI generated cue script.",
                )
            )
        return items

    @staticmethod
    def _compose_cue_script(*, cue: str, text: str) -> str:
        normalized_cue = cue.strip().strip("[]")
        normalized_text = re.sub(r"\s+", " ", text.strip())
        return f"[{normalized_cue}] {normalized_text}".strip()

    @staticmethod
    def _estimate_duration_ms(text: str) -> int:
        word_count = len(_WORD_PATTERN.findall(text))
        if word_count <= 0:
            return 1400
        return max(1400, min(6000, word_count * 420))


class ScriptJobHandler:
    job_type = "ai_script_generation"

    def __init__(self, *, script_service: ScriptService) -> None:
        self._script_service = script_service

    def run(self, job: JobData) -> JobRunResult:
        generation_id = str(job.payload.get("generation_id") or job.entity_id or "").strip()
        if not generation_id:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MISSING_GENERATION_ID",
                error_message="generation_id is required",
            )
        return self._script_service.run_generation_job(generation_id=generation_id)
