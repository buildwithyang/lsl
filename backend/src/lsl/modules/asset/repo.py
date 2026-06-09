from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.asset.model import AssetModel
from lsl.modules.asset.schema import AssetData


class AssetRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def upsert_completed_upload(
        self,
        *,
        object_key: str,
        category: str,
        entity_id: str,
        filename: str | None,
        content_type: str | None,
        file_size: int | None,
        etag: str | None,
        storage_provider: str,
        upload_status: int,
    ) -> None:
        stmt = select(AssetModel).where(AssetModel.object_key == object_key).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                if model is None:
                    model = AssetModel(object_key=object_key)
                    db.add(model)

                model.category = category
                model.entity_id = entity_id
                model.filename = filename or model.filename
                model.content_type = content_type or model.content_type
                model.file_size = file_size if file_size is not None else model.file_size
                model.etag = etag or model.etag
                model.storage_provider = storage_provider
                model.upload_status = int(upload_status)
                db.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to persist asset record: {exc}") from exc

    def list_assets(
        self,
        *,
        limit: int,
        category: str | None = None,
        entity_id: str | None = None,
    ) -> list[AssetData]:
        stmt = select(AssetModel)
        if category:
            stmt = stmt.where(AssetModel.category == category)
        if entity_id:
            stmt = stmt.where(AssetModel.entity_id == entity_id)
        stmt = stmt.order_by(AssetModel.created_at.desc()).limit(limit)

        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list asset records: {exc}") from exc

    def get_asset_by_object_key(self, *, object_key: str) -> AssetData | None:
        stmt = select(AssetModel).where(AssetModel.object_key == object_key).limit(1)
        try:
            with self._session_scope() as db:
                model = db.execute(stmt).scalar_one_or_none()
                return self._to_data(model) if model is not None else None
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query asset by object_key: {exc}") from exc

    def list_assets_by_object_keys(self, *, object_keys: list[str]) -> list[AssetData]:
        if not object_keys:
            return []

        stmt = select(AssetModel).where(AssetModel.object_key.in_(object_keys))
        try:
            with self._session_scope() as db:
                rows = db.execute(stmt).scalars().all()
                return [self._to_data(model) for model in rows]
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to query assets by object_keys: {exc}") from exc

    @staticmethod
    def _to_data(model: AssetModel) -> AssetData:
        return AssetData(
            object_key=model.object_key,
            category=model.category,
            entity_id=model.entity_id,
            filename=model.filename,
            content_type=model.content_type,
            file_size=model.file_size,
            etag=model.etag,
            upload_status=int(model.upload_status),
            created_at=model.created_at,
        )
