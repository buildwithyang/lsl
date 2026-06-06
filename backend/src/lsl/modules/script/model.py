from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from lsl.core.db import Base
from lsl.core.sql_types import JSONString, UUIDHexString


class ScriptGenerationModel(Base):
    __tablename__ = "script_generations"
    __table_args__ = (
        Index("idx_script_generations_session_id", "session_id"),
        Index("idx_script_generations_transcript_id", "transcript_id"),
        Index("idx_script_generations_status_created_at", "x_status", "created_at"),
    )

    generation_id: Mapped[str] = mapped_column(UUIDHexString(), primary_key=True)
    session_id: Mapped[str] = mapped_column(UUIDHexString(), nullable=False)
    transcript_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
    job_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
    provider: Mapped[str] = mapped_column("x_provider", String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column("x_description", Text, nullable=True)
    target_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cue_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cue_style: Mapped[str | None] = mapped_column(String(200), nullable=True)
    must_include_json: Mapped[list[str]] = mapped_column(
        JSONString(),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    preview_items_json: Mapped[list[dict]] = mapped_column(
        JSONString(),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    plan_sections_json: Mapped[list[dict]] = mapped_column(
        JSONString(),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    raw_result_json: Mapped[dict | None] = mapped_column(JSONString(), nullable=True)
    status: Mapped[int] = mapped_column("x_status", SmallInteger, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
    )
