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


def test_extract_recovers_page_title():
    extractor = _build_extractor()
    with patch.object(WebpageExtractor, "_fetch_html", return_value=SAMPLE_BLOG_HTML):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/cats"))
    assert result.title == "The Cat Care Guide"


def test_extract_returns_empty_content_when_fetch_fails():
    extractor = _build_extractor()
    with patch.object(WebpageExtractor, "_fetch_html", return_value=None):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/missing"))
    assert result.main_text == ""
    assert result.meta.get("reason") == "fetch_failed"


def test_extract_truncates_long_content():
    long_html = "<html><body><article>" + ("Sentence about cats. " * 5000) + "</article></body></html>"
    extractor = _build_extractor(max_chars=1000)
    with patch.object(WebpageExtractor, "_fetch_html", return_value=long_html):
        result = extractor.extract(WebpageSourceInput(type="webpage", url="https://example.com/long"))
    assert len(result.main_text) <= 1000
    assert result.meta.get("truncated") is True
    assert "[... omitted ...]" in result.main_text
