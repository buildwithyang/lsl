# Podcast from Webpage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "播客 (Podcast)" mode that turns a webpage URL into a CUE-rich dialogue script through the existing script/revision/TTS pipeline.

**Architecture:** New `material` backend module hosts a pluggable `SourceExtractor` interface; v1 ships a single `WebpageExtractor` (trafilatura). A `script_from_material` job orchestrates extracting → script generation. Frontend adds a third Mode tab `podcast` next to `audio`/`ai_script`.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic v2 / trafilatura · React / TypeScript

**Reference spec:** `docs/superpowers/specs/2026-05-15-podcast-from-webpage-design.md`

**Reference module:** `backend/src/lsl/modules/script/` — copy patterns from here (file layout, repo style, job handler shape, schema conventions).

---

## File Structure

**Backend — new files:**

```
backend/src/lsl/modules/material/
├── __init__.py                 # public re-exports
├── README.md                   # module design doc (CN)
├── api.py                      # FastAPI router (POST /materials/generate-session, GET /materials/generations/{id})
├── service.py                  # MaterialService + MaterialJobHandler
├── repo.py                     # MaterialRepository
├── schema.py                   # Pydantic request/response models
├── model.py                    # SQLAlchemy MaterialGenerationModel
├── types.py                    # SourceType / MaterialGenerationStatus enums + dataclasses
├── extractor/
│   ├── __init__.py             # factory entry point
│   ├── base.py                 # SourceExtractor Protocol + ExtractedContent + SourceExtractionInput
│   ├── factory.py              # build_extractor(source_input) -> SourceExtractor
│   └── webpage.py              # WebpageExtractor (trafilatura)

backend/tests/
├── test_webpage_extractor.py
├── test_material_repo.py
├── test_material_service.py
├── test_material_job.py
└── test_material_api.py
```

**Backend — modified files:**

- `backend/src/lsl/main.py` — wire MaterialService + MaterialJobHandler into lifespan
- `backend/src/lsl/core/config.py` — add `MATERIAL_WEBPAGE_TIMEOUT_SECONDS`, `MATERIAL_WEBPAGE_MAX_BODY_BYTES`, `MATERIAL_EXTRACTED_TEXT_MAX_CHARS`
- `backend/src/lsl/modules/script/model.py` — add nullable `material_generation_id` column
- `backend/src/lsl/modules/script/repo.py` — accept/persist/return `material_generation_id`
- `backend/src/lsl/modules/script/service.py` — add `start_generation_from_material(...)` method
- `backend/src/lsl/modules/script/schema.py` — add `material_generation_id: str | None = None` to `ScriptGenerationData`

**Frontend — new files:**

- `frontend/src/lib/api/materials.ts` — API client
- `frontend/src/components/create-session/PodcastSessionForm.tsx` — form component (copy AiScriptSessionForm)

**Frontend — modified files:**

- `frontend/src/pages/CreateSession.tsx` — add `podcast` mode + tab
- `frontend/src/i18n/en.ts` and `frontend/src/i18n/zh-CN.ts` — add podcast labels
- `frontend/src/types/api.ts` — add Material types

**Docs:**

- `README.md` — add `trafilatura` to `uv pip install` line + module list
- `README.zh-CN.md` — same update in Chinese version
- `app.env.example` (if present in `backend/`) — add new MATERIAL_* env vars

---

## Important Conventions From the Existing Codebase

Skim before writing code:

- IDs are hex UUID strings (`uuid.uuid4().hex`); columns use `UUIDHexString()` from `lsl.core.sql_types`
- JSON columns use `JSONString()` from `lsl.core.sql_types` (DB-agnostic)
- SQLAlchemy column names sometimes prefix with `x_` to dodge reserved words (e.g. `x_status`, `x_provider`)
- All schemas compatible with both SQLite and PostgreSQL — no PostgreSQL-only defaults
- DB tables are created via `Base.metadata.create_all(engine)` in `backend/src/lsl/core/db.py:79`; **no migration files needed**
- Repository methods raise `RuntimeError` for not-found internal errors; services raise `ValueError` for user-facing 404s
- `Settings` is `dataclass(frozen=True)` with `_get_env_int/_get_env_float/_get_env_str/_get_env_bool` helpers in `backend/src/lsl/core/config.py`
- Verify backend imports after edits: `env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"`
- Run tests: `env PYTHONPATH=backend/src uv run pytest backend/tests`
- Run single test: `env PYTHONPATH=backend/src uv run pytest backend/tests/test_xxx.py -v`
- The frontend `AiScriptSessionForm.tsx` already passes `uiLanguage` as `cueLanguage` (line 87 in current code); the "uniform default" is therefore already done for ai_script. Podcast form just needs to do the same.

---

## Task 1: Add `trafilatura` dependency

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Install the package into the active venv**

Run:
```bash
uv pip install trafilatura
```
Expected: package installs successfully.

- [ ] **Step 2: Verify the import works**

Run:
```bash
env PYTHONPATH=backend/src uv run python -c "import trafilatura; print(trafilatura.__version__)"
```
Expected: prints a version number, no error.

- [ ] **Step 3: Update `README.md` to mention the new dependency**

Find the `uv pip install` line in `README.md` (around line 131):

```bash
uv pip install fastapi uvicorn pydantic sqlalchemy python-dotenv requests httpx openai json-repair redis alibabacloud-oss-v2
```

Append `trafilatura`:

```bash
uv pip install fastapi uvicorn pydantic sqlalchemy python-dotenv requests httpx openai json-repair redis alibabacloud-oss-v2 trafilatura
```

Add a bullet under the "Notes:" list:

```markdown
- `trafilatura` is used to extract main text from arbitrary HTML pages for the podcast feature.
```

- [ ] **Step 4: Mirror the same change in `README.zh-CN.md`**

Update the `uv pip install` line and add the equivalent Chinese note.

- [ ] **Step 5: Commit**

```bash
git add README.md README.zh-CN.md
git commit -m "$(cat <<'EOF'
chore: add trafilatura dependency for podcast feature

Trafilatura extracts main text from arbitrary HTML pages; required by the
upcoming `material.extractor.webpage` module.
EOF
)"
```

---

## Task 2: Create empty `material` module skeleton

**Files:**
- Create: `backend/src/lsl/modules/material/__init__.py`
- Create: `backend/src/lsl/modules/material/types.py`
- Create: `backend/src/lsl/modules/material/extractor/__init__.py`

- [ ] **Step 1: Create `types.py` with enums and dataclasses**

```python
# backend/src/lsl/modules/material/types.py
from __future__ import annotations

from enum import IntEnum, Enum


class SourceType(str, Enum):
    WEBPAGE = "webpage"


class MaterialGenerationStatus(IntEnum):
    PENDING = 0
    EXTRACTING = 1
    EXTRACTED = 2
    COMPLETED = 3
    FAILED = 4


def material_generation_status_to_name(status: int) -> str:
    mapping = {
        int(MaterialGenerationStatus.PENDING): "pending",
        int(MaterialGenerationStatus.EXTRACTING): "extracting",
        int(MaterialGenerationStatus.EXTRACTED): "extracted",
        int(MaterialGenerationStatus.COMPLETED): "completed",
        int(MaterialGenerationStatus.FAILED): "failed",
    }
    return mapping.get(int(status), "pending")
```

- [ ] **Step 2: Create the placeholder `__init__.py` files**

```python
# backend/src/lsl/modules/material/__init__.py
# Public exports are added at the end of the implementation; left empty for now.
```

```python
# backend/src/lsl/modules/material/extractor/__init__.py
```

- [ ] **Step 3: Verify imports still work**

```bash
env PYTHONPATH=backend/src uv run python -c "from lsl.modules.material.types import MaterialGenerationStatus; print(MaterialGenerationStatus.PENDING)"
```
Expected: prints `MaterialGenerationStatus.PENDING`.

- [ ] **Step 4: Commit**

```bash
git add backend/src/lsl/modules/material
git commit -m "feat(material): scaffold module + status/source type enums"
```

---

## Task 3: Define extractor interface

**Files:**
- Create: `backend/src/lsl/modules/material/extractor/base.py`

- [ ] **Step 1: Write `base.py` with the dataclass + Protocol**

```python
# backend/src/lsl/modules/material/extractor/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, Union

from pydantic import BaseModel, Field, HttpUrl

from lsl.modules.material.types import SourceType


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    title: str | None
    main_text: str
    canonical_url: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class WebpageSourceInput(BaseModel):
    type: Literal["webpage"]
    url: HttpUrl


SourceInput = Annotated[Union[WebpageSourceInput], Field(discriminator="type")]


class SourceExtractor(Protocol):
    source_type: SourceType

    def extract(self, payload: SourceInput) -> ExtractedContent: ...
```

- [ ] **Step 2: Verify import**

```bash
env PYTHONPATH=backend/src uv run python -c "from lsl.modules.material.extractor.base import ExtractedContent, WebpageSourceInput; print(ExtractedContent(title='t', main_text='x'))"
```
Expected: prints `ExtractedContent(title='t', main_text='x', canonical_url=None, meta={})`

- [ ] **Step 3: Commit**

```bash
git add backend/src/lsl/modules/material/extractor/base.py
git commit -m "feat(material): define SourceExtractor protocol and ExtractedContent"
```

---

## Task 4: Implement `WebpageExtractor` with TDD

**Files:**
- Test: `backend/tests/test_webpage_extractor.py`
- Create: `backend/src/lsl/modules/material/extractor/webpage.py`

- [ ] **Step 1: Write the first failing test — basic extraction from HTML string**

```python
# backend/tests/test_webpage_extractor.py
from __future__ import annotations

from unittest.mock import patch

import pytest

from lsl.modules.material.extractor.base import WebpageSourceInput
from lsl.modules.material.extractor.webpage import WebpageExtractor


SAMPLE_BLOG_HTML = """
<!DOCTYPE html>
<html>
<head><title>The Cat Care Guide</title></head>
<body>
  <nav>Home | About</nav>
  <article>
    <h1>The Cat Care Guide</h1>
    <p>Cats are independent animals that still need daily care.</p>
    <p>Provide fresh water, balanced food, and a clean litter box.</p>
    <p>Take your cat to the vet at least once a year for a checkup.</p>
  </article>
  <footer>Copyright 2026</footer>
</body>
</html>
"""


def _build_extractor(**overrides):
    defaults = dict(timeout_seconds=15.0, max_body_bytes=5_000_000, max_chars=50_000)
    defaults.update(overrides)
    return WebpageExtractor(**defaults)


def test_extract_pulls_main_text_from_static_html():
    extractor = _build_extractor()
    with patch.object(WebpageExtractor, "_fetch_html", return_value=SAMPLE_BLOG_HTML):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/cats"))
    assert "Cats are independent animals" in result.main_text
    assert "Copyright 2026" not in result.main_text
```

- [ ] **Step 2: Run the test — confirm it fails because the module/class doesn't exist**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement the minimal `WebpageExtractor`**

```python
# backend/src/lsl/modules/material/extractor/webpage.py
from __future__ import annotations

import logging
from typing import Any

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
        return trafilatura.fetch_url(url)

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
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: PASS.

- [ ] **Step 5: Add title-extraction test**

Append to `test_webpage_extractor.py`:

```python
def test_extract_recovers_page_title():
    extractor = _build_extractor()
    with patch.object(WebpageExtractor, "_fetch_html", return_value=SAMPLE_BLOG_HTML):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/cats"))
    assert result.title == "The Cat Care Guide"
```

- [ ] **Step 6: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: 2 passing.

- [ ] **Step 7: Add fetch-failure test**

Append:

```python
def test_extract_returns_empty_content_when_fetch_fails():
    extractor = _build_extractor()
    with patch.object(WebpageExtractor, "_fetch_html", return_value=None):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/missing"))
    assert result.main_text == ""
    assert result.meta.get("reason") == "fetch_failed"
```

- [ ] **Step 8: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: 3 passing.

- [ ] **Step 9: Add truncation test**

Append:

```python
def test_extract_truncates_long_content():
    long_html = "<html><body><article>" + ("Sentence about cats. " * 5000) + "</article></body></html>"
    extractor = _build_extractor(max_chars=1000)
    with patch.object(WebpageExtractor, "_fetch_html", return_value=long_html):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/long"))
    assert len(result.main_text) <= 1000
    assert result.meta.get("truncated") is True
    assert "[... omitted ...]" in result.main_text
```

- [ ] **Step 10: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: 4 passing.

- [ ] **Step 11: Commit**

```bash
git add backend/src/lsl/modules/material/extractor/webpage.py backend/tests/test_webpage_extractor.py
git commit -m "feat(material): implement WebpageExtractor with title extraction and truncation"
```

---

## Task 5: Extractor factory

**Files:**
- Modify: `backend/src/lsl/modules/material/extractor/__init__.py` (add factory)
- Create: `backend/src/lsl/modules/material/extractor/factory.py`
- Test: append to `backend/tests/test_webpage_extractor.py`

- [ ] **Step 1: Write failing tests for the factory**

Append to `test_webpage_extractor.py`:

```python
from lsl.core.config import Settings
from lsl.modules.material.extractor.factory import build_extractor


def _settings_with_material_defaults():
    return Settings(
        MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15.0,
        MATERIAL_WEBPAGE_MAX_BODY_BYTES=5_000_000,
        MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50_000,
    )


def test_factory_returns_webpage_extractor_for_webpage_input():
    extractor = build_extractor(
        WebpageSourceInput(type="webpage", url="https://example.com"),
        settings=_settings_with_material_defaults(),
    )
    assert isinstance(extractor, WebpageExtractor)


def test_factory_raises_for_unknown_type():
    class FakeInput:
        type = "pdf"

    with pytest.raises(ValueError):
        build_extractor(FakeInput(), settings=_settings_with_material_defaults())
```

- [ ] **Step 2: Run, confirm failure**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: 2 new tests fail (`ImportError` or `AttributeError`).

- [ ] **Step 3: Add the `MATERIAL_*` settings (minimum required to make tests pass)**

Open `backend/src/lsl/core/config.py`. Find the existing `SCRIPT_LLM_HTTP_TIMEOUT` field in the `Settings` dataclass and add new fields right after it (before the next section):

```python
    # Material / Webpage extractor
    # 单次抓取 HTTP 超时，秒。
    MATERIAL_WEBPAGE_TIMEOUT_SECONDS: float = 15.0
    # 响应 Body 最大字节数，超过则截断。
    MATERIAL_WEBPAGE_MAX_BODY_BYTES: int = 5 * 1024 * 1024
    # 抽取出的正文最大字符数，超过则按 head+tail 截断。
    MATERIAL_EXTRACTED_TEXT_MAX_CHARS: int = 50_000
```

Find the `from_env` classmethod and add the env reads near other `_get_env_*` calls:

```python
            MATERIAL_WEBPAGE_TIMEOUT_SECONDS=_get_env_float("MATERIAL_WEBPAGE_TIMEOUT_SECONDS", cls.MATERIAL_WEBPAGE_TIMEOUT_SECONDS),
            MATERIAL_WEBPAGE_MAX_BODY_BYTES=_get_env_int("MATERIAL_WEBPAGE_MAX_BODY_BYTES", cls.MATERIAL_WEBPAGE_MAX_BODY_BYTES),
            MATERIAL_EXTRACTED_TEXT_MAX_CHARS=_get_env_int("MATERIAL_EXTRACTED_TEXT_MAX_CHARS", cls.MATERIAL_EXTRACTED_TEXT_MAX_CHARS),
```

- [ ] **Step 4: Implement the factory**

```python
# backend/src/lsl/modules/material/extractor/factory.py
from __future__ import annotations

from lsl.core.config import Settings
from lsl.modules.material.extractor.base import SourceExtractor, WebpageSourceInput
from lsl.modules.material.extractor.webpage import WebpageExtractor


def build_extractor(payload, *, settings: Settings) -> SourceExtractor:
    if isinstance(payload, WebpageSourceInput) or getattr(payload, "type", None) == "webpage":
        return WebpageExtractor(
            timeout_seconds=settings.MATERIAL_WEBPAGE_TIMEOUT_SECONDS,
            max_body_bytes=settings.MATERIAL_WEBPAGE_MAX_BODY_BYTES,
            max_chars=settings.MATERIAL_EXTRACTED_TEXT_MAX_CHARS,
        )
    raise ValueError(f"Unsupported source type: {getattr(payload, 'type', payload)!r}")
```

- [ ] **Step 5: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_webpage_extractor.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Verify backend imports**

```bash
env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"
```
Expected: prints `main import ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/lsl/modules/material/extractor/factory.py backend/src/lsl/core/config.py backend/tests/test_webpage_extractor.py
git commit -m "feat(material): add extractor factory and MATERIAL_* settings"
```

---

## Task 6: Database model

**Files:**
- Create: `backend/src/lsl/modules/material/model.py`
- Modify: `backend/src/lsl/modules/script/model.py`

- [ ] **Step 1: Write the `MaterialGenerationModel`**

```python
# backend/src/lsl/modules/material/model.py
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
```

- [ ] **Step 2: Add `material_generation_id` column to `ScriptGenerationModel`**

Open `backend/src/lsl/modules/script/model.py`. In the `ScriptGenerationModel` class, add a new column right after the `job_id` field (around line 23):

```python
    material_generation_id: Mapped[str | None] = mapped_column(UUIDHexString(), nullable=True)
```

- [ ] **Step 3: Verify imports**

```bash
env PYTHONPATH=backend/src uv run python -c "from lsl.modules.material.model import MaterialGenerationModel; print(MaterialGenerationModel.__tablename__)"
```
Expected: prints `material_generations`.

- [ ] **Step 4: Confirm DB schema creation works in-memory**

```bash
env PYTHONPATH=backend/src uv run python -c "
from sqlalchemy import create_engine
from lsl.core.db import Base
import lsl.modules.material.model
import lsl.modules.script.model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
print('schema created ok')
"
```
Expected: prints `schema created ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/lsl/modules/material/model.py backend/src/lsl/modules/script/model.py
git commit -m "feat(material): add MaterialGenerationModel and script_generation.material_generation_id"
```

---

## Task 7: Material repository with TDD

**Files:**
- Test: `backend/tests/test_material_repo.py`
- Create: `backend/src/lsl/modules/material/repo.py`

- [ ] **Step 1: Write the first failing test — create_generation + get_by_id round-trip**

```python
# backend/tests/test_material_repo.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.db import Base
import lsl.modules.material.model  # noqa: F401 - register table
import lsl.modules.script.model  # noqa: F401 - register table
from lsl.modules.material.repo import MaterialRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)


def test_create_and_get_generation(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    row = repo.create_generation(
        generation_id=gen_id,
        session_id=session_id,
        source_type="webpage",
        source_payload={"url": "https://example.com"},
    )
    assert row["generation_id"] == gen_id
    assert row["status_name"] == "pending"
    assert row["source_payload"] == {"url": "https://example.com"}

    fetched = repo.get_by_id(gen_id)
    assert fetched is not None
    assert fetched["session_id"] == session_id
```

- [ ] **Step 2: Run, confirm failure**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_repo.py -v
```
Expected: FAIL with `ImportError: cannot import name 'MaterialRepository'`.

- [ ] **Step 3: Implement `MaterialRepository`**

```python
# backend/src/lsl/modules/material/repo.py
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.modules.material.model import MaterialGenerationModel
from lsl.modules.material.types import MaterialGenerationStatus, material_generation_status_to_name


class MaterialRepository:
    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[OrmSession]:
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    def create_generation(
        self,
        *,
        generation_id: str,
        session_id: str,
        source_type: str,
        source_payload: dict[str, Any],
    ) -> dict[str, Any]:
        model = MaterialGenerationModel(
            generation_id=self._require_uuid(generation_id, "generation_id"),
            session_id=self._require_uuid(session_id, "session_id"),
            source_type=source_type,
            source_payload_json=dict(source_payload),
            status=int(MaterialGenerationStatus.PENDING),
        )
        try:
            with self._session_scope() as db:
                db.add(model)
                db.commit()
                db.refresh(model)
                return self._to_row(model)
        except SQLAlchemyError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to create material generation: {exc}") from exc

    def set_job_id(self, *, generation_id: str, job_id: str) -> None:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.job_id = self._require_uuid(job_id, "job_id")
            db.commit()

    def get_by_id(self, generation_id: str) -> dict[str, Any] | None:
        normalized = self._parse_uuid(generation_id)
        if normalized is None:
            return None
        stmt = select(MaterialGenerationModel).where(MaterialGenerationModel.generation_id == normalized).limit(1)
        with self._session_scope() as db:
            model = db.execute(stmt).scalar_one_or_none()
            return self._to_row(model) if model is not None else None

    def mark_extracting(self, *, generation_id: str) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.EXTRACTING)
            model.error_code = None
            model.error_message = None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def mark_extracted(
        self,
        *,
        generation_id: str,
        title: str | None,
        text: str,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.EXTRACTED)
            model.extracted_title = title
            model.extracted_text = text
            model.extracted_meta_json = dict(meta) if meta else None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def set_script_generation_id(self, *, generation_id: str, script_generation_id: str) -> None:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.script_generation_id = self._require_uuid(script_generation_id, "script_generation_id")
            db.commit()

    def mark_completed(self, *, generation_id: str) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.COMPLETED)
            model.error_code = None
            model.error_message = None
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def mark_failed(
        self,
        *,
        generation_id: str,
        error_code: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        with self._session_scope() as db:
            model = self._get_required(db, generation_id)
            model.status = int(MaterialGenerationStatus.FAILED)
            model.error_code = error_code
            model.error_message = error_message
            db.commit()
            db.refresh(model)
            return self._to_row(model)

    def _get_required(self, db: OrmSession, generation_id: str) -> MaterialGenerationModel:
        normalized = self._require_uuid(generation_id, "generation_id")
        model = db.get(MaterialGenerationModel, normalized)
        if model is None:
            raise RuntimeError("Material generation not found")
        return model

    @staticmethod
    def _parse_uuid(value: str) -> str | None:
        try:
            return uuid.UUID(value).hex
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_uuid(value: str, field_name: str) -> str:
        parsed = MaterialRepository._parse_uuid(value)
        if parsed is None:
            raise RuntimeError(f"Invalid {field_name}")
        return parsed

    @staticmethod
    def _to_row(model: MaterialGenerationModel) -> dict[str, Any]:
        status = int(model.status)
        return {
            "generation_id": model.generation_id,
            "session_id": model.session_id,
            "source_type": model.source_type,
            "source_payload": dict(model.source_payload_json or {}),
            "extracted_title": model.extracted_title,
            "extracted_text": model.extracted_text,
            "extracted_meta": dict(model.extracted_meta_json or {}),
            "script_generation_id": model.script_generation_id,
            "job_id": model.job_id,
            "status": status,
            "status_name": material_generation_status_to_name(status),
            "error_code": model.error_code,
            "error_message": model.error_message,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
```

- [ ] **Step 4: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_repo.py -v
```
Expected: PASS.

- [ ] **Step 5: Add status-transition tests**

Append to `test_material_repo.py`:

```python
def _seed_generation(repo: MaterialRepository) -> str:
    gen_id = uuid.uuid4().hex
    repo.create_generation(
        generation_id=gen_id,
        session_id=uuid.uuid4().hex,
        source_type="webpage",
        source_payload={"url": "https://example.com"},
    )
    return gen_id


def test_mark_extracting_then_extracted_then_completed(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)

    repo.mark_extracting(generation_id=gen_id)
    assert repo.get_by_id(gen_id)["status_name"] == "extracting"

    repo.mark_extracted(generation_id=gen_id, title="Cats", text="Hello cats", meta={"truncated": False})
    row = repo.get_by_id(gen_id)
    assert row["status_name"] == "extracted"
    assert row["extracted_title"] == "Cats"
    assert row["extracted_text"] == "Hello cats"

    repo.mark_completed(generation_id=gen_id)
    assert repo.get_by_id(gen_id)["status_name"] == "completed"


def test_mark_failed_records_error_code_and_message(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)
    repo.mark_failed(generation_id=gen_id, error_code="FETCH_TIMEOUT", error_message="timeout 15s")
    row = repo.get_by_id(gen_id)
    assert row["status_name"] == "failed"
    assert row["error_code"] == "FETCH_TIMEOUT"
    assert row["error_message"] == "timeout 15s"


def test_set_script_generation_id_persists(session_factory):
    repo = MaterialRepository(session_factory)
    gen_id = _seed_generation(repo)
    script_gen_id = uuid.uuid4().hex
    repo.set_script_generation_id(generation_id=gen_id, script_generation_id=script_gen_id)
    assert repo.get_by_id(gen_id)["script_generation_id"] == script_gen_id


def test_get_by_id_returns_none_for_invalid_uuid(session_factory):
    repo = MaterialRepository(session_factory)
    assert repo.get_by_id("not-a-uuid") is None
```

- [ ] **Step 6: Run, confirm all pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_repo.py -v
```
Expected: 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/lsl/modules/material/repo.py backend/tests/test_material_repo.py
git commit -m "feat(material): add MaterialRepository with status transitions"
```

---

## Task 8: Pydantic request/response schemas

**Files:**
- Create: `backend/src/lsl/modules/material/schema.py`

- [ ] **Step 1: Write `schema.py`**

```python
# backend/src/lsl/modules/material/schema.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from lsl.modules.job.types import JobData
from lsl.modules.material.extractor.base import SourceInput, WebpageSourceInput
from lsl.modules.session.schema import SessionData


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "successful"
    data: T


# Re-export so callers that import from schema.py still work.
__all__ = [
    "ApiResponse",
    "GenerateMaterialSessionData",
    "GenerateMaterialSessionRequest",
    "MaterialGenerationData",
    "SourceInput",
    "WebpageSourceInput",
]


class GenerateMaterialSessionRequest(BaseModel):
    source: SourceInput
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    target_language: str = Field(..., max_length=16)
    cue_language: str | None = Field(default=None, max_length=16)
    prompt: str | None = Field(default=None, max_length=4000)
    turn_count: int = Field(default=8, ge=2, le=24)
    speaker_count: int = Field(default=2, ge=2, le=4)
    difficulty: str | None = Field(default="intermediate", max_length=32)
    cue_style: str | None = Field(default="自然口语、便于 TTS 演绎", max_length=200)
    must_include: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("title", "description", "cue_language", "prompt", "difficulty", "cue_style")
    @classmethod
    def normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("target_language")
    @classmethod
    def normalize_target_language(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_language is required")
        return normalized

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class MaterialGenerationData(BaseModel):
    generation_id: str
    session_id: str
    source_type: str
    source_payload: dict[str, Any]
    extracted_title: str | None = None
    extracted_text: str | None = None
    extracted_meta: dict[str, Any] = Field(default_factory=dict)
    script_generation_id: str | None = None
    job_id: str | None = None
    status: int
    status_name: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "MaterialGenerationData":
        return cls(**row)


class GenerateMaterialSessionData(BaseModel):
    session: SessionData
    material_generation: MaterialGenerationData
    job: JobData
```

- [ ] **Step 2: Verify import**

```bash
env PYTHONPATH=backend/src uv run python -c "from lsl.modules.material.schema import GenerateMaterialSessionRequest, WebpageSourceInput; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Smoke-test schema validation manually**

```bash
env PYTHONPATH=backend/src uv run python -c "
from lsl.modules.material.schema import GenerateMaterialSessionRequest
req = GenerateMaterialSessionRequest.model_validate({
  'source': {'type': 'webpage', 'url': 'https://example.com/cats'},
  'target_language': 'en-US',
})
print(req.source.url, req.target_language, req.turn_count)
"
```
Expected: prints URL, language, turn count.

- [ ] **Step 4: Commit**

```bash
git add backend/src/lsl/modules/material/schema.py
git commit -m "feat(material): add Pydantic request/response schemas"
```

---

## Task 9: Extend `ScriptService` with `start_generation_from_material`

**Files:**
- Modify: `backend/src/lsl/modules/script/repo.py`
- Modify: `backend/src/lsl/modules/script/service.py`
- Modify: `backend/src/lsl/modules/script/schema.py`

This task adds a new method that lets `material.service` kick off script generation from extracted webpage content, *without* creating a new HTTP route on the script module.

- [ ] **Step 1: Extend `ScriptRepository.create_generation` to accept `material_generation_id`**

In `backend/src/lsl/modules/script/repo.py`, modify the `create_generation` method signature to accept an optional `material_generation_id` parameter. Add it to the kwargs and pass it to the model:

```python
    def create_generation(
        self,
        *,
        generation_id: str,
        session_id: str,
        provider: str,
        title: str,
        description: str | None,
        target_language: str | None,
        cue_language: str | None,
        prompt: str,
        turn_count: int,
        speaker_count: int,
        difficulty: str | None,
        cue_style: str | None,
        must_include: list[str],
        material_generation_id: str | None = None,
    ) -> dict[str, Any]:
        model = ScriptGenerationModel(
            generation_id=self._require_uuid(generation_id, field_name="generation_id"),
            session_id=self._require_uuid(session_id, field_name="session_id"),
            provider=provider,
            title=title,
            description=description,
            target_language=target_language,
            cue_language=cue_language,
            prompt=prompt,
            turn_count=int(turn_count),
            speaker_count=int(speaker_count),
            difficulty=difficulty,
            cue_style=cue_style,
            must_include_json=list(must_include),
            material_generation_id=(
                self._require_uuid(material_generation_id, field_name="material_generation_id")
                if material_generation_id
                else None
            ),
            status=int(ScriptGenerationStatus.PENDING),
        )
```

Also update `_to_row` (around line 207) to include the new field:

```python
            "material_generation_id": model.material_generation_id,
```

- [ ] **Step 2: Update `ScriptGenerationData` to expose `material_generation_id`**

In `backend/src/lsl/modules/script/schema.py`, add a new field to `ScriptGenerationData` (around line 93):

```python
    material_generation_id: str | None = None
```

- [ ] **Step 3: Add `start_generation_from_material` to `ScriptService`**

In `backend/src/lsl/modules/script/service.py`, add a new public method on the `ScriptService` class (after `generate_session`):

```python
    def start_generation_from_material(
        self,
        *,
        session_id: str,
        material_generation_id: str,
        title: str,
        description: str | None,
        target_language: str | None,
        cue_language: str | None,
        prompt: str,
        turn_count: int,
        speaker_count: int,
        difficulty: str | None,
        cue_style: str | None,
        must_include: list[str],
    ) -> tuple[ScriptGenerationData, JobData]:
        generation_id = uuid.uuid4().hex
        self._repository.create_generation(
            generation_id=generation_id,
            session_id=session_id,
            provider=self._generator.provider_name,
            title=title,
            description=description,
            target_language=target_language,
            cue_language=cue_language,
            prompt=prompt,
            turn_count=turn_count,
            speaker_count=speaker_count,
            difficulty=difficulty,
            cue_style=cue_style,
            must_include=must_include,
            material_generation_id=material_generation_id,
        )
        job = self._job_service.create_job(
            job_type=ScriptJobHandler.job_type,
            entity_type="script_generation",
            entity_id=generation_id,
            payload={"generation_id": generation_id},
        )
        self._repository.set_job_id(generation_id=generation_id, job_id=job.job_id)
        logger.info(
            "Script generation started from material material_generation_id=%s generation_id=%s session_id=%s job_id=%s",
            material_generation_id,
            generation_id,
            session_id,
            job.job_id,
        )
        return self.get_generation(generation_id=generation_id), job
```

Add `from lsl.modules.job.types import JobData` to the imports at the top of the file. (Check existing imports; some may already exist.)

- [ ] **Step 4: Verify backend imports**

```bash
env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"
```
Expected: prints `main import ok`.

- [ ] **Step 5: Run existing script tests to confirm no regression**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_script_job.py -v
```
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/lsl/modules/script/
git commit -m "feat(script): add start_generation_from_material hook for podcast flow"
```

---

## Task 10: `MaterialService.create_from_url` with TDD

**Files:**
- Test: `backend/tests/test_material_service.py`
- Create: `backend/src/lsl/modules/material/service.py`

- [ ] **Step 1: Write the failing test — service creates session + generation + job**

```python
# backend/tests/test_material_service.py
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.config import Settings
from lsl.core.db import Base
import lsl.modules.material.model  # noqa: F401
import lsl.modules.script.model  # noqa: F401
from lsl.modules.asset.providers import FakeStorageProvider
from lsl.modules.asset.service import AssetService
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.material.extractor.base import ExtractedContent, WebpageSourceInput
from lsl.modules.material.extractor.webpage import WebpageExtractor
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.schema import GenerateMaterialSessionRequest
from lsl.modules.material.service import MaterialJobHandler, MaterialService
from lsl.modules.revision.repo import RevisionRepository
from lsl.modules.revision.service import RevisionService
from lsl.modules.revision.types import RevisionGenerateRequest, RevisionSuggestion
from lsl.modules.script.repo import ScriptRepository
from lsl.modules.script.service import ScriptJobHandler, ScriptService
from lsl.modules.script.types import GeneratedScript, GeneratedScriptTurn, ScriptGenerateRequest
from lsl.modules.session.repo import SessionRepository
from lsl.modules.session.service import SessionService
from lsl.modules.transcript.repo import TranscriptRepository
from lsl.modules.transcript.service import TranscriptService


class StubExtractor:
    def __init__(self, *, result: ExtractedContent | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls: list = []

    def extract(self, payload):
        self.calls.append(payload)
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeScriptGenerator:
    provider_name = "fake-script"

    def generate(self, req: ScriptGenerateRequest) -> GeneratedScript:
        return GeneratedScript(
            utterances=[
                GeneratedScriptTurn(speaker="user-1", cue="calm", text="Hello cats."),
                GeneratedScriptTurn(speaker="user-2", cue="warm", text="Yes, lovely creatures."),
            ]
        )

    def generate_progressively(self, req: ScriptGenerateRequest) -> Iterator[GeneratedScriptTurn]:
        yield from self.generate(req).utterances


class NoopRevisionGenerator:
    provider_name = "noop"

    def generate(self, req: RevisionGenerateRequest) -> list[RevisionSuggestion]:
        return []

    def generate_progressively(self, req):
        return iter(())


@pytest.fixture()
def services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)
    settings = Settings(STORAGE_PROVIDER="fake", ASSET_BASE_URL="http://assets.test")
    asset_service = AssetService(settings=settings, storage=FakeStorageProvider(), repository=None)
    job_service = JobService(repository=JobRepository(factory), lock_ttl_seconds=30)
    transcript_service = TranscriptService(repository=TranscriptRepository(factory))
    session_service = SessionService(
        repository=SessionRepository(factory),
        asset_service=asset_service,
        transcript_service=transcript_service,
    )
    revision_service = RevisionService(
        repository=RevisionRepository(factory),
        generator=NoopRevisionGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
    )
    script_service = ScriptService(
        repository=ScriptRepository(factory),
        generator=FakeScriptGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
        revision_service=revision_service,
        job_service=job_service,
    )
    job_service.register_handler(ScriptJobHandler(script_service=script_service))

    extractor = StubExtractor(
        result=ExtractedContent(title="The Cat Care Guide", main_text="Cats need daily care.", canonical_url="https://example.com/cats")
    )
    material_service = MaterialService(
        repository=MaterialRepository(factory),
        session_service=session_service,
        script_service=script_service,
        job_service=job_service,
        extractor_factory=lambda payload: extractor,
    )
    job_service.register_handler(MaterialJobHandler(material_service=material_service))
    return material_service, job_service, extractor


def test_create_from_url_creates_session_generation_and_job(services):
    material_service, _job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
            "cue_language": "zh-CN",
            "title": "Cat care",
        }
    )
    data = material_service.create_from_url(req)
    assert data.session.session.session_id
    assert data.material_generation.status_name == "pending"
    assert data.material_generation.source_payload == {"url": "https://example.com/cats"}
    assert data.job.job_id
```

- [ ] **Step 2: Run, confirm fail**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_service.py::test_create_from_url_creates_session_generation_and_job -v
```
Expected: `ImportError: cannot import name 'MaterialService'`.

- [ ] **Step 3: Implement `MaterialService.create_from_url` (and the `MaterialJobHandler` stub)**

```python
# backend/src/lsl/modules/material/service.py
from __future__ import annotations

import logging
import uuid
from typing import Callable

from lsl.modules.job.service import JobService
from lsl.modules.job.types import JobData, JobRunResult, JobStatus
from lsl.modules.material.extractor.base import ExtractedContent, SourceInput, WebpageSourceInput
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.schema import (
    GenerateMaterialSessionData,
    GenerateMaterialSessionRequest,
    MaterialGenerationData,
)
from lsl.modules.script.service import ScriptService
from lsl.modules.session.schema import CreateSessionRequest, UpdateSessionRequest
from lsl.modules.session.service import SessionService

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "Podcast from webpage"
_MIN_EXTRACTED_TEXT_CHARS = 200


class MaterialService:
    def __init__(
        self,
        *,
        repository: MaterialRepository,
        session_service: SessionService,
        script_service: ScriptService,
        job_service: JobService,
        extractor_factory: Callable[[SourceInput], object],
    ) -> None:
        self._repository = repository
        self._session_service = session_service
        self._script_service = script_service
        self._job_service = job_service
        self._extractor_factory = extractor_factory

    def create_from_url(self, payload: GenerateMaterialSessionRequest) -> GenerateMaterialSessionData:
        session = self._session_service.create_session(
            CreateSessionRequest(
                title=payload.title or _DEFAULT_TITLE,
                description=payload.description,
                target_language=payload.target_language,
                f_type=2,
            )
        )
        generation_id = uuid.uuid4().hex
        self._repository.create_generation(
            generation_id=generation_id,
            session_id=session.session.session_id,
            source_type=payload.source.type,
            source_payload=self._source_to_payload(payload.source),
        )
        job = self._job_service.create_job(
            job_type=MaterialJobHandler.job_type,
            entity_type="material_generation",
            entity_id=generation_id,
            payload={
                "generation_id": generation_id,
                "request": self._serialize_request(payload),
            },
        )
        self._repository.set_job_id(generation_id=generation_id, job_id=job.job_id)
        logger.info(
            "Material generation session created generation_id=%s session_id=%s job_id=%s source_type=%s",
            generation_id,
            session.session.session_id,
            job.job_id,
            payload.source.type,
        )
        generation = MaterialGenerationData.from_row(self._repository.get_by_id(generation_id))
        session = self._session_service.get_session(session.session.session_id, auto_refresh=False)
        return GenerateMaterialSessionData(
            session=session,
            material_generation=generation,
            job=job,
        )

    def get_generation(self, *, generation_id: str) -> MaterialGenerationData:
        row = self._repository.get_by_id(generation_id)
        if row is None:
            raise ValueError("material generation not found")
        return MaterialGenerationData.from_row(row)

    @staticmethod
    def _source_to_payload(source: SourceInput) -> dict[str, str]:
        if isinstance(source, WebpageSourceInput) or getattr(source, "type", None) == "webpage":
            return {"url": str(source.url)}
        raise ValueError(f"Unsupported source type: {getattr(source, 'type', None)!r}")

    @staticmethod
    def _serialize_request(payload: GenerateMaterialSessionRequest) -> dict:
        return {
            "title": payload.title,
            "description": payload.description,
            "target_language": payload.target_language,
            "cue_language": payload.cue_language,
            "prompt": payload.prompt,
            "turn_count": payload.turn_count,
            "speaker_count": payload.speaker_count,
            "difficulty": payload.difficulty,
            "cue_style": payload.cue_style,
            "must_include": list(payload.must_include),
        }


class MaterialJobHandler:
    job_type = "script_from_material"

    def __init__(self, *, material_service: MaterialService) -> None:
        self._material_service = material_service

    def run(self, job: JobData) -> JobRunResult:
        generation_id = str(job.payload.get("generation_id") or job.entity_id or "").strip()
        if not generation_id:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MISSING_GENERATION_ID",
                error_message="generation_id is required",
            )
        request_payload = job.payload.get("request") or {}
        return self._material_service.run_material_job(
            generation_id=generation_id,
            request_payload=dict(request_payload),
        )
```

(`run_material_job` is implemented in Task 11. For now, add a placeholder method that raises so the import works.)

Append to `service.py` (temporarily — will be replaced in Task 11):

```python
    def run_material_job(self, *, generation_id: str, request_payload: dict) -> JobRunResult:
        raise NotImplementedError("run_material_job is implemented in Task 11")
```

- [ ] **Step 4: Run the test, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_service.py::test_create_from_url_creates_session_generation_and_job -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/lsl/modules/material/service.py backend/tests/test_material_service.py
git commit -m "feat(material): add MaterialService.create_from_url"
```

---

## Task 11: Implement `run_material_job` — extracting + chain to script (TDD)

**Files:**
- Modify: `backend/src/lsl/modules/material/service.py`
- Modify: `backend/tests/test_material_service.py`

- [ ] **Step 1: Write the failing happy-path test**

Append to `test_material_service.py`:

```python
def test_run_material_job_extracts_then_chains_to_script(services):
    material_service, job_service, _extractor = services
    req = GenerateMaterialSessionRequest.model_validate(
        {
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
            "title": "Cat care",
        }
    )
    data = material_service.create_from_url(req)

    # Drive the job runner manually (synchronous claim + run).
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "completed"
    assert refreshed.script_generation_id is not None
    assert refreshed.extracted_title == "The Cat Care Guide"
```

- [ ] **Step 2: Run, confirm fail**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_service.py::test_run_material_job_extracts_then_chains_to_script -v
```
Expected: FAIL (`NotImplementedError`).

- [ ] **Step 3: Replace the placeholder `run_material_job`**

In `backend/src/lsl/modules/material/service.py`, replace the placeholder method:

```python
    def run_material_job(self, *, generation_id: str, request_payload: dict) -> JobRunResult:
        row = self._repository.get_by_id(generation_id)
        if row is None:
            return JobRunResult(
                status=JobStatus.FAILED,
                error_code="MATERIAL_GENERATION_NOT_FOUND",
                error_message="material generation not found",
            )
        if row["status_name"] == "completed":
            return JobRunResult(status=JobStatus.COMPLETED, progress=100)

        self._repository.mark_extracting(generation_id=generation_id)
        try:
            source_input = self._build_source_input(row["source_type"], row["source_payload"])
            extractor = self._extractor_factory(source_input)
            extracted: ExtractedContent = extractor.extract(source_input)
        except Exception as exc:
            logger.exception("Material extraction failed generation_id=%s", generation_id)
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="EXTRACTION_FAILED",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="EXTRACTION_FAILED", error_message=str(exc))

        if len(extracted.main_text or "") < _MIN_EXTRACTED_TEXT_CHARS:
            message = "Extracted content is empty or too short"
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="EXTRACTION_EMPTY",
                error_message=message,
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="EXTRACTION_EMPTY", error_message=message)

        self._repository.mark_extracted(
            generation_id=generation_id,
            title=extracted.title,
            text=extracted.main_text,
            meta=extracted.meta,
        )
        if extracted.title:
            self._session_service.update_session(
                session_id=row["session_id"],
                payload=UpdateSessionRequest(
                    title=extracted.title,
                    description=request_payload.get("description"),
                    target_language=request_payload.get("target_language"),
                    f_type=2,
                ),
            )

        prompt = self._build_prompt(
            extracted=extracted,
            user_steering=request_payload.get("prompt"),
        )

        try:
            script_generation, _job = self._script_service.start_generation_from_material(
                session_id=row["session_id"],
                material_generation_id=generation_id,
                title=extracted.title or request_payload.get("title") or _DEFAULT_TITLE,
                description=request_payload.get("description"),
                target_language=request_payload.get("target_language"),
                cue_language=request_payload.get("cue_language"),
                prompt=prompt,
                turn_count=int(request_payload.get("turn_count") or 8),
                speaker_count=int(request_payload.get("speaker_count") or 2),
                difficulty=request_payload.get("difficulty"),
                cue_style=request_payload.get("cue_style"),
                must_include=list(request_payload.get("must_include") or []),
            )
        except Exception as exc:
            logger.exception("Script-from-material chain failed generation_id=%s", generation_id)
            self._repository.mark_failed(
                generation_id=generation_id,
                error_code="SCRIPT_GENERATION_FAILED",
                error_message=str(exc),
            )
            return JobRunResult(status=JobStatus.FAILED, error_code="SCRIPT_GENERATION_FAILED", error_message=str(exc))

        self._repository.set_script_generation_id(
            generation_id=generation_id,
            script_generation_id=script_generation.generation_id,
        )
        self._repository.mark_completed(generation_id=generation_id)
        logger.info(
            "Material job completed generation_id=%s script_generation_id=%s",
            generation_id,
            script_generation.generation_id,
        )
        return JobRunResult(status=JobStatus.COMPLETED, progress=100)

    @staticmethod
    def _build_source_input(source_type: str, payload: dict):
        if source_type == "webpage":
            return WebpageSourceInput(type="webpage", url=payload.get("url"))
        raise ValueError(f"Unsupported source type: {source_type!r}")

    @staticmethod
    def _build_prompt(*, extracted: ExtractedContent, user_steering: str | None) -> str:
        parts: list[str] = []
        if extracted.title:
            parts.append(f"Webpage title: {extracted.title}")
        if extracted.canonical_url:
            parts.append(f"Source URL: {extracted.canonical_url}")
        parts.append("Generate a two-host podcast-style dialogue that discusses the content below.")
        if user_steering:
            parts.append(f"Additional instructions: {user_steering}")
        parts.append("Webpage content:")
        parts.append(extracted.main_text)
        return "\n\n".join(parts)
```

(Note: Task 10 stub is now replaced. The "creating the placeholder" step from Task 10 is intentionally a stepping stone — keep this rewrite atomic with its tests.)

- [ ] **Step 4: Run, confirm pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_service.py -v
```
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/lsl/modules/material/service.py backend/tests/test_material_service.py
git commit -m "feat(material): wire run_material_job extract + script chain"
```

---

## Task 12: Failure-path tests for the job (TDD)

**Files:**
- Modify: `backend/tests/test_material_service.py`

- [ ] **Step 1: Append failure tests**

```python
def test_run_material_job_marks_failed_on_extractor_exception(services):
    material_service, job_service, extractor = services
    extractor._exc = RuntimeError("boom")
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/cats"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "failed"
    assert refreshed.error_code == "EXTRACTION_FAILED"
    assert "boom" in (refreshed.error_message or "")


def test_run_material_job_marks_failed_when_text_too_short(services):
    material_service, job_service, extractor = services
    extractor._result = ExtractedContent(title="Tiny", main_text="Short", canonical_url="https://example.com/x")
    req = GenerateMaterialSessionRequest.model_validate(
        {"source": {"type": "webpage", "url": "https://example.com/x"}, "target_language": "en-US"}
    )
    data = material_service.create_from_url(req)
    jobs = job_service.claim_due_jobs(limit=10, worker_id="test")
    for job in jobs:
        job_service.run_claimed_job(job)

    refreshed = material_service.get_generation(generation_id=data.material_generation.generation_id)
    assert refreshed.status_name == "failed"
    assert refreshed.error_code == "EXTRACTION_EMPTY"
```

- [ ] **Step 2: Run, confirm both pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_service.py -v
```
Expected: 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_material_service.py
git commit -m "test(material): cover extractor failure and too-short content paths"
```

---

## Task 13: API endpoints

**Files:**
- Create: `backend/src/lsl/modules/material/api.py`
- Test: `backend/tests/test_material_api.py`

- [ ] **Step 1: Write `api.py`**

```python
# backend/src/lsl/modules/material/api.py
from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.material.schema import (
    ApiResponse,
    GenerateMaterialSessionData,
    GenerateMaterialSessionRequest,
    MaterialGenerationData,
)
from lsl.modules.material.service import MaterialService

router = APIRouter(prefix="/materials", tags=["materials"])


def get_material_service(request: Request) -> MaterialService:
    service = getattr(request.app.state, "material_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Material service is not initialized")
    return cast(MaterialService, service)


@router.post("/generate-session", response_model=ApiResponse[GenerateMaterialSessionData])
def generate_material_session(
    payload: GenerateMaterialSessionRequest,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.create_from_url(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/generations/{generation_id}", response_model=ApiResponse[MaterialGenerationData])
def get_material_generation(
    generation_id: str,
    material_service: MaterialService = Depends(get_material_service),
):
    try:
        data = material_service.get_generation(generation_id=generation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data)
```

- [ ] **Step 2: Write API tests with `TestClient`**

```python
# backend/tests/test_material_api.py
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Reuse the exact test harness used by test_material_service.py — keeps the
# wiring identical so any drift fails in both places.
from tests.test_material_service import (
    FakeScriptGenerator,
    NoopRevisionGenerator,
    StubExtractor,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.config import Settings
from lsl.core.db import Base
import lsl.modules.material.model  # noqa: F401
import lsl.modules.script.model  # noqa: F401
from lsl.modules.asset.providers import FakeStorageProvider
from lsl.modules.asset.service import AssetService
from lsl.modules.job.repo import JobRepository
from lsl.modules.job.service import JobService
from lsl.modules.material.extractor.base import ExtractedContent
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.service import MaterialJobHandler, MaterialService
from lsl.modules.revision.repo import RevisionRepository
from lsl.modules.revision.service import RevisionService
from lsl.modules.script.repo import ScriptRepository
from lsl.modules.script.service import ScriptJobHandler, ScriptService
from lsl.modules.session.repo import SessionRepository
from lsl.modules.session.service import SessionService
from lsl.modules.transcript.repo import TranscriptRepository
from lsl.modules.transcript.service import TranscriptService


@pytest.fixture()
def material_service_and_extractor():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)
    settings = Settings(STORAGE_PROVIDER="fake", ASSET_BASE_URL="http://assets.test")
    asset_service = AssetService(settings=settings, storage=FakeStorageProvider(), repository=None)
    job_service = JobService(repository=JobRepository(factory), lock_ttl_seconds=30)
    transcript_service = TranscriptService(repository=TranscriptRepository(factory))
    session_service = SessionService(
        repository=SessionRepository(factory),
        asset_service=asset_service,
        transcript_service=transcript_service,
    )
    revision_service = RevisionService(
        repository=RevisionRepository(factory),
        generator=NoopRevisionGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
    )
    script_service = ScriptService(
        repository=ScriptRepository(factory),
        generator=FakeScriptGenerator(),
        session_service=session_service,
        transcript_service=transcript_service,
        revision_service=revision_service,
        job_service=job_service,
    )
    job_service.register_handler(ScriptJobHandler(script_service=script_service))
    extractor = StubExtractor(
        result=ExtractedContent(title="T", main_text="x" * 500, canonical_url="https://example.com/x")
    )
    material_service = MaterialService(
        repository=MaterialRepository(factory),
        session_service=session_service,
        script_service=script_service,
        job_service=job_service,
        extractor_factory=lambda payload: extractor,
    )
    job_service.register_handler(MaterialJobHandler(material_service=material_service))
    return material_service, extractor


def _build_app(material_service):
    from lsl.modules.material.api import router

    app = FastAPI()
    app.include_router(router)
    app.state.material_service = material_service
    return TestClient(app)


def test_post_generate_session_returns_three_tuple(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/generate-session",
        json={
            "source": {"type": "webpage", "url": "https://example.com/cats"},
            "target_language": "en-US",
            "title": "Cat care",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["session"]["session"]["session_id"]
    assert body["data"]["material_generation"]["status_name"] == "pending"
    assert body["data"]["job"]["job_id"]


def test_post_generate_session_rejects_invalid_url(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/generate-session",
        json={
            "source": {"type": "webpage", "url": "not-a-url"},
            "target_language": "en-US",
        },
    )
    assert resp.status_code == 422


def test_post_generate_session_rejects_missing_target_language(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.post(
        "/materials/generate-session",
        json={
            "source": {"type": "webpage", "url": "https://example.com/cats"},
        },
    )
    assert resp.status_code == 422


def test_get_generation_returns_404_for_unknown(material_service_and_extractor):
    material_service, _extractor = material_service_and_extractor
    client = _build_app(material_service)
    resp = client.get("/materials/generations/00000000000000000000000000000000")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run, confirm all pass**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests/test_material_api.py -v
```
Expected: 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/src/lsl/modules/material/api.py backend/tests/test_material_api.py
git commit -m "feat(material): add POST /materials/generate-session and GET /materials/generations/{id}"
```

---

## Task 14: Public module exports

**Files:**
- Modify: `backend/src/lsl/modules/material/__init__.py`

- [ ] **Step 1: Add public exports**

```python
# backend/src/lsl/modules/material/__init__.py
from lsl.modules.material.api import router
from lsl.modules.material.extractor.factory import build_extractor
from lsl.modules.material.repo import MaterialRepository
from lsl.modules.material.service import MaterialJobHandler, MaterialService

__all__ = [
    "MaterialJobHandler",
    "MaterialRepository",
    "MaterialService",
    "build_extractor",
    "router",
]
```

- [ ] **Step 2: Verify imports**

```bash
env PYTHONPATH=backend/src uv run python -c "from lsl.modules.material import MaterialService, MaterialJobHandler, MaterialRepository, build_extractor, router; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/lsl/modules/material/__init__.py
git commit -m "feat(material): expose module public surface"
```

---

## Task 15: Wire `MaterialService` into `main.py`

**Files:**
- Modify: `backend/src/lsl/main.py`

- [ ] **Step 1: Add imports**

At the top of `backend/src/lsl/main.py`, alongside the other module imports (around lines 27-36), add:

```python
from lsl.modules.material import MaterialJobHandler, MaterialRepository, MaterialService, build_extractor
from lsl.modules.material.api import router as material_router
```

- [ ] **Step 2: Construct the repository inside `lifespan`**

In the `lifespan` function, after the existing `script_repository = ...` block (around line 170), add:

```python
    material_repository = (
        MaterialRepository(db_resources.session_factory)
        if db_resources.session_factory is not None
        else None
    )
```

- [ ] **Step 3: Construct the service after `script_service` is built**

After the `script_service = ScriptService(...)` block (around line 280), add:

```python
    material_service = (
        MaterialService(
            repository=material_repository,
            session_service=session_service,
            script_service=script_service,
            job_service=job_service,
            extractor_factory=lambda payload: build_extractor(payload, settings=settings),
        )
        if material_repository is not None
        and session_service is not None
        and script_service is not None
        and job_service is not None
        else None
    )
```

- [ ] **Step 4: Register the job handler**

In the `if job_service is not None:` block (around line 283), after the `if script_service is not None: ... ScriptJobHandler(...)` line, add:

```python
        if material_service is not None:
            job_service.register_handler(MaterialJobHandler(material_service=material_service))
```

- [ ] **Step 5: Expose on `app.state`**

In the `app.state.*` assignments (around line 302), add:

```python
    app.state.material_service = material_service
```

- [ ] **Step 6: Include the router**

At the bottom of `main.py` (around line 348), in the `app.include_router(...)` block, add:

```python
app.include_router(material_router, dependencies=protected_router_dependencies)
```

- [ ] **Step 7: Verify the app starts**

```bash
env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"
```
Expected: prints `main import ok`.

Also smoke-start the app for 3 seconds to be sure:

```bash
env PYTHONPATH=backend/src timeout 3 uv run uvicorn --app-dir backend/src lsl.main:app --port 18888 2>&1 | head -30 || true
```
Expected: no traceback; you see startup logs from FastAPI.

- [ ] **Step 8: Commit**

```bash
git add backend/src/lsl/main.py
git commit -m "feat(main): wire MaterialService into app lifespan + register router"
```

---

## Task 16: Update env example

**Files:**
- Modify: `backend/src/lsl/main.py` *(no — env example only)*
- Modify: search for the env example file

- [ ] **Step 1: Find the env example file**

```bash
find /Users/yuhaiyang/Documents/code/myself/lsl -maxdepth 4 -name "app.env.example" -not -path "*/node_modules/*"
```
Expected: one file. If `backend/app.env.example` does not exist, also check the project root or the `deploy/` directory.

- [ ] **Step 2: Append the new MATERIAL_* env block**

Append to whatever env example file you found:

```env

# Material / Webpage extraction
MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15
MATERIAL_WEBPAGE_MAX_BODY_BYTES=5242880
MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50000
```

If no env example file exists in the repo, skip this task (the defaults in `Settings` are already sensible) and document the new vars in the module README only.

- [ ] **Step 3: Commit**

```bash
git add backend/app.env.example  # or whichever path you found
git commit -m "chore: document MATERIAL_* env vars in app.env.example"
```

---

## Task 17: Backend module README

**Files:**
- Create: `backend/src/lsl/modules/material/README.md`

- [ ] **Step 1: Write the module README**

```markdown
# LSL - Material Module

Material 模块负责把外部来源（v1 仅支持网页 URL）抽取为正文，并通过 `script` 模块产出带 CUE 的对话脚本。用户面叫"播客（Podcast）"。

## 当前接口

- `POST /materials/generate-session` 创建文本 session、material_generation 记录和异步 job（`job_type=script_from_material`）
- `GET /materials/generations/{generation_id}` 查询 material_generation 状态、抽取标题、关联的 `script_generation_id`

## 请求体

```json
{
  "source": {"type": "webpage", "url": "https://en.wikipedia.org/wiki/Domestic_cat"},
  "target_language": "en-US",
  "cue_language": "zh-CN",
  "prompt": "用初学者口吻，重点讲日常照护",
  "turn_count": 12,
  "speaker_count": 2,
  "difficulty": "intermediate",
  "must_include": ["litter box"],
  "title": null,
  "description": null
}
```

`source` 是 discriminated union（`source.type` 当前必须是 `"webpage"`）；未来扩展加 PDF / YouTube 等只需新增 extractor + 新的 `type` 值。

## 异步流程

Job 内三阶段：

1. `extracting`：调 `extractor.factory.build_extractor` 选 extractor 抽取正文；写 `extracted_title / extracted_text / extracted_meta_json`。
2. 调 `script_service.start_generation_from_material(...)` 创建 `script_generation` 记录，并把 `material_generation.script_generation_id` 写好。
3. 复用现有 `script` 流程完成对话生成、transcript、revision 写入。

抽取出的网页正文以 prompt context 注入 script generator：service 把 title + canonical URL + 用户 steering prompt + 正文按段拼接传给 `script.generator`。

## 失败语义

| 失败点 | error_code |
|---|---|
| 抓取超时 / 失败 | EXTRACTION_FAILED |
| 抽取正文 < 200 字符 | EXTRACTION_EMPTY |
| 下游 script 生成失败 | SCRIPT_GENERATION_FAILED |

失败时 session 保留、不自动重试。

## 安全

应用层只做最小校验（URL 格式、http/https 协议）。SSRF / IP 黑名单 / 鉴权 / 速率限制由线上网关层处理。

## 配置

```env
MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15
MATERIAL_WEBPAGE_MAX_BODY_BYTES=5242880
MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50000
```

依赖 `trafilatura`（纯 Python，本机运行，无 API key）。

## 与 transcript / script 的边界

- `transcript.source_type` 保持 `"ai_script"`，**不引入新枚举**。
- `script_generation.material_generation_id` 用作反向追溯。`transcript → script_generation → material_generation → URL` 是完整的追溯链。
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/lsl/modules/material/README.md
git commit -m "docs(material): add module README"
```

---

## Task 18: Frontend types

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add types**

Search `frontend/src/types/api.ts` for the existing `GenerateScriptSessionRequest` and `GenerateScriptSessionResponse` types as a reference. Add the equivalents for material:

```typescript
export interface GenerateMaterialSessionRequest {
  source: { type: 'webpage'; url: string };
  title?: string | null;
  description?: string | null;
  targetLanguage: string;
  cueLanguage?: string | null;
  prompt?: string | null;
  turnCount?: number;
  speakerCount?: number;
  difficulty?: string | null;
  cueStyle?: string | null;
  mustInclude?: string[];
}

export interface MaterialGeneration {
  generation_id: string;
  session_id: string;
  source_type: string;
  source_payload: Record<string, unknown>;
  extracted_title: string | null;
  extracted_text: string | null;
  extracted_meta: Record<string, unknown>;
  script_generation_id: string | null;
  job_id: string | null;
  status: number;
  status_name: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateMaterialSessionResponse {
  session: GenerateScriptSessionResponse['session'];
  material_generation: MaterialGeneration;
  job: GenerateScriptSessionResponse['job'];
}
```

If `GenerateScriptSessionResponse` is not exported from `types/api.ts`, look at where it lives (likely the same file or `types/index.ts`) and either re-export it or replace the `['session']` / `['job']` references with explicit type aliases that already exist alongside.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npm run typecheck 2>&1 | tail -20
```
(If `typecheck` is not a script, use `npx tsc --noEmit` instead.)
Expected: no new type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(frontend): add Material request/response types"
```

---

## Task 19: Frontend API client

**Files:**
- Create: `frontend/src/lib/api/materials.ts`

- [ ] **Step 1: Write the client (mirror `scripts.ts`)**

```typescript
// frontend/src/lib/api/materials.ts
import { requestJson } from '@/lib/api/client'
import type {
  GenerateMaterialSessionRequest,
  GenerateMaterialSessionResponse,
  MaterialGeneration,
} from '@/types/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function generateMaterialSession(payload: GenerateMaterialSessionRequest): Promise<GenerateMaterialSessionResponse> {
  const response = await requestJson<ApiResponse<GenerateMaterialSessionResponse>>('/materials/generate-session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source: payload.source,
      title: payload.title ?? null,
      description: payload.description ?? null,
      target_language: payload.targetLanguage,
      cue_language: payload.cueLanguage ?? null,
      prompt: payload.prompt ?? null,
      turn_count: payload.turnCount,
      speaker_count: payload.speakerCount,
      difficulty: payload.difficulty,
      cue_style: payload.cueStyle,
      must_include: payload.mustInclude,
    }),
  })
  return response.data
}

export async function getMaterialGeneration(generationId: string): Promise<MaterialGeneration> {
  const response = await requestJson<ApiResponse<MaterialGeneration>>(`/materials/generations/${generationId}`)
  return response.data
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/materials.ts
git commit -m "feat(frontend): add Material API client"
```

---

## Task 20: Frontend i18n labels

**Files:**
- Modify: `frontend/src/i18n/en.ts`
- Modify: `frontend/src/i18n/zh-CN.ts`

- [ ] **Step 1: Add English labels**

In `frontend/src/i18n/en.ts`, find the block around `'create.aiScript': 'AI Script'` (around line 141) and add new entries for the podcast mode. Add immediately after that line:

```typescript
  'create.podcast': 'Podcast',
  'create.podcastSubtitle': 'Turn any webpage into a two-host dialogue you can listen to.',
  'create.podcastUrl': 'Webpage URL',
  'create.podcastUrlPlaceholder': 'e.g., https://en.wikipedia.org/wiki/Domestic_cat',
  'create.podcastSteeringPrompt': 'Optional guidance',
  'create.podcastSteeringPromptPlaceholder': 'e.g., explain like I am a beginner; focus on practical examples',
  'create.createPodcast': 'Create Podcast',
  'validation.urlRequired': 'URL is required',
  'validation.urlInvalid': 'Must be a valid http(s) URL',
```

- [ ] **Step 2: Add Chinese labels**

In `frontend/src/i18n/zh-CN.ts`, find the equivalent `'create.aiScript'` line and add immediately after it:

```typescript
  'create.podcast': '播客',
  'create.podcastSubtitle': '把任意网页变成两位主持人的对话，可以直接听。',
  'create.podcastUrl': '网页地址',
  'create.podcastUrlPlaceholder': '例如：https://en.wikipedia.org/wiki/Domestic_cat',
  'create.podcastSteeringPrompt': '可选指引',
  'create.podcastSteeringPromptPlaceholder': '例如：用初学者的口吻，重点讲实用例子',
  'create.createPodcast': '生成播客',
  'validation.urlRequired': '请填写 URL',
  'validation.urlInvalid': '必须是 http(s) 地址',
```

- [ ] **Step 3: Verify TypeScript still compiles**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/
git commit -m "feat(frontend): add i18n labels for podcast mode (en + zh-CN)"
```

---

## Task 21: `PodcastSessionForm` component

**Files:**
- Create: `frontend/src/components/create-session/PodcastSessionForm.tsx`

- [ ] **Step 1: Open `AiScriptSessionForm.tsx` and copy its structure as a starting point**

Read `frontend/src/components/create-session/AiScriptSessionForm.tsx` end-to-end first. The new component reuses most of that structure but:

- Replaces the `Scenario Prompt` input with **URL** (required) + **Optional Steering Prompt** (optional textarea).
- The submit handler validates the URL and calls `generateMaterialSession(...)` instead of `generateScriptSession(...)`.
- The session title field becomes optional (empty allowed).

- [ ] **Step 2: Write the new component**

```tsx
// frontend/src/components/create-session/PodcastSessionForm.tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Headphones } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useApp } from '@/context/AppContext';
import type { Difficulty } from '@/types';
import { generateMaterialSession } from '@/lib/api/materials';
import { mapSessionItem } from '@/lib/domain';
import { useI18n } from '@/i18n';

type PodcastSessionFormProps = {
  active: boolean;
};

const URL_PATTERN = /^https?:\/\/.+/i;

export function PodcastSessionForm({ active }: PodcastSessionFormProps) {
  const navigate = useNavigate();
  const { dispatch } = useApp();
  const { t, language: uiLanguage } = useI18n();

  const [url, setUrl] = useState('');
  const [sessionName, setSessionName] = useState('');
  const [sessionDescription, setSessionDescription] = useState('');
  const [targetLanguage, setTargetLanguage] = useState('en-US');
  const [steeringPrompt, setSteeringPrompt] = useState('');
  const [turnCount, setTurnCount] = useState('8');
  const [speakerCount, setSpeakerCount] = useState('2');
  const [difficulty, setDifficulty] = useState<Difficulty>('Beginner');
  const [cueStyle, setCueStyle] = useState(() => t('create.defaultCueStyle'));
  const [mustInclude, setMustInclude] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const steeringRef = useRef<HTMLTextAreaElement | null>(null);

  const clearErrors = useCallback(() => setErrors({}), []);
  const adjustHeight = useCallback((el?: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  useEffect(() => {
    if (!active) clearErrors();
  }, [active, clearErrors]);

  useEffect(() => {
    adjustHeight(steeringRef.current);
  }, [steeringPrompt, adjustHeight]);

  const handleSubmit = useCallback(async () => {
    clearErrors();
    const next: Record<string, string> = {};
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      next.url = t('validation.urlRequired');
    } else if (!URL_PATTERN.test(trimmedUrl)) {
      next.url = t('validation.urlInvalid');
    }
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    setIsSubmitting(true);
    try {
      const result = await generateMaterialSession({
        source: { type: 'webpage', url: trimmedUrl },
        title: sessionName || null,
        description: sessionDescription || null,
        targetLanguage,
        cueLanguage: uiLanguage,
        prompt: steeringPrompt || null,
        turnCount: Number(turnCount),
        speakerCount: Number(speakerCount),
        difficulty,
        cueStyle,
        mustInclude: mustInclude.split(',').map((s) => s.trim()).filter(Boolean),
      });
      const session = mapSessionItem(result.session);
      dispatch({ type: 'ADD_SESSION', payload: session });
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      console.error('Failed to create podcast session', err);
      setErrors({ submit: String(err) });
    } finally {
      setIsSubmitting(false);
    }
  }, [
    clearErrors,
    cueStyle,
    difficulty,
    dispatch,
    mustInclude,
    navigate,
    sessionDescription,
    sessionName,
    speakerCount,
    steeringPrompt,
    targetLanguage,
    t,
    turnCount,
    uiLanguage,
    url,
  ]);

  if (!active) return null;

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="podcast-url">{t('create.podcastUrl')}</Label>
        <Input
          id="podcast-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t('create.podcastUrlPlaceholder')}
        />
        {errors.url && <p className="mt-1 text-xs text-red-600">{errors.url}</p>}
      </div>

      <div>
        <Label htmlFor="podcast-target-lang">{t('create.targetLanguage')}</Label>
        <Select value={targetLanguage} onValueChange={setTargetLanguage}>
          <SelectTrigger id="podcast-target-lang"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="en-US">{t('create.targetLanguage.english')}</SelectItem>
            <SelectItem value="zh-CN">{t('create.targetLanguage.chinese')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label htmlFor="podcast-steering">{t('create.podcastSteeringPrompt')}</Label>
        <Textarea
          id="podcast-steering"
          ref={steeringRef}
          value={steeringPrompt}
          onChange={(e) => setSteeringPrompt(e.target.value)}
          placeholder={t('create.podcastSteeringPromptPlaceholder')}
          rows={2}
        />
      </div>

      <div>
        <Label htmlFor="podcast-session-name">{t('create.sessionName')}</Label>
        <Input
          id="podcast-session-name"
          value={sessionName}
          onChange={(e) => setSessionName(e.target.value)}
          placeholder={t('create.sessionNamePlaceholder')}
        />
      </div>

      <Button onClick={handleSubmit} disabled={isSubmitting} className="w-full">
        {isSubmitting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('create.creating')}
          </>
        ) : (
          <>
            <Headphones className="mr-2 h-4 w-4" /> {t('create.createPodcast')}
          </>
        )}
      </Button>
    </div>
  );
}
```

(Difficulty / turn count / cue style / must-include fields can be added under an "Advanced" collapsible later. v1 ships with sensible defaults — keep the form short and inviting.)

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/create-session/PodcastSessionForm.tsx
git commit -m "feat(frontend): add PodcastSessionForm component"
```

---

## Task 22: Wire `podcast` mode into `CreateSession`

**Files:**
- Modify: `frontend/src/pages/CreateSession.tsx`

Note: there is an uncommitted single-line change in this file (`useState<'audio' | 'ai_script'>('ai_script')`). Keep that intent (default to a non-audio mode) — possibly change the default to `'podcast'` since that's likely the most interesting new feature, but check with the user first.

- [ ] **Step 1: Update the `mode` union and default**

Open `frontend/src/pages/CreateSession.tsx`. Change line 11:

```typescript
const [mode, setMode] = useState<'audio' | 'ai_script' | 'podcast'>('podcast');
```

And line 13:

```typescript
const handleModeChange = useCallback((nextMode: 'audio' | 'ai_script' | 'podcast') => {
```

- [ ] **Step 2: Import the new icon and form**

At the top, add to imports:

```typescript
import { ArrowLeft, Mic, Sparkles, Headphones } from 'lucide-react';
import { PodcastSessionForm } from '@/components/create-session/PodcastSessionForm';
```

- [ ] **Step 3: Add the podcast tab button**

Find the existing `<button onClick={() => handleModeChange('ai_script')} ...>` block (around line 40) and add another tab button after it:

```tsx
        <button
          onClick={() => handleModeChange('podcast')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-[13px] font-medium transition-all duration-200',
            mode === 'podcast'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Headphones className="h-4 w-4" /> {t('create.podcast')}
        </button>
```

- [ ] **Step 4: Render the form**

After `<AiScriptSessionForm active={mode === 'ai_script'} />` (around line 54), add:

```tsx
      <PodcastSessionForm active={mode === 'podcast'} />
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 6: Start dev server and manually test in browser**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npm run dev
```
Open the app in a browser, navigate to Create Session, confirm:
- Three tabs render: Audio Upload / AI Script / 播客 (or Podcast)
- Clicking 播客 shows the new form with URL + steering prompt fields
- Submitting with empty URL shows inline error
- Submitting with a valid URL hits the backend (network tab shows POST `/materials/generate-session`)

(If the backend isn't running yet, just verify the UI; backend smoke test happens in Task 23.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/CreateSession.tsx
git commit -m "feat(frontend): add Podcast mode tab to CreateSession"
```

---

## Task 23: End-to-end smoke test

**Files:** None to modify; this is a manual verification.

- [ ] **Step 1: Run the full backend test suite**

```bash
env PYTHONPATH=backend/src uv run pytest backend/tests -v
```
Expected: ALL tests pass (existing + new material tests).

- [ ] **Step 2: Boot the backend**

```bash
env PYTHONPATH=backend/src uv run uvicorn --app-dir backend/src lsl.main:app --reload --env-file .env
```

(Set `SCRIPT_PROVIDER=fake` in `.env` for this smoke if you don't have an LLM key configured. The fake provider returns a static dialogue.)

- [ ] **Step 3: Boot the frontend in another terminal**

```bash
cd /Users/yuhaiyang/Documents/code/myself/lsl/frontend && npm run dev
```

- [ ] **Step 4: End-to-end run**

In a browser:
1. Log in.
2. Create Session → 播客.
3. Paste `https://en.wikipedia.org/wiki/Domestic_cat`.
4. Pick `English` as target language.
5. Submit.
6. Verify the redirect to the session detail page.
7. Verify the generation progresses through `extracting` → `extracted` → `completed` (the script preview should fill in as the fake LLM streams turns).
8. Verify the session title updates to the page title (`Domestic cat`).
9. Verify the revise / listening flow works on the produced session (same as AI script flow).

- [ ] **Step 5: Cleanup data**

If smoke runs leave dummy sessions in `data/lsl.sqlite3`, delete them via the UI or wipe the DB (`rm data/lsl.sqlite3 && env PYTHONPATH=backend/src uv run python -c "import lsl.main"` will recreate it on next start).

- [ ] **Step 6: No commit needed for this task** — smoke only.

---

## Self-Review Checklist (run before announcing the plan is done)

- [ ] Each spec section has a corresponding task:
  - § 1 Scope — covered as the overall goal.
  - § 2 Frontend UX — Tasks 20, 21, 22.
  - § 3 Backend module structure — Tasks 2–8, 14, 17.
  - § 4 Data flow — Tasks 10, 11, 12 (sync + async + transitions).
  - § 5 API contract — Tasks 8, 13.
  - § 6 Failure scenarios — Tasks 11, 12 (extractor failure, too-short content, script chain failure paths).
  - § 7 Testing — Tasks 4, 5, 7, 10–13, 23.
  - § 8 Configuration — Tasks 5, 16.
  - § 9 Future extension — covered by extractor factory pattern, but no implementation tasks (correct, this is v1).
- [ ] No `TBD` / `TODO` / "fill in later" anywhere.
- [ ] Type/method names consistent across tasks (`MaterialService`, `MaterialJobHandler`, `MaterialRepository`, `WebpageExtractor`, `start_generation_from_material`, `script_from_material`).
- [ ] DRY: extractor factory used by both service and tests; FakeScriptGenerator copied from existing tests pattern rather than reinvented.
- [ ] YAGNI: no PDF / YouTube / monologue / caching / retry / rate limit / SSRF protection in scope.
- [ ] Frequent commits: each task ends with a commit.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-15-podcast-from-webpage.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Pick one when ready.
