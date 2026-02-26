"""test_web_crawler.py — 使用 scrapling.parser.Selector 做單元測試。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from scrapling.parser import Selector
from ops.web_crawler import _resolve_field, _parse_with_fields, fetch_web_source

# ── 共用 HTML / source fixture ────────────────────────────────────

SIMPLE_HTML = """
<html><body>
  <div class="item">
    <h2><a href="/article/1">標題一</a></h2>
    <p>摘要一</p>
  </div>
  <div class="item">
    <h2><a href="https://example.com/article/2">標題二</a></h2>
    <p>摘要二</p>
  </div>
</body></html>
"""

BASE_SOURCE = {
    "name": "測試來源",
    "key": "test",
    "url": "https://example.com",
    "selector": "div.item",
    "fields": {
        "title": "h2 a",
        "url": "h2 a::attr(href)",
        "summary": "p",
    },
    "limit": 10,
    "tags": ["test"],
    "category": "community",
}


# ── _resolve_field（使用 scrapling Selector）─────────────────────

class TestResolveField:
    def _item(self, html: str) -> Any:
        return Selector(html)

    def test_text_selector(self) -> None:
        item = self._item("<div><h2>Hello</h2></div>")
        assert _resolve_field(item, "h2") == "Hello"

    def test_attr_selector_with_base_url(self) -> None:
        item = self._item('<div><a href="/path">Link</a></div>')
        result = _resolve_field(item, "a::attr(href)", "https://example.com")
        # /path 以 / 開頭，不以 http 開頭，但也不需要 urljoin（以 / 開頭視為站內絕對路徑）
        assert "/path" in result

    def test_relative_href_urljoin(self) -> None:
        item = self._item('<div><a href="path">Link</a></div>')
        result = _resolve_field(item, "a::attr(href)", "https://example.com/base/")
        assert result == "https://example.com/base/path"

    def test_absolute_href_unchanged(self) -> None:
        item = self._item('<div><a href="https://other.com/page">Link</a></div>')
        result = _resolve_field(item, "a::attr(href)", "https://example.com")
        assert result == "https://other.com/page"

    def test_missing_selector_returns_empty(self) -> None:
        item = self._item("<div><h2>Hello</h2></div>")
        assert _resolve_field(item, "span") == ""

    def test_none_selector_returns_empty(self) -> None:
        item = self._item("<div><h2>Hello</h2></div>")
        assert _resolve_field(item, None) == ""

    def test_multiple_selectors_fallback(self) -> None:
        item = self._item("<div><p class='alt'>Alt Text</p></div>")
        result = _resolve_field(item, "h2, p.alt")
        assert result == "Alt Text"

    def test_attr_missing_returns_empty(self) -> None:
        item = self._item("<div><a>No href</a></div>")
        result = _resolve_field(item, "a::attr(href)", "https://example.com")
        assert result == ""

    def test_no_base_url_relative_href_returns_empty(self) -> None:
        item = self._item('<div><a href="relative">Link</a></div>')
        result = _resolve_field(item, "a::attr(href)", "")
        assert result == ""

    def test_explicit_text_pseudo(self) -> None:
        item = self._item("<div><h2>Text Node</h2></div>")
        result = _resolve_field(item, "h2::text")
        assert result == "Text Node"


# ── _parse_with_fields ────────────────────────────────────────────

class TestParseWithFields:
    def test_success(self) -> None:
        page = Selector(SIMPLE_HTML)
        result = _parse_with_fields(page, BASE_SOURCE)
        assert len(result) == 2
        assert result[0]["title"] == "標題一"
        assert result[0]["summary"] == "摘要一"
        assert result[1]["title"] == "標題二"

    def test_no_selector_returns_empty(self) -> None:
        page = Selector(SIMPLE_HTML)
        source = {**BASE_SOURCE, "selector": ""}
        assert _parse_with_fields(page, source) == []

    def test_selector_not_found_short_page(self) -> None:
        page = Selector("<html><body>short</body></html>")
        result = _parse_with_fields(page, BASE_SOURCE)
        assert result == []

    def test_selector_not_found_long_page(self) -> None:
        page = Selector(f"<html><body><p>{'A' * 300}</p></body></html>")
        result = _parse_with_fields(page, BASE_SOURCE)
        assert result == []

    def test_limit_respected(self) -> None:
        html = "".join(
            f'<div class="item"><h2><a href="/a/{i}">T{i}</a></h2><p>S{i}</p></div>'
            for i in range(20)
        )
        page = Selector(html)
        source = {**BASE_SOURCE, "limit": 5}
        result = _parse_with_fields(page, source)
        assert len(result) == 5

    def test_skip_item_without_title(self) -> None:
        html = '<div class="item"><p>只有摘要沒有標題</p></div>'
        page = Selector(html)
        result = _parse_with_fields(page, BASE_SOURCE)
        assert result == []

    def test_entry_fields_correct(self) -> None:
        page = Selector(SIMPLE_HTML)
        result = _parse_with_fields(page, BASE_SOURCE)
        entry = result[0]
        assert entry["source"] == "測試來源"
        assert entry["source_key"] == "test"
        assert entry["tags"] == ["test"]
        assert entry["category"] == "community"
        assert entry["published"] == ""


# ── fetch_web_source ──────────────────────────────────────────────

class TestFetchWebSource:
    def _make_response(self, text: str, status: int = 200) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.text = text
        mock_resp.status_code = status
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_success(self) -> None:
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get") as mock_get:
            mock_get.return_value = self._make_response(SIMPLE_HTML)
            result = fetch_web_source(BASE_SOURCE)
        assert len(result) == 2
        assert result[0]["title"] == "標題一"
        assert result[0]["source_key"] == "test"

    def test_no_url_returns_empty(self) -> None:
        source = {**BASE_SOURCE, "url": ""}
        result = fetch_web_source(source)
        assert result == []

    def test_timeout_retries_and_returns_empty(self) -> None:
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get") as mock_get, \
             patch("ops.web_crawler.time.sleep"):
            mock_get.side_effect = requests.exceptions.Timeout
            result = fetch_web_source(BASE_SOURCE)
        assert result == []
        assert mock_get.call_count == 2  # MAX_RETRIES = 2

    def test_http_error_retries(self) -> None:
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get") as mock_get, \
             patch("ops.web_crawler.time.sleep"):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403")
            mock_resp.headers = {"content-type": "text/html"}
            mock_get.return_value = mock_resp
            result = fetch_web_source(BASE_SOURCE)
        assert result == []

    def test_connection_error_returns_empty(self) -> None:
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get") as mock_get, \
             patch("ops.web_crawler.time.sleep"):
            mock_get.side_effect = requests.exceptions.ConnectionError("refused")
            result = fetch_web_source(BASE_SOURCE)
        assert result == []

    def test_unexpected_error_returns_empty(self) -> None:
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get") as mock_get:
            mock_get.side_effect = RuntimeError("unexpected")
            result = fetch_web_source(BASE_SOURCE)
        assert result == []

    def test_json_content_type_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        mock_resp = MagicMock()
        mock_resp.text = '{"data": []}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.raise_for_status = MagicMock()
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", False), \
             patch("ops.web_crawler.requests.get", return_value=mock_resp), \
             caplog.at_level(logging.WARNING, logger="web_crawler"):
            fetch_web_source(BASE_SOURCE)
        assert "json" in caplog.text.lower() or "js" in caplog.text.lower()


# ── scrapling fetcher 路徑 ────────────────────────────────────────

class TestFetchWebSourceScraplingFetchers:
    def _make_mock_page(self, html: str) -> MagicMock:
        """建立模擬 scrapling fetcher 回傳的 page 物件。"""
        real_page = Selector(html)
        return real_page

    def test_fetcher_success(self) -> None:
        mock_page = self._make_mock_page(SIMPLE_HTML)
        mock_fetcher = MagicMock()
        mock_fetcher.get.return_value = mock_page
        source = {**BASE_SOURCE, "fetcher": "fetcher"}
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", True), \
             patch("ops.web_crawler.Fetcher", mock_fetcher, create=True):
            result = fetch_web_source(source)
        assert len(result) == 2

    def test_dynamic_fetcher_success(self) -> None:
        mock_page = self._make_mock_page(SIMPLE_HTML)
        mock_dynamic = MagicMock()
        mock_dynamic.fetch.return_value = mock_page
        source = {**BASE_SOURCE, "fetcher": "dynamic"}
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", True), \
             patch("ops.web_crawler.DynamicFetcher", mock_dynamic, create=True):
            result = fetch_web_source(source)
        assert len(result) == 2

    def test_stealthy_fetcher_success(self) -> None:
        mock_page = self._make_mock_page(SIMPLE_HTML)
        mock_stealthy = MagicMock()
        mock_stealthy.fetch.return_value = mock_page
        source = {**BASE_SOURCE, "fetcher": "stealthy"}
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", True), \
             patch("ops.web_crawler.StealthyFetcher", mock_stealthy, create=True):
            result = fetch_web_source(source)
        assert len(result) == 2

    def test_scrapling_failure_fallback_to_requests(self) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.get.side_effect = Exception("scrapling crash")
        mock_resp = MagicMock()
        mock_resp.text = SIMPLE_HTML
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        source = {**BASE_SOURCE, "fetcher": "fetcher"}
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", True), \
             patch("ops.web_crawler.Fetcher", mock_fetcher, create=True), \
             patch("ops.web_crawler.requests.get", return_value=mock_resp):
            result = fetch_web_source(source)
        assert len(result) == 2

    def test_no_fetcher_field_skips_scrapling(self) -> None:
        """若 source 沒有 fetcher 欄位，直接走 requests fallback。"""
        source = {**BASE_SOURCE}  # 沒有 "fetcher" key
        mock_resp = MagicMock()
        mock_resp.text = SIMPLE_HTML
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        with patch("ops.web_crawler._SCRAPLING_FETCHERS_AVAILABLE", True), \
             patch("ops.web_crawler.requests.get", return_value=mock_resp):
            result = fetch_web_source(source)
        assert len(result) == 2
