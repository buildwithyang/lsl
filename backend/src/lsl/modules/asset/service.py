import logging
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import requests

from lsl.core.config import Settings
from lsl.modules.asset.repo import AssetRepository
from lsl.modules.asset.schema import AssetData, AssetListItemData
from lsl.modules.asset.types import StorageProvider

logger = logging.getLogger(__name__)


class AssetService:
    """
    asset 业务层：
    - 生成 object_key
    - 生成上传用 presigned URL
    - 生成访问 URL
    """

    def __init__(
        self,
        settings: Settings,
        storage: StorageProvider,
        repository: Optional[AssetRepository] = None,
    ):
        self._settings = settings
        self._storage = storage
        self._repository = repository

    def generate_object_key(
        self,
        *,
        category: str,
        entity_id: str,
        filename: str,
    ) -> str:
        """
        根据业务生成系统内部 asset 唯一标识(object key)
        """
        ext = Path(filename).suffix
        uid = uuid.uuid4().hex

        return f"{category}/{entity_id}/{uid}{ext}"


    def generate_upload_url(
        self,
        *,
        object_key: str,
        content_type: str,
        expires: timedelta = timedelta(minutes=10),
    ) -> str:
        """
        生成上传用 Presigned PUT URL
        """
        return self._storage.generate_presigned_put_url(
            object_key=object_key,
            content_type=content_type,
            expires=expires,
        )

    def build_asset_url(self, object_key: str) -> str:
        """
        生成最终访问 URL(读)
        """
        base = self._settings.ASSET_BASE_URL.rstrip("/")
        return f"{base}/{object_key}"

    def complete_upload(
        self,
        *,
        object_key: str,
        category: Optional[str],
        entity_id: Optional[str],
        filename: Optional[str],
        content_type: Optional[str],
        file_size: Optional[int],
        etag: Optional[str],
    ) -> None:
        if self._repository is None:
            raise RuntimeError("Asset repository is not configured. Set DATABASE_URL to enable persistence.")

        parsed_category, parsed_entity_id = self._parse_category_and_entity(object_key)

        final_category = category or parsed_category
        final_entity_id = entity_id or parsed_entity_id

        if category and category != parsed_category:
            raise ValueError("category does not match object_key")
        if entity_id and entity_id != parsed_entity_id:
            raise ValueError("entity_id does not match object_key")

        final_filename = filename or Path(object_key).name

        self._repository.upsert_completed_upload(
            object_key=object_key,
            category=final_category,
            entity_id=final_entity_id,
            filename=final_filename,
            content_type=content_type,
            file_size=file_size,
            etag=etag,
            storage_provider=self._settings.STORAGE_PROVIDER,
            upload_status=0,
        )

    def save_generated_asset(
        self,
        *,
        category: str,
        entity_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> dict[str, Any]:
        object_key = self.generate_object_key(
            category=category,
            entity_id=entity_id,
            filename=filename,
        )
        normalized_content_type = content_type.strip() or "application/octet-stream"

        if self._settings.STORAGE_PROVIDER != "fake":
            upload_url = self.generate_upload_url(
                object_key=object_key,
                content_type=normalized_content_type,
            )
            upload_host = urlsplit(upload_url).netloc
            upload_started_at = time.monotonic()
            logger.info(
                "Generated asset upload started object_key=%s storage_provider=%s size=%s content_type=%s upload_host=%s",
                object_key,
                self._settings.STORAGE_PROVIDER,
                len(data),
                normalized_content_type,
                upload_host,
            )
            try:
                response = requests.put(
                    upload_url,
                    data=data,
                    headers={"Content-Type": normalized_content_type},
                    timeout=self._settings.ASSET_PUT_TIMEOUT,
                )
            except Exception as exc:
                logger.exception(
                    "Generated asset upload failed object_key=%s storage_provider=%s size=%s upload_host=%s elapsed_ms=%s exc_type=%s",
                    object_key,
                    self._settings.STORAGE_PROVIDER,
                    len(data),
                    upload_host,
                    int((time.monotonic() - upload_started_at) * 1000),
                    type(exc).__name__,
                )
                raise
            logger.info(
                "Generated asset upload response object_key=%s status=%s elapsed_ms=%s",
                object_key,
                response.status_code,
                int((time.monotonic() - upload_started_at) * 1000),
            )
            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Failed to upload generated asset: status={response.status_code} body={response.text[:200]}"
                )
            etag = response.headers.get("ETag")
        else:
            etag = None

        self.complete_upload(
            object_key=object_key,
            category=category,
            entity_id=entity_id,
            filename=filename,
            content_type=normalized_content_type,
            file_size=len(data),
            etag=etag,
        )
        logger.info(
            "Generated asset saved object_key=%s storage_provider=%s size=%s content_type=%s",
            object_key,
            self._settings.STORAGE_PROVIDER,
            len(data),
            normalized_content_type,
        )
        return {
            "object_key": object_key,
            "asset_url": self.build_asset_url(object_key),
            "content_type": normalized_content_type,
            "file_size": len(data),
        }

    def list_assets(
        self,
        *,
        limit: int = 20,
        category: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> list[AssetListItemData]:
        if self._repository is None:
            raise RuntimeError("Asset repository is not configured. Set DATABASE_URL to enable persistence.")
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 100:
            raise ValueError("limit must be less than or equal to 100")

        assets = self._repository.list_assets(
            limit=limit,
            category=category,
            entity_id=entity_id,
        )
        return [self._with_asset_url(asset) for asset in assets]

    def get_asset_by_object_key(self, *, object_key: str) -> AssetListItemData:
        if self._repository is None:
            raise RuntimeError("Asset repository is not configured. Set DATABASE_URL to enable persistence.")

        normalized = object_key.strip().lstrip("/")
        if not normalized:
            raise ValueError("object_key is required")

        asset = self._repository.get_asset_by_object_key(object_key=normalized)
        if asset is None:
            raise ValueError("asset not found")

        return self._with_asset_url(asset)

    def list_assets_by_object_keys(self, *, object_keys: list[str]) -> dict[str, AssetListItemData]:
        if self._repository is None:
            raise RuntimeError("Asset repository is not configured. Set DATABASE_URL to enable persistence.")

        normalized = sorted({item.strip().lstrip("/") for item in object_keys if item and item.strip()})
        if not normalized:
            return {}

        assets = self._repository.list_assets_by_object_keys(object_keys=normalized)
        return {asset.object_key: self._with_asset_url(asset) for asset in assets}

    def _with_asset_url(self, asset: AssetData) -> AssetListItemData:
        return AssetListItemData(**asset.model_dump(), asset_url=self.build_asset_url(asset.object_key))

    @staticmethod
    def _parse_category_and_entity(object_key: str) -> tuple[str, str]:
        parts = [p for p in object_key.strip("/").split("/") if p]
        if len(parts) < 3:
            raise ValueError("object_key must be in format: {category}/{entity_id}/{filename}")
        return parts[0], parts[1]
