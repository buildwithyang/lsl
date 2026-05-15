from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from lsl.core.db import Base
from lsl.core.sql_types import JSONString, UUIDHexString


class MaterialGenerationModel(Base):
    __tablename__ = "material_generations"
    __table_args__ = (
        Index("idx_material_generations_session_id", "session_id"),
        Index("idx_material_generations_status_created_at", "x_status", "created_at"),
    )

    generation_id: Mapped[str] = mapped_column(UUIDHexString(), primary_key=True)
    session_id: Mapped[str] = mapped_column(UUIDHexString(), nullable=False)
    source_type: Mapped[str] = mapped_column("x_source_type", String(32), nullable=False)
    source_payload_json: Mapped[dict] = mapped_column(JSONString(), nullable=False, default=dict)
    extracted_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_meta_json: Mapped[dict | None] = mapped_column(JSONString(), nullable=True)
    script_generation_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
    job_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
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
