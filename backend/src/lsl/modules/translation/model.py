from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from lsl.core.db import Base
from lsl.core.sql_types import JSONString, UUIDHexString


class TranslationModel(Base):
    __tablename__ = "translation_translations"
    __table_args__ = (
        UniqueConstraint("source_type", "source_entity_id", "target_language", name="uq_translation_source_target"),
        Index("idx_translation_translations_session", "session_id", "created_at"),
        Index("idx_translation_translations_status_created_at", "x_status", "created_at"),
    )

    translation_id: Mapped[str] = mapped_column(UUIDHexString(), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    job_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
    provider: Mapped[str] = mapped_column("x_provider", String(32), nullable=False)
    model: Mapped[str | None] = mapped_column("x_model", String(128), nullable=True)
    status: Mapped[int] = mapped_column("x_status", SmallInteger, nullable=False, server_default=text("0"))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_result_json: Mapped[dict | None] = mapped_column(JSONString(), nullable=True)
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

    items: Mapped[list["TranslationItemModel"]] = relationship(
        back_populates="translation",
        cascade="all, delete-orphan",
        order_by=lambda: (TranslationItemModel.source_seq, TranslationItemModel.source_item_key),
        primaryjoin=lambda: TranslationModel.translation_id == foreign(TranslationItemModel.translation_id),
        foreign_keys=lambda: [TranslationItemModel.translation_id],
    )


class TranslationItemModel(Base):
    __tablename__ = "translation_items"
    __table_args__ = (
        UniqueConstraint("translation_id", "source_item_key", name="uq_translation_items_source_item"),
        Index("idx_translation_items_translation_seq", "translation_id", "source_seq"),
        Index("idx_translation_items_status", "translation_id", "x_status"),
    )

    item_id: Mapped[str] = mapped_column(UUIDHexString(), primary_key=True)
    translation_id: Mapped[str] = mapped_column(UUIDHexString(), nullable=False)
    source_item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    translation: Mapped[TranslationModel] = relationship(
        back_populates="items",
        primaryjoin=lambda: foreign(TranslationItemModel.translation_id) == TranslationModel.translation_id,
        foreign_keys=lambda: [TranslationItemModel.translation_id],
    )
