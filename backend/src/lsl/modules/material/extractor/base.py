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
