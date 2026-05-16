from __future__ import annotations

import logging
from typing import Any

import httpx
import trafilatura

from lsl.modules.material.extractor.base import ExtractedContent, WebpageSourceInput
from lsl.modules.material.types import SourceType

logger = logging.getLogger(__name__)

_TRUNCATION_PLACEHOLDER = "\n\n[... omitted ...]\n\n"
_TRUNCATION_HEAD_SHARE = 0.9  # 90% from start, 10% from tail


class WebpageExtractor:
    source_type = SourceType.WEBPAGE

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_body_bytes: int,
        max_chars: int,
    ) -> None:
        self._timeout_seconds = float(timeout_seconds)
        self._max_body_bytes = int(max_body_bytes)
        self._max_chars = int(max_chars)

    def extract(self, payload: WebpageSourceInput) -> ExtractedContent:
        url = str(payload.url)
        html = self._fetch_html(url)
        if html is None:
            return ExtractedContent(title=None, main_text="", meta={"reason": "fetch_failed"})

        extracted_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        ) or ""

        title = self._extract_title(html)
        canonical_url = url

        truncated = False
        if len(extracted_text) > self._max_chars:
            extracted_text = self._truncate(extracted_text)
            truncated = True

        meta: dict[str, Any] = {}
        if truncated:
            meta["truncated"] = True

        return ExtractedContent(
            title=title,
            main_text=extracted_text,
            canonical_url=canonical_url,
            meta=meta,
        )

    def _fetch_html(self, url: str) -> str | None:
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self._timeout_seconds,
            ) as client:
                with client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        logger.warning(
                            "Webpage fetch returned HTTP %s for url=%s",
                            response.status_code,
                            url,
                        )
                        return None
                    content_type = response.headers.get("content-type", "")
                    if content_type and not (
                        content_type.startswith("text/html")
                        or content_type.startswith("text/plain")
                        or content_type.startswith("application/xhtml")
                    ):
                        logger.warning(
                            "Webpage fetch returned unsupported content-type=%s url=%s",
                            content_type,
                            url,
                        )
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > self._max_body_bytes:
                            logger.info(
                                "Webpage fetch truncated at %s bytes url=%s",
                                self._max_body_bytes,
                                url,
                            )
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    try:
                        return body.decode(encoding, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return body.decode("utf-8", errors="replace")
        except httpx.HTTPError as exc:
            logger.warning("Webpage fetch failed url=%s error=%s", url, exc)
            return None

    def _extract_title(self, html: str) -> str | None:
        try:
            metadata = trafilatura.extract_metadata(html)
        except Exception:  # pragma: no cover
            return None
        if metadata is None:
            return None
        title = (getattr(metadata, "title", None) or "").strip()
        return title or None

    def _truncate(self, text: str) -> str:
        budget = self._max_chars - len(_TRUNCATION_PLACEHOLDER)
        if budget <= 0:
            return text[: self._max_chars]
        head_len = int(budget * _TRUNCATION_HEAD_SHARE)
        tail_len = budget - head_len
        head = text[:head_len]
        tail = text[-tail_len:] if tail_len > 0 else ""
        return f"{head}{_TRUNCATION_PLACEHOLDER}{tail}"
